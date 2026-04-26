# GCP 셋업 — PostgreSQL + TimescaleDB on Compute Engine

> **대상**: ax_nilm Database 모듈 dev/prod DB 인스턴스 프로비저닝
> **이유**: Cloud SQL/AlloyDB 가 TimescaleDB 확장을 미지원 → 자체 관리 VM 필수
> **리전**: `asia-northeast3` (서울) — 기존 GCS 원본 버킷과 동일, egress 0

---

## 1. 사전 준비

### 1.1 로컬 머신 (Windows)
- `gcloud` SDK 설치 + 로그인
  ```bash
  ! gcloud auth login
  ! gcloud auth application-default login
  ```
- `openssl`, `bash` (Git Bash / WSL)

### 1.2 GCP 프로젝트
- 프로젝트 ID 확인: `gcloud projects list`
- **결제 계정 활성화** 확인 — VM 생성 즉시 과금 시작 (시간 단위)
- 사용 권한: 본인 계정에 `Owner` 또는 (`Compute Admin` + `IAP Tunnel User` + `Secret Manager Admin`)

### 1.3 결제 알림 (권장)
- Console → Billing → Budgets & alerts → 월 ₩150,000 임계 알림
- 만약 잘못 설정해 e2-standard-4 등 큰 머신을 띄우면 빠르게 인지 가능

---

## 2. 환경변수

스크립트 모두가 환경변수로 입력을 받음. 셋업 세션마다 1회 export.

```bash
export PROJECT_ID=<당신의 GCP 프로젝트 ID>      # 필수
export ZONE=asia-northeast3-a                  # default
export INSTANCE_NAME=ax-nilm-db-dev            # default
export MACHINE_TYPE=e2-standard-2              # default (2vCPU/8GB)
export DISK_SIZE=100                           # default GB
export DB_NAME=ax_nilm                         # default
export APP_USER=ax_nilm_app                    # default
export SECRET_NAME=ax-nilm-db-app-password     # default
```

prod 단계에서는 `INSTANCE_NAME=ax-nilm-db-prod` + `MACHINE_TYPE=n2-standard-8` + `DISK_SIZE=500` 으로 별도 셋업.

---

## 3. 실행 순서

### 3.1 VM 프로비저닝 (~30 초 + VM 부팅 후 시작 스크립트 ~3-5 분)

```bash
bash Database/scripts/gcp/01_provision_vm.sh
```

생성되는 리소스:
- 방화벽 규칙 2개 (`ax-nilm-allow-iap-{ssh,postgres}`) — IAP 35.235.240.0/20 만 허용
- VM `${INSTANCE_NAME}` — ephemeral public IP (apt 아웃바운드용), OS Login 활성, 시작 스크립트 자동 실행
  - 인바운드는 firewall 가 IAP 만 허용 → public IP 있어도 22/5432 외부 직접 접근 불가
  - Prod 전환 시: `--no-address` + Cloud NAT 패턴으로 변경 (런북 §9 참조)

### 3.2 시작 스크립트 완료 확인

```bash
gcloud compute ssh ${INSTANCE_NAME} --tunnel-through-iap --zone=${ZONE} \
    --command='sudo journalctl -u google-startup-scripts.service --no-pager | tail -50'
```

- 마지막 줄에 `ax_nilm VM init complete: ...` 가 보이면 OK
- 보이지 않으면 추가 대기 (3-5분 정상). 5분 초과 시 로그 전체 확인.

### 3.3 DB 셋업 (앱 사용자 + Secret Manager + 스키마 적용)

```bash
bash Database/scripts/gcp/03_setup_db.sh
```

수행 작업:
1. `ax_nilm_app` 비밀번호 32자 랜덤 생성 → Secret Manager `${SECRET_NAME}` 저장
2. `schemas/001~004` + `migrations/01~07` 11개 SQL 파일을 VM 으로 SCP
3. `ax_nilm_app` 사용자 생성/갱신 + `public` 스키마에 `SELECT/INSERT/UPDATE/DELETE` GRANT
4. SQL 의존 순서대로 적용

스크립트 종료 시 화면에 IAP 터널 + DSN 사용 예시 출력.

---

## 4. 로컬 dev 머신에서 DB 사용

### 4.1 IAP 터널 (별도 터미널에서 유지)

로컬에 다른 Postgres 가 5432-5435 를 점유 중일 수 있으므로 .env 의 `LOCAL_PG_PORT` (기본 5436) 로 매핑:

```bash
gcloud compute start-iap-tunnel ${INSTANCE_NAME} 5432 \
    --local-host-port=localhost:${LOCAL_PG_PORT} \
    --zone=${ZONE}
```

이 프로세스가 살아 있는 동안만 로컬 `localhost:${LOCAL_PG_PORT}` 가 VM 의 PostgreSQL 로 포워딩됨. 종료하면 바로 끊김 (의도된 보안 동작).

### 4.2 `DATABASE_URL` 설정

```bash
APP_PASSWORD=$(gcloud secrets versions access latest --secret=${SECRET_NAME})
export DATABASE_URL="postgresql+asyncpg://${APP_USER}:${APP_PASSWORD}@localhost:${LOCAL_PG_PORT}/${DB_NAME}"
```

이후 `Database/src/db.py` 의 `session_scope()` 가 정상 동작.

### 4.3 연결 검증

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

## 5. 비용 모니터링

### 5.1 일일 비용 빠른 확인
```bash
gcloud billing accounts list
# 그 후 Console: Billing → Reports → 필터: project = ${PROJECT_ID}
```

### 5.2 VM 일시 중지 (개발 안 하는 시간)
```bash
gcloud compute instances stop ${INSTANCE_NAME} --zone=${ZONE}
# 다시 시작:
gcloud compute instances start ${INSTANCE_NAME} --zone=${ZONE}
```
- 중지 중: 디스크 비용만 (~$17/월), 컴퓨트 0
- 데이터/설정 모두 보존, 시작 시 PostgreSQL 자동 재기동

---

## 6. 백업 (운영 진입 전 필수)

dev 단계에서는 생략 가능. prod 진입 전 다음 추가:

### 6.1 디스크 스냅샷 정책
```bash
gcloud compute resource-policies create snapshot-schedule ax-nilm-db-daily \
    --region=${ZONE%-*} \
    --max-retention-days=7 \
    --start-time=18:00 \
    --hourly-schedule=24

gcloud compute disks add-resource-policies ${INSTANCE_NAME} \
    --resource-policies=ax-nilm-db-daily \
    --zone=${ZONE}
```

### 6.2 logical dump (option)
```bash
gcloud compute ssh ${INSTANCE_NAME} --tunnel-through-iap --zone=${ZONE} \
    --command='sudo -u postgres pg_dump -Fc ax_nilm > /tmp/ax_nilm.dump'
gcloud compute scp --tunnel-through-iap --zone=${ZONE} \
    ${INSTANCE_NAME}:/tmp/ax_nilm.dump ./ax_nilm_$(date +%Y%m%d).dump
```

---

## 7. 트러블슈팅

| 증상 | 원인 / 조치 |
|------|------------|
| `permission denied for table ...` | `ALTER DEFAULT PRIVILEGES` 가 적용 시점 이후 테이블에만 작동. 기존 테이블에 직접 GRANT 추가: `GRANT ALL ON ALL TABLES IN SCHEMA public TO ax_nilm_app;` |
| IAP SSH 가 `permission denied` | `roles/iap.tunnelResourceAccessor` 본인 계정에 부여 필요 |
| `extension "timescaledb" is not available` | VM init 스크립트가 끝나기 전 → §3.2 로그에서 `ax_nilm VM init complete` 대기 |
| `pg_dump: ... could not connect ...` | IAP 터널이 끊김 — §4.1 재실행 |
| 비용이 예상보다 높음 | `gcloud compute instances list` 로 다른 VM 확인. 안 쓰는 외부 IP 도 과금 대상 |

---

## 8. Teardown (개발 종료 시)

```bash
# VM 삭제 (디스크도 함께)
gcloud compute instances delete ${INSTANCE_NAME} --zone=${ZONE}

# 방화벽 규칙 삭제
gcloud compute firewall-rules delete ax-nilm-allow-iap-ssh ax-nilm-allow-iap-postgres

# Secret 삭제 (필요 시)
gcloud secrets delete ${SECRET_NAME}
```

이렇게 하면 컴퓨트/스토리지/네트워크 비용 모두 0.

---

## 9. 다음 단계 (P3 Phase B)

- `Database/tests/` integration tests — IAP 터널 활성 상태에서 pytest 실행
- `Database/scripts/load_dev10.py` (예정) — GCS `nilm/training_dev10/` parquet 을 `power_1min` 스타일로 집계 후 적재
- prod 인스턴스 별도 셋업 (`ax-nilm-db-prod`, n2-standard-8) — 본 runbook 그대로, env 만 변경
