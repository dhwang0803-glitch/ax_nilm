from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pywt
import torch
from torch.utils.data import Dataset

if TYPE_CHECKING:
    import gcsfs as gcsfs_type

def _wavelet_denoise(signal: np.ndarray, wavelet: str = "db4", level: int = 1) -> np.ndarray:
    """agg_power 고주파 노이즈 제거. level=1로 최고주파수 성분만 제거해 transient 보존."""
    if len(signal) < 2 ** (level + 1):
        return signal
    coeffs = pywt.wavedec(signal, wavelet, level=level)
    sigma = np.median(np.abs(coeffs[-1])) / 0.6745  # MAD 기반 노이즈 추정
    threshold = sigma * np.sqrt(2 * np.log(max(len(signal), 2)))
    coeffs[1:] = [pywt.threshold(c, threshold, mode="soft") for c in coeffs[1:]]
    denoised = pywt.waverec(coeffs, wavelet)
    return np.clip(denoised[: len(signal)], 0, None).astype(np.float32)


# ── GCS 경로 상수 ─────────────────────────────────────────────────────────────
GCS_BUCKET = "ax-nilm-data-dhwang0803-us"
GCS_RAW_PREFIX = "nilm/training_dev10"
GCS_LABEL_FILE = "nilm/labels/training.parquet"

_DEFAULT_RAW_PREFIX = f"{GCS_BUCKET}/{GCS_RAW_PREFIX}"
_DEFAULT_LABEL_PATH = f"{GCS_BUCKET}/{GCS_LABEL_FILE}"

APPLIANCE_INDEX: dict[str, int] = {
    "TV": 0, "전기포트": 1, "선풍기": 2, "의류건조기": 3, "전기밥솥": 4,
    "식기세척기/건조기": 5, "세탁기": 6, "헤어드라이기": 7, "에어프라이어": 8,
    "진공청소기(유선)": 9, "전자레인지": 10, "에어컨": 11, "인덕션(전기레인지)": 12,
    "전기장판/담요": 13, "온수매트": 14, "제습기": 15, "컴퓨터": 16,
    "공기청정기": 17, "전기다리미": 18, "일반 냉장고": 19, "김치냉장고": 20,
    "무선공유기/셋톱박스": 21,
}
N_APPLIANCES = 22

_labels_cache: dict[str, pd.DataFrame] = {}


def _yyyymmdd(d: str) -> str:
    return str(d).replace("-", "")


def _pa_fs(gcs_fs: "gcsfs_type.GCSFileSystem"):
    """gcsfs → pyarrow FSSpec 래퍼 (parquet/dataset 읽기용)."""
    from pyarrow.fs import PyFileSystem, FSSpecHandler
    return PyFileSystem(FSSpecHandler(gcs_fs))


# ── labels 캐시 ───────────────────────────────────────────────────────────────

def _load_labels_df(
    gcs_fs: "gcsfs_type.GCSFileSystem",
    label_path: str = _DEFAULT_LABEL_PATH,
) -> pd.DataFrame:
    if label_path not in _labels_cache:
        import pyarrow.parquet as pq
        table = pq.read_table(label_path, filesystem=_pa_fs(gcs_fs))
        _labels_cache[label_path] = table.to_pandas()
    return _labels_cache[label_path]


# ── 탐색 함수 ─────────────────────────────────────────────────────────────────

def list_channels_gcs(
    gcs_fs: "gcsfs_type.GCSFileSystem",
    house_id: str,
    bucket_prefix: str = _DEFAULT_RAW_PREFIX,
) -> list[str]:
    """GCS 파티션에서 house의 channel 목록 반환."""
    path = f"{bucket_prefix}/household_id={house_id}/"
    try:
        items = gcs_fs.ls(path)
        channels = []
        for item in items:
            name = item.rstrip("/").split("/")[-1]
            if name.startswith("channel="):
                channels.append(name[len("channel="):])
        return sorted(channels)
    except Exception as e:
        print(f"[list_channels_gcs] {path} 접근 실패: {e}")
        return []


def get_house_start_date_gcs(
    gcs_fs: "gcsfs_type.GCSFileSystem",
    house_id: str,
    channel: str = "ch01",
    bucket_prefix: str = _DEFAULT_RAW_PREFIX,
) -> date:
    """GCS 날짜 파티션에서 house의 데이터 시작일 반환."""
    path = f"{bucket_prefix}/household_id={house_id}/channel={channel}/"
    try:
        items = gcs_fs.ls(path)
    except Exception as e:
        raise FileNotFoundError(f"date 파티션 없음: {path}") from e

    dates = []
    for item in items:
        name = item.rstrip("/").split("/")[-1]
        if name.startswith("date="):
            d = name[len("date="):]
            dates.append(date(int(d[:4]), int(d[4:6]), int(d[6:8])))

    if not dates:
        raise FileNotFoundError(f"date 파티션 없음: {path}")
    return min(dates)


# ── 원천데이터 로드 ────────────────────────────────────────────────────────────

def load_channel_data_gcs(
    gcs_fs: "gcsfs_type.GCSFileSystem",
    house_id: str,
    channel: str,
    date_range: tuple[str, str] | None = None,
    bucket_prefix: str = _DEFAULT_RAW_PREFIX,
) -> pd.DataFrame:
    """GCS 파티션에서 채널 데이터 로드."""
    import pyarrow.dataset as ds

    path = f"{bucket_prefix}/household_id={house_id}/channel={channel}"
    dataset = ds.dataset(path, filesystem=_pa_fs(gcs_fs), partitioning="hive")

    if date_range is not None:
        start, end = int(_yyyymmdd(date_range[0])), int(_yyyymmdd(date_range[1]))
        filt = (ds.field("date") >= start) & (ds.field("date") <= end)
        table = dataset.to_table(filter=filt)
    else:
        table = dataset.to_table()

    _PART_COLS = {"household_id", "channel", "date"}
    drop = [c for c in table.column_names if c in _PART_COLS]
    if drop:
        table = table.drop(drop)

    df = table.to_pandas()
    df["date_time"] = pd.to_datetime(df["date_time"])
    return df.sort_values("date_time").reset_index(drop=True)


# ── 라벨 로드 ─────────────────────────────────────────────────────────────────

def load_all_labels_gcs(
    gcs_fs: "gcsfs_type.GCSFileSystem",
    house_id: str,
    channel: str,
    date_range: tuple[str, str] | None = None,
    label_path: str = _DEFAULT_LABEL_PATH,
) -> list[dict]:
    """labels/training.parquet에서 house+channel 라벨 조회."""
    df = _load_labels_df(gcs_fs, label_path)
    mask = (df["household_id"] == house_id) & (df["channel"] == channel)

    if date_range is not None:
        start, end = _yyyymmdd(date_range[0]), _yyyymmdd(date_range[1])
        mask &= df["date"].apply(lambda d: start <= _yyyymmdd(str(d)) <= end)

    return df[mask].to_dict(orient="records")


def get_appliance_name_gcs(
    gcs_fs: "gcsfs_type.GCSFileSystem",
    house_id: str,
    channel: str,
    label_path: str = _DEFAULT_LABEL_PATH,
) -> str | None:
    """channel의 가전 이름 반환. 없으면 None."""
    df = _load_labels_df(gcs_fs, label_path)
    rows = df[(df["household_id"] == house_id) & (df["channel"] == channel)]
    if rows.empty or "appliance_name" not in rows.columns:
        return None
    return rows.iloc[0]["appliance_name"]


# ── Dataset ───────────────────────────────────────────────────────────────────

class GCSNILMDataset(Dataset):
    """GCS에서 직접 읽는 NILM 이벤트 기반 샘플링 데이터셋."""

    def __init__(
        self,
        houses: list[str],
        gcs_fs: "gcsfs_type.GCSFileSystem",
        bucket_prefix: str = _DEFAULT_RAW_PREFIX,
        label_path: str = _DEFAULT_LABEL_PATH,
        window_size: int = 1024,
        stride: int = 30,
        date_range: tuple[str, str] | None = None,
        week: int | None = None,
        max_week: int | None = None,
        scaler=None,
        fit_scaler: bool = False,
        cache_dir: str | Path | None = None,
        event_context: int | None = None,
        steady_stride: int | None = None,
        resample_hz: int = 30,
        appliance_group: str | None = None,
        denoise: bool = True,
    ):
        """
        event_context   : 전환점 기준 ±N 윈도우. None이면 전수 슬라이딩.
        steady_stride   : 정상 구간 커버리지 stride. None이면 stride × 20 자동 설정.
        cache_dir       : house별 30Hz _segments를 npz로 캐시. window_index는 항상 재생성.
        resample_hz     : 다운샘플 목표 Hz (30 or 1). slow/always_on 그룹에는 1 권장.
        appliance_group : "fast" | "slow" | "always_on". 지정 시 해당 그룹 가전만 validity=True.
        denoise         : True면 wavelet denoising 적용 (ablation 비교 시 False로 설정).
        """
        from datetime import timedelta

        try:
            from .preprocessor import PowerScaler
            from .loader import build_active_mask
        except ImportError:
            from acquisition.preprocessor import PowerScaler
            from acquisition.loader import build_active_mask

        try:
            from .dataset import _event_window_starts, _downsample_block_avg, _downsample_mask, _compute_per_appliance_ctx
        except ImportError:
            from acquisition.dataset import _event_window_starts, _downsample_block_avg, _downsample_mask, _compute_per_appliance_ctx

        from classifier.label_map import SPEED_GROUP

        self.window_size = window_size
        self.stride = stride
        self.scaler = scaler
        self.resample_hz = resample_hz
        self.appliance_group = appliance_group

        # cache_key: TDA 캐시 파일명 등 외부에서 참조용 (전체 파라미터 해시)
        self.cache_key = hashlib.md5(
            f"{sorted(houses)}|{date_range}|{week}|{max_week}|{window_size}|{stride}|{bucket_prefix}|{resample_hz}".encode()
        ).hexdigest()[:12]

        # 주차/기간 파라미터 해시 — house별 캐시 파일명에 사용 (denoise 포함해 캐시 오염 방지)
        _week_key = hashlib.md5(
            f"{date_range}|{week}|{max_week}|{window_size}|{stride}|{bucket_prefix}|{denoise}".encode()
        ).hexdigest()[:8]

        self._segments: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
        self._window_index: list[tuple[int, int]] = []
        _all_agg: list[np.ndarray] = []

        # ── 1단계: house별 캐시 로드 또는 GCS 빌드 ────────────────────────────
        # 캐시를 house별로 분리해 빌드 시 메모리를 house 하나 분량만 사용
        if cache_dir:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)

        for house_id in houses:
            _hcache = (
                Path(cache_dir) / f"nilm_gcs_{house_id}_{_week_key}.npz"
                if cache_dir else None
            )

            if _hcache and _hcache.exists():
                _d = np.load(str(_hcache))
                agg_power    = _d["agg"]
                target_power = _d["target"]
                on_off_mask  = _d["on_off"]
                validity     = _d["validity"]
                print(f"[GCSNILMDataset] 캐시 로드: {_hcache.name}")
            else:
                channels = list_channels_gcs(gcs_fs, house_id, bucket_prefix)
                if "ch01" not in channels:
                    print(f"[GCSNILMDataset] {house_id}: ch01 없음 — 스킵")
                    continue

                if max_week is not None:
                    start_date = get_house_start_date_gcs(gcs_fs, house_id, bucket_prefix=bucket_prefix)
                    dr: tuple[str, str] | None = (
                        start_date.isoformat(),
                        (start_date + timedelta(days=max_week * 7 - 1)).isoformat(),
                    )
                elif week is not None:
                    start_date = get_house_start_date_gcs(gcs_fs, house_id, bucket_prefix=bucket_prefix)
                    dr = (
                        (start_date + timedelta(days=(week - 1) * 7)).isoformat(),
                        (start_date + timedelta(days=week * 7 - 1)).isoformat(),
                    )
                else:
                    dr = date_range

                agg_df = load_channel_data_gcs(gcs_fs, house_id, "ch01", dr, bucket_prefix)
                timestamps = agg_df["date_time"]
                n_samples = len(agg_df)

                target_power = np.zeros((N_APPLIANCES, n_samples), dtype=np.float32)
                on_off_mask  = np.zeros((N_APPLIANCES, n_samples), dtype=bool)
                validity     = np.zeros(N_APPLIANCES, dtype=bool)

                for ch in channels:
                    if ch == "ch01":
                        continue
                    name = get_appliance_name_gcs(gcs_fs, house_id, ch, label_path)
                    if name not in APPLIANCE_INDEX:
                        continue
                    idx = APPLIANCE_INDEX[name]
                    try:
                        tgt_df = load_channel_data_gcs(gcs_fs, house_id, ch, dr, bucket_prefix)
                        merged = agg_df[["date_time"]].merge(
                            tgt_df[["date_time", "active_power"]],
                            on="date_time",
                            how="left",
                        )
                        target_power[idx] = merged["active_power"].fillna(0).to_numpy(dtype=np.float32)
                        tgt_labels = load_all_labels_gcs(gcs_fs, house_id, ch, dr, label_path)
                        on_off_mask[idx] = build_active_mask(tgt_labels, timestamps)
                        validity[idx] = True
                    except Exception as e:
                        print(f"[GCSNILMDataset] {house_id}/{ch} 로드 실패: {e}")

                agg_power = agg_df["active_power"].fillna(0).to_numpy(dtype=np.float32)
                if denoise:
                    agg_power = _wavelet_denoise(agg_power)

                if _hcache:
                    np.savez_compressed(
                        str(_hcache),
                        agg=agg_power, target=target_power,
                        on_off=on_off_mask, validity=validity,
                    )
                    print(f"[GCSNILMDataset] 캐시 저장: {_hcache.name}")

            # 다운샘플 — 캐시는 항상 30Hz로 저장, 리샘플은 로드 후 적용
            if resample_hz < 30:
                _factor = 30 // resample_hz
                agg_power    = _downsample_block_avg(agg_power,    _factor)
                target_power = _downsample_block_avg(target_power, _factor)
                on_off_mask  = _downsample_mask(on_off_mask,       _factor)

            if fit_scaler:
                _all_agg.append(agg_power)
            self._segments.append((agg_power, target_power, on_off_mask, validity))

        # ── 2단계: scaler fit & 적용 ──────────────────────────────────────────
        if fit_scaler and _all_agg:
            self.scaler = PowerScaler().fit(np.concatenate(_all_agg))

        if self.scaler is not None:
            self._segments = [
                (self.scaler.transform(agg), self.scaler.transform_target(tgt), on_off, validity)
                for agg, tgt, on_off, validity in self._segments
            ]

        # ── 2.5단계: appliance_group 필터 — 해당 그룹 외 가전 validity=False ──
        if appliance_group is not None:
            _group_names = {n for n, g in SPEED_GROUP.items() if g == appliance_group}
            filtered = []
            for agg, tgt, on_off, val in self._segments:
                new_val = val.copy()
                for name, idx in APPLIANCE_INDEX.items():
                    if name not in _group_names:
                        new_val[idx] = False
                filtered.append((agg, tgt, on_off, new_val))
            self._segments = filtered

        # ── 3단계: window_index 생성 (항상 재생성, 캐시 불필요) ───────────────
        _ss = steady_stride if steady_stride is not None else stride * 20
        _per_app_ctx = _compute_per_appliance_ctx(stride, cap=event_context) if event_context is not None else None
        total_transitions = 0
        total_event_windows = 0
        total_steady_windows = 0

        for seg_idx, (agg, _, on_off, validity) in enumerate(self._segments):
            n_samples = len(agg)
            if _per_app_ctx is not None:
                starts, n_trans, n_event, n_steady = _event_window_starts(
                    on_off, validity, n_samples, window_size, stride, _per_app_ctx, _ss
                )
                total_transitions += n_trans
                total_event_windows += n_event
                total_steady_windows += n_steady
            else:
                starts = range(0, n_samples - window_size + 1, stride)

            for s in starts:
                self._window_index.append((seg_idx, s))

        if _per_app_ctx is not None:
            _ratio = total_steady_windows / total_event_windows if total_event_windows > 0 else float("inf")
            print(
                f"[GCSNILMDataset] event_context=per-appliance(cap={event_context})  steady_stride={_ss}  전환점={total_transitions:,}\n"
                f"  이벤트 윈도우={total_event_windows:,} / 정상 전용={total_steady_windows:,}"
                f"  → 비율 1:{_ratio:.1f}\n"
                f"  총 {len(self._window_index):,} windows"
            )
            # per-class ON 윈도우 수 (리뷰 7번) — type2 등 희소 가전 100개 미만 모니터링
            try:
                from classifier.label_map import APPLIANCE_LABELS
            except ImportError:
                APPLIANCE_LABELS = [str(i) for i in range(N_APPLIANCES)]
            _seg_wins: dict[int, list[int]] = {}
            for _si, _s in self._window_index:
                _seg_wins.setdefault(_si, []).append(_s)
            _on_win = np.zeros(N_APPLIANCES, dtype=int)
            for _si, _starts in _seg_wins.items():
                _, _, _oo, _val = self._segments[_si]
                _ctrs = np.clip(np.array(_starts) + window_size // 2, 0, _oo.shape[1] - 1)
                _on_win += (_oo[:, _ctrs] & _val[:, None]).sum(axis=1)
            print("  per-class ON 윈도우 (center 기준):")
            for _i, _name in enumerate(APPLIANCE_LABELS):
                _flag = " ⚠️ <100" if _on_win[_i] < 100 else ""
                print(f"    {_name}: {_on_win[_i]:,}{_flag}")
        else:
            print(f"[GCSNILMDataset] full sliding  →  {len(self._window_index):,} windows")

    def __len__(self) -> int:
        return len(self._window_index)

    def __getitem__(self, idx: int):
        seg_idx, start = self._window_index[idx]
        agg, target, on_off, validity = self._segments[seg_idx]
        end = start + self.window_size
        return (
            torch.from_numpy(agg[start:end].copy()),
            torch.from_numpy(target[:, start:end].copy()),
            torch.from_numpy(on_off[:, start:end].copy()),
            torch.from_numpy(validity.copy()),
        )
