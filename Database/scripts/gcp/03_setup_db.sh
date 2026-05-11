#!/usr/bin/env bash
# ax_nilm — VM 부팅 후 실행: 앱 사용자 + Secret Manager + 스키마 적용.
#
# 본 스크립트는 로컬(개발 머신) 에서 실행되며 다음을 수행한다:
#   1. 앱 사용자 비밀번호를 로컬에서 안전하게 생성
#   2. Secret Manager 에 비밀번호 저장 (회전·접근통제 일원화)
#   3. VM 으로 schemas/migrations SQL 을 SCP
#   4. IAP SSH + psql 로 ax_nilm_app 사용자 생성, 스키마 적용
#
# 실행: bash Database/scripts/gcp/03_setup_db.sh
# 사전: 01_provision_vm.sh 완료, VM init script 가 "ax_nilm VM init complete" 출력

set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID 환경변수가 필요합니다}"
: "${ZONE:=asia-northeast3-a}"
: "${INSTANCE_NAME:=ax-nilm-db-dev}"
: "${DB_NAME:=ax_nilm}"
: "${APP_USER:=ax_nilm_app}"
: "${SECRET_NAME:=ax-nilm-db-app-password}"

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCHEMAS_DIR="${REPO_ROOT}/Database/schemas"
MIGRATIONS_DIR="${REPO_ROOT}/Database/migrations"
REMOTE_TMP=/tmp/ax_nilm_sql

gcloud config set project "${PROJECT_ID}" >/dev/null

# ─── 1. 앱 비밀번호 생성 + Secret Manager 저장 ─────────────────────────
if gcloud secrets describe "${SECRET_NAME}" >/dev/null 2>&1; then
    echo "(Secret '${SECRET_NAME}' 이미 존재 — 기존 latest 버전 사용)"
else
    echo "=== Secret 생성 + 비밀번호 신규 발급 ==="
    # 32 chars, ASCII URL-safe (PostgreSQL md5 인증 호환)
    APP_PASSWORD="$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)"
    printf '%s' "${APP_PASSWORD}" \
        | gcloud secrets create "${SECRET_NAME}" \
            --data-file=- \
            --replication-policy=automatic \
            --labels=app=ax-nilm,role=db-app
    echo "(Secret 생성 완료. 비밀번호는 Secret Manager 에만 보관 — 본 스크립트 종료 시 메모리에서 삭제)"
fi

APP_PASSWORD="$(gcloud secrets versions access latest --secret="${SECRET_NAME}")"

# ─── 2. SQL 파일 SCP ─────────────────────────────────────────────────
echo
echo "=== SQL 파일 VM 으로 전송 ==="
gcloud compute ssh "${INSTANCE_NAME}" --tunnel-through-iap --zone="${ZONE}" \
    --command="rm -rf ${REMOTE_TMP} && mkdir -p ${REMOTE_TMP}/schemas ${REMOTE_TMP}/migrations"

gcloud compute scp --tunnel-through-iap --zone="${ZONE}" \
    "${SCHEMAS_DIR}"/*.sql "${INSTANCE_NAME}:${REMOTE_TMP}/schemas/"

gcloud compute scp --tunnel-through-iap --zone="${ZONE}" \
    "${MIGRATIONS_DIR}"/*.sql "${INSTANCE_NAME}:${REMOTE_TMP}/migrations/"

# ─── 3. 앱 사용자 + 권한 ─────────────────────────────────────────────
echo
echo "=== ${APP_USER} 사용자 생성/갱신 + GRANT ==="
# heredoc 다중 이스케이프 + DO 블록 안 :'var' psql 변수치환 미동작 회피 →
# 로컬에서 SQL 파일 생성 후 SCP. 임시파일은 적용 직후 양쪽에서 삭제.

EXISTS_OUT="$(gcloud compute ssh "${INSTANCE_NAME}" --tunnel-through-iap --zone="${ZONE}" \
    --command="sudo -u postgres psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname = '${APP_USER}'\"" 2>/dev/null \
    | tr -d '[:space:]')"

if [[ "${EXISTS_OUT}" == "1" ]]; then
    SQL_VERB="ALTER"
else
    SQL_VERB="CREATE"
fi

USER_TMP="$(mktemp)"
trap 'rm -f "${USER_TMP}"' EXIT

ESCAPED_PWD="${APP_PASSWORD//\'/\'\'}"

cat > "${USER_TMP}" <<SQL
${SQL_VERB} ROLE ${APP_USER} WITH LOGIN PASSWORD '${ESCAPED_PWD}';
GRANT CONNECT ON DATABASE ${DB_NAME} TO ${APP_USER};
GRANT USAGE ON SCHEMA public TO ${APP_USER};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ${APP_USER};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ${APP_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${APP_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO ${APP_USER};
SQL

gcloud compute scp --tunnel-through-iap --zone="${ZONE}" \
    "${USER_TMP}" "${INSTANCE_NAME}:/tmp/ax_nilm_user.sql"

gcloud compute ssh "${INSTANCE_NAME}" --tunnel-through-iap --zone="${ZONE}" \
    --command="sudo -u postgres psql -d ${DB_NAME} -v ON_ERROR_STOP=1 -f /tmp/ax_nilm_user.sql && rm /tmp/ax_nilm_user.sql"

# ─── 4. 스키마 + 마이그레이션 적용 (의존 순서) ────────────────────────
echo
echo "=== 스키마 적용 (schemas/001~004 → migrations/01~07) ==="
gcloud compute ssh "${INSTANCE_NAME}" --tunnel-through-iap --zone="${ZONE}" \
    --command="sudo -u postgres bash -c '
        cd ${REMOTE_TMP}
        for f in schemas/001_core_tables.sql \
                 schemas/002_timeseries_tables.sql \
                 schemas/003_seed_appliance_types.sql \
                 schemas/004_nilm_inference_tables.sql \
                 migrations/20260426_01_add_aggregators.sql \
                 migrations/20260426_02_extend_households.sql \
                 migrations/20260426_03_add_dr_tables.sql \
                 migrations/20260426_04_add_power_efficiency_30min.sql \
                 migrations/20260426_05_enable_pgvector_skeleton.sql \
                 migrations/20260426_06_add_nilm_label_index.sql \
                 migrations/20260426_07_seed_appliance_status_codes.sql; do
            echo \"--- applying \$f ---\"
            psql -d ${DB_NAME} -v ON_ERROR_STOP=1 -f \"\$f\"
        done
    '"

# ─── 5. 적재 마무리: 정리 + DSN 출력 ─────────────────────────────────
gcloud compute ssh "${INSTANCE_NAME}" --tunnel-through-iap --zone="${ZONE}" \
    --command="rm -rf ${REMOTE_TMP}"

VM_INTERNAL_IP="$(gcloud compute instances describe "${INSTANCE_NAME}" \
    --zone="${ZONE}" \
    --format='value(networkInterfaces[0].networkIP)')"

cat <<EOF

✅ DB 셋업 완료.

로컬 dev 머신 → VM 5432 IAP 터널 (별도 터미널에서 유지):
  gcloud compute start-iap-tunnel ${INSTANCE_NAME} 5432 \\
      --local-host-port=localhost:5432 --zone=${ZONE}

위 터널이 살아 있는 동안:
  export DATABASE_URL="postgresql+asyncpg://${APP_USER}:\$(gcloud secrets versions access latest --secret=${SECRET_NAME})@localhost:5432/${DB_NAME}"

  python -c "
import asyncio
from Database.src.db import session_scope
from sqlalchemy import text
async def main():
    async with session_scope() as s:
        r = await s.execute(text('SELECT extname FROM pg_extension ORDER BY extname'))
        print(list(r.scalars()))
asyncio.run(main())
"
  → ['btree_gist', 'pg_stat_statements', 'plpgsql', 'timescaledb', 'vector']

EOF
