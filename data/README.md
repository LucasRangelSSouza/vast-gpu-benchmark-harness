# Data

Curated CSV files from the campaign (public Kaggle dataset `lucasrangelss/gpu-ai-benchmark-campaign-2026`). One row per measured run or attempt; the columns are described in the dataset page. Host locations and instance identifiers were removed.

- `lease_ledger.csv`: one row per rented instance: hours, hourly price, estimated cost, ready time (host location removed)
- `rental_cost_by_gpu.csv`: rental rolled up by GPU model
- `campaign_totals.json`: reconciled campaign totals
- `queue_simulation.csv`: queue simulation fed by 223 measured request times
- `llm_serving.csv`: load-test rows used to price a million output tokens
