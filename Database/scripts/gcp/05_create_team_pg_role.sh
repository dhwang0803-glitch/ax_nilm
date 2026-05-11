#!/usr/bin/env bash
# ax_nilm — ax_nilm_team PG 역할 신설 + 권한 마이그레이션 + 팀원 secret 스왑.
#
# 본 스크립트는 다음을 수행한다 (idempotent):
#   1. ax_nilm_team 비밀번호 32자 생성 → Secret Manager 'ax-nilm-db-team-password' 저장
#   2. VM 에서 ax_nilm_team CREATE/ALTER ROLE
#   3. migrations/20260427_09_team_writer_role_grants.sql 적용
#   4. 팀원 secret 바인딩 스왑:
#      - 'ax-nilm-db-app-password' 에서 팀원 제거
#      - 'ax-nilm-db-team-password' 에 팀원 추가
#
# 실행: bash Database/scripts/gcp/05_create_team_pg_role.sh
# 사전: PROJECT_ID 환경변수, 04_split_team_secret_access.sh 적용 후 실행
# 권한: project owner

set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID 환경변수가 필요합니다}"
: "${ZONE:=asia-northeast3-a}"
: "${INSTANCE_NAME:=ax-nilm-db-dev}"
: "${DB_NAME:=ax_nilm}"
: "${TEAM_USER:=ax_nilm_team}"
: "${TEAM_SECRET:=ax-nilm-db-team-password}"
: "${APP_SECRET:=ax-nilm-db-app-password}"
: "${TEAM_MEMBERS:=dkswndus6988@gmail.com jiminxkey@gmail.com}"

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
MIGRATION_FILE="${REPO_ROOT}/Database/migrations/20260427_09_team_writer_role_grants.sql"
SM_ROLE="roles/secretmanager.secretAccessor"

if [[ ! -f "${MIGRATION_FILE}" ]]; then
    echo "ERROR: ${MIGRATION_FILE} 없음" >&2
    exit 1
fi

gcloud config set project "${PROJECT_ID}" >/dev/null

# ─── 1. 비밀번호 생성 + Secret Manager 저장 ────────────────────────
if gcloud secrets describe "${TEAM_SECRET}" >/dev/null 2>&1; then
    echo "(Secret '${TEAM_SECRET}' 이미 존재 — 기존 latest 버전 사용)"
else
    echo "=== Secret '${TEAM_SECRET}' 신규 생성 ==="
    TEAM_PASSWORD="$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)"
    printf '%s' "${TEAM_PASSWORD}" \
        | gcloud secrets create "${TEAM_SECRET}" \
            --data-file=- \
            --replication-policy=automatic \
            --labels=app=ax-nilm,role=db-team
fi
TEAM_PASSWORD="$(gcloud secrets versions access latest --secret="${TEAM_SECRET}")"

# ─── 2. ax_nilm_team 역할 생성/갱신 ────────────────────────────────
echo
echo "=== ${TEAM_USER} 역할 CREATE/ALTER ==="

EXISTS_OUT="$(gcloud compute ssh "${INSTANCE_NAME}" --tunnel-through-iap --zone="${ZONE}" \
    --command="sudo -u postgres psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname = '${TEAM_USER}'\"" 2>/dev/null \
    | tr -d '[:space:]')"

if [[ "${EXISTS_OUT}" == "1" ]]; then
    SQL_VERB="ALTER"
    echo "(역할 ${TEAM_USER} 이미 존재 — 비밀번호 갱신)"
else
    SQL_VERB="CREATE"
    echo "(역할 ${TEAM_USER} 신규 생성)"
fi

USER_TMP="$(mktemp)"
trap 'rm -f "${USER_TMP}"' EXIT
ESCAPED_PWD="${TEAM_PASSWORD//\'/\'\'}"

cat > "${USER_TMP}" <<SQL
${SQL_VERB} ROLE ${TEAM_USER} WITH LOGIN PASSWORD '${ESCAPED_PWD}';
SQL

gcloud compute scp --tunnel-through-iap --zone="${ZONE}" \
    "${USER_TMP}" "${INSTANCE_NAME}:/tmp/ax_nilm_team_user.sql" >/dev/null

gcloud compute ssh "${INSTANCE_NAME}" --tunnel-through-iap --zone="${ZONE}" \
    --command="sudo -u postgres psql -d ${DB_NAME} -v ON_ERROR_STOP=1 -f /tmp/ax_nilm_team_user.sql && rm /tmp/ax_nilm_team_user.sql" >/dev/null

# ─── 3. 권한 마이그레이션 적용 ─────────────────────────────────────
echo
echo "=== 권한 마이그레이션 적용 ==="

REMOTE_MIG=/tmp/team_writer_role_grants.sql
gcloud compute scp --tunnel-through-iap --zone="${ZONE}" \
    "${MIGRATION_FILE}" "${INSTANCE_NAME}:${REMOTE_MIG}" >/dev/null

gcloud compute ssh "${INSTANCE_NAME}" --tunnel-through-iap --zone="${ZONE}" \
    --command="sudo -u postgres psql -d ${DB_NAME} -v ON_ERROR_STOP=1 -f ${REMOTE_MIG} && rm ${REMOTE_MIG}"

# ─── 4. 팀원 secret 바인딩 스왑 ────────────────────────────────────
echo
echo "=== 팀원 secret 바인딩 스왑 ==="

for MEMBER in ${TEAM_MEMBERS}; do
    echo
    echo "--- ${MEMBER} ---"

    HAS_APP_BINDING="$(gcloud secrets get-iam-policy "${APP_SECRET}" \
        --flatten='bindings[].members' \
        --filter="bindings.role=${SM_ROLE} AND bindings.members=user:${MEMBER}" \
        --format='value(bindings.role)' 2>/dev/null | head -n1)"

    if [[ -n "${HAS_APP_BINDING}" ]]; then
        echo "  [1/2] secret '${APP_SECRET}' 에서 ${MEMBER} 제거"
        gcloud secrets remove-iam-policy-binding "${APP_SECRET}" \
            --member="user:${MEMBER}" \
            --role="${SM_ROLE}" \
            --condition=None \
            >/dev/null
    else
        echo "  [1/2] secret '${APP_SECRET}' 바인딩 없음 — skip"
    fi

    echo "  [2/2] secret '${TEAM_SECRET}' 에 ${MEMBER} 추가"
    gcloud secrets add-iam-policy-binding "${TEAM_SECRET}" \
        --member="user:${MEMBER}" \
        --role="${SM_ROLE}" \
        >/dev/null
done

# ─── 5. 사후 검증 ──────────────────────────────────────────────────
echo
echo "=== 사후 검증 ==="

echo
echo "[A] db-app-password 바인딩 (팀원 없어야 함):"
APP_BINDINGS="$(gcloud secrets get-iam-policy "${APP_SECRET}" \
    --flatten='bindings[].members' \
    --filter="bindings.role=${SM_ROLE}" \
    --format='value(bindings.members)' 2>/dev/null)"
if [[ -z "${APP_BINDINGS}" ]]; then
    echo "  ✓ 바인딩 없음 (owner inherit 만)"
else
    echo "${APP_BINDINGS}" | sed 's/^/  /'
fi

echo
echo "[B] db-team-password 바인딩 (팀원 보여야 함):"
gcloud secrets get-iam-policy "${TEAM_SECRET}" \
    --flatten='bindings[].members' \
    --filter="bindings.role=${SM_ROLE}" \
    --format='value(bindings.members)' 2>/dev/null | sort | sed 's/^/  /'

echo
echo "[C] ax_nilm_team DML 가능 테이블 (6개 보여야 함):"
gcloud compute ssh "${INSTANCE_NAME}" --tunnel-through-iap --zone="${ZONE}" \
    --command="sudo -u postgres psql -d ${DB_NAME} -tAc \"SELECT string_agg(DISTINCT table_name, ', ' ORDER BY table_name) FROM information_schema.role_table_grants WHERE grantee = '${TEAM_USER}' AND privilege_type = 'INSERT'\"" 2>/dev/null | sed 's/^/  /'

cat <<EOF

✅ ax_nilm_team 역할 + 권한 + secret 스왑 완료.

팀원 안내사항:
  1) 본인 .env 의 두 줄 갱신:
       APP_USER=${TEAM_USER}
       SECRET_NAME=${TEAM_SECRET}
  2) 새 secret 접근 검증:
       gcloud secrets versions access latest --secret=${TEAM_SECRET}
  3) DB 접속 후 권한 자가검증:
       INSERT INTO appliance_status_intervals (...) VALUES (...);  -- 성공
       DELETE FROM households WHERE 1=0;                            -- "permission denied"
EOF
