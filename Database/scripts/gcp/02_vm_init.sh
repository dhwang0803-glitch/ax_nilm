#!/usr/bin/env bash
# ax_nilm — VM 시작 스크립트 (cloud-init equivalent).
#
# 본 파일은 01_provision_vm.sh 가 --metadata-from-file startup-script 로 주입한다.
# VM 부팅 직후 root 로 1회 자동 실행. 결과 로그:
#   sudo journalctl -u google-startup-scripts.service
#
# 작업:
#   1. 시스템 패키지 갱신
#   2. PostgreSQL 16 (PGDG repo) + TimescaleDB 2.x (Timescale repo) 설치
#   3. timescaledb-tune (메모리/워커 자동 튜닝)
#   4. listen_addresses, pg_hba (IAP 내부 IP 만 허용)
#   5. ax_nilm DB 생성, 확장 enable
#   6. 완료 마커 출력 (01 스크립트 hint 와 일치)

set -euxo pipefail

PG_VERSION=16
DB_NAME=ax_nilm

# ─── 1. 시스템 패키지 ─────────────────────────────────────────────────
apt-get update
apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg lsb-release apt-transport-https

# ─── 2.a. PostgreSQL 16 (PGDG 공식 repo) ──────────────────────────────
install -d /usr/share/keyrings
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    | gpg --dearmor -o /usr/share/keyrings/postgresql-keyring.gpg

echo "deb [signed-by=/usr/share/keyrings/postgresql-keyring.gpg] \
http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list

# ─── 2.b. TimescaleDB (Timescale 공식 repo) ───────────────────────────
curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/timescaledb-keyring.gpg

echo "deb [signed-by=/usr/share/keyrings/timescaledb-keyring.gpg] \
https://packagecloud.io/timescale/timescaledb/debian/ $(lsb_release -cs) main" \
    > /etc/apt/sources.list.d/timescaledb.list

apt-get update
apt-get install -y --no-install-recommends \
    "postgresql-${PG_VERSION}" \
    "postgresql-client-${PG_VERSION}" \
    "postgresql-${PG_VERSION}-pgvector" \
    "timescaledb-2-postgresql-${PG_VERSION}" \
    timescaledb-tools

# ─── 3. timescaledb-tune ──────────────────────────────────────────────
# --yes 플래그가 모든 권장값 자동 채택. `yes |` 추가 시 timescaledb-tune
# 종료 후 yes 가 SIGPIPE → exit 141 → pipefail+set -e 로 스크립트 중단.
timescaledb-tune --quiet --yes --pg-version "${PG_VERSION}"

# ─── 4. listen_addresses + pg_hba (IAP 진입만 허용) ───────────────────
PG_CONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"
HBA_CONF="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"

# 모든 인터페이스에서 listen — 방화벽이 IAP 만 허용하므로 노출 위험 없음
sed -i "s/^#\?listen_addresses.*/listen_addresses = '*'/" "${PG_CONF}"

# pg_hba: 기존 룰 보존 + 외부에서 IP 무관 md5 인증 (IAP 가 통과시킨 것만 도달)
# IAP TCP forwarding 은 VM 내부에서 보면 메타데이터 서버가 source 가 아닌
# 실제 SSH 세션처럼 들어오므로 source 0.0.0.0/0 이라도 외부 직접 접근 불가.
cat >> "${HBA_CONF}" <<'HBA_EOF'

# ax_nilm — IAP TCP forwarding 으로만 도달. 방화벽이 35.235.240.0/20 만 통과.
host    all             all             0.0.0.0/0               md5
HBA_EOF

systemctl restart postgresql

# ─── 5. ax_nilm DB + 확장 ─────────────────────────────────────────────
sudo -u postgres psql <<SQL
CREATE DATABASE ${DB_NAME};
\c ${DB_NAME}
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS vector;
SQL

# ─── 6. 완료 마커 ────────────────────────────────────────────────────
echo "ax_nilm VM init complete: PostgreSQL ${PG_VERSION} + TimescaleDB + pgvector ready, DB=${DB_NAME}"
