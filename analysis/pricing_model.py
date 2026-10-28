"""From a benchmark to a price per unit: utilization ceilings (Erlang C) and the price formula, using the measured service time."""
import matplotlib.pyplot as plt
import numpy as np
from benchkit import max_utilization, p95_wait, unit_price, usd_per_million_tokens
from common import BLUE, GREEN, ORANGE, read, save_fig, save_table, update_summary

q = read("queue_simulation.csv")
service = float(q.service_p50.iloc[0])
mu = 1 / service

slots = [1, 2, 4, 8, 16, 32, 64, 128]
ceil = {c: max_utilization(c, service, 1.0) for c in slots}
tab = __import__("pandas").DataFrame({"slots": slots, "max_utilization": [ceil[c] for c in slots]}).set_index("slots")
tab["price_multiplier"] = 1 / tab.max_utilization
save_table(tab.round(3), "utilization_ceiling")

llm = read("llm_serving.csv")
llm = llm[llm.valid_run & ~llm.thinking.astype(bool)]
awq = llm[(llm.variant == "plain") & (llm.gpu == "RTX 5090") & (llm.ttft_p95_short_s <= 3)]
cost_full = min(usd_per_million_tokens(r.dph_usd, r.agg_out_tps) for r in awq.itertuples())

fig, axes = plt.subplots(1, 2, figsize=(11, 3.9))
for c in (1, 8, 32, 64):
    rr = np.arange(0.02, 0.98, 0.01)
    axes[0].plot(rr, [min(p95_wait(c, r, mu), 30) for r in rr], label=f"{c} slot{'s' if c > 1 else ''}")
axes[0].axhline(1, ls="--", color="grey"); axes[0].set_ylim(0, 12)
axes[0].set_xlabel("Utilization"); axes[0].set_ylabel("95th percentile wait (s)"); axes[0].legend(frameon=False)
us = np.arange(0.1, 0.91, 0.05)
for m, col in ((0.2, GREEN), (0.4, BLUE), (0.6, ORANGE)):
    axes[1].plot(us, [unit_price(cost_full, u, margin=m) for u in us], color=col, label=f"margin {m:.0%}")
axes[1].set_xlabel("Utilization"); axes[1].set_ylabel("US$ per million output tokens"); axes[1].set_yscale("log"); axes[1].legend(frameon=False)
axes[1].set_title(f"Price for a card whose cost at full load is US${cost_full:.2f}", fontsize=9)
save_fig(fig, "pricing_model.png")

update_summary({"service_time_median_s": service, "util_ceiling_1_slot": ceil[1], "util_ceiling_8_slots": ceil[8], "util_ceiling_32_slots": ceil[32],
                "cost_full_load_5090_usd_per_m": cost_full, "price_5090_pool32": unit_price(cost_full, ceil[32])})
print(tab.round(3))
