#!/usr/bin/env bash
# ax_nilm — ax_nilm_app 사용자 생성/갱신 (03_setup_db.sh 의 user 단계만 재실행).
#
# 03 의 heredoc 안 psql 변수치환이 DO 블록에서 작동하지 않아 실패한 경우
# 사용. 본 스크립트는 SQL 파일을 로컬에서 직접 생성해 SCP → 적용 → 양쪽
# 임시파일 삭제 패턴이라 견고함.
#
# 실행: bash Database/scripts/gcp/03b_create_app_user.sh

set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID 환경변수가 필요합니다}"
: "${ZONE:=asia-northeast3-a}"
: "${INSTANCE_NAME:=ax-nilm-db-dev}"
: "${DB_NAME:=ax_nilm}"
: "${APP_USER:=ax_nilm_app}"
: "${SECRET_NAME:=ax-nilm-db-app-password}"

gcloud config set project "${PROJECT_ID}" >/dev/null

APP_PASSWORD="$(gcloud secrets versions access latest --secret="${SECRET_NAME}")"

# 사용자 존재 여부 확인 → CREATE vs ALTER 결정
EXISTS_OUT="$(gcloud compute ssh "${INSTANCE_NAME}" --tunnel-through-iap --zone="${ZONE}" \
    --command="sudo -u postgres psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname = '${APP_USER}'\"" 2>/dev/null | tr -d '[:space:]')"

if [[ "${EXISTS_OUT}" == "1" ]]; then
    SQL_VERB="ALTER"
    echo "(사용자 ${APP_USER} 이미 존재 — 비밀번호 갱신)"
else
    SQL_VERB="CREATE"
    echo "(사용자 ${APP_USER} 신규 생성)"
fi

# SQL 파일 로컬 생성. 종료 시 trap 으로 삭제.
TMPFILE="$(mktemp)"
trap 'rm -f "${TMPFILE}"' EXIT

# 비밀번호 안에 작은따옴표가 있을 가능성 — openssl rand 결과는 안전하지만
# 일반화 위해 SQL 표준 escape ('' → ').
ESCAPED_PWD="${APP_PASSWORD//\'/\'\'}"

cat > "${TMPFILE}" <<SQL
${SQL_VERB} ROLE ${APP_USER} WITH LOGIN PASSWORD '${ESCAPED_PWD}';

-- DB / 스키마 권한
GRANT CONNECT ON DATABASE ${DB_NAME} TO ${APP_USER};
GRANT USAGE ON SCHEMA public TO ${APP_USER};

-- 기존 테이블 / 시퀀스 (이미 schemas/migrations 적용됨 → 일괄 GRANT)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ${APP_USER};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ${APP_USER};

-- 향후 추가될 테이블 / 시퀀스
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${APP_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO ${APP_USER};
SQL

# SCP + 적용 + 원격 임시파일 삭제 (비밀번호가 디스크에 남지 않도록)
gcloud compute scp --tunnel-through-iap --zone="${ZONE}" \
    "${TMPFILE}" "${INSTANCE_NAME}:/tmp/ax_nilm_user.sql"

gcloud compute ssh "${INSTANCE_NAME}" --tunnel-through-iap --zone="${ZONE}" \
    --command='sudo -u postgres psql -d '"${DB_NAME}"' -v ON_ERROR_STOP=1 -f /tmp/ax_nilm_user.sql && rm /tmp/ax_nilm_user.sql'

echo
echo "✅ ${APP_USER} 권한 설정 완료."
echo
echo "검증:"
echo "  gcloud compute start-iap-tunnel ${INSTANCE_NAME} 5432 --local-host-port=localhost:5432 --zone=${ZONE}"
echo "  (별도 터미널 유지)"
echo "  export DATABASE_URL=\"postgresql+asyncpg://${APP_USER}:\$(gcloud secrets versions access latest --secret=${SECRET_NAME})@localhost:5432/${DB_NAME}\""
echo "  python -c \"import asyncio; from Database.src.db import session_scope; from sqlalchemy import text;"
echo "  async def m():"
echo "      async with session_scope() as s:"
echo "          r = await s.execute(text('SELECT count(*) FROM appliance_types'))"
echo "          print('appliance_types:', r.scalar_one())"
echo "  asyncio.run(m())\""
