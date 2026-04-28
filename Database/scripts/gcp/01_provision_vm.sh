#!/usr/bin/env bash
# ax_nilm — GCP Compute Engine VM 프로비저닝 (PostgreSQL + TimescaleDB)
#
# 본 스크립트는 다음을 생성한다:
#   1. 방화벽 규칙 — IAP TCP forwarding 만 (SSH 22, PostgreSQL 5432)
#   2. VM — public IP 없음, 시작 시 02_vm_init.sh 자동 실행
#
# 실행: bash Database/scripts/gcp/01_provision_vm.sh
# 사전: Database/docs/gcp_setup.md §1 (gcloud 인증/프로젝트/API enable)

set -euo pipefail

# ─── 환경변수 (Database/docs/gcp_setup.md §2 참조) ────────────────────
: "${PROJECT_ID:?PROJECT_ID 환경변수가 필요합니다 (예: export PROJECT_ID=my-gcp-project)}"
: "${ZONE:=asia-northeast3-a}"
: "${REGION:=asia-northeast3}"
: "${INSTANCE_NAME:=ax-nilm-db-dev}"
: "${MACHINE_TYPE:=e2-standard-2}"
: "${DISK_SIZE:=100}"
: "${IMAGE_FAMILY:=debian-12}"
: "${IMAGE_PROJECT:=debian-cloud}"
: "${SUBNET:=default}"
: "${SERVICE_ACCOUNT:=}"  # 빈 값이면 default compute SA 사용

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INIT_SCRIPT="${SCRIPT_DIR}/02_vm_init.sh"

if [[ ! -f "${INIT_SCRIPT}" ]]; then
    echo "ERROR: ${INIT_SCRIPT} 없음" >&2
    exit 1
fi

echo "=== 프로젝트 컨텍스트 ==="
gcloud config set project "${PROJECT_ID}"
gcloud config set compute/zone "${ZONE}"
gcloud config set compute/region "${REGION}"

echo
echo "=== 필수 API enable (idempotent) ==="
gcloud services enable \
    compute.googleapis.com \
    iap.googleapis.com \
    secretmanager.googleapis.com

echo
echo "=== 방화벽: IAP → SSH (22) ==="
# IAP TCP forwarding 의 발신 IP 범위 = 35.235.240.0/20 (Google 고정)
if ! gcloud compute firewall-rules describe ax-nilm-allow-iap-ssh >/dev/null 2>&1; then
    gcloud compute firewall-rules create ax-nilm-allow-iap-ssh \
        --network="${SUBNET}" \
        --direction=INGRESS \
        --action=ALLOW \
        --rules=tcp:22 \
        --source-ranges=35.235.240.0/20 \
        --target-tags=ax-nilm-db
else
    echo "(이미 존재 — skip)"
fi

echo
echo "=== 방화벽: IAP → PostgreSQL (5432) ==="
if ! gcloud compute firewall-rules describe ax-nilm-allow-iap-postgres >/dev/null 2>&1; then
    gcloud compute firewall-rules create ax-nilm-allow-iap-postgres \
        --network="${SUBNET}" \
        --direction=INGRESS \
        --action=ALLOW \
        --rules=tcp:5432 \
        --source-ranges=35.235.240.0/20 \
        --target-tags=ax-nilm-db
else
    echo "(이미 존재 — skip)"
fi

echo
echo "=== VM 생성 ==="
# Public IP: 부여 (ephemeral). 사유:
#   - 시작 스크립트가 apt 로 deb.debian.org / Timescale repo 받아야 함
#   - --no-address 면 Cloud NAT 추가 필요 (월 ~₩40K) → dev 비용 비효율
#   - 인바운드는 firewall 가 IAP(35.235.240.0/20) 만 허용 — public IP 가 있어도
#     포트 22/5432 외부 직접 접근 차단. 추가되는 건 아웃바운드만.
# Prod 전환 시: --no-address + Cloud NAT 로 변경.
# --shielded-*: secure boot + integrity monitoring
# --metadata enable-oslogin=TRUE: SSH 키 IAM 으로 관리 (개별 키 분배 불필요)

SA_FLAG=""
if [[ -n "${SERVICE_ACCOUNT}" ]]; then
    SA_FLAG="--service-account=${SERVICE_ACCOUNT}"
fi

gcloud compute instances create "${INSTANCE_NAME}" \
    --machine-type="${MACHINE_TYPE}" \
    --image-family="${IMAGE_FAMILY}" \
    --image-project="${IMAGE_PROJECT}" \
    --boot-disk-size="${DISK_SIZE}GB" \
    --boot-disk-type=pd-ssd \
    --subnet="${SUBNET}" \
    --tags=ax-nilm-db \
    --shielded-secure-boot \
    --shielded-vtpm \
    --shielded-integrity-monitoring \
    --metadata=enable-oslogin=TRUE \
    --metadata-from-file=startup-script="${INIT_SCRIPT}" \
    --scopes=cloud-platform \
    ${SA_FLAG}

echo
echo "=== 결과 ==="
gcloud compute instances describe "${INSTANCE_NAME}" \
    --format='value(name,status,zone.basename(),networkInterfaces[0].networkIP)'

cat <<EOF

✅ VM 생성 완료. 시작 스크립트(02_vm_init.sh) 가 백그라운드 실행 중.
   (PostgreSQL + TimescaleDB 설치 ~3-5분 소요)

다음 단계:
  1) 시작 스크립트 완료 확인:
       gcloud compute ssh ${INSTANCE_NAME} --tunnel-through-iap \\
           --command='sudo journalctl -u google-startup-scripts.service --no-pager | tail -50'
     마지막에 "ax_nilm VM init complete" 가 보이면 OK.

  2) DB 설정 (앱 사용자 + Secret Manager + 스키마 적용):
       bash Database/scripts/gcp/03_setup_db.sh

EOF
