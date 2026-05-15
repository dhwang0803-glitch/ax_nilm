# anomaly-detection — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.
> 담당 요구사항: **REQ-002** (이상 탐지 및 진단)

## 관련 문서

- 요구사항: [`docs/REQ-002 이상 탐지 및 진단.md`](../docs/REQ-002%20이상%20탐지%20및%20진단.md)
- 파일 맵: [`docs/MAP.md`](docs/MAP.md)
- 상류 의존: `nilm-engine` (DisaggregationResult 입력)
- 하류 의존: Database 모듈, Frontend 모듈 (DiagnosisReport 소비)

## 모듈 역할

**이상 탐지 엔진** — nilm-engine이 산출한 가전별 시계열 소비 데이터로부터
성능 저하·비정상 작동을 탐지하고, LLM 진단 리포트 및 심각도별 알림을 전달한다.

| 서브모듈 | REQ ID | 역할 |
|---------|--------|------|
| `src/models/schemas.py` | ANOM-000 | 공유 데이터 타입 (Severity, AnomalyType, AnomalyEvent, DiagnosisReport) |
| `src/detectors/statistical.py` | ANOM-001 | 통계 기반 성능 저하 감지 |
| `src/detectors/pattern.py` | ANOM-002 | Isolation Forest 비정상 패턴 탐지 |
| `src/diagnosis/reporter.py` | ANOM-003 | 룰 기반 + LLM 진단 리포트 |
| `src/notifier/alert.py` | ANOM-004 | FCM/SMTP 심각도별 알림 |
| `src/service.py` | 전체 | 파이프라인 public API (오케스트레이터) |

## 파일 위치 규칙 (MANDATORY)

```
anomaly-detection/
├── src/
│   ├── models/
│   │   └── schemas.py       ← ANOM-000: 공유 타입 (수정 시 전 모듈 영향)
│   ├── detectors/
│   │   ├── statistical.py   ← ANOM-001: 통계 기반 탐지
│   │   └── pattern.py       ← ANOM-002: Isolation Forest 패턴 탐지
│   ├── diagnosis/
│   │   └── reporter.py      ← ANOM-003: 진단 리포트 (LLM은 HIGH만)
│   ├── notifier/
│   │   └── alert.py         ← ANOM-004: FCM/SMTP 라우팅
│   └── service.py           ← 파이프라인 public API
├── tests/                   ← pytest 단위 테스트
├── config/
│   └── anomaly.yaml         ← 임계값·LLM·알림 설정
└── docs/MAP.md
```

## PoC 환경 특이사항

- AI Hub 데이터셋 제약(31일)으로 PoC 모드에서는 **최근 1주 vs 이전 3주** 비교
- `config/anomaly.yaml` → `poc_mode.enabled: true` 로 제어
- 프로덕션 전환 시 `poc_mode.enabled: false` → 3개월 베이스라인으로 자동 전환

## LLM 정책

- **HIGH 심각도 이벤트만** OpenAI API 호출 (비용 최소화)
- `OPENAI_API_KEY` 환경변수 미설정 또는 호출 실패 시 룰 기반 템플릿으로 자동 폴백
- 하드코딩 금지 — 모든 API 키는 `os.getenv()` 사용

## 알림 정책

| 심각도 | 채널 | 기준 |
|--------|------|------|
| HIGH | FCM 즉시 푸시 (3회 재시도 → SMTP 폴백) | 최대 전력 > 기준 +30% |
| MEDIUM | Celery 일일 요약 큐 | 소비량 > 기준 +20% |
| LOW | Celery 주간 리포트 큐 | 주기성 패턴 편차 |
