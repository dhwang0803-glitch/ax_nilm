"""Celery 배치 작업 — 월별 기준선 계산 및 캐시백 사전 산정.

스케줄:
  매월 1일 00:00  — 전 가구 당월 기준선(monthly_baselines) 갱신
  매월 5일 00:00  — 전월 캐시백 결과(cashback_results) 확정 저장
    (한전 청구 기준: 전월 사용량 집계 완료 후)

Database 브랜치 Repository 연동 후 구현.
"""
from __future__ import annotations

import os
from datetime import date

from celery import Celery
from celery.schedules import crontab

BROKER  = os.getenv("CELERY_BROKER_URL",  "redis://localhost:6379/0")
BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

app = Celery("energy_cashback", broker=BROKER, backend=BACKEND)

app.conf.beat_schedule = {
    # 매월 1일 자정 — 당월 기준선 갱신
    "monthly-baseline-refresh": {
        "task":     "tasks.batch_compute.refresh_all_baselines",
        "schedule": crontab(day_of_month="1", hour="0", minute="0"),
    },
    # 매월 5일 자정 — 전월 캐시백 확정
    "monthly-cashback-finalize": {
        "task":     "tasks.batch_compute.finalize_cashback_results",
        "schedule": crontab(day_of_month="5", hour="0", minute="0"),
    },
}


@app.task(name="tasks.batch_compute.refresh_all_baselines")
def refresh_all_baselines() -> dict:
    """전 가구 당월 기준선(2개년 동월 평균) 계산 → monthly_baselines 적재.

    Database 브랜치 Repository 연동 후 구현.
    """
    raise NotImplementedError("Database 브랜치 Repository 연동 후 구현")


@app.task(name="tasks.batch_compute.finalize_cashback_results")
def finalize_cashback_results(billing_month: str | None = None) -> dict:
    """전월 실측 사용량 기준 캐시백 산정 → cashback_results 저장.

    Args:
        billing_month: "YYYY-MM" 형식. None이면 전월 자동 계산.
    """
    raise NotImplementedError("Database 브랜치 Repository 연동 후 구현")


@app.task(name="tasks.batch_compute.refresh_household_baseline")
def refresh_household_baseline(household_id: str, ref_month: str) -> dict:
    """단일 가구 기준선 즉시 갱신 (신규 가입 시 트리거).

    Args:
        household_id: 가구 ID
        ref_month: "YYYY-MM" 형식
    """
    raise NotImplementedError("Database 브랜치 Repository 연동 후 구현")
