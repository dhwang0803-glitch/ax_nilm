import pandas as pd
import numpy as np


def extract_time_features(meta_df: pd.DataFrame) -> pd.DataFrame:
    """메타데이터 DataFrame → 시간 관련 피처 DataFrame.

    meta_df 필수 컬럼: date_dt (datetime), temperature
    """
    df = pd.DataFrame(index=meta_df.index)

    dt = meta_df["date_dt"]
    df["month"]       = dt.dt.month
    df["weekday"]     = dt.dt.dayofweek          # 0=월 ~ 6=일
    df["is_weekend"]  = dt.dt.dayofweek.isin([5, 6]).astype(int)
    df["is_monday"]   = (dt.dt.dayofweek == 0).astype(int)
    df["week_of_year"] = dt.dt.isocalendar().week.astype(int)

    # 계절 (북반구 기준)
    df["season"] = dt.dt.month.map(
        {12: 0, 1: 0, 2: 0,   # 겨울
         3: 1, 4: 1, 5: 1,    # 봄
         6: 2, 7: 2, 8: 2,    # 여름
         9: 3, 10: 3, 11: 3}  # 가을
    )

    # 기온 피처
    temp = pd.to_numeric(meta_df["temperature"], errors="coerce")
    df["temperature"]    = temp
    df["temp_missing"]   = temp.isna().astype(int)
    df["temperature"]    = temp.fillna(temp.median())
    df["is_cold"]        = (df["temperature"] < 10).astype(int)
    df["is_hot"]         = (df["temperature"] > 28).astype(int)

    return df
