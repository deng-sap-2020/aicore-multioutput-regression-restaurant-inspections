# Training Logic

## Overview

The model predicts two numeric scores simultaneously from a restaurant inspection record:

| Target | Description |
|---|---|
| `inspection_score` | Overall inspection score |
| `lowest_score` | Lowest individual violation score |

This is a **multi-output regression** problem — a single LightGBM regressor is wrapped in scikit-learn's `MultiOutputRegressor` to produce both predictions in one pass.

---

## Pipeline

### 1. Load data (`preprocess`)

`inspections.csv` is read from `DATA_SOURCE`. The dataset contains 11,654 records.

### 2. Scale targets

Both target columns (`inspection_score`, `lowest_score`) are standardised with `StandardScaler` (zero mean, unit variance). The fitted scaler is saved to `OUTPUT_PATH/standard_scaler.pickle` so the serving layer can inverse-transform predictions back to the original scale.

### 3. Encode categorical features

`business_postal_code` is ordinally encoded — each unique postal code is assigned an integer. Unknown codes seen at inference time get the value `-1`. The fitted encoder is saved to `OUTPUT_PATH/ord-enc.pickle`.

### 4. Embed text features

`violation_description` is embedded using the sentence-transformer model `multi-qa-MiniLM-L6-cos-v1`, which produces a 384-dimensional dense vector per record. Each dimension becomes its own column (`violation_description_0` … `violation_description_383`).

This step is the most expensive — encoding 11k+ descriptions sequentially takes several minutes on CPU.

### 5. Train

`MultiOutputRegressor(LGBMRegressor())` is fit on the combined feature matrix (1 categorical column + 384 embedding columns). The trained model is saved to `OUTPUT_PATH/inspection-mo-regression-model.pickle`.

### 6. Preprocessing cache (`cache_preprocessing`)

A flag `cache_preprocessing = False` exists to skip re-embedding on subsequent runs by saving/loading `inspections_preprocessed.csv`. It is currently disabled.

---

## Artifacts produced

| File | Used by |
|---|---|
| `inspection-mo-regression-model.pickle` | `serve.py` — makes predictions |
| `ord-enc.pickle` | `serve.py` — encodes postal code at inference |
| `standard_scaler.pickle` | `serve.py` — inverse-transforms predicted scores |

---

## Interpreting validation RMSE

The targets are **StandardScaler-normalized** before training (zero mean, unit variance), so RMSE values are in **standard deviation units**, not original score units.

A naive model that always predicts the mean would score RMSE = 1.0. The approximated R² is `1 - RMSE²` (valid because the scaled variance = 1):

| Target | RMSE | Approx. R² | Interpretation |
|---|---|---|---|
| `inspection_score` | 0.30 | ~0.91 | Errors are 30% of a std dev — strong fit |
| `lowest_score` | 0.60 | ~0.64 | Errors are 60% of a std dev — moderate fit |

`lowest_score` is roughly twice as hard to predict — the overall inspection score is an aggregate that smooths variation, while the lowest individual violation score depends on edge cases less captured by postal code and violation description alone.

To convert RMSE back to **original score units**, multiply by the standard deviation of each column in the raw data:

```python
print(inspections[["inspection_score", "lowest_score"]].std())
# real_world_error = RMSE × std
```

---

## Suggestions

### 1. Enable the preprocessing cache for local iteration
Set `cache_preprocessing = True` to save the embedded DataFrame after the first run. Re-runs skip the slow sentence-transformer step entirely. The cached CSV is ~35 MB for this dataset size.

### 2. Batch-encode embeddings
`sentence_transformer.encode()` is called with a plain Python list, which uses a default batch size of 32. Passing `batch_size=256` (or higher, depending on available RAM) cuts encoding time significantly:
```python
embeddings = sentence_transformer.encode(feature_values, batch_size=256, show_progress_bar=True)
```

### 3. Tune LightGBM hyperparameters
`LGBMRegressor()` uses all defaults. Key parameters worth tuning:
- `n_estimators` (default 100) — more trees generally improve accuracy at the cost of training time
- `num_leaves` (default 31) — controls tree complexity
- `learning_rate` (default 0.1) — lower rates with more trees often generalise better

A simple starting point:
```python
regressor = lgb.LGBMRegressor(n_estimators=500, num_leaves=63, learning_rate=0.05)
```

### 4. ~~Add evaluation metrics~~ ✓ applied
The `train` function now splits 80/20, fits on the training split, and logs validation RMSE per target using `np.sqrt(mean_squared_error(...))` (version-safe across scikit-learn 1.1–1.6).

### 5. ~~Fix the sentence-transformer cache path~~ ✓ applied
The model cache now resolves to a project-relative `.cache/` directory via `Path(__file__).parents[2] / ".cache"`, working correctly both locally and inside Docker (`/app/src/train.py` → two levels up → `/app/.cache`).
