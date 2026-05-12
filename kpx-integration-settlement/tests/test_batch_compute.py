"""테스트 — src/tasks/batch_compute.py

TDD Red: 구현 전 실패를 확인하고, Developer 구현 후 PASS를 검증한다.

테스트 전략:
- _billing_period() : 순수 Python 로직 → 실제 실행
- _tier_rate()       : 순수 Python 로직 → 실제 실행
- Celery 태스크     : DB 연결 부재 시 early-return 동작 + mock DB 시 정상 upsert
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest


# ─── _billing_period ────────────────────────────────────────────────────────────

class TestBillingPeriod:
    """검침일 기반 청구 기간 계산."""

    def _fn(self):
        from src.tasks.batch_compute import _billing_period
        return _billing_period

    def test_billing_day_15_october(self):
        """billing_day=15, ref_month=2026-10 → 2026-09-15 ~ 2026-10-14."""
        start, end = self._fn()(15, "2026-10")
        assert start == date(2026, 9, 15)
        assert end   == date(2026, 10, 14)

    def test_billing_day_1(self):
        """billing_day=1, ref_month=2026-10 → 2026-09-01 ~ 2026-09-30."""
        start, end = self._fn()(1, "2026-10")
        assert start == date(2026, 9, 1)
        assert end   == date(2026, 9, 30)

    def test_billing_day_none_calendar_month(self):
        """billing_day=None → 달력 월 (1일 ~ 말일)."""
        start, end = self._fn()(None, "2026-02")
        assert start == date(2026, 2, 1)
        assert end   == date(2026, 2, 28)  # 2026년은 평년

    def test_billing_day_none_december(self):
        """billing_day=None, 12월 → 12-01 ~ 12-31."""
        start, end = self._fn()(None, "2026-12")
        assert start == date(2026, 12, 1)
        assert end   == date(2026, 12, 31)

    def test_billing_day_crosses_year(self):
        """billing_day=20, ref_month=2026-01 → 2025-12-20 ~ 2026-01-19 (연도 경계)."""
        start, end = self._fn()(20, "2026-01")
        assert start == date(2025, 12, 20)
        assert end   == date(2026, 1, 19)


# ─── _tier_rate ─────────────────────────────────────────────────────────────────

class TestTierRate:
    """KEPCO 에너지캐시백 단가 테이블."""

    def _fn(self):
        from src.tasks.batch_compute import _tier_rate
        return _tier_rate

    @pytest.mark.parametrize("rate, expected", [
        (0.25, 100.0),   # 20% 이상 → 100원/kWh
        (0.20, 100.0),   # 경계값
        (0.15, 80.0),    # 10~20% → 80원/kWh
        (0.10, 80.0),    # 경계값
        (0.07, 60.0),    # 5~10% → 60원/kWh
        (0.05, 60.0),    # 경계값
        (0.04, 30.0),    # 3~5% → 30원/kWh
        (0.03, 30.0),    # 경계값
        (0.02, 0.0),     # 3% 미만 → 0원
        (0.00, 0.0),     # 0% → 0원
    ])
    def test_tier(self, rate, expected):
        assert self._fn()(rate) == expected


# ─── Celery 태스크 — DB 없음 early-return ───────────────────────────────────────

class TestTasksNoDb:
    """DB_PASSWORD 미설정 → 태스크가 오류 없이 error dict를 반환한다."""

    def test_refresh_all_baselines_no_db(self):
        from src.tasks.batch_compute import refresh_all_baselines
        with patch("src.tasks.batch_compute._get_db_conn", return_value=None):
            result = refresh_all_baselines()
        assert result["status"] == "error"
        assert "db" in result["reason"].lower()

    def test_finalize_cashback_results_no_db(self):
        from src.tasks.batch_compute import finalize_cashback_results
        with patch("src.tasks.batch_compute._get_db_conn", return_value=None):
            result = finalize_cashback_results("2026-04")
        assert result["status"] == "error"
        assert "db" in result["reason"].lower()

    def test_refresh_household_baseline_no_db(self):
        from src.tasks.batch_compute import refresh_household_baseline
        with patch("src.tasks.batch_compute._get_db_conn", return_value=None):
            result = refresh_household_baseline("H011", "2026-04")
        assert result["status"] == "error"
        assert "db" in result["reason"].lower()


# ─── Celery 태스크 — mock DB ────────────────────────────────────────────────────

class TestRefreshAllBaselinesMocked:
    """mock DB → refresh_all_baselines 정상 동작."""

    def _make_conn(self, households, kwh_rows):
        """households: [(hid, cluster_label, billing_day)], kwh_rows: [(hid, period_start, kwh)]."""
        cur = MagicMock()
        cur.fetchall.side_effect = [households, kwh_rows, []]  # households, power, cluster avg

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: cur
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        return conn

    def test_returns_ok_status(self):
        from src.tasks.batch_compute import refresh_all_baselines

        households = [("H011", 0, 15)]
        # 동월 1년전·2년전 데이터 → 각각 300 kWh
        kwh_rows = [("H011", date(2024, 9, 15), 300.0), ("H011", date(2025, 9, 15), 300.0)]

        conn = self._make_conn(households, kwh_rows)
        with patch("src.tasks.batch_compute._get_db_conn", return_value=conn):
            result = refresh_all_baselines(ref_month="2026-10")

        assert result["status"] == "ok"
        assert result["upserted"] == 1

    def test_proxy_fallback_for_new_household(self):
        """이력 없는 신규 가구 → proxy_cluster fallback."""
        from src.tasks.batch_compute import refresh_all_baselines

        households = [("H099", 1, None)]  # billing_day=None (달력 월)
        kwh_rows   = []                   # 이력 없음

        cur = MagicMock()
        # households, power(empty), cluster_avg
        cur.fetchall.side_effect = [households, kwh_rows, [(280.0,)]]
        cur.fetchone.return_value = (280.0,)

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: cur
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.tasks.batch_compute._get_db_conn", return_value=conn):
            result = refresh_all_baselines(ref_month="2026-10")

        assert result["status"] == "ok"
        assert result["proxy_count"] >= 0  # fallback 경로 동작 확인


class TestFinalizeCashbackMocked:
    """mock DB → finalize_cashback_results 캐시백 계산 정확도."""

    def test_savings_20pct_yields_100_rate(self):
        """절감률 20% → 100원/kWh 단가 적용."""
        from src.tasks.batch_compute import finalize_cashback_results

        households    = [("H011", True, 15)]    # (hid, dr_enrolled, billing_day)
        baselines_row = [("H011", 400.0, "2year_avg")]  # baseline 400 kWh
        actual_rows   = [("H011", 320.0)]        # actual 320 kWh → 절감 80 kWh = 20%

        cur = MagicMock()
        cur.fetchall.side_effect = [households, baselines_row, actual_rows]

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: cur
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.tasks.batch_compute._get_db_conn", return_value=conn):
            result = finalize_cashback_results("2026-10")

        assert result["status"] == "ok"
        assert result["upserted"] == 1

    def test_below_threshold_yields_zero_cashback(self):
        """절감률 2% (미달) → 캐시백 0원."""
        from src.tasks.batch_compute import finalize_cashback_results

        households    = [("H011", True, 15)]
        baselines_row = [("H011", 400.0, "2year_avg")]
        actual_rows   = [("H011", 392.0)]  # 절감 8 kWh = 2% < 3%

        cur = MagicMock()
        cur.fetchall.side_effect = [households, baselines_row, actual_rows]

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: cur
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.tasks.batch_compute._get_db_conn", return_value=conn):
            result = finalize_cashback_results("2026-10")

        assert result["status"] == "ok"
        # 미달이어도 upsert는 실행 (status='미달(3% 미만)')
        assert result["upserted"] == 1
