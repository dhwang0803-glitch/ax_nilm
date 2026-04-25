"""Celery 배치 작업 — power_efficiency_30min 사전 계산.

트리거 방식:
  1. beat (1시간 주기)  — 전 가구 30분 집계 CBL 사전 계산
  2. DR 이벤트 수신 시  — 해당 이벤트 구간 즉시 계산

Database 브랜치 완성 후 Repository 연동 예정.
현재 Celery 앱 구조 및 태스크 시그니처만 정의.
"""
from __future__ import annotations

import os

from celery import Celery

BROKER  = os.getenv("CELERY_BROKER_URL",  "redis://localhost:6379/0")
BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

app = Celery("kpx_settlement", broker=BROKER, backend=BACKEND)

app.conf.beat_schedule = {
    "hourly-precompute": {
        "task":     "tasks.batch_compute.precompute_all_households",
        "schedule": 3600,  # 1시간
    },
}


@app.task(name="tasks.batch_compute.precompute_all_households")
def precompute_all_households() -> dict:
    """전 가구 30분 단위 CBL 사전 계산 → power_efficiency_30min 테이블 적재.

    Database 브랜치 Repository 연동 후 구현.
    """
    raise NotImplementedError("Database 브랜치 Repository 연동 후 구현")


@app.task(name="tasks.batch_compute.precompute_dr_event")
def precompute_dr_event(event_id: str) -> dict:
    """DR 이벤트 수신 시 해당 구간 즉시 계산 → power_efficiency_30min 적재.

    Args:
        event_id: dr_events 테이블의 이벤트 ID
    """
    raise NotImplementedError("Database 브랜치 Repository 연동 후 구현")
