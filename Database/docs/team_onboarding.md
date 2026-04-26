# 팀원 DB 접근 온보딩 — 5분 가이드

> **대상**: ax_nilm 프로젝트 팀원 — 본인 GCP 계정에 IAM 부여를 이미 받은 상태에서 처음 dev DB (`ax-nilm-db-dev`) 에 접속
> **사전 조건**: project owner 가 본인 계정에 다음 3개 role 부여 완료 (관리자가 일괄 부여) —
> `roles/iap.tunnelResourceAccessor`, `roles/compute.osLogin`, `roles/secretmanager.secretAccessor`
> **VM/스키마 셋업은 본 문서 범위 외** — 인프라 구축은 [`gcp_setup.md`](./gcp_setup.md) 참조

---

## 0. 한눈에 보는 흐름

```
gcloud 로그인 → .env 로드 → IAP 터널 (별도 셸) → DSN 조립 → SELECT 검증
```

---

## 1. 로컬 사전 준비 (1회)

### 1.1 도구 설치
- `gcloud` SDK ([설치 가이드](https://cloud.google.com/sdk/docs/install))
- Python 3.11+ + `cryptography`, `sqlalchemy[asyncio]`, `asyncpg` (Database 코드 실행 시)
- Windows: Git Bash / WSL 권장 (셸 스크립트 호환)

### 1.2 gcloud 인증
```bash
! gcloud auth login                          # 사용자 OAuth
! gcloud auth application-default login      # ADC (Python SDK 용)
! gcloud config set project ax-nilm
```

### 1.3 IAM 확인 (관리자 부여가 적용됐는지 self-check)
```bash
gcloud projects get-iam-policy ax-nilm \
    --flatten="bindings[].members" \
    --format="value(bindings.role)" \
    --filter="bindings.members:user:$(gcloud config get-value account)"
```
다음 3개 줄이 보여야 함:
```
roles/iap.tunnelResourceAccessor
roles/compute.osLogin
roles/secretmanager.secretAccessor
```
없으면 owner(`dhwang0803@gmail.com`) 에게 요청.

---

## 2. 저장소 + .env 준비

### 2.1 저장소 클론
```bash
git clone https://github.com/<org>/ax_nilm.git
cd ax_nilm
```

### 2.2 `Database/.env` 받기
- `Database/.env` 는 **gitignore 대상**이라 repo 에 없음
- owner 에게 별도 안전 채널(1Password / Bitwarden / 사내 보안 채널)로 요청
- 받은 .env 를 `Database/.env` 로 저장. **절대 커밋 금지** (root `CLAUDE.md` 보안 규칙)

### 2.3 환경변수 로드 (셸을 새로 열 때마다 1회)
```bash
set -a; source Database/.env; set +a
```
- `CLOUDSDK_PYTHON` 이 .env 에 있어 Git Bash 에서 gcloud 정상 동작
- 주요 변수: `PROJECT_ID=ax-nilm`, `ZONE=asia-northeast3-a`, `INSTANCE_NAME=ax-nilm-db-dev`, `LOCAL_PG_PORT=5436`

---

## 3. DB 연결 (매 작업 세션)

### 3.1 IAP 터널 (별도 터미널에서 살려둠)
```bash
gcloud compute start-iap-tunnel "$INSTANCE_NAME" 5432 \
    --local-host-port="localhost:$LOCAL_PG_PORT" \
    --zone="$ZONE"
```
- 이 프로세스가 살아 있는 동안만 `localhost:5436` 이 VM Postgres 로 포워딩
- 닫으면 즉시 끊김 (의도된 보안 동작 — VM 인바운드는 IAP 만 허용)
- 이미 5436 점유 시 .env 의 `LOCAL_PG_PORT` 변경

### 3.2 작업 셸: DSN 조립
```bash
APP_PWD=$(gcloud secrets versions access latest --secret="$SECRET_NAME")
export DATABASE_URL="postgresql+asyncpg://$APP_USER:$APP_PWD@localhost:$LOCAL_PG_PORT/$DB_NAME"
```
- 비밀번호는 Secret Manager 에서 매 셸 동적 조립 — 평문으로 저장 금지

### 3.3 연결 검증 (시드 23행 확인)
```bash
python -c "
import asyncio
from Database.src.db import session_scope
from sqlalchemy import text
async def main():
    async with session_scope() as s:
        r = await s.execute(text('SELECT count(*) FROM appliance_types'))
        print('appliance_types:', r.scalar_one())
asyncio.run(main())
"
# → appliance_types: 23
```

---

## 4. 자주 쓰는 작업

### 4.1 psql REPL
```bash
PGPASSWORD="$APP_PWD" psql \
    -h localhost -p "$LOCAL_PG_PORT" \
    -U "$APP_USER" -d "$DB_NAME"
```

### 4.2 Python Repository 사용 예
`Database/src/repositories/` 하위 모듈을 `session_scope()` 로 래핑해서 사용. 직접 SQL 작성 대신 Repository 인터페이스 경유 (브랜치 `CLAUDE.md` 참조).

### 4.3 PII 복호화는 별도 키 필요
`household_pii.address_enc`, `members_enc` 는 Fernet 암호화 BYTEA. 복호화하려면 `CREDENTIAL_MASTER_KEY` 시크릿 추가 부여 필요 (분석 역할은 기본 불가 — 권한 분리 정책).

---

## 5. 보안 체크리스트 (커밋 전)

- [ ] `Database/.env` 는 `.gitignore` 에 포함 (확인됨)
- [ ] `DATABASE_URL`, `APP_PWD`, 시크릿 값을 코드/노트북/로그에 평문 저장하지 않음
- [ ] PII 평문(주소·구성원·맞벌이) 을 응답·로그·DB 평문컬럼에 출력하지 않음
- [ ] `gcloud auth list` 로 본인 계정만 활성인지 확인 (다른 프로젝트 owner 계정 혼선 방지)

---

## 6. 트러블슈팅

| 증상 | 원인 / 조치 |
|------|------------|
| `gcloud: command not found` | SDK 미설치 또는 PATH 누락. `gcloud --version` 으로 확인 |
| `Permission 'iap.tunnelInstances.accessViaIAP' denied` | IAM 미부여 — §1.3 self-check 후 owner 에게 요청 |
| `Permission denied on secret` | `roles/secretmanager.secretAccessor` 미부여 |
| `psql: could not connect to server` | IAP 터널이 죽었거나 다른 셸에서 실행 안 됨 — §3.1 재시작 |
| `permission denied for table ...` (Python) | `ax_nilm_app` 은 DML 만. DDL/스키마 변경은 owner 에게 요청 |
| `extension "timescaledb" is not available` | VM init 미완 — owner 에게 보고 (팀원 책임 외) |
| Bash 에서 gcloud 가 hang / Python 에러 | `.env` 의 `CLOUDSDK_PYTHON` 절대경로 따옴표 확인 |
| 5436 이 다른 프로세스로 점유 | `.env` 의 `LOCAL_PG_PORT` 를 다른 미사용 포트로 변경 |

---

## 7. 비용/매너 노트

- VM 은 owner 가 일시 중지·재기동을 결정. 팀원이 임의로 `gcloud compute instances delete` 하지 않음
- 무거운 분석 쿼리는 `EXPLAIN ANALYZE` 로 먼저 비용 확인 후 실행
- 작업 종료 시 IAP 터널 셸 닫기 (떠 있어도 무료지만 위생)

---

## 8. 관련 문서

- 인프라 셋업 (관리자 전용): [`gcp_setup.md`](./gcp_setup.md)
- 스키마 설계: [`schema_design.md`](./schema_design.md)
- 데이터셋: [`dataset_spec.md`](./dataset_spec.md)
- NILM 모델 ↔ DB 인터페이스: [`model_interface.md`](./model_interface.md)
- GCS 데이터 접근: [`nilm_gcs_access_guide.md`](./nilm_gcs_access_guide.md)
