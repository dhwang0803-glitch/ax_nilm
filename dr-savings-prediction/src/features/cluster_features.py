import numpy as np
import joblib
from pathlib import Path
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


class ClusterFeaturizer:
    """가구 일간 소비 프로파일 → cluster_id 피처 생성.

    fit 시 KMeans 학습, transform 시 cluster_id 반환.
    학습·추론 모두 동일 모델 인스턴스를 사용해야 한다.
    """

    def __init__(self, n_clusters: int = 9, random_state: int = 42):
        self.n_clusters = n_clusters
        self.scaler = StandardScaler()
        self.kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
        self._fitted = False

    def _extract_hourly(self, profiles: np.ndarray) -> np.ndarray:
        """(N, 1440) → (N, 24) 시간대 평균."""
        return profiles.reshape(len(profiles), 24, 60).mean(axis=2)

    def fit(self, profiles: np.ndarray) -> "ClusterFeaturizer":
        hourly = self._extract_hourly(profiles)
        X = self.scaler.fit_transform(hourly)
        self.kmeans.fit(X)
        self._fitted = True
        return self

    def transform(self, profiles: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("fit() 먼저 호출 필요")
        hourly = self._extract_hourly(profiles)
        X = self.scaler.transform(hourly)
        return self.kmeans.predict(X)

    def fit_transform(self, profiles: np.ndarray) -> np.ndarray:
        return self.fit(profiles).transform(profiles)

    def save(self, path: Path) -> None:
        joblib.dump({"scaler": self.scaler, "kmeans": self.kmeans,
                     "n_clusters": self.n_clusters}, path)

    @classmethod
    def load(cls, path: Path) -> "ClusterFeaturizer":
        data = joblib.load(path)
        obj = cls(n_clusters=data["n_clusters"])
        obj.scaler = data["scaler"]
        obj.kmeans = data["kmeans"]
        obj._fitted = True
        return obj
