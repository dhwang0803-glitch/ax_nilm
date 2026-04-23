# dr-savings-prediction

> 이 파일은 [`_claude_templates/CLAUDE_dr-savings-prediction.md`](../_claude_templates/CLAUDE_dr-savings-prediction.md)를 실제 작업 디렉토리에 적용한 것입니다.
> 세부 규칙은 템플릿 파일을 참조하세요. 루트 [`CLAUDE.md`](../CLAUDE.md) 보안 규칙도 함께 적용됩니다.

## 이 브랜치에서 작업 시작 체크리스트

1. `config/.env.example`을 복사해 `config/.env` 생성 후 실제 값 입력
2. `pip install -r requirements.txt` (생성 후)
3. MLflow 서버 연결 확인: `mlflow ui --backend-store-uri ./mlruns`
4. TimescaleDB 연결 확인: `python scripts/predict.py --dry-run`

## 파일 생성 금지 위치

- `dr-savings-prediction/*.py` (루트 직접 생성 금지)
- 프로젝트 루트 직접 생성 금지

모든 규칙은 [`_claude_templates/CLAUDE_dr-savings-prediction.md`](../_claude_templates/CLAUDE_dr-savings-prediction.md) 참조.
