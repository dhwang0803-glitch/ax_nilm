"""dev10 가구의 households.cluster_label 적재 (one-shot, 재실행 안전).

전략 (옵션 A — dr-savings-prediction 의 학습된 KMeans 활용)
============================================================
1) `power_1min` 에서 dev10 가구의 ch01(main breaker) 1분 단위 active power 조회
2) (가구, 일자) 별 1440분 프로파일 재구성. 결측 분은 0 W 로 padding.
3) 완전 일자(또는 거의 완전 — 1300+ minute coverage) 만 채택해 노이즈 줄임.
4) `dr-savings-prediction/models_output/clusterizer.joblib` 로드 →
   profiles (N, 1440) → ClusterFeaturizer.transform → 일별 cluster_id (N,)
5) 가구별 majority vote (최빈값) → 가구당 단일 cluster_label (0~8)
6) `households.cluster_label` UPDATE (재실행 시 동일 값 멱등).

실행 전제
---------
- IAP 터널 `localhost:5436` 활성, `DATABASE_URL` export 완료
- 본인 계정 `ax_nilm_app` (UPDATE 가능)
- `dr-savings-prediction/models_output/clusterizer.joblib` 디스크 존재
- Python: numpy, scikit-learn, joblib, sqlalchemy[async], asyncpg, pandas

검증
----
실행 후 ``SELECT household_id, cluster_label FROM households
WHERE cluster_label IS NOT NULL ORDER BY household_id;`` → dev10 10가구 모두
0~8 범위 값 보유. 같은 가구 재실행 시 결과 동일.
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

# Database 패키지 root 를 import path 에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from Database.src.db import session_scope, dispose_engine  # noqa: E402

# clusterizer.joblib 위치 — dr-savings-prediction 폴더가 같은 워크스페이스에 있다고 가정
CLUSTERIZER_PATH = PROJECT_ROOT / "dr-savings-prediction" / "models_output" / "clusterizer.joblib"

# ch01 = main breaker = 가구 총합 (NILM 표준 채널 매핑)
MAIN_CHANNEL = 1

# 일자별 1440 분 프로파일 채택 임계 (이상치 보호) — 90% 이상 minute 가용한 날만 사용
MIN_MINUTES_PER_DAY = 1300


async def fetch_dev10_household_ids() -> list[str]:
    async with session_scope() as s:
        rows = await s.execute(
            text(
                "SELECT DISTINCT household_id FROM power_1min "
                "WHERE channel_num = :ch ORDER BY household_id"
            ),
            {"ch": MAIN_CHANNEL},
        )
        return [r[0] for r in rows.all()]


async def fetch_household_minutes(household_id: str) -> pd.DataFrame:
    """ch01 의 (bucket_ts, active_power_avg) 전부를 DataFrame 으로."""
    async with session_scope() as s:
        rows = await s.execute(
            text(
                "SELECT bucket_ts, active_power_avg FROM power_1min "
                "WHERE household_id = :h AND channel_num = :ch "
                "ORDER BY bucket_ts"
            ),
            {"h": household_id, "ch": MAIN_CHANNEL},
        )
        df = pd.DataFrame(rows.all(), columns=["bucket_ts", "active_power_avg"])
    df["bucket_ts"] = pd.to_datetime(df["bucket_ts"], utc=True)
    # NULL/NaN active_power_avg 는 0 W 로 — clusterizer 학습 시도 동일 가정 (전력 미측정 = 0)
    df["active_power_avg"] = df["active_power_avg"].fillna(0.0).astype(float)
    return df


def build_daily_profiles(df: pd.DataFrame) -> tuple[np.ndarray, list[pd.Timestamp]]:
    """(bucket_ts, active_power_avg) → (N_days, 1440) 프로파일.

    - day = bucket_ts 의 UTC 날짜 (KST 자정 ≠ UTC 자정 이지만 일별 패턴 추출엔 영향 미미)
    - 분 인덱스 = hour*60 + minute
    - 한 day 내 minute 1300개 미만은 제외
    """
    if df.empty:
        return np.zeros((0, 1440)), []

    df = df.copy()
    df["day"] = df["bucket_ts"].dt.floor("D")
    df["minute_idx"] = df["bucket_ts"].dt.hour * 60 + df["bucket_ts"].dt.minute

    profiles: list[np.ndarray] = []
    days: list[pd.Timestamp] = []
    for day, g in df.groupby("day"):
        if len(g) < MIN_MINUTES_PER_DAY:
            continue
        # 1440 분 vector. 결측 minute 는 0 으로.
        prof = np.zeros(1440, dtype=np.float64)
        prof[g["minute_idx"].to_numpy()] = g["active_power_avg"].to_numpy()
        profiles.append(prof)
        days.append(day)

    if not profiles:
        return np.zeros((0, 1440)), []
    return np.stack(profiles), days


def majority_vote(cluster_ids: np.ndarray) -> int:
    """ndarray of cluster_ids → 최빈값 단일 정수."""
    counts = Counter(int(c) for c in cluster_ids)
    return counts.most_common(1)[0][0]


async def update_cluster_label(household_id: str, cluster_label: int) -> None:
    async with session_scope() as s:
        await s.execute(
            text(
                "UPDATE households SET cluster_label = :c WHERE household_id = :h"
            ),
            {"c": cluster_label, "h": household_id},
        )


async def main() -> None:
    if not CLUSTERIZER_PATH.exists():
        raise SystemExit(
            f"clusterizer.joblib not found: {CLUSTERIZER_PATH}\n"
            "dr-savings-prediction 브랜치 산출물이 워크스페이스에 있어야 함."
        )

    # ClusterFeaturizer.load 의존을 피하고 raw dict 로드 (브랜치 import 회피)
    bundle = joblib.load(CLUSTERIZER_PATH)
    scaler = bundle["scaler"]
    kmeans = bundle["kmeans"]
    # 학습 시점 sklearn 1.8.0 ↔ 실행 1.7.2 dtype 차이 — 명시 강제
    kmeans.cluster_centers_ = np.ascontiguousarray(
        kmeans.cluster_centers_, dtype=np.float64
    )
    n_clusters = bundle.get("n_clusters", kmeans.n_clusters)
    print(f"[load] clusterizer n_clusters={n_clusters}")

    households = await fetch_dev10_household_ids()
    print(f"[query] dev10 households (ch{MAIN_CHANNEL:02d}): {households}")
    if not households:
        raise SystemExit("dev10 가구 미발견 — power_1min 적재 확인 필요")

    summary: list[tuple[str, int, int, dict[int, int]]] = []
    for h in households:
        df = await fetch_household_minutes(h)
        profiles, days = build_daily_profiles(df)
        if len(profiles) == 0:
            print(f"[skip] {h}: 완전 일자 없음 (minute coverage < {MIN_MINUTES_PER_DAY})")
            continue

        # ClusterFeaturizer.transform 와 동일 로직: (N,1440)→(N,24) 시간평균→scaler→kmeans
        hourly = profiles.reshape(len(profiles), 24, 60).mean(axis=2)
        X = scaler.transform(hourly)
        # sklearn 1.7.2 KMeans 는 float64 강제 — scaler 출력이 float32 일 수 있어 명시 캐스트
        X = np.ascontiguousarray(X, dtype=np.float64)
        cluster_ids = kmeans.predict(X)

        majority = majority_vote(cluster_ids)
        dist = dict(sorted(Counter(int(c) for c in cluster_ids).items()))
        summary.append((h, len(profiles), majority, dist))

        await update_cluster_label(h, majority)
        print(f"[update] {h}: days={len(profiles)} → cluster_label={majority} dist={dist}")

    print("\n=== Summary ===")
    for h, n_days, majority, dist in summary:
        print(f"  {h}  days={n_days}  cluster={majority}  dist={dist}")

    # 검증
    async with session_scope() as s:
        rows = await s.execute(
            text(
                "SELECT household_id, cluster_label FROM households "
                "WHERE cluster_label IS NOT NULL ORDER BY household_id"
            )
        )
        result = rows.all()
    print(f"\n[verify] households with cluster_label set: {len(result)}")
    for h, c in result:
        print(f"  {h}: {c}")

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
