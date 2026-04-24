# NILM 모델 비교 실험 결과

> **현재 환경**: AIHub 한국 가정 전력 데이터 30Hz · 3모델 주차별 추가학습 비교

---

## 환경 설정

| 항목 | 값 |
|------|-----|
| 데이터셋 | AIHub 한국 가정 전력 데이터 (30Hz) |
| train houses | house_067, 004, 024, 036, 042, 045, 068, 109 (8가구) |
| val house | house_011 |
| test house | house_007 |
| 입력 | ch01 active_power (aggregate) |
| window_size | 1024 samples (≈34초 @ 30Hz) |
| stride | 30 samples (1초) |
| optimizer | Adam |
| learning_rate | 1e-3 |
| batch_size | 32 |
| epochs | 50 (early stopping patience=10) |
| loss | MSE (validity mask 적용) |
| 평가 지표 | MAE (W) / RMSE (W) / SAE / R² |
| 학습 환경 | Google Colab T4 GPU |

---

## 실험 결과 요약

| EXP | 학습 기간 | 모델 | 종료 epoch | best_epoch | val_MAE | MAE (W) ↓ | RMSE (W) ↓ | SAE ↓ | R² ↑ | 비고 |
|-----|----------|------|-----------|-----------|---------|-----------|------------|-------|------|------|
| EXP1 | 09-22~09-28 | seq2point | | | | | | | | baseline ☆ |
| EXP1 | 09-22~09-28 | bert4nilm | | | | | | | | |
| EXP1 | 09-22~09-28 | cnn_tda   | | | | | | | | |
| EXP2 | 09-29~10-05 | seq2point | | | | | | | | |
| EXP2 | 09-29~10-05 | bert4nilm | | | | | | | | |
| EXP2 | 09-29~10-05 | cnn_tda   | | | | | | | | |
| EXP3 | 10-06~10-12 | seq2point | | | | | | | | |
| EXP3 | 10-06~10-12 | bert4nilm | | | | | | | | |
| EXP3 | 10-06~10-12 | cnn_tda   | | | | | | | | |
| EXP4 | 10-13~10-19 | seq2point | | | | | | | | |
| EXP4 | 10-13~10-19 | bert4nilm | | | | | | | | |
| EXP4 | 10-13~10-19 | cnn_tda   | | | | | | | | |

---

## EXP1 — 2023-09-22 ~ 2023-09-28 (scratch)

### seq2point

**날짜**: &nbsp;&nbsp;&nbsp; **종료 epoch**: &nbsp;&nbsp;&nbsp; **best_epoch**:

| best_epoch | val_MAE | MAE (W) | RMSE (W) | SAE | R² |
|-----------|---------|---------|----------|-----|----|
| | | | | | |

**메모**: - &nbsp;&nbsp;&nbsp; → 22종 개별: [appliance_breakdown.md](appliance_breakdown.md) EXP1/seq2point

---

### bert4nilm

**날짜**: &nbsp;&nbsp;&nbsp; **종료 epoch**: &nbsp;&nbsp;&nbsp; **best_epoch**:

| best_epoch | val_MAE | MAE (W) | RMSE (W) | SAE | R² |
|-----------|---------|---------|----------|-----|----|
| | | | | | |

**메모**: - &nbsp;&nbsp;&nbsp; → 22종 개별: [appliance_breakdown.md](appliance_breakdown.md) EXP1/bert4nilm

---

### cnn_tda

**날짜**: &nbsp;&nbsp;&nbsp; **종료 epoch**: &nbsp;&nbsp;&nbsp; **best_epoch**:

| best_epoch | val_MAE | MAE (W) | RMSE (W) | SAE | R² |
|-----------|---------|---------|----------|-----|----|
| | | | | | |

**메모**: - &nbsp;&nbsp;&nbsp; → 22종 개별: [appliance_breakdown.md](appliance_breakdown.md) EXP1/cnn_tda

---

## EXP2 — 2023-09-29 ~ 2023-10-05 (EXP1 이어받기)

### seq2point

**날짜**: &nbsp;&nbsp;&nbsp; **종료 epoch**: &nbsp;&nbsp;&nbsp; **best_epoch**:

| best_epoch | val_MAE | MAE (W) | RMSE (W) | SAE | R² | EXP1 대비 MAE 개선 |
|-----------|---------|---------|----------|-----|----|--------------------|
| | | | | | | |

**메모**: - &nbsp;&nbsp;&nbsp; → 22종 개별: [appliance_breakdown.md](appliance_breakdown.md) EXP2/seq2point

---

### bert4nilm

**날짜**: &nbsp;&nbsp;&nbsp; **종료 epoch**: &nbsp;&nbsp;&nbsp; **best_epoch**:

| best_epoch | val_MAE | MAE (W) | RMSE (W) | SAE | R² | EXP1 대비 MAE 개선 |
|-----------|---------|---------|----------|-----|----|--------------------|
| | | | | | | |

**메모**: - &nbsp;&nbsp;&nbsp; → 22종 개별: [appliance_breakdown.md](appliance_breakdown.md) EXP2/bert4nilm

---

### cnn_tda

**날짜**: &nbsp;&nbsp;&nbsp; **종료 epoch**: &nbsp;&nbsp;&nbsp; **best_epoch**:

| best_epoch | val_MAE | MAE (W) | RMSE (W) | SAE | R² | EXP1 대비 MAE 개선 |
|-----------|---------|---------|----------|-----|----|--------------------|
| | | | | | | |

**메모**: - &nbsp;&nbsp;&nbsp; → 22종 개별: [appliance_breakdown.md](appliance_breakdown.md) EXP2/cnn_tda

---

## EXP3 — 2023-10-06 ~ 2023-10-12 (EXP2 이어받기)

### seq2point

**날짜**: &nbsp;&nbsp;&nbsp; **종료 epoch**: &nbsp;&nbsp;&nbsp; **best_epoch**:

| best_epoch | val_MAE | MAE (W) | RMSE (W) | SAE | R² | EXP2 대비 MAE 개선 |
|-----------|---------|---------|----------|-----|----|--------------------|
| | | | | | | |

**메모**: - &nbsp;&nbsp;&nbsp; → 22종 개별: [appliance_breakdown.md](appliance_breakdown.md) EXP3/seq2point

---

### bert4nilm

**날짜**: &nbsp;&nbsp;&nbsp; **종료 epoch**: &nbsp;&nbsp;&nbsp; **best_epoch**:

| best_epoch | val_MAE | MAE (W) | RMSE (W) | SAE | R² | EXP2 대비 MAE 개선 |
|-----------|---------|---------|----------|-----|----|--------------------|
| | | | | | | |

**메모**: - &nbsp;&nbsp;&nbsp; → 22종 개별: [appliance_breakdown.md](appliance_breakdown.md) EXP3/bert4nilm

---

### cnn_tda

**날짜**: &nbsp;&nbsp;&nbsp; **종료 epoch**: &nbsp;&nbsp;&nbsp; **best_epoch**:

| best_epoch | val_MAE | MAE (W) | RMSE (W) | SAE | R² | EXP2 대비 MAE 개선 |
|-----------|---------|---------|----------|-----|----|--------------------|
| | | | | | | |

**메모**: - &nbsp;&nbsp;&nbsp; → 22종 개별: [appliance_breakdown.md](appliance_breakdown.md) EXP3/cnn_tda

---

## EXP4 — 2023-10-13 ~ 2023-10-19 (EXP3 이어받기)

### seq2point

**날짜**: &nbsp;&nbsp;&nbsp; **종료 epoch**: &nbsp;&nbsp;&nbsp; **best_epoch**:

| best_epoch | val_MAE | MAE (W) | RMSE (W) | SAE | R² | EXP3 대비 MAE 개선 |
|-----------|---------|---------|----------|-----|----|--------------------|
| | | | | | | |

**메모**: - &nbsp;&nbsp;&nbsp; → 22종 개별: [appliance_breakdown.md](appliance_breakdown.md) EXP4/seq2point

---

### bert4nilm

**날짜**: &nbsp;&nbsp;&nbsp; **종료 epoch**: &nbsp;&nbsp;&nbsp; **best_epoch**:

| best_epoch | val_MAE | MAE (W) | RMSE (W) | SAE | R² | EXP3 대비 MAE 개선 |
|-----------|---------|---------|----------|-----|----|--------------------|
| | | | | | | |

**메모**: - &nbsp;&nbsp;&nbsp; → 22종 개별: [appliance_breakdown.md](appliance_breakdown.md) EXP4/bert4nilm

---

### cnn_tda

**날짜**: &nbsp;&nbsp;&nbsp; **종료 epoch**: &nbsp;&nbsp;&nbsp; **best_epoch**:

| best_epoch | val_MAE | MAE (W) | RMSE (W) | SAE | R² | EXP3 대비 MAE 개선 |
|-----------|---------|---------|----------|-----|----|--------------------|
| | | | | | | |

**메모**: - &nbsp;&nbsp;&nbsp; → 22종 개별: [appliance_breakdown.md](appliance_breakdown.md) EXP4/cnn_tda

---

## 포화점 판단

| 구간 | seq2point 개선 | bert4nilm 개선 | cnn_tda 개선 | 평균 개선 | 판정 |
|------|---------------|----------------|--------------|----------|------|
| EXP1→EXP2 | | | | | |
| EXP2→EXP3 | | | | | |
| EXP3→EXP4 | | | | | |

> 평균 개선율 < 5% 이면 포화로 판단, 학습 중단.

---

## 최종 선정 모델

| 항목 | 값 |
|------|-----|
| EXP | |
| 모델 | |
| best_epoch / 종료 epoch | |
| MAE (W) | |
| RMSE (W) | |
| SAE | |
| R² | |
| 베이스라인(미학습) 대비 | |
