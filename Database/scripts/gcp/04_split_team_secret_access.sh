#!/usr/bin/env bash
# ax_nilm — 팀원 secretAccessor 권한 분리 (REQ-007 PII 권한 분리).
#
# Phase B-2 에서 두 팀원에 일괄 부여한 project-level
# `roles/secretmanager.secretAccessor` 는 모든 secret 에 적용되어
# Fernet 키(`ax-nilm-credential-master-key`) 까지 노출 → PII 평문 복호화 가능.
#
# 본 스크립트는 다음을 수행한다 (각 팀원에 대해 idempotent):
#   1. project-level `roles/secretmanager.secretAccessor` 제거
#   2. secret-level `roles/secretmanager.secretAccessor` 를
#      `ax-nilm-db-app-password` 에만 부여
# → Fernet 키 secret 은 명시적 부여 없으므로 default-deny.
#
# 실행:
#   bash Database/scripts/gcp/04_split_team_secret_access.sh
#
# 사전: PROJECT_ID 환경변수 (`set -a; source Database/.env; set +a`)
#       owner 권한 필요 (본인 계정).

set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID 환경변수가 필요합니다}"
: "${APP_SECRET:=ax-nilm-db-app-password}"
: "${PII_KEY_SECRET:=ax-nilm-credential-master-key}"

# 대상 팀원 — 공백 구분. 환경변수로 override 가능.
: "${TEAM_MEMBERS:=dkswndus6988@gmail.com jiminxkey@gmail.com}"

ROLE="roles/secretmanager.secretAccessor"

gcloud config set project "${PROJECT_ID}" >/dev/null

# ─── 0. 사전 점검 ─────────────────────────────────────────────────────
echo "=== 사전 점검 ==="
for SECRET in "${APP_SECRET}" "${PII_KEY_SECRET}"; do
    if ! gcloud secrets describe "${SECRET}" >/dev/null 2>&1; then
        echo "ERROR: secret '${SECRET}' 가 존재하지 않습니다." >&2
        exit 1
    fi
done
echo "  ✓ ${APP_SECRET} 존재"
echo "  ✓ ${PII_KEY_SECRET} 존재"

# 본인 계정이 owner 인지 sanity (스크립트 실행 권한)
SELF_EMAIL="$(gcloud config get-value account 2>/dev/null)"
echo "  실행 계정: ${SELF_EMAIL}"

# ─── 1. 팀원별 권한 분리 ────────────────────────────────────────────
for MEMBER in ${TEAM_MEMBERS}; do
    echo
    echo "=== ${MEMBER} ==="

    # 1-a. project-level binding 존재 확인
    HAS_PROJECT_BINDING="$(gcloud projects get-iam-policy "${PROJECT_ID}" \
        --flatten='bindings[].members' \
        --filter="bindings.role=${ROLE} AND bindings.members=user:${MEMBER}" \
        --format='value(bindings.role)' 2>/dev/null | head -n1)"

    if [[ -n "${HAS_PROJECT_BINDING}" ]]; then
        echo "  [1/2] project-level ${ROLE} 제거"
        gcloud projects remove-iam-policy-binding "${PROJECT_ID}" \
            --member="user:${MEMBER}" \
            --role="${ROLE}" \
            --condition=None \
            >/dev/null
    else
        echo "  [1/2] project-level ${ROLE} 없음 — skip"
    fi

    # 1-b. secret-level binding (db-app-password 에만) — idempotent
    echo "  [2/2] secret '${APP_SECRET}' 에 ${ROLE} 부여"
    gcloud secrets add-iam-policy-binding "${APP_SECRET}" \
        --member="user:${MEMBER}" \
        --role="${ROLE}" \
        >/dev/null
done

# ─── 2. 사후 검증 ─────────────────────────────────────────────────────
echo
echo "=== 사후 검증 ==="

echo
echo "[A] 팀원 project-level secretAccessor 가 사라졌는지:"
for MEMBER in ${TEAM_MEMBERS}; do
    REMAINING="$(gcloud projects get-iam-policy "${PROJECT_ID}" \
        --flatten='bindings[].members' \
        --filter="bindings.role=${ROLE} AND bindings.members=user:${MEMBER}" \
        --format='value(bindings.role)' 2>/dev/null | head -n1)"
    if [[ -z "${REMAINING}" ]]; then
        echo "  ✓ ${MEMBER}: project-level ${ROLE} 제거됨"
    else
        echo "  ✗ ${MEMBER}: project-level ${ROLE} 가 아직 남아있음 — 수동 확인 필요" >&2
    fi
done

echo
echo "[B] db-app-password secret 바인딩 (팀원 보여야 함):"
gcloud secrets get-iam-policy "${APP_SECRET}" \
    --flatten='bindings[].members' \
    --filter="bindings.role=${ROLE}" \
    --format='value(bindings.members)' 2>/dev/null | sort

echo
echo "[C] Fernet 키 secret 바인딩 (팀원 없어야 함 — owner 만 inherit):"
FERNET_BINDINGS="$(gcloud secrets get-iam-policy "${PII_KEY_SECRET}" \
    --flatten='bindings[].members' \
    --filter="bindings.role=${ROLE}" \
    --format='value(bindings.members)' 2>/dev/null)"
if [[ -z "${FERNET_BINDINGS}" ]]; then
    echo "  ✓ ${PII_KEY_SECRET}: secret-level ${ROLE} 바인딩 없음 (owner inherit 만)"
else
    echo "  ${FERNET_BINDINGS}"
fi

cat <<EOF

✅ 권한 분리 완료.

팀원 시점 검증 (팀원이 직접 실행 — 본인 계정 owner 라 셀프 검증 불가):
  # PERMISSION_DENIED 가 떠야 함:
  gcloud secrets versions access latest --secret=${PII_KEY_SECRET}

  # 정상 응답 (32자 base64 PG 비번):
  gcloud secrets versions access latest --secret=${APP_SECRET}

IAM 캐시로 1-2 분 늦게 반영될 수 있음.
EOF
