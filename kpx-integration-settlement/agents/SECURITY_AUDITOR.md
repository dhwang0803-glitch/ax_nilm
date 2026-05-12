# Security Auditor Agent 지시사항 (kpx-integration-settlement 브랜치)

## 역할

코드 작성 후 실행 전, 또는 git commit 직전에 호출된다.
**개인식별 정보·자격증명·실제 인프라 정보**가 코드나 스테이징 영역에 노출되었는지 점검하고,
위반 항목이 있으면 즉시 차단한다.

> **kpx-integration-settlement 특이사항**: OpenAI API 키, TimescaleDB 접속 정보(IAP 터널 포함)는 하드코딩 절대 금지.
> 가구별 전력 소비 데이터는 개인식별 가능 정보(PII) — mock 데이터(HH001~HH003)도 실 가구 정보가 없어야 한다.

---

## 실행 시점

1. **코드 작성/수정 직후, 실행 전** — `src/` 파일에 자격증명이 들어갔는지 확인
2. **git commit 직전** — 스테이징 영역 전수 검사 후 커밋 허용 여부 결정

---

## 점검 절차

### Step 0. 점검 대상 파일 수집

```bash
# 방법 A: 스테이징된 파일 (커밋 직전)
git diff --cached --name-only --diff-filter=ACM

# 방법 B: 최근 수정된 파일 (실행 전 점검)
git diff HEAD --name-only --diff-filter=ACM
```

수집한 파일 목록을 기준으로 이하 체크를 실행한다.

---

### [S01] 하드코딩 자격증명 탐지 — FAIL 시 즉시 차단

점검 대상: 수집된 `.py` 파일 전체

```bash
grep -rn --include="*.py" \
  -iE "(api_key|password|secret|token|passwd|pwd|openai_key)\s*=\s*['\"][^'\"]{6,}['\"]" \
  <대상 파일들>
```

**판정 기준**:
- 매칭 라인이 있으면 → **FAIL**
- 예외: `os.getenv(...)`, `dotenv_values(...)`, `config.get(...)` 형태는 PASS
- 예외: 변수명에 `example`, `sample`, `test`, `placeholder` 포함 시 PASS

---

### [S02] os.getenv() 실제 인프라 기본값 탐지 — FAIL 시 즉시 차단

```bash
grep -rn --include="*.py" \
  -E "os\.getenv\s*\([^)]+,\s*['\"][^'\"]+['\"]" \
  <대상 파일들>
```

추출된 라인에서 기본값이 아래에 해당하면 **FAIL**:
- 실제 IP 패턴: `\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b` (127.0.0.1 제외)
- DB명 패턴: `localhost`, `postgres` 이외의 특정 DB명
- 사용자명 패턴: `postgres` 이외의 특정 사용자명

허용되는 기본값 (PASS):
- `"localhost"`, `"5432"`, `"5436"` (IAP 터널 포트), `"postgres"`, `""`, `"0.0.0.0"`
- `"HH001"` (가구 ID 기본값 — mock 전환 기준으로 허용)

---

### [S03] env.get() / dict.get() 실제 인프라 기본값 탐지 — FAIL 시 차단

```bash
grep -rn --include="*.py" \
  -E "env\.get\s*\([^)]+,\s*['\"][^'\"]+['\"]" \
  <대상 파일들>
```

S02와 동일한 기준으로 기본값 판정.

---

### [S04] 실제 IP 주소 하드코딩 탐지 — FAIL 시 차단

```bash
grep -rn --include="*.py" \
  -E "\"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\"" \
  <대상 파일들>
```

**판정 기준**:
- `"127.0.0.1"`, `"0.0.0.0"` → PASS (루프백/와일드카드)
- 그 외 실제 IP → **FAIL**

---

### [S05] .env 파일 스테이징 여부 — FAIL 시 즉시 차단

```bash
git diff --cached --name-only | grep -E "(^|/)\.env(\.|$)"
```

`config/.env`, `.env.local` 등이 staged → **FAIL**
`config/.env.example` → PASS

---

### [S06] 민감 파일 git 추적 여부 — FAIL 시 차단

```bash
git ls-files | grep -E "\.(env|pem|key|p12|pfx)$|credentials\.json|secrets\.json"
```

위 패턴 파일이 git에 추적 중 → **FAIL**

---

### [S07] .gitignore 필수 항목 누락 — FAIL 시 차단

```bash
cat .gitignore
```

아래 항목이 **모두** 포함되어야 PASS:
- `.env` 또는 `config/.env`
- `*.pem`
- `*.key`
- `credentials.json`
- `.claude/settings.local.json`
- `*.parquet` (전력 소비 원시 데이터 — PII)
- `*.joblib` (학습 모델 — 가구 패턴 포함 가능)

---

### [S08] 하드코딩 로컬 경로 — WARNING (커밋 허용, 보고 필요)

```bash
grep -rn --include="*.py" \
  -E "\"C:/Users/[^\"]+\"|'C:/Users/[^']+'" \
  <대상 파일들>
```

**판정 기준**:
- 모듈 최상단 상수이고 CLI 인자로 덮어쓸 수 있으면 → **WARNING** (허용)
- 함수 내부 직접 사용 → **FAIL**

---

### [S09] mock 데이터 가구 PII 노출 — WARNING

`data_tools.py`의 `_MOCK_DATA` 내 실제 가구 개인정보(이름, 주소, 연락처) 포함 여부 확인.

```bash
grep -rn "HH001\|HH002\|HH003" src/agent/data_tools.py | grep -iE "(name|address|phone|email|주소|이름|연락처)"
```

실제 개인정보 발견 → **WARNING** (보안팀 검토 권고)

---

## 전체 실행 스크립트

```bash
#!/usr/bin/env bash
# kpx-integration-settlement/ 에서 실행
echo "=== Security Audit 시작 (kpx-integration-settlement) ==="
echo "점검 시각: $(date '+%Y-%m-%d %H:%M')"
FAIL_COUNT=0
WARN_COUNT=0

STAGED=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null)
MODIFIED=$(git diff HEAD --name-only --diff-filter=ACM 2>/dev/null)
TARGET_PY=$(echo -e "${STAGED}\n${MODIFIED}" | grep '\.py$' | grep '^kpx-integration-settlement/' | sort -u)

echo "점검 파일: $(echo "$TARGET_PY" | grep -c '.py')개"
echo "---"

# S01~S09 점검 (상위 SECURITY_AUDITOR.md 스크립트 동일 구조)
# ... (생략 — 상위 _agent_templates/SECURITY_AUDITOR.md 전체 실행 스크립트 참조)

echo ""
echo "=== Security Audit 완료 ==="
echo "FAIL: ${FAIL_COUNT}건 / WARN: ${WARN_COUNT}건"
if [ "$FAIL_COUNT" -gt 0 ]; then
  echo ">>> 커밋 차단 — FAIL 항목 수정 후 재실행"
else
  echo ">>> 커밋 진행 가능"
fi
```

---

## Orchestrator에 전달할 결과 형식

```
[Security Auditor 결과]
- 실행 시점: 코드 작성 후 / 커밋 직전
- 점검 파일: N개 (kpx-integration-settlement/src/ 기준)
- PASS: N건 / FAIL: N건 / WARN: N건

FAIL 항목:
- [S번호 FAIL] 설명
  위반 파일: src/agent/data_tools.py:라인번호
  위반 내용: (실제 값은 마스킹 — 예: api_key = "ab**...")

판단:
- FAIL 0건 → 커밋/실행 허용
- FAIL 1건 이상 → 즉시 차단, 수정 요청
- WARN만 존재 → 허용, 보고서에 기록
```

---

## 주의사항

1. 점검 결과 출력에 실제 자격증명 값을 포함하지 않는다 (마스킹 처리)
2. `DEFAULT_HH=HH001` 환경변수 기본값은 PASS (mock 전환 기준으로 허용)
3. IAP 터널 포트 `5436` 하드코딩은 PASS (localhost 루프백 + 변경 가능한 포트)
4. `config/.env.example`은 민감 정보 없이 키 이름만 포함된 경우 PASS
