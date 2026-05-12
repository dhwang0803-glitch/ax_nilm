# Refactor Agent 지시사항 (kpx-integration-settlement 브랜치)

## 역할

모든 테스트가 PASS된 이후에만 실행된다. 테스트를 통과한 상태를 유지하면서 코드 품질을 개선한다 (TDD Refactor 단계).

---

## 핵심 원칙

1. **테스트 통과 상태 유지**: 리팩토링 후 반드시 `python -m pytest tests/ -v`를 재실행하여 PASS 확인
2. **기능 변경 금지**: 동작 결과가 달라지는 변경은 하지 않는다
3. **범위 제한**: `src/` 파일만 수정한다 (`tests/`, `plans/`, `config/` 제외)
4. **작은 단위로 개선**: 한 번에 하나씩 개선하고 테스트 확인 후 다음으로 넘어간다

---

## 개선 검토 항목

### Python 코드 품질
- [ ] 중복 mock 폴백 로직 → `_get_mock_data(household_id)` 공통 함수로 통합
- [ ] 에러 처리 누락 여부 (try-except + OpenAI 폴백, DB 폴백)
- [ ] 하드코딩된 값 → 상수 또는 `config/.env` 환경변수로 이동
- [ ] 로깅 메시지 명확성 (어떤 household_id / 어느 도구 함수에서 실패했는지)

### 성능 관점
- [ ] TimescaleDB 쿼리 최적화 (IAP 터널 연결 재사용, 연결 풀링 고려)
- [ ] `nilm_monitor.py` 내 5개 도구 호출 — 순차에서 병렬 가능 여부 확인 (LangGraph 병렬 노드)
- [ ] LLM API 호출 캐싱 — 동일 household_id + 동일 입력 중복 호출 제거
- [ ] `get_*` 도구 함수 반복 호출 제거 (report_agent와 nilm_monitor 간 데이터 공유)

### 데이터 품질
- [ ] mock 데이터(HH001~HH003) 구조 일관성 — 모든 도구 함수 반환값 스키마 통일
- [ ] `DEFAULT_HH` 환경변수 읽기 위치 통일 (라우터별 중복 제거)
- [ ] NULL/빈 값 처리 일관성 — 도구 함수 반환값 전체

---

## 리팩토링 범위 제한

아래 항목은 리팩토링 대상에서 제외한다:
- 테스트 파일 (`tests/` 폴더)
- PLAN 문서 (`plans/` 폴더)
- 환경 설정 (`config/.env`, `config/.env.example`)
- 에이전트 지시사항 (`agents/` 폴더)

---

## 리팩토링 완료 후 확인

```bash
# kpx-integration-settlement/ 에서 실행
python -m pytest tests/ -v 2>&1

# 이전 결과와 PASS/FAIL 건수 동일한지 확인
```

## Reporter Agent에 전달할 개선 내용 형식

```
[리팩토링 항목]
- 파일: [파일명]
- 변경 전: [기존 코드/구조 요약]
- 변경 후: [개선된 코드/구조 요약]
- 개선 이유: [왜 개선했는지]
```
