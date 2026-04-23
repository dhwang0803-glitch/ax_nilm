import pandas as pd
import numpy as np
from .time_features import extract_time_features


class FeatureExtractor:
    """NILM 출력 + 메타데이터 + cluster_id → 예측 피처 행렬.

    profiles: (N, 1440) 가구 일간 전력 프로파일 (W, 1분 단위)
    meta_df : house, date_dt, house_type, temperature 포함 DataFrame
    cluster_ids: (N,) ClusterFeaturizer.transform() 결과
    """

    # DR 이벤트 기본 윈도우 (17~20시)
    DR_WINDOW = (17 * 60, 20 * 60)

    def transform(
        self,
        profiles: np.ndarray,
        meta_df: pd.DataFrame,
        cluster_ids: np.ndarray,
    ) -> pd.DataFrame:
        n = len(profiles)
        assert len(meta_df) == n and len(cluster_ids) == n

        feat = {}

        # 전력 통계 피처
        hourly = profiles.reshape(n, 24, 60).mean(axis=2)   # (N, 24)
        feat["total_kwh"]     = profiles.sum(axis=1) / 60 / 1000
        feat["peak_w"]        = profiles.max(axis=1)
        feat["mean_w"]        = profiles.mean(axis=1)
        feat["std_w"]         = profiles.std(axis=1)
        feat["peak_hour"]     = np.argmax(hourly, axis=1).astype(float)

        # 시간대 비율
        total = hourly.sum(axis=1) + 1e-9
        feat["morning_ratio"] = hourly[:, 6:9].sum(axis=1)  / total
        feat["daytime_ratio"] = hourly[:, 9:18].sum(axis=1) / total
        feat["evening_ratio"] = hourly[:, 18:23].sum(axis=1)/ total
        feat["night_ratio"]   = (hourly[:, :6].sum(axis=1) + hourly[:, 23:].sum(axis=1)) / total

        # DR 이벤트 윈도우 소비량 (절감 잠재 구간)
        s, e = self.DR_WINDOW
        feat["dr_window_kwh"] = profiles[:, s:e].sum(axis=1) / 60 / 1000

        # 시간대별 평균 전력 (24개)
        for h in range(24):
            feat[f"h{h:02d}"] = hourly[:, h]

        feat_df = pd.DataFrame(feat, index=meta_df.index)

        # 시간 피처 결합
        time_feat = extract_time_features(meta_df)
        feat_df = pd.concat([feat_df, time_feat], axis=1)

        # 가구원수 인코딩
        def encode_house_size(s: str) -> int:
            if "1" in s:
                return 1
            elif "4" in s:
                return 4
            return 2
        feat_df["house_size"] = meta_df["house_type"].apply(encode_house_size)

        # cluster_id (범주형 → 정수)
        feat_df["cluster_id"] = cluster_ids.astype(int)

        return feat_df
