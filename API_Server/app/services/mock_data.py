"""내장 mock 응답 — Frontend MSW handler (`Frontend/tests/fixtures/*.ts`) 와 1:1 동등.

`USE_DB=false` (기본) 일 때 모든 데이터 라우터가 본 모듈의 함수를 호출한다.
실 DB 전환 시 services/<domain>_service.py 가 본 mock 을 fallback 으로 두고
DB 쿼리 결과로 교체.
"""
from __future__ import annotations

import math

from app.models.cashback import CashbackGoal, CashbackMission, CashbackTracker
from app.models.dashboard import (
    ApplianceShare,
    DashboardKpis,
    DashboardSummary,
    MonthEntry,
    MonthlyBlock,
    WeeklyBlock,
    WeeklyDay,
)
from app.models.insights import (
    AnomalyHighlight,
    InsightsKpi,
    InsightsResponse,
    Recommendation,
    WeeklyTrendEntry,
)
from app.models.settings import (
    AccountProfile,
    AccountResponse,
    AnomalyEvent,
    AnomalyEventsResponse,
    AnomalyKpi,
    DoNotDisturb,
    EmailResponse,
    EmailToggles,
    KepcoLink,
    NotificationRow,
    NotificationsResponse,
    SecurityResponse,
    SessionEntry,
)
from app.models.usage import HourlyBlock, HourlyEntry, UsageAnalysis, UsageApplianceItem


# ─── 공용 빌더 ─────────────────────────────────────────


def _weekly_days() -> list[WeeklyDay]:
    raw = [
        ("월", 5.8, 6.2),
        ("화", 6.1, 6.5),
        ("수", 6.5, 6.0),
        ("목", 6.3, 6.8),
        ("금", 7.0, 7.2),
        ("토", 6.8, 6.5),
        ("일", 4.5, 6.3),
    ]
    return [WeeklyDay(day=d, prevWeek=p, thisWeek=t) for d, p, t in raw]


def _monthly_block() -> MonthlyBlock:
    months_kwh = [285, 252, 198, 175, 168, 220, 285, 312, 245, 210, 218, 0]
    return MonthlyBlock(
        year=2026,
        months=[MonthEntry(month=i + 1, kwh=v) for i, v in enumerate(months_kwh)],
        currentMonth=11,
    )


# ─── Dashboard ─────────────────────────────────────────


def build_dashboard_summary() -> DashboardSummary:
    return DashboardSummary(
        kpis=DashboardKpis(
            monthlyUsageKwh=218,
            monthlyDeltaPercent=-8.4,
            estimatedCashbackKrw=4820,
            cashbackRateKrwPerKwh=30,
            estimatedBillKrw=31200,
        ),
        weekly=WeeklyBlock(
            days=_weekly_days(),
            thisWeekTotal=45.5,
            prevWeekTotal=43.0,
            avgPerDay=6.5,
        ),
        monthly=_monthly_block(),
        applianceBreakdown=[
            ApplianceShare(name="냉난방", sharePercent=36),
            ApplianceShare(name="냉장고", sharePercent=22),
            ApplianceShare(name="세탁/건조", sharePercent=18),
            ApplianceShare(name="주방", sharePercent=12),
            ApplianceShare(name="기타", sharePercent=12),
        ],
    )


# ─── Usage ─────────────────────────────────────────────


def _hourly_curve() -> list[HourlyEntry]:
    """Frontend `usageData.ts` 와 동일한 곡선 — sin 기반 + 저녁 피크."""
    out: list[HourlyEntry] = []
    for h in range(24):
        base = 1.2
        wave = math.sin(((h - 6) * math.pi) / 12) * 0.6
        evening_spike = 0.8 if 18 <= h <= 22 else 0.0
        average = round(base + wave + evening_spike, 2)

        today = round(
            base
            + 0.2
            + math.sin(((h - 7) * math.pi) / 12) * 0.7
            + (1.0 if 19 <= h <= 22 else 0.0),
            2,
        )
        out.append(HourlyEntry(hour=h, average=average, today=today))
    return out


def build_usage_analysis() -> UsageAnalysis:
    return UsageAnalysis(
        weekly=WeeklyBlock(
            days=_weekly_days(),
            thisWeekTotal=45.5,
            prevWeekTotal=43.0,
        ),
        hourly=HourlyBlock(hours=_hourly_curve()),
        applianceBreakdown=[
            UsageApplianceItem(name="에어컨/난방", kwh=16.4, sharePercent=36, weekOverWeekPercent=12),
            UsageApplianceItem(name="냉장고", kwh=10.0, sharePercent=22, weekOverWeekPercent=-2),
            UsageApplianceItem(name="세탁/건조", kwh=8.2, sharePercent=18, weekOverWeekPercent=5),
            UsageApplianceItem(name="주방", kwh=5.5, sharePercent=12, weekOverWeekPercent=0),
            UsageApplianceItem(name="조명/기타", kwh=5.4, sharePercent=12, weekOverWeekPercent=-3),
        ],
        monthly=_monthly_block(),
    )


# ─── Cashback ──────────────────────────────────────────


def build_cashback_tracker() -> CashbackTracker:
    return CashbackTracker(
        goal=CashbackGoal(
            month=11,
            targetSavingsPercent=10,
            targetCashbackKrw=11900,
            daysRemaining=15,
            currentSavingsPercent=8.4,
            expectedSavingsPercent=9.5,
            progressPercent=62,
            expectedProgressPercent=8,
        ),
        weekly=WeeklyBlock(
            days=_weekly_days(),
            thisWeekTotal=45.5,
            prevWeekTotal=43.0,
        ),
        monthly=_monthly_block(),
        missions=[
            CashbackMission(id="m1", title="저녁 19–21시 건조기 미사용", expectedSavingsKwh=2.1, status="pending"),
            CashbackMission(id="m2", title="대기전력 멀티탭 OFF", expectedSavingsKwh=0.7, status="done"),
            CashbackMission(id="m3", title="에어컨 26→27℃", expectedSavingsKwh=1.4, status="pending"),
        ],
    )


# ─── Insights (AI 진단) ────────────────────────────────


def build_insights() -> InsightsResponse:
    return InsightsResponse(
        generatedAt="2026-04-30 09:12",
        modelVersion="v2.4",
        sampleHouseholds=79,
        kpi=InsightsKpi(
            weeklyDiagnosisCount=12,
            weeklyDiagnosisDelta=3,
            monthlyEstimatedSavingKrw=9840,
            monthlySavingDelta=1230,
            modelConfidence=0.92,
        ),
        anomalyHighlights=[
            AnomalyHighlight(
                id="hl-001",
                appliance="에어컨",
                severity="high",
                headline="정상 대비 25% 과소비",
                recommendation="필터 청소 후 설정 온도를 1℃ 올리면 월 1,200원 절약 예상.",
                detectedAt="2026-04-29 14:22",
            ),
            AnomalyHighlight(
                id="hl-002",
                appliance="김치냉장고",
                severity="medium",
                headline="평소 대비 12% 추가 소비",
                recommendation="도어 패킹 점검 권장. 동일 모델 평균 대비 8% 높음.",
                detectedAt="2026-04-28 09:11",
            ),
        ],
        recommendations=[
            Recommendation(id="rec-001", appliance="에어컨", action="필터 청소 · 설정 온도 +1℃", estimatedSavingKrw=1200, confidence=0.91),
            Recommendation(id="rec-002", appliance="김치냉장고", action="도어 패킹 점검 · 정온 모드 전환", estimatedSavingKrw=540, confidence=0.78),
            Recommendation(id="rec-003", appliance="건조기", action="표준 코스 대신 저온 코스 사용 (주 2회 기준)", estimatedSavingKrw=880, confidence=0.85),
            Recommendation(id="rec-004", appliance="TV", action="대기전력 차단 멀티탭 사용 권장", estimatedSavingKrw=320, confidence=0.69),
            Recommendation(id="rec-005", appliance="세탁기", action="찬물 세탁 빈도 증가 (주 1회 → 3회)", estimatedSavingKrw=410, confidence=0.74),
            Recommendation(id="rec-006", appliance="인덕션", action="여열 활용 — 종료 1분 전 전원 차단", estimatedSavingKrw=180, confidence=0.62),
        ],
        weeklyTrend=[
            WeeklyTrendEntry(weekLabel="W14", diagnosisCount=7, estimatedSavingKrw=6100),
            WeeklyTrendEntry(weekLabel="W15", diagnosisCount=9, estimatedSavingKrw=7400),
            WeeklyTrendEntry(weekLabel="W16", diagnosisCount=8, estimatedSavingKrw=7050),
            WeeklyTrendEntry(weekLabel="W17", diagnosisCount=11, estimatedSavingKrw=8900),
            WeeklyTrendEntry(weekLabel="W18", diagnosisCount=12, estimatedSavingKrw=9840),
        ],
    )


# ─── Settings ──────────────────────────────────────────


def build_account(*, email: str, name: str) -> AccountResponse:
    return AccountResponse(
        profile=AccountProfile(
            name=name,
            email=email,
            phone="010-****-1234",
            memberCount=3,
        ),
        kepco=KepcoLink(
            customerNo="12-3456-7890-12",
            addressMasked="서울특별시 ○○구 ○○로 ***",
            contractType="주택용 저압",
            linkedAt="2026-04-15",
        ),
    )


def build_notifications() -> NotificationsResponse:
    return NotificationsResponse(
        matrix=[
            NotificationRow(kind="anomaly", email=True, sms=True, push=True),
            NotificationRow(kind="cashback", email=True, sms=False, push=True),
            NotificationRow(kind="weeklyReport", email=True, sms=False, push=False),
            NotificationRow(kind="system", email=False, sms=False, push=True),
        ],
        doNotDisturb=DoNotDisturb(enabled=True, startMinutes=22 * 60, endMinutes=7 * 60),
    )


def build_security() -> SecurityResponse:
    return SecurityResponse(
        twoFactorEnabled=False,
        sessions=[
            SessionEntry(id="s-cur", device="Chrome · macOS", location="서울", lastActiveAt="2026-04-30 09:42", current=True),
            SessionEntry(id="s-mob", device="Safari · iPhone 15", location="서울", lastActiveAt="2026-04-29 21:18", current=False),
            SessionEntry(id="s-other", device="Edge · Windows 11", location="부산", lastActiveAt="2026-04-26 14:03", current=False),
        ],
    )


def build_anomaly_events() -> AnomalyEventsResponse:
    return AnomalyEventsResponse(
        kpi=AnomalyKpi(monthCount=8, avgResponseMinutes=192, unresolvedCount=2),
        events=[
            AnomalyEvent(id="ev-001", occurredAt="2026-04-29 14:22", appliance="에어컨", severity="high", description="정격 대비 25% 과소비 (필터 점검 권장)", status="open"),
            AnomalyEvent(id="ev-002", occurredAt="2026-04-28 09:11", appliance="김치냉장고", severity="medium", description="평소 대비 12% 추가 소비 감지", status="open"),
            AnomalyEvent(id="ev-003", occurredAt="2026-04-26 19:45", appliance="세탁기", severity="low", description="표준 코스 대비 15분 지연", status="resolved"),
            AnomalyEvent(id="ev-004", occurredAt="2026-04-24 11:03", appliance="건조기", severity="medium", description="정상 대비 18% 과소비 (필터 청소 후 정상)", status="resolved"),
            AnomalyEvent(id="ev-005", occurredAt="2026-04-22 22:48", appliance="인덕션", severity="low", description="대기 전력 평소 대비 5W 증가", status="resolved"),
            AnomalyEvent(id="ev-006", occurredAt="2026-04-19 06:15", appliance="에어컨", severity="high", description="정상 가동 후 자동 정지 반복", status="resolved"),
            AnomalyEvent(id="ev-007", occurredAt="2026-04-15 13:30", appliance="TV", severity="low", description="대기 전력 0.4W 초과", status="resolved"),
            AnomalyEvent(id="ev-008", occurredAt="2026-04-12 20:02", appliance="세탁기", severity="medium", description="탈수 시 모터 부하 증가", status="resolved"),
        ],
    )


def build_email(*, primary_email: str) -> EmailResponse:
    return EmailResponse(
        primaryEmail=primary_email,
        alternateEmail=None,
        toggles=EmailToggles(anomaly=True, cashback=True, weeklyReport=False, policy=False),
        lastTestAt="2026-04-25 10:18",
    )
