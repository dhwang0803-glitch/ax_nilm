# Test Writer Agent 지시사항

## 역할

구현 전에 실패하는 테스트를 먼저 작성한다 (TDD Red 단계).
구현 후에는 테스트를 실행하고 결과를 수집한다 (검증 단계).

---

## 테스트 작성 원칙

1. 구현 코드가 없어도 테스트를 먼저 작성한다
2. 각 테스트는 하나의 요구사항만 검증한다
3. 기대값을 명확하게 명시한다
4. 테스트 실패 시 원인을 파악할 수 있는 메시지를 포함한다
5. 외부 API/네트워크 의존 테스트는 실제 호출과 Mock 모드를 구분한다

---

## 브랜치별 테스트 파일 위치

| 브랜치 | 테스트 디렉토리 | 형식 |
|--------|--------------|------|
| `API_Server` | `API_Server/tests/` | pytest + httpx AsyncClient |
| `Database` | `Database/tests/` | pytest + 실제 TimescaleDB 연결 (테스트 DB) |
| `nilm-engine` | `nilm-engine/tests/` | pytest (신호처리, 가전 분해 정확도) |
| `anomaly-detection` | `anomaly-detection/tests/` | pytest (이상 탐지, 알림 트리거) |
| `dr-savings-prediction` | `dr-savings-prediction/tests/` | pytest (군집화, 피처 추출) |
| `kpx-integration-settlement` | `kpx-integration-settlement/tests/` | pytest (KPX API, 정산, RAG LLM) |
| `Frontend` | `Frontend/tests/` | Jest + Playwright |

---

## 테스트 작성 예시 (pytest)

### kpx-integration-settlement — DR 이벤트 수신 테스트

```python
import pytest
from src.kpx.client import KPXClient

@pytest.mark.asyncio
async def test_dr_event_parsing():
    """KPX DR 이벤트 JSON을 정상적으로 파싱한다"""
    raw_event = {
        "event_id": "DR-2024-001",
        "start_time": "2024-08-01T17:00:00",
        "end_time": "2024-08-01T20:00:00",
        "target_reduction_kw": 500.0,
    }
    client = KPXClient()
    event = client.parse_event(raw_event)
    assert event.event_id == "DR-2024-001"
    assert event.duration_minutes == 180
```

### kpx-integration-settlement — 절감량 수식 산출 테스트

```python
import numpy as np
from src.settlement.calculator import compute_savings

def test_compute_savings_direct_calculation():
    """에어컨 채널 19:30~20:00 전력을 직접 합산해 절감량을 산출한다 (학습 모델 불사용)"""
    # 1440분 프로파일: 19:30~20:00(30분) 구간에만 1000W
    profile = np.zeros(1440)
    profile[19*60+30 : 20*60] = 1000.0  # 30분간 1000W

    savings_kwh = compute_savings(profile)
    expected = 1000.0 * 30 / 60 / 1000  # 0.5 kWh
    assert abs(savings_kwh - expected) < 1e-6
```

### Database — TimescaleDB Repository 테스트

```python
@pytest.fixture
async def repo(test_db_url):
    from src.repositories.power_profile_repository import PowerProfileRepository
    repo = PowerProfileRepository(test_db_url)
    yield repo
    await repo.close()

@pytest.mark.asyncio
async def test_save_and_retrieve_power_profile(repo):
    profile = PowerProfileSchema(house_id="house_001", date="20240801", data=[0.0]*1440)
    saved = await repo.save(profile)
    loaded = await repo.get_by_id(saved.id)
    assert loaded.house_id == "house_001"
```

### nilm-engine — 가전 분해 테스트

```python
from src.disaggregation.nilm import NILMDisaggregator

def test_ac_channel_detected():
    """에어컨(channel_id=7) 이 활성화된 프로파일에서 AC 채널을 분리한다"""
    disaggregator = NILMDisaggregator()
    result = disaggregator.predict(sample_profile_with_ac)
    assert result["ac_kw"] > 0
```

---

## 필수 테스트 카테고리

### kpx-integration-settlement
- KPX DR 이벤트 수신 및 파싱
- 절감량 수식 산출 (NILM 에어컨 채널 직접 계산)
- 정산 데이터 생성 및 전송 형식 검증
- LLM RAG 보고서 생성 (기상 메타데이터 + 절감량 → LLM 입력 구성)
- 전력거래소 연계 Mock 서버 통합 테스트

### Database
- PowerProfile, DREvent, DRResult Repository save/retrieve 라운드트립
- TimescaleDB 하이퍼테이블 시계열 쿼리 정확성
- 마이그레이션 up/down 검증

### nilm-engine
- 22종 가전 분류 정확도 (F1-score 기준)
- 1440분 프로파일 입력 → 가전별 채널 분리 출력
- 에어컨 채널(AC) 분리 정확도 (절감량 산출 의존성)

### anomaly-detection
- 성능 저하/비정상 작동 감지 정확도
- 심각도별 알림 트리거 조건

### dr-savings-prediction
- K-Means k=3 군집화 재현성 (동일 입력 → 동일 군집)
- 피처 추출 정확성 (dr_window_kwh, total_kwh 등)

### API_Server
- DR 의사결정 엔드포인트 CRUD
- 인증 (OAuth 2.0/JWT)
- WebSocket 실시간 데이터 수신

---

## 테스트 결과 수집 형식

```
전체 테스트: X건
PASS: X건
FAIL: X건
SKIP: X건

FAIL 목록:
- [테스트 ID]: [실패 메시지]
```
