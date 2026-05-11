#!/usr/bin/env bash
# ax_nilm — 02_vm_init.sh 가 timescaledb-tune 단계 이후 중단된 경우 이어서 실행.
# (apt install 은 이미 완료된 상태 가정 — 일회성 복구용)
#
# 사용 (로컬에서):
#   gcloud compute scp --tunnel-through-iap --zone=$ZONE \
#       Database/scripts/gcp/02b_resume_init.sh $INSTANCE_NAME:/tmp/
#   gcloud compute ssh $INSTANCE_NAME --tunnel-through-iap --zone=$ZONE \
#       --command='sudo bash /tmp/02b_resume_init.sh'
#
# 모든 단계 idempotent.

set -euxo pipefail

PG_VERSION=16
DB_NAME=ax_nilm
PG_CONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"
HBA_CONF="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"

# ─── listen_addresses ────────────────────────────────────────────────
sed -i "s/^#\?listen_addresses.*/listen_addresses = '*'/" "${PG_CONF}"

# ─── pg_hba (이미 추가됐으면 skip) ────────────────────────────────────
HBA_MARKER="ax_nilm — IAP TCP forwarding"
if ! grep -qF "${HBA_MARKER}" "${HBA_CONF}"; then
    cat >> "${HBA_CONF}" <<'HBA_EOF'

# ax_nilm — IAP TCP forwarding 으로만 도달. 방화벽이 35.235.240.0/20 만 통과.
host    all             all             0.0.0.0/0               md5
HBA_EOF
fi

systemctl restart postgresql

# ─── DB 생성 (없을 때만) ─────────────────────────────────────────────
DB_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" || true)
if [[ "${DB_EXISTS}" != "1" ]]; then
    sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME}"
fi

# ─── 확장 (idempotent IF NOT EXISTS) ─────────────────────────────────
sudo -u postgres psql -d "${DB_NAME}" -v ON_ERROR_STOP=1 <<SQL
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS vector;
SQL

echo "ax_nilm VM init complete: PostgreSQL ${PG_VERSION} + TimescaleDB + pgvector ready, DB=${DB_NAME}"
