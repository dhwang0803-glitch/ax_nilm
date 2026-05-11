# 파일/디렉토리 맵

> 상위 구조 지도. 파일이 추가될 때마다 갱신하지 않는다.
> 갱신 트리거: 새 최상위 폴더/브랜치가 생길 때만.

## 최상위 구조

```
ax_nilm/
├── CLAUDE.md                  — 프로젝트 전역 Claude Code 지침
├── _claude_templates/         — 브랜치별 CLAUDE.md 템플릿
├── _agent_templates/          — 에이전트 역할 문서 (9종)
├── .claude/commands/          — 커스텀 슬래시 커맨드 (PR-report)
├── .githooks/                 — Git 훅 (post-checkout)
├── .github/                   — PR 템플릿
├── docs/
│   ├── context/               — 공유 지식 베이스 (architecture, ADR, MAP)
│   └── class-diagrams/        — 요구사항별 클래스 다이어그램 (.drawio)
├── Database/                  — 데이터 레이어 브랜치 작업 폴더
│   ├── schemas/               — DDL (001_core, 002_timeseries, 003_seed)
│   ├── migrations/            — 스키마 변경 이력 (YYYYMMDD_*.sql)
│   ├── src/                   — Repository · ORM 모델 (import 전용)
│   ├── scripts/               — ETL · 검증 실행 스크립트
│   ├── tests/                 — pytest
│   ├── docs/                  — 스키마 설계 근거 · 데이터셋 명세
│   └── agents/                — 에이전트 역할 문서 사본
├── nilm-engine/               — NILM 분해 엔진 브랜치 작업 폴더 (REQ-001)
│   ├── src/
│   │   ├── acquisition/       — 30Hz 데이터 수집·전처리 (dataset.py, gcs_loader.py)
│   │   ├── features/          — 웨이블릿 + TDA 특징 추출
│   │   ├── models/            — CNN·TDA 인코더 (PyTorch nn.Module)
│   │   ├── classifier/        — 22종 레이블 정의 (label_map.py — 단일 진실 공급원)
│   │   ├── disaggregator.py   — 분해 파이프라인 public API
│   │   └── postprocessor.py   — 예측 후처리 (min_active spike 제거·gap 메우기·always_on 고정)
│   ├── scripts/               — 학습·추론 실행 스크립트 및 Colab 노트북
│   ├── config/                — model.yaml · dataset.yaml 하이퍼파라미터
│   ├── tests/                 — pytest
│   └── docs/                  — 실험 결과·라벨링 기준·개선 계획 (gitignore 대상, 로컬 전용)
└── {다른 모듈 브랜치}/          — API_Server / Execution_Engine / Frontend 등
                                 (post-checkout 훅이 각 브랜치 진입 시 자동 생성)
```

## 브랜치 ↔ 폴더 대응

| 브랜치 | 최상위 폴더 | 상태 |
|--------|-------------|------|
| `main` | (통합 브랜치, 전체 루트) | — |
| `docs` | `docs/context/` 만 편집 | 활성 |
| `Database` | `Database/` | 활성 |
| `nilm-engine` | `nilm-engine/` | 활성 |
| `dr-savings-prediction` | `dr-savings-prediction/` | 활성 |
| `API_Server` | `API_Server/` | 미착수 |
| `Execution_Engine` | `Execution_Engine/` | 미착수 |
| `Frontend` | `Frontend/` | 미착수 |

각 모듈 브랜치의 내부 규칙은 `_claude_templates/CLAUDE_{브랜치명}.md` 참조.

---

## dr-savings-prediction 모듈 분석 결과

### 사용 데이터셋
- **경로**: 로컬 `학습데이터-라벨링데이터/` (79가구)
- **구성**: 분전반(ch01) + 가전별 이벤트(ch02~ch23) parquet
- **ch01 주요 컬럼**: date, house_type, temperature, windchill, humidity
- **ch02~ch23 주요 컬럼**: date, start_time, end_time, power_consumption, appliance_type

### K-Means 군집화 결과 (k=3)

| 군집 | 비율 | 특성 |
|------|------|------|
| C0 | 65% | 저소비 — 하루 평균 소비량 낮음 |
| C1 | 15% | 고소비 — 피크 전력 높음, DR 참여 잠재력 최대 |
| C2 | 20% | 중소비 — 오전(08-12시) 및 낮(12-16시) 패턴이 C1과 유사 |

- **k 선택 근거**: Silhouette k=2(0.44) > k=3(0.37)이나, 저/중/고 실무 해석 가능성 고려해 k=3 채택
- **입력**: 1440분 프로파일 → 24시간 평균(24차원) → StandardScaler → KMeans

### DR 절감량 — 계산 방식

**채택 방법 — 전체 미터(ch01) 기반 직접 계산**
- 절감량(kWh) = CBL[이벤트 구간] - ch01 실측[이벤트 구간]
- CBL: 이벤트 직전 10 평일 중 상위 2일·하위 2일 제외한 6일 가중평균 (KPX 표준)
- 이벤트 구간: KPX 발령 시각 수신 후 동적 결정 (평일 06:00~21:00 내 가변, 최소 30분 전 통보)

**에어컨 채널(ch03 등) 역할**
- KPX 정산 기준은 ch01 전체 미터이며, 에어컨 채널은 가전별 기여 분해(UI 표시용)에만 사용
- 에어컨 보유 가구 46/79 (58%) — 나머지 42%는 세탁기·의류건조기·전기밥솥 등 부하 이동형으로 DR 참여

**가전 유형별 DR 전략**
- 온도 제어형 (에어컨, 전기장판 등): DR 구간 중 설정값 조절 또는 조기 종료
- 부하 이동형 (세탁기, 의류건조기, 전기밥솥 등): DR 구간 전·후로 사용 시점 이동 (총 사용량 동일, 구간 내 소비만 감소)
- 상시 부하 (냉장고, 공기청정기 등): DR 절감 대상 제외

> 정산 단가: kWh당 1,500원 (국민DR 기준). 5분 단위 측정.
