# API_Server

ax_nilm 프로젝트의 FastAPI 백엔드. Frontend (Vite SPA) 7개 화면이 호출하는
14개 엔드포인트를 제공한다.

## 빠른 시작

```bash
cd API_Server
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell
pip install -r requirements.txt

cp config/.env.example config/.env
# 필요 시 JWT_SECRET 등 수정

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger UI: http://localhost:8000/docs
- 헬스체크: http://localhost:8000/healthz

## 데모 자격증명

`Frontend/tests/fixtures/handlers.ts` 의 MSW 모킹과 동일.

| 항목 | 값 |
|---|---|
| Email | `test@example.com` |
| Password | `nilm-mock-2026!` |
| Household | `H001` (단일 테넌트, JWT claims) |

## 엔드포인트 (Frontend 계약)

### 인증 (`/auth/*`)
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/auth/login` | 이메일/비밀번호 로그인 — JWT httpOnly 쿠키 발급 |
| POST | `/auth/signup` | 회원가입 (`taken@test.com` 은 데모용 422) |
| POST | `/auth/logout` | 쿠키 만료 (204) |
| POST | `/auth/oauth/{provider}` | OAuth stub — kakao/naver/google |
| GET | `/auth/me` | 현재 사용자 정보 (쿠키 검증) |

### 데이터 (`/api/*`)
| 경로 | 응답 |
|---|---|
| `GET /api/dashboard/summary` | KPI + 주간/월간 + 가전 분해 |
| `GET /api/usage/analysis` | 주간/시간대별/가전별/월별 사용량 |
| `GET /api/cashback/tracker` | 목표·미션·진행률 |
| `GET /api/insights/summary` | AI 진단 + 이상 하이라이트 + 추천 |
| `GET /api/settings/account` | 프로필 + 한전 연동 정보 |
| `GET /api/settings/notifications` | 알림 매트릭스 + 방해금지 |
| `GET /api/settings/security` | 2FA + 활성 세션 |
| `GET /api/settings/anomaly-events` | 이상 탐지 이력 |
| `GET /api/settings/email` | 이메일 알림 설정 |

모든 `/api/*` 는 `ax_nilm_session` 쿠키 필수. 미인증 → 401 (Frontend 인터셉터가 `/auth/login` 으로 redirect).

## 데이터 소스 전환

`config/.env` 의 `USE_DB`:

- `false` (기본): 내장 mock 응답. Frontend MSW 와 동등. **현재 활성화된 모드.**
- `true`: `Database/src/repositories/` 를 통해 실 DB 조회. `DATABASE_URL` + `CREDENTIAL_MASTER_KEY` 필요.

> 실 DB 통합은 Phase 2 — 현재는 Frontend 즉시 배포가 우선.

## 테스트

```bash
pytest -q
```

전 테스트는 `USE_DB=false` 환경에서 동작. 실 DB 의존 없음.

## 디렉토리

```
API_Server/
├── app/
│   ├── main.py              # FastAPI 앱 + CORS + 라우터 등록
│   ├── config.py            # pydantic-settings (env 기반)
│   ├── deps.py              # FastAPI 의존성 (CurrentUser)
│   ├── auth/jwt_utils.py    # JWT + 쿠키 헬퍼
│   ├── routers/             # auth, dashboard, usage, cashback, insights, settings
│   ├── services/mock_data.py  # MSW 와 동등한 mock 응답
│   └── models/              # Pydantic 응답 스키마
├── tests/                   # pytest (TestClient)
├── config/.env.example
└── requirements.txt
```

## 배포 시 점검

- `JWT_SECRET` 을 32+ byte 랜덤값으로 교체 (절대 코드 기본값 사용 금지)
- `COOKIE_SECURE=true` (HTTPS 필수)
- `CORS_ALLOWED_ORIGINS` 에 실제 Frontend 도메인만 등록
- 데모 계정은 prod 에서 비활성화 (USE_DB=true 로 실제 사용자 인증 흐름 활성화)
