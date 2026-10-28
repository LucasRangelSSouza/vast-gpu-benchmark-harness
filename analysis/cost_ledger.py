"""Cost of the campaign: rental by GPU, cumulative spend, status mix and the gap between hourly rental and total spend."""
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import BLUE, DATA, GREEN, GREY, ORANGE, gpu_name, read, save_fig, save_table, update_summary

led = read("lease_ledger.csv").drop(columns=["geo"], errors="ignore")
led["gpu"] = led.gpu.fillna("unknown").map(gpu_name)
led["started"] = pd.to_datetime(led.started_utc)
tot = json.loads((DATA / "campaign_totals.json").read_text())

by = led.groupby("gpu").agg(rentals=("est_cost_usd", "size"), hours=("created_to_destroyed_h", "sum"), usd=("est_cost_usd", "sum")).sort_values("usd", ascending=False)
by["usd_per_hour"] = by.usd / by.hours.replace(0, np.nan)
save_table(by.round(3), "rental_by_gpu")

status = led.groupby("status").agg(rows=("est_cost_usd", "size"), usd=("est_cost_usd", "sum"), hours=("created_to_destroyed_h", "sum"))
status["share_usd"] = status.usd / status.usd.sum()
save_table(status.round(3), "rental_by_status")

fig, axes = plt.subplots(1, 3, figsize=(14, 4))
b = by[by.usd > 0]
axes[0].barh(b.index[::-1], b.usd[::-1], color=BLUE)
for i, v in enumerate(b.usd[::-1]):
    axes[0].text(v, i, f" {v:.2f}", va="center", fontsize=8)
axes[0].set_xlabel("Estimated rental (US$)"); axes[0].set_title("Rental by GPU model")
cum = led.dropna(subset=["started"]).sort_values("started")
cum["cum_usd"] = cum.est_cost_usd.cumsum()
axes[1].step(cum.started, cum.cum_usd, where="post", color=ORANGE)
axes[1].set_title("Cumulative hourly-rental estimate"); axes[1].tick_params(axis="x", rotation=30)
axes[2].bar(["hourly rental\nestimate", "reconciled\nspend"], [tot["estimated_hourly_rental_usd"], tot["reconciled_total_usd"]], color=[BLUE, GREEN])
for i, v in enumerate([tot["estimated_hourly_rental_usd"], tot["reconciled_total_usd"]]):
    axes[2].text(i, v + 0.5, f"{v:.2f}", ha="center")
axes[2].set_title("What the hourly rate does not see")
save_fig(fig, "cost_ledger.png")

update_summary({
    "ledger_rows": len(led), "ledger_hours": led.created_to_destroyed_h.sum(), "ledger_usd": led.est_cost_usd.sum(),
    "reconciled_total_usd": tot["reconciled_total_usd"], "hourly_estimate_usd": tot["estimated_hourly_rental_usd"],
    "reconciled_over_hourly": tot["reconciled_total_usd"] / tot["estimated_hourly_rental_usd"],
    "partial_share_usd": status.loc["partial", "share_usd"] if "partial" in status.index else 0.0,
    "most_expensive_gpu": by.index[0], "most_expensive_gpu_usd": by.usd.iloc[0],
    "median_hourly_price": led.dph_usd[led.dph_usd > 0].median(),
})
print(by.round(2).head(8))
