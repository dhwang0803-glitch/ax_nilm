# anomaly-detection 파일 맵

## src/

| 파일 | ANOM ID | 역할 |
|------|---------|------|
| `src/models/schemas.py` | ANOM-000 | Severity · AnomalyType · AnomalyEvent · DisaggregationResult |
| `src/detectors/statistical.py` | ANOM-001 | StatisticalAnomalyDetector (소비량·피크·작동시간) |
| `src/detectors/pattern.py` | ANOM-002 | PatternAnomalyDetector (Isolation Forest + 주기성) |
| `src/service.py` | 전체 | AnomalyDetectionService (파이프라인 오케스트레이터) |
| `src/repository.py` | — | DB 저장 연동 (`save_events` → Database.AnomalyEventRepository) |

## config/

| 파일 | 역할 |
|------|------|
| `config/anomaly.yaml` | 임계값 · PoC 모드 · Isolation Forest 설정 |

## tests/

| 파일 | 대상 |
|------|------|
| `tests/test_statistical.py` | StatisticalAnomalyDetector |
| `tests/test_pattern.py` | PatternAnomalyDetector |

## 데이터 흐름

```
nilm-engine
  └─ DisaggregationResult[]
        │
        ├─ StatisticalAnomalyDetector  (ANOM-001)
        └─ PatternAnomalyDetector      (ANOM-002)
              │
              └─ AnomalyEvent[]
                    │
                    └─ save_events(session, household_id, events)
                          └─ Database.AnomalyEventRepository
                                └─ anomaly_events 테이블
```
