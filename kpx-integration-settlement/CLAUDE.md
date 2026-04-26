# kpx-integration-settlement

> 이 파일은 [`_claude_templates/CLAUDE_kpx-integration-settlement.md`](../_claude_templates/CLAUDE_kpx-integration-settlement.md)를 실제 작업 디렉토리에 적용한 것입니다.
> 세부 규칙은 템플릿 파일을 참조하세요. 루트 [`CLAUDE.md`](../CLAUDE.md) 보안 규칙도 함께 적용됩니다.

## 이 브랜치에서 작업 시작 체크리스트

1. `config/.env.example`을 복사해 `config/.env` 생성 후 실제 값 입력
2. `pip install openai sentence-transformers celery redis xgboost`
3. Redis 실행 확인: `redis-cli ping`
4. 벤치마크 실행: `python -m benchmark.run_benchmark --cbl`

## 파일 생성 금지 위치

- `kpx-integration-settlement/*.py` (루트 직접 생성 금지)
- 프로젝트 루트 직접 생성 금지

모든 규칙은 [`_claude_templates/CLAUDE_kpx-integration-settlement.md`](../_claude_templates/CLAUDE_kpx-integration-settlement.md) 참조.
