"""전력 소비 패턴 임베딩 생성.

1440분 프로파일 → 24시간 평균 → sentence-transformers 임베딩(384차원).
실시간 DR 이벤트 및 오프라인 배치 모두 동일 모델 사용.

개인식별정보 제외: household_id는 DB 저장 키로만 사용하고 임베딩 입력에 포함하지 않음.
"""
from __future__ import annotations

import numpy as np


def profile_to_hourly(profile_1440: np.ndarray) -> np.ndarray:
    """(1440,) 1분 프로파일 → (24,) 시간 평균."""
    return profile_1440.reshape(24, 60).mean(axis=1)


def hourly_to_text(hourly: np.ndarray, temperature: float | None = None) -> str:
    """24시간 평균 전력(W) → LLM/임베딩용 텍스트 표현."""
    parts = [f"{h:02d}시:{w:.1f}W" for h, w in enumerate(hourly)]
    text = "시간대별 평균 전력 " + " ".join(parts)
    if temperature is not None:
        text += f" 기온:{temperature:.1f}도"
    return text


class PowerPatternEmbedder:
    """전력 패턴 텍스트 임베딩 생성기.

    sentence-transformers 모델(all-MiniLM-L6-v2, 384차원) 사용.
    모델은 최초 호출 시 로드 (lazy init).
    """

    _model = None
    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

    @classmethod
    def _get_model(cls):
        if cls._model is None:
            from sentence_transformers import SentenceTransformer
            cls._model = SentenceTransformer(cls.MODEL_NAME)
        return cls._model

    def embed_profile(
        self,
        profile_1440: np.ndarray,
        temperature: float | None = None,
    ) -> np.ndarray:
        """(1440,) 프로파일 → (384,) 임베딩 벡터."""
        hourly = profile_to_hourly(profile_1440)
        text   = hourly_to_text(hourly, temperature)
        model  = self._get_model()
        return model.encode(text, normalize_embeddings=True)

    def embed_text(self, text: str) -> np.ndarray:
        """임의 텍스트 → (384,) 임베딩 벡터 (쿼리용)."""
        return self._get_model().encode(text, normalize_embeddings=True)
