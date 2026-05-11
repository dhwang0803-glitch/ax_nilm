# anomaly-detection — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.
> 담당 요구사항: **REQ-002** (이상 탐지)

## 관련 문서

- 요구사항: [`docs/REQ-002 이상 탐지 및 진단.md`](../docs/REQ-002%20이상%20탐지%20및%20진단.md)
- 파일 맵: [`docs/MAP.md`](docs/MAP.md)
- 상류 의존: `nilm-engine` (DisaggregationResult 입력)
- 하류 의존: Database 모듈, Frontend 모듈 (AnomalyEvent 소비)

## 모듈 역할

**이상 탐지 엔진** — nilm-engine이 산출한 가전별 시계열 소비 데이터로부터
성능 저하·비정상 작동을 탐지하고 AnomalyEvent 리스트를 반환한다.

진단 리포트(ANOM-003) · 알림(ANOM-004)은 다른 팀 담당.

| 서브모듈 | REQ ID | 역할 |
|---------|--------|------|
| `src/models/schemas.py` | ANOM-000 | 공유 데이터 타입 (Severity, AnomalyType, AnomalyEvent) |
| `src/detectors/statistical.py` | ANOM-001 | 통계 기반 성능 저하 감지 |
| `src/detectors/pattern.py` | ANOM-002 | Isolation Forest 비정상 패턴 탐지 |
| `src/service.py` | 전체 | 파이프라인 public API |

## 파일 위치 규칙 (MANDATORY)

```
anomaly-detection/
├── src/
│   ├── models/
│   │   └── schemas.py       ← ANOM-000: 공유 타입 (수정 시 하류 영향 확인)
│   ├── detectors/
│   │   ├── statistical.py   ← ANOM-001: 통계 기반 탐지
│   │   └── pattern.py       ← ANOM-002: Isolation Forest 패턴 탐지
│   └── service.py           ← 파이프라인 public API
├── tests/                   ← pytest 단위 테스트
└── config/
    └── anomaly.yaml         ← 임계값·PoC 모드 설정
```

## DB 연결

`anomaly-detection/src/repository.py` 의 `save_events()` 는 `Database.src.db.session_scope()` 를 사용한다.
연결 설정은 `Database/.env` 를 통해 주입 — **onboarding 절차**: [`Database/docs/team_onboarding.md`](../Database/docs/team_onboarding.md)

```bash
# 1) IAP 터널 (별도 터미널)
gcloud compute start-iap-tunnel "$INSTANCE_NAME" 5432 \
    --local-host-port="localhost:$LOCAL_PG_PORT" --zone="$ZONE"

# 2) 환경변수 로드
set -a; source Database/.env; set +a
APP_PWD=$(gcloud secrets versions access latest --secret="$SECRET_NAME")
export DATABASE_URL="postgresql+asyncpg://$APP_USER:$APP_PWD@localhost:$LOCAL_PG_PORT/$DB_NAME"
```

`anomaly_events` 테이블 DDL + GRANT: `Database/migrations/20260507_11_add_anomaly_events.sql`

## PoC 환경 특이사항

- AI Hub 데이터셋 제약(31일)으로 PoC 모드에서는 **최근 1주 vs 이전 3주** 비교
- `config/anomaly.yaml` → `poc_mode.enabled: true` 로 제어
- 프로덕션 전환 시 `poc_mode.enabled: false` → 3개월 베이스라인으로 자동 전환
