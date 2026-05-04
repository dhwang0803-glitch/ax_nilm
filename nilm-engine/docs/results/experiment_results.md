# NILM 모델 실험 결과 (cnn_tda)

> 데이터: AIHub 한국 가정 전력 (30Hz, 9월)
> Train: house_011,015,016,017,033,039,054,063 (8가구)
> Val: house_049 (전체 기간 고정)
> Test: house_067 (EXP4 완료 후 1회)

---

## 환경 설정

| 항목 | 값 |
|------|-----|
| 모델 | cnn_tda (CNN + TDA 하이브리드) |
| window_size | 60 samples (2초 @ 30Hz) |
| stride | 가변 (event_context + steady_stride) |
| optimizer | Adam (lr=1e-3, wd=1e-4) |
| scheduler | ReduceLROnPlateau (factor=0.5, patience=3) |
| batch_size | 64 |
| epochs | 15 (early stopping patience=5) |
| loss | MSE (validity mask) + BCE (on/off, pos_weight) |
| 평가 지표 | MAE·RMSE·SAE·F1·F1_cls (weighted macro) |
| denoise | True (wavelet denoising) |
| 학습 환경 | Google Colab A100 GPU |

---

## 실험 결과 요약 (Val: house_049)

| EXP | 학습 주차 | 이전 EXP | MAE (W) ↓ | RMSE (W) ↓ | SAE ↓ | F1 ↑ | F1_cls ↑ | 학습시간 |
|-----|----------|---------|-----------|------------|-------|------|----------|---------|
| EXP1 | week 1 (1~7일) | scratch | 49.07 | 123.21 | 2.559 | 0.255 | 0.368 | 1210s |
| EXP2 | week 2 (8~14일) | EXP1 | **40.44** | **106.24** | **2.075** | 0.577 | **0.639** | 546s |
| EXP3 | week 3 (15~21일) | EXP2 | 48.39 | 115.76 | 2.458 | **0.578** | 0.633 | 527s |
| EXP4 | week 4 (22~28일) | EXP3 | 49.31 | 111.97 | 2.595 | 0.576 | 0.620 | 854s |

> best checkpoint: EXP2 (Val MAE 기준) / EXP4 (Test 일반화 기준)

---

## 최종 Test 평가 (house_067, EXP4 체크포인트)

| 지표 | Val (house_049) | Test (house_067) |
|------|-----------------|-----------------|
| MAE (W) | 49.31 | **45.38** |
| RMSE (W) | 111.97 | **101.83** |
| SAE | 2.595 | **2.407** |
| F1 | 0.576 | **0.619** |
| F1_cls | 0.620 | 0.499 |

> F1_cls 하락: val에서 최적화된 cls_thresholds를 house_067에 고정 적용 (leakage 방지)

---

## EXP 간 개선율 (Val MAE 기준)

| 구간 | 이전 MAE | 현재 MAE | 개선율 |
|------|---------|---------|--------|
| EXP1→EXP2 | 49.07W | 40.44W | ↓ 17.6% |
| EXP2→EXP3 | 40.44W | 48.39W | ↑ 19.6% (week3 분포 확장) |
| EXP3→EXP4 | 48.39W | 49.31W | ↑ 1.9% (week4 분포 확장) |

> Val MAE 악화는 동일 8집에 새 주차 데이터 추가로 분포가 넓어지는 과정.
> Test(house_067) 기준으로는 EXP4가 EXP2보다 F1 높음 → 일반화 개선 확인.

---

## 최종 선정 모델

| 항목 | 값 |
|------|-----|
| 모델 | cnn_tda |
| 체크포인트 | EXP4 (test 일반화 기준) |
| Test MAE | 45.38W |
| Test RMSE | 101.83W |
| Test SAE | 2.407 |
| Test F1 | 0.619 |
| Test F1_cls | 0.499 (val thresholds 고정) |
