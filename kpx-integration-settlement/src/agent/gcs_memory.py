"""GCS 기반 NILM 상태 모니터링 메모리 조회.

상태 모니터링 모델이 GCS 버킷에 저장한 long_term / short_term JSON을 읽는다.

버킷 경로 규칙:
    gs://{BUCKET}/memory/long_term/{household_id}.json
    gs://{BUCKET}/memory/short_term/{household_id}.json

환경변수:
    NILM_MEMORY_BUCKET  — GCS 버킷명 (없으면 로컬 폴백)
    NILM_MEMORY_LOCAL   — 로컬 폴백 디렉토리 (기본: ./memory)
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BUCKET = os.getenv("NILM_MEMORY_BUCKET")
_LOCAL_DIR = os.getenv("NILM_MEMORY_LOCAL", "./memory")

_HH_ID_RE = re.compile(r"\A[A-Za-z0-9_-]+\Z")


def _read_from_gcs(bucket: str, blob_path: str) -> dict | list | None:
    try:
        from google.cloud import storage  # type: ignore[import-untyped]

        client = storage.Client()
        blob = client.bucket(bucket).blob(blob_path)
        if not blob.exists():
            logger.warning("GCS blob not found: gs://%s/%s", bucket, blob_path)
            return None
        return json.loads(blob.download_as_text())
    except Exception:
        logger.exception("GCS read failed: gs://%s/%s", bucket, blob_path)
        return None


def _read_from_local(base_dir: str, rel_path: str) -> dict | list | None:
    fp = Path(base_dir) / rel_path
    if not fp.exists():
        logger.debug("Local file not found: %s", fp)
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Local file read failed: %s", fp)
        return None


def _read_memory(memory_type: str, household_id: str) -> dict | list | None:
    """long_term 또는 short_term JSON을 GCS → 로컬 순으로 읽기 시도."""
    if not _HH_ID_RE.match(household_id):
        logger.warning("Invalid household_id rejected: %s", household_id)
        return None
    rel_path = f"memory/{memory_type}/{household_id}.json"

    if _BUCKET:
        data = _read_from_gcs(_BUCKET, rel_path)
        if data is not None:
            return data

    if _LOCAL_DIR:
        data = _read_from_local(_LOCAL_DIR, rel_path)
        if data is not None:
            return data

    return None


def get_long_term(household_id: str) -> dict[str, Any] | None:
    """가전별 모드 레퍼런스 (baseline) 조회.

    Returns:
        { "에어컨": { "appliance": "에어컨", "modes": { "송풍": { ... } } }, ... }
        또는 None
    """
    return _read_memory("long_term", household_id)


def get_short_term(household_id: str) -> list[dict[str, Any]] | None:
    """최근 이벤트 로그 조회.

    Returns:
        [ { "appliance": "세탁기", "mode": "교반", "started_at": "...", ... }, ... ]
        또는 None
    """
    return _read_memory("short_term", household_id)
