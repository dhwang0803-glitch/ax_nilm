#!/usr/bin/env bash
# ax_nilm — VM 디스크 일일 스냅샷 정책 활성화.
#
# 사고 시 24시간 내 롤백 안전망. 팀원 권한 분리(05) 설계가 누수되거나
# 누군가 실수로 데이터를 손상시켜도 어제 자정 시점으로 되돌릴 수 있게 한다.
#
# 정책:
#   - 매일 09:00 UTC (= KST 18:00) 자동 스냅샷
#   - 7일치 보관 (자동 삭제)
#   - region: asia-northeast3 (VM 과 동일)
#
# 비용 추산:
#   100GB 디스크 × 7 스냅샷 incremental ≈ $5~10/월 (변화량 의존)
#
# 실행: bash Database/scripts/gcp/06_enable_disk_snapshots.sh

set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID 환경변수가 필요합니다}"
: "${ZONE:=asia-northeast3-a}"
: "${REGION:=asia-northeast3}"
: "${INSTANCE_NAME:=ax-nilm-db-dev}"
: "${POLICY_NAME:=ax-nilm-db-daily-snapshot}"
: "${RETENTION_DAYS:=7}"
: "${SNAPSHOT_TIME:=09:00}"  # UTC — KST 는 +9 → 18:00 KST

gcloud config set project "${PROJECT_ID}" >/dev/null

# ─── 1. 정책 생성 (없으면) ────────────────────────────────────────
if gcloud compute resource-policies describe "${POLICY_NAME}" --region="${REGION}" >/dev/null 2>&1; then
    echo "(정책 '${POLICY_NAME}' 이미 존재 — skip)"
else
    echo "=== 스냅샷 정책 생성 ==="
    gcloud compute resource-policies create snapshot-schedule "${POLICY_NAME}" \
        --region="${REGION}" \
        --max-retention-days="${RETENTION_DAYS}" \
        --start-time="${SNAPSHOT_TIME}" \
        --daily-schedule
fi

# ─── 2. VM 디스크에 정책 부착 ─────────────────────────────────────
DISK_NAME="$(gcloud compute instances describe "${INSTANCE_NAME}" \
    --zone="${ZONE}" \
    --format='value(disks[0].source.basename())')"

echo
echo "=== 디스크 '${DISK_NAME}' 에 정책 부착 ==="

ATTACHED="$(gcloud compute disks describe "${DISK_NAME}" --zone="${ZONE}" \
    --format='value(resourcePolicies)' 2>/dev/null | grep -c "${POLICY_NAME}" || true)"

if [[ "${ATTACHED}" -gt 0 ]]; then
    echo "(정책 이미 부착됨 — skip)"
else
    gcloud compute disks add-resource-policies "${DISK_NAME}" \
        --resource-policies="${POLICY_NAME}" \
        --zone="${ZONE}"
fi

# ─── 3. 검증 ───────────────────────────────────────────────────────
echo
echo "=== 검증 ==="
echo "디스크에 부착된 정책:"
gcloud compute disks describe "${DISK_NAME}" --zone="${ZONE}" \
    --format="value(resourcePolicies)" | sed 's/^/  /'

cat <<EOF

✅ 일일 스냅샷 정책 활성화 완료.

- 다음 자동 스냅샷: 매일 09:00 UTC (= 18:00 KST)
- 보관: ${RETENTION_DAYS} 일 (이후 자동 삭제)
- 첫 스냅샷은 다음 정시에 생성. 즉시 백업이 필요하면:
    gcloud compute disks snapshot ${DISK_NAME} --zone=${ZONE} \\
        --snapshot-names=ax-nilm-db-manual-\$(date +%Y%m%d-%H%M)

복원 절차 (사고 발생 시):
  1) 스냅샷 목록:
       gcloud compute snapshots list --filter="sourceDisk:${DISK_NAME}"
  2) 디스크 복제:
       gcloud compute disks create restored-\$(date +%Y%m%d) \\
           --source-snapshot=<SNAP_NAME> --zone=${ZONE}
  3) VM stop → 디스크 detach/attach 교체 → start
EOF
