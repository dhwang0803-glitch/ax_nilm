# {BRANCH} — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.
> **이 파일은 기본 템플릿입니다. 브랜치 역할에 맞게 수정하세요.**

## 모듈 역할

TODO: 이 브랜치가 담당하는 기능을 한 문장으로 서술하세요.

## 파일 위치 규칙 (MANDATORY)

```
{BRANCH}/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← yaml, .env.example
└── docs/      ← 설계 문서, 리포트
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| import되는 모듈, 유틸 함수 | `src/` |
| `python scripts/run_xxx.py`로 실행 | `scripts/` |
| pytest | `tests/` |
| `.yaml`, `.env.example` | `config/` |
| 문서, 리포트 | `docs/` |

**`{BRANCH}/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

TODO: 주요 라이브러리를 기입하세요.

```python
import psycopg2
from dotenv import load_dotenv
```

## import 규칙

```python
# scripts/ 에서 src/ 모듈 import 방법
ROOT = Path(__file__).resolve().parents[2]  # scripts/는 parents[2]가 ROOT
_SRC = ROOT / "{BRANCH}" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
import my_module
```

## 인터페이스

- **업스트림**: TODO (어떤 데이터/결과를 받는지)
- **다운스트림**: TODO (어떤 데이터/결과를 내보내는지)

## 토큰 절감 규칙 (MANDATORY)

### 파일 읽기 전략
- 작업 시작 시 대상 파일의 전체 크기를 먼저 확인한다 (wc -l 또는 limit=1)
- 500줄 이하 파일은 전체 읽기 허용
- 500줄 초과 파일은 목차/헤더를 먼저 읽고(limit=30), 작업에 필요한 구간을 특정한 뒤 해당 구간만 읽는다
- 판단이 불확실하면 "이 구간만 읽어도 되는지" 사용자에게 확인 후 진행한다

### 출력 간결화
- 파일 Write 후 변경 내용을 반복 설명하지 않는다 (diff를 보면 알 수 있는 내용은 생략)
- 단, 설계 판단이 들어간 경우는 한 줄로 근거를 남긴다
- 탐색 중간 결과를 전부 나열하지 않고, 최종 결론만 보고한다

### 세션 관리
- 단일 세션에서 서로 독립적인 작업을 연속 수행하지 않는다 — 작업 단위별로 세션을 분리한다
- 컨텍스트가 커졌다고 느끼면 /compact 실행을 사용자에게 권고한다
