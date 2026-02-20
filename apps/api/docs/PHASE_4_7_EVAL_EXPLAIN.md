# Phase 4.7: Evaluation Metrics + Explainability

Standardized `meta.eval` and `meta.explain` fields for predictive endpoints.

## meta.eval

Evaluation metrics schema (backtest-style).

### Schema

```json
{
  "metrics": {
    "mae": 1.23,
    "mape": 15.5,
    "rmse": 1.8,
    "smape": 12.0
  },
  "test_points": 20,
  "train_points": 80,
  "horizon": 24,
  "granularity": "hour",
  "points_used": 100,
  "window": 14,
  "backtest_window": {
    "start_ts": "2024-01-01T00:00:00",
    "end_ts": "2024-01-31T23:59:59"
  }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| metrics | object | Standard metrics (mae, mape, rmse, smape when available) |
| test_points | int | Number of holdout points used for evaluation |
| train_points | int | Number of training points |
| horizon | int | Forecast horizon (e.g. 24 hours) |
| granularity | string | "hour" or "day" |
| points_used | int | Points used in computation (e.g. trends) |
| window | int | Window size (e.g. trends) |
| backtest_window | object | Optional start_ts/end_ts for backtest period |

### Metrics

- **MAE** (Mean Absolute Error): Average |predicted - actual|. Lower is better.
- **MAPE** (Mean Absolute Percentage Error): Average of |predicted - actual| / max(actual, 1) × 100.
- **RMSE** (Root Mean Squared Error): sqrt(mean((predicted - actual)²)). Penalizes large errors more.
- **SMAPE** (Symmetric MAPE): 100 × mean(2|predicted - actual| / (|predicted| + |actual|)).

### Example (risk)

```json
{
  "meta": {
    "eval": {
      "metrics": {"mae": 2.1, "mape": 18.3},
      "test_points": 15,
      "train_points": 60,
      "horizon": 24,
      "granularity": "hour"
    }
  }
}
```

---

## meta.explain

Explainability schema (linear coefficients).

### Schema

```json
{
  "features": [
    {
      "name": "Hour = 23",
      "raw_feature": "preprocess__hour__x1_23.0",
      "effect": "increase",
      "coef": 0.42,
      "weight": 0.42
    },
    {
      "name": "Day of week = Wednesday",
      "raw_feature": "preprocess__dow__x0_2.0",
      "effect": "decrease",
      "coef": -0.15,
      "weight": 0.15
    }
  ],
  "method": "linear_coefficients",
  "notes": "Poisson regression feature effects (higher weight = stronger impact)."
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| features | array | List of feature effects, sorted by weight (desc) |
| method | string | "linear_coefficients" |
| notes | string | Short description |

### Feature item

| Field | Type | Description |
|-------|------|-------------|
| name | string | Human-readable label |
| raw_feature | string | Original encoded feature name |
| effect | string | "increase" or "decrease" |
| coef | number | Signed coefficient |
| weight | number | abs(coef) for display ordering |

### Frontend display

- Render `features` as a bar chart or list, sorted by `weight`.
- Use `name` for labels; `effect` for color (e.g. green = increase, red = decrease).
- Show `weight` as bar length or prominence.
- `raw_feature` is available for debugging.

---

## Endpoint coverage

| Endpoint | meta.eval | meta.explain |
|----------|-----------|--------------|
| /predict/risk | Backtest metrics when available | Formatted coefficients |
| /predict/forecast | null | null |
| /predict/trends | points_used, window | null |
| /predict/timeseries | omitted | omitted |
