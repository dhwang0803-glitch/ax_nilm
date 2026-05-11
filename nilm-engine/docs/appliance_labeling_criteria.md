# 22가전 라벨링 기준 (AI Hub 71685 별첨4)

> 출처: `'23년 인공지능 학습용 데이터 활용 가이드라인 (전기 인프라 지능화를 위한 가전기기 전력 사용량 데이터) v1.0`, 별첨 4 — 가전기기별 라벨링 기준 가이드라인
> 정리일: 2026-04-28
> 용도: 가전별 ON/OFF 판정 임계값 / CNN+TDA 상태 분류 모델 학습 라벨 정합성 검증 / 평가 임계값 교체

---

## 0. 공통 정의

### 가전기기 활성/비활성 상태 판정 (공통)

가전이 다음 신호를 모두 보일 때 **활성(active)** 으로 판단:
- 가전기기에서 전원이 들어와 동작 (소비 전력이 0이 아님, noise 수준 이상)
- 단순 신호 동작(기기의 메인 전원에 비해 상대적으로 낮은 전력 사용)으로 구분
- 예시: 가구의 스스로 추가적인 단순 Display 점등, 예약/코스 선택 등은 활성에서 제외

각 가전마다 다음 **세 조건의 조합**으로 활성 구간을 라벨링:

1. **대기전력 임계값** — 이 값 이하는 비활성으로 간주
2. **활성 최소 동작 시간** — 활성으로 인정되는 최소 동작 시간
3. **Gap 분리 시간** — 두 활성 구간 사이 이 시간 이상 비활성이면 별도 구간으로 분리

### 라벨링 절차

- 1차: 오토라벨링
- 2차: 크라우드 워커가 가전별 가이드 참조하여 활성/비활성 구간 조정
- 3차: 두 명의 작업자가 동일 데이터에 대해 교차 검수

### 22가전 패턴 그룹 분류 (PDF의 TYPE)

> 코드의 `_ON_THRESHOLD` type1~4 분류와는 다름 — 코드 type은 임계값 묶음용, PDF TYPE은 라벨링 패턴 그룹용

| PDF TYPE | 그룹명 | 가전 |
|---------|--------|------|
| TYPE A | 전열 기기 | 헤어드라이기, 전기포트, 전기장판/담요, 온수매트, 인덕션, 전기다리미, 에어프라이어 |
| TYPE B | 비교적 계단형 패턴 | 선풍기, 진공청소기(유선), TV, 전자레인지, 컴퓨터 |
| TYPE C | 동작 코스가 다양한 가전 | 전기밥솥, 세탁기, 의류건조기, 식기세척기, 에어컨 |
| TYPE D | 상대적으로 오래 켜두는 가전 | 공기청정기, 제습기, 일반 냉장고, 김치냉장고, 무선공유기/셋톱박스 |

---

## 1. 가전별 임계값 표

| # | 채널 | 가전 | PDF TYPE | 대기전력 임계(W) | 활성 최소 시간 | Gap 시간 |
|---|------|------|----------|------------------|---------------|---------|
| 0 | ch02 | TV | B | 5 | 2분 | 1초 |
| 1 | ch03 | 전기포트 | A | 15 | 0.5초 | 1초 |
| 2 | ch04 | 선풍기 | B | 2 | 0.5초 | 1초 |
| 3 | ch05 | 의류건조기 | C | 5 | 1분 | 1분 |
| 4 | ch06 | 전기밥솥 | C | 5 | 기준 없음 | 5분 |
| 5 | ch07 | 식기세척기/건조기 | C | 10 | 1분 | 5분 |
| 6 | ch08 | 세탁기 | C | 10 | 1분 | 10초 |
| 7 | ch09 | 헤어드라이기 | A | 15 | 0.5초 | 1초 |
| 8 | ch10 | 에어프라이어 | A | 10 | 0.5초 | 1초 |
| 9 | ch11 | 진공청소기(유선) | B | 6 | 0.5초 | 1초 |
| 10 | ch12 | 전자레인지 | C | 10 | 10초 | 1초 |
| 11 | ch13 | 에어컨 | C | 2 | 1분 | 5분 |
| 12 | ch14 | 인덕션(전기레인지) | A | 15 | 0.5초 | 1초 |
| 13 | ch15 | 전기장판/담요 | A | 5 | 0.5초 | 1초 |
| 14 | ch16 | 온수매트 | A | 5 | 0.5초 | 1초 |
| 15 | ch17 | 제습기 | D | 3 | 30초 | 5분 |
| 16 | ch18 | 컴퓨터 | B | 5 | 10초 | 1분 |
| 17 | ch19 | 공기청정기 | D | 3 | 1분 | 1분 |
| 18 | ch20 | 전기다리미 | A | 15 | 기준 없음 | 1초 |
| 19 | ch21 | 일반 냉장고 | D | (Always-On) | 1시간 봉우리 | — |
| 20 | ch22 | 김치냉장고 | D | (Always-On) | 일반 냉장고와 동일 | — |
| 21 | ch23 | 무선공유기/셋톱박스 | D | 기본전력 + 0.5 | 2분 지속 | — |

> 채널 번호는 `'23년 활용가이드라인` 별첨 매핑 기준. 코드의 인덱스(0~21)는 `nilm-engine/src/classifier/label_map.py:APPLIANCE_LABELS` 순서.

---

## 2. 가전별 세부 룰

### TYPE A — 전열 기기

전열기로 비교적 단순한 패턴. 동작 시 다른 기기에 비해 상대적으로 높은 소비전력. ON 상태 명확.

#### 1. 헤어드라이기
- 대기전력 임계: **15W**, 활성 최소 0.5초, Gap 1초
- 분리기준: 대기전력(15W) 이하로 1초 이상 분리되는 모든 구간 분리하여 라벨링
- 특성: 명확한 ON/OFF 구간, 사용자에 따라 짧은 순간 ON/OFF 반복

#### 2. 전기포트
- 대기전력 임계: **15W**, 활성 최소 0.5초, Gap 1초
- 분리기준: 대기전력(15W) 이하로 1초 이상 분리되는 모든 구간 분리

#### 3. 전기장판/전기담요
- 대기전력 임계: **5W**, 활성 최소 0.5초, Gap 1초
- 분리기준: 대기전력(5W) 이하로 1초 이상 분리되는 모든 구간 분리
- **특수 룰**: 활성구간이 0.5초 미만이라도 다음 활성구간과의 간격이 분리기준(1초) 미만이고 전체 구간이 0.5초 이상인 경우 활성 유지로 간주

#### 4. 온수매트
- 대기전력 임계: **5W**, 활성 최소 0.5초, Gap 1초
- 분리기준: 대기전력(5W) 이하로 1초 이상 분리되는 모든 구간 분리
- 전기장판과 동일한 특수 룰 적용

#### 5. 인덕션(전기레인지)
- 대기전력 임계: **15W**, 활성 최소 0.5초, Gap 1초
- 분리기준: 대기전력(15W) 이하로 1초 이상 분리되는 모든 구간 분리
- 전기장판과 동일한 특수 룰 적용
- 특성: 인덕션 특성상 기기 활성 시 약 1000W 이상으로 급상승

#### 6. 전기다리미
- 대기전력 임계: **15W**, 활성 최소 시간 기준 없음, Gap 1초
- 분리기준: 대기전력(15W) 이하로 1초 이상 분리되는 모든 구간 분리
- 특성: 전열기기로서 ON 상태가 매우 명확하게 구분됨

#### 7. 에어프라이어
- 대기전력 임계: **10W**, 활성 최소 0.5초, Gap 1초
- 분리기준: 대기전력(10W) 이하로 1초 이상 분리되는 모든 구간 분리
- 특성: ON 상태 명확, 히팅-대기(바람순환) 패턴으로 구성. 10W 이하로 1초 이상 끊어지면 구분

---

### TYPE B — 비교적 계단형 패턴

#### 8. 선풍기
- 대기전력 임계: **2W**, 활성 최소 0.5초, Gap 1초
- 분리기준: 대기전력(2W) 이하로 1초 이상 분리되는 모든 구간 분리

#### 9. 진공청소기(유선)
- 대기전력 임계: **6W**, 활성 최소 0.5초, Gap 1초
- 분리기준: 대기전력(6W) 이하로 1초 이상 분리되는 모든 구간 분리
- 특성: 청소기 외 구동(On)-Off 구간이 명확

#### 10. TV
- 대기전력 임계: **5W**, 활성 최소 **2분** 이상 동작, Gap 1초
- 분리기준: 대기전력(5W) 이하로 1초 이상 분리되는 모든 구간 분리
- 특성: 기기마다 다른 변동 폭이 있어 일반적인 변동 등을 감안한 대기전력의 절대적/상대적 위치를 통해 판단
- **센서 동작 구간 제외 룰**: 대기 전력 이상으로 비슷한 전력 수준으로 가동되는 구간(센서 동작)은 라벨링 제외. 2분 이상 동작하는 경우에만 분리 기준(1초)에 따라 라벨링

#### 11. 전자레인지
- 대기전력 임계: **10W**, 활성 최소 10초 이상, Gap 1초
- 분리기준: 대기전력(10W) 이하로 1초 이상 분리되는 모든 구간 분리
- 특성: 동작 시 최소 1000W 이상 소모. 10W 이하 수준으로 끊어지는 구간은 센싱/내부 불빛 ON(기기 도어 Open/Close)/동작코스 종료

#### 12. 컴퓨터
- 대기전력 임계: **5W**, 활성 최소 10초 이상, Gap **1분**
- 분리기준: 대기전력(5W) 이하로 1분 이상 분리되는 모든 구간 분리
- 특성: "기기별 보기" 기능 활용, 다른 날짜 데이터를 종합하여 대기전력 범위 판단
- 비교적 부정확한 구분이 자주 발생, 대기전력이 5~10w 정도로 상대적으로 높은 경우도 있음. ON 상태에 비해서 확실히 낮음

---

### TYPE C — 동작 코스가 다양한 가전

#### 13. 전기밥솥
- 대기전력 임계: **5W**, 활성 최소 시간 기준 없음, Gap **5분**
- 분리기준: 대기전력(5W) 이하로 5분 이상 분리되는 모든 구간 분리
- 특성: 취사와 보온 상태 구분
  - 취사 상태: 매우 짧은 전력 기록 구간이 순간적으로 나타나거나, 긴 전력 기록 및 전력 수치 또한 들쭉날쭉. 코스에 따라 다양
  - 보온 상태: 비교적 유사한 패턴(지속시간, 전력 수치) 반복 기록
- 5분 이상 분리되지 않으면 하나의 구간으로 라벨링

#### 14. 세탁기
- 대기전력 임계: **10W**, 활성 최소 1분, Gap 10초
- 분리기준: 대기전력(10W) 이하로 10초 이상 분리되는 모든 구간 분리
- 특성: 동작 시 기록되는 전력 수치는 비교적 확실하게 구분됨. 세탁 코스에 따라 동작 중 휴지 구간이 다양. 10W 미만이라도 단일 구간으로 정의하는 경우도 있음. 세탁 코스에 따라 전력 패턴 매우 다양

#### 15. 의류건조기
- 대기전력 임계: **5W**, 활성 최소 1분, Gap 1분
- 분리기준: 대기전력(5W) 이하로 1분 이상 분리되는 모든 구간 분리
- 특성: 구동 시 명확하게 구분되는 소비전력이 기록됨. 건조 코스에 따라 시작 후 주기적으로 상대적으로 낮은 전력을 소비하는 구간 및 휴지 구간 모두 소비가 낮은 구간이 나타나기도 함

#### 16. 식기세척기
- 대기전력 임계: **10W**, 활성 최소 1분, Gap 5분
- 분리기준: 대기전력(10W) 이하로 5분 이상 분리되는 모든 구간 분리
- 특성: 활성 상태인 경우 비교적 부정확하게 구분됨. 코스에 따라 세척과 세척 사이의 휴지 구간이 길게 나타나는 경우가 자주 나타남. 5분 기준으로 분리하여 구분이 어려운 경우도 있음

#### 17. 에어컨
- 대기전력 임계: **2W**, 활성 최소 1분, Gap 5분
- 분리기준: 대기전력(2W) 이하로 5분 이상 분리되는 모든 구간 분리
- 특성: 실외기 기동 없이 송풍만 동작하는 상태이므로 낮은 소비전력이 사용된다고 기기가 활성된 상태로 판정할 수 없으며 — Always On 제품도 아님
- "기기별 보기" 활용: 대기전력으로 판단되는 짧은 2W 소비전력 이상 운전(예: 인버터 미풍 모드)은 활성 구간으로 라벨링

---

### TYPE D — 상대적으로 오래 켜두는 가전

#### 18. 공기청정기
- 대기전력 임계: **3W (상한)**, 활성 최소 1분, Gap 1분
- 분리기준: 대기전력(3W) 이하로 1분 이상 분리되는 모든 구간 분리
- 특성: 24시간 내내 전원이 켜져 있을 가능성이 높은 기기. "공기청정", "대기"같은 정형 모드도 측정 후 분리에 따라 "OFF"/"ON" 등 4가지 상태가 구분됨. 가전 자체가 켜져있어도 활성 상태가 아닐 수 있음
- "기기별 보기" 기능 통해 낮게 소비되는 전력 수준(공기청정기 OFF 상태가 아님) 및 대기상태 판단 후 활성 ON 상태에서만 라벨링
- **특수 룰**: 대기전력 상한 기준 3W → 기기별 보기 활용 후 대기전력 가장 낮은 소비전력 3W 이상이라면, 해당 가전의 3W를 대기전력으로 보고, 3W 이상 동작 구간을 활성으로 라벨링
- 보통 상태 동작 시 24시간 기준 전체 데이터가 3W 이상

#### 19. 제습기
- 대기전력 임계: **3W (상한)**, 활성 최소 30초, Gap 5분
- 분리기준: 대기전력(3W) 이하로 5분 이상 분리되는 모든 구간 분리
- 특성: 제습 코스 / "Fan만 동작" / "인버터 ON-OFF" 세가지 상태로 크게 구분됨
- "기기별 보기"를 활용해 세가지 상태 구분 후 전체 수준 판단. "Fan만 동작" 상태에서 단일 구간에 따라 라벨링 수행
- "인버터 ON-OFF" 상태로 구분되는 구간만 분리하여 라벨링 수행

#### 20. 일반 냉장고
- **Always-On 기기** (24시간 전체를 활성으로 판단)
- 라벨링 방법: 24시간 전체를 X축 스케일 기준으로 1시간 구간(TASK)을 별로 초기 설정 후 X축 스케일을 1시간으로 설정 후 주기로 설정. **X축 스케일 1시간으로 설정**, 1시간으로 설정 후 시간을 기준으로 봉우리(컴프레서 기동 사이클)를 일관되게 라벨링
- 가이드와 동일한 스케일을 설정 후 구분되는 모든 봉우리를 라벨링
- 시작점/끝점 판단 사례: 냉장고 시작 시 가동되는 Always On 기기의 경우, 각 기기별 패턴이 명확하게 분리되지 않을 수 있음

#### 21. 김치냉장고
- **일반 냉장고와 동일** 라벨링 룰 적용
- 특성: 일반 냉장고와 동일하게 1시간 단위 봉우리 라벨링

#### 22. 무선공유기/셋톱박스
- 대기전력 임계: **기본 사용 전력 + 0.5W 이상** (절대값 아님)
- 활성 최소 2분 지속
- **특수 룰**: 2분 이상 지속되고, 기본 사용 전력보다 0.5W 이상 상대적으로 높은 구간을 라벨링
- X축 2분 스케일까지 확대 후에도 여전히 구분되는 상승이면 라벨링
- 특성: 대부분 일정한(유사한) 수준의 전력을 소비하는 Always On 기기. 전체맵, "기기별 보기" 상 구분되며 2분 이상 지속되는 봉우리만 구간으로 라벨링

---

## 3. Python 코드 스니펫 (즉시 import 가능)

`nilm-engine/src/classifier/label_map.py` 또는 별도 파일에 추가:

```python
from __future__ import annotations
from typing import TypedDict, Literal


class LabelingCriteria(TypedDict):
    """AI Hub 71685 별첨4 가전기기별 라벨링 기준."""
    threshold_w: float | None      # 대기전력 임계값 (W). None = Always-On
    threshold_kind: Literal["absolute", "upper_bound", "relative", "always_on"]
    min_active_seconds: float | None   # 활성 최소 동작 시간 (초). None = 기준 없음
    gap_seconds: float | None          # Gap 분리 시간 (초). None = 적용 안 함
    pdf_group: Literal["A_heating", "B_step", "C_cycle", "D_always"]
    notes: str


# 22가전 라벨링 기준 — APPLIANCE_LABELS 순서와 일치 (인덱스 0~21)
APPLIANCE_LABELING: dict[str, LabelingCriteria] = {
    "TV": {
        "threshold_w": 5.0, "threshold_kind": "absolute",
        "min_active_seconds": 120.0, "gap_seconds": 1.0,
        "pdf_group": "B_step",
        "notes": "센서 동작 구간(대기전력 이상 비슷한 수준)은 제외. 2분 이상만 라벨링.",
    },
    "전기포트": {
        "threshold_w": 15.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "A_heating", "notes": "",
    },
    "선풍기": {
        "threshold_w": 2.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "B_step", "notes": "",
    },
    "의류건조기": {
        "threshold_w": 5.0, "threshold_kind": "absolute",
        "min_active_seconds": 60.0, "gap_seconds": 60.0,
        "pdf_group": "C_cycle",
        "notes": "코스에 따라 휴지 구간 다양 — Gap 1분으로 분리.",
    },
    "전기밥솥": {
        "threshold_w": 5.0, "threshold_kind": "absolute",
        "min_active_seconds": None, "gap_seconds": 300.0,
        "pdf_group": "C_cycle",
        "notes": "취사/보온 상태 구분. 5분 이상 분리되지 않으면 단일 구간.",
    },
    "식기세척기/건조기": {
        "threshold_w": 10.0, "threshold_kind": "absolute",
        "min_active_seconds": 60.0, "gap_seconds": 300.0,
        "pdf_group": "C_cycle", "notes": "",
    },
    "세탁기": {
        "threshold_w": 10.0, "threshold_kind": "absolute",
        "min_active_seconds": 60.0, "gap_seconds": 10.0,
        "pdf_group": "C_cycle",
        "notes": "코스 중간 휴지 시 단일 구간. 10W 미만이라도 단일 구간 가능.",
    },
    "헤어드라이기": {
        "threshold_w": 15.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "A_heating",
        "notes": "짧은 ON/OFF 반복 가능.",
    },
    "에어프라이어": {
        "threshold_w": 10.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "A_heating",
        "notes": "히팅-대기(바람순환) 패턴.",
    },
    "진공청소기(유선)": {
        "threshold_w": 6.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "B_step", "notes": "",
    },
    "전자레인지": {
        "threshold_w": 10.0, "threshold_kind": "absolute",
        "min_active_seconds": 10.0, "gap_seconds": 1.0,
        "pdf_group": "C_cycle",
        "notes": "동작 시 최소 1000W 이상. 10W 이하는 센싱/도어/종료 신호.",
    },
    "에어컨": {
        "threshold_w": 2.0, "threshold_kind": "absolute",
        "min_active_seconds": 60.0, "gap_seconds": 300.0,
        "pdf_group": "C_cycle",
        "notes": "인버터 미풍 모드(2W 이상)도 활성. Always-On 아님.",
    },
    "인덕션(전기레인지)": {
        "threshold_w": 15.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "A_heating",
        "notes": "활성 시 약 1000W 이상으로 급상승.",
    },
    "전기장판/담요": {
        "threshold_w": 5.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "A_heating",
        "notes": "0.5초 미만이라도 다음 활성과 1초 미만 간격이고 전체 0.5초 이상이면 활성 유지.",
    },
    "온수매트": {
        "threshold_w": 5.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "A_heating",
        "notes": "전기장판과 동일 룰.",
    },
    "제습기": {
        "threshold_w": 3.0, "threshold_kind": "upper_bound",
        "min_active_seconds": 30.0, "gap_seconds": 300.0,
        "pdf_group": "D_always",
        "notes": "대기전력 상한 3W. 제습/Fan만/인버터 ON-OFF 3가지 상태 구분.",
    },
    "컴퓨터": {
        "threshold_w": 5.0, "threshold_kind": "absolute",
        "min_active_seconds": 10.0, "gap_seconds": 60.0,
        "pdf_group": "B_step",
        "notes": "기기별 보기로 다른 날 데이터 종합해 대기전력 범위 판단. 대기 5~10W 가능.",
    },
    "공기청정기": {
        "threshold_w": 3.0, "threshold_kind": "upper_bound",
        "min_active_seconds": 60.0, "gap_seconds": 60.0,
        "pdf_group": "D_always",
        "notes": "대기전력 상한 3W. 24시간 ON 가능성 높지만 활성 상태 아닐 수 있음.",
    },
    "전기다리미": {
        "threshold_w": 15.0, "threshold_kind": "absolute",
        "min_active_seconds": None, "gap_seconds": 1.0,
        "pdf_group": "A_heating",
        "notes": "ON 상태 매우 명확.",
    },
    "일반 냉장고": {
        "threshold_w": None, "threshold_kind": "always_on",
        "min_active_seconds": 3600.0, "gap_seconds": None,
        "pdf_group": "D_always",
        "notes": "24시간 전체 활성. X축 1시간 스케일에서 컴프 사이클 봉우리 라벨링.",
    },
    "김치냉장고": {
        "threshold_w": None, "threshold_kind": "always_on",
        "min_active_seconds": 3600.0, "gap_seconds": None,
        "pdf_group": "D_always",
        "notes": "일반 냉장고와 동일.",
    },
    "무선공유기/셋톱박스": {
        "threshold_w": 0.5, "threshold_kind": "relative",
        "min_active_seconds": 120.0, "gap_seconds": None,
        "pdf_group": "D_always",
        "notes": "기본 사용 전력 + 0.5W 이상이 임계. X축 2분 스케일 확대 후에도 구분되는 상승만 라벨링.",
    },
}


def get_threshold(appliance_name: str) -> float:
    """가전별 ON 판정 임계값 (W). Always-On은 보수적으로 5W 반환."""
    crit = APPLIANCE_LABELING[appliance_name]
    if crit["threshold_kind"] == "always_on":
        return 5.0
    if crit["threshold_kind"] == "relative":
        # 상대값(기본전력+0.5W)은 가구별 baseline 학습 필요 — 1차 적용은 5W 절대값
        return 5.0
    assert crit["threshold_w"] is not None
    return crit["threshold_w"]


def get_min_active_samples(appliance_name: str, sampling_rate_hz: int = 30) -> int | None:
    """활성 최소 동작 시간을 샘플 수로 변환. None이면 시간 기준 없음."""
    sec = APPLIANCE_LABELING[appliance_name]["min_active_seconds"]
    return None if sec is None else int(sec * sampling_rate_hz)


def get_gap_samples(appliance_name: str, sampling_rate_hz: int = 30) -> int | None:
    """Gap 분리 시간을 샘플 수로 변환. None이면 적용 안 함."""
    sec = APPLIANCE_LABELING[appliance_name]["gap_seconds"]
    return None if sec is None else int(sec * sampling_rate_hz)
```

---

## 4. 코드 적용 시 주의

### 임계값 종류(`threshold_kind`)별 처리

| kind | 의미 | 코드 처리 |
|------|------|----------|
| `absolute` | 18가전. PDF 임계값을 그대로 사용 | `pred >= threshold_w` |
| `upper_bound` | 공기청정기·제습기. **대기전력 "상한"** — 가전별로 이 값 이하의 가장 낮은 안정 수준을 대기전력으로 보고, 그 위를 ON으로 판정. 단순 `pred >= 3W`도 1차 근사로 OK | `pred >= threshold_w` (1차 근사) |
| `always_on` | 냉장고 2종. ON/OFF 분류 자체가 부적합. 회귀로만 다루거나 항상 ON으로 고정 | 분류 헤드에서 제외 또는 `pred = True` 고정 |
| `relative` | 공유기/셋톱박스. 기본전력 + 0.5W. 가구별 baseline 학습 필요 | 1차는 5W 절대값. 정확도 한계 명시 |

### 활성 최소 시간 / Gap 시간 적용 시점

- **학습 라벨**: 이미 PDF 룰에 따라 라벨링 완료 (`build_active_mask`로 timestamp interval 그대로 사용)
- **모델 출력 후처리**: 짧은 ON spike 제거(min_active_seconds 미만) + 짧은 OFF gap 메우기(gap_seconds 미만) → 평가 시 PDF 라벨과 정합
- **윈도우 평가 (D 방안)**: 합의 폭을 가전별 `min_active_seconds`와 정렬:
  - 0.5초 가전(전열 7종, 선풍기, 진공청소기): center 15샘플(≈0.5s @ 30Hz) 합의로 충분
  - 1분 가전(에어컨·세탁기·건조기·식기세척기·공기청정기): 1분 = 1800샘플 → 현재 윈도우 1024(34초)로 부족. 다운샘플(1Hz) + 긴 윈도우 또는 별도 평가 윈도우 필요
  - 2분 가전(TV, 공유기): 2분 = 3600샘플 → 마찬가지

### 상태 분류 모델(향후 CNN+TDA) 학습 시

- 현재 라벨은 `active_inactive` 단일 boolean (ON/OFF 2-state)
- 일부 가전(전기밥솥: 취사/보온, 제습기: 제습/Fan/인버터, 공기청정기: 4가지 상태)은 **다중 상태**가 의미 있음
- 다중 상태 라벨은 PDF 라벨에 없으므로 별도 어노테이션 필요 — 우선 ON/OFF 2-state로 학습 후 확장

---

## 5. 참조

- 원문: `'23년 인공지능 학습용 데이터 활용 가이드라인 (전기 인프라 지능화를 위한 가전기기 전력 사용량 데이터) v1.0`, 별첨 4, pp.37~66
- 채널 매핑: 별첨 5 (디렉토리 구성 및 수량)
- 코드 위치: `nilm-engine/src/classifier/label_map.py:APPLIANCE_LABELS`, `_ON_THRESHOLD`
- 관련 검토 문서: `tmp/f1_fix_review.md` 0번 항목
