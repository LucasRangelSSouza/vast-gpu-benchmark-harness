# Cost per million tokens, monthly cost and capacity under an SLA.
# Original harness script, copied unmodified apart from this header. Comments inside may be in Portuguese.
"""M12: custo por milhao de tokens, custo mensal (24/6=624h, 24/7=730h) e capacidade sob SLA parametrizavel, a partir do MEDIDO.
Tudo derivado de data/derived/llm_summary.jsonl. USD_BRL datado em eco.common. Saida: data/derived/gpu_cost_benefit_ranked.csv"""
import csv
import json
import sys

sys.path.insert(0, ".")
from eco.common import DATA, USD_BRL  # noqa: E402

TTFT_P95_MAX = 3.0   # metas iniciais (spec 7.3), parametrizaveis
TPS_USER_MIN = 20.0
HOURS = {"24x6": 624, "24x7": 730}
ACTIVE_FRACTIONS = (0.02, 0.05, 0.10)
CURRENT_BRL_MONTH = 3500.0


def main():
    rows = [json.loads(line) for line in open(DATA / "derived" / "llm_summary.jsonl", encoding="utf-8")]
    groups = {}
    for r in rows:
        if r["thinking"]:
            continue
        groups.setdefault((r["gpu"], r["variant"], r["model"], r.get("dph_usd")), []).append(r)
    out = []
    for (gpu, variant, model, dph), rs in groups.items():
        rs.sort(key=lambda r: r["users"])
        ok_levels = [r for r in rs if r["errors"] == 0 and r.get("ttft_p95_short_s") is not None and r["ttft_p95_short_s"] <= TTFT_P95_MAX
                     and (r["decode_tps_per_user_p50"] or 0) >= TPS_USER_MIN]
        best = ok_levels[-1] if ok_levels else None
        peak = max(rs, key=lambda r: r["agg_out_tps"])
        row = {"gpu": gpu, "variant": variant, "model": model, "dph_usd": dph, "usd_brl": USD_BRL,
               "peak_agg_tps": peak["agg_out_tps"], "peak_at_users": peak["users"], "peak_ttft_p95": peak["ttft_p95_s"],
               "sla_users": best["users"] if best else 0, "sla_agg_tps": best["agg_out_tps"] if best else 0,
               "sla_decode_tps_user": best["decode_tps_per_user_p50"] if best else None, "sla_ttft_p95_short": best["ttft_p95_short_s"] if best else None, "sla_ttft_p95_long8k": best["ttft_p95_long8k_s"] if best else None,
               "passes_sla": bool(best), "measurement_kind": "measured+calculated"}
        for k, h in HOURS.items():
            row[f"month_brl_{k}"] = round((dph or 0) * h * USD_BRL, 0)
        tps = row["sla_agg_tps"] or row["peak_agg_tps"]
        row["usd_per_m_out_tokens_full_util"] = round((dph or 0) / (tps * 3600) * 1e6, 3) if tps else None
        for f in ACTIVE_FRACTIONS:
            row[f"clients_at_{int(f*100)}pct_active"] = int(row["sla_users"] / f) if row["sla_users"] else 0
        row["vs_current_3500"] = round(row["month_brl_24x7"] / CURRENT_BRL_MONTH, 2) if dph else None
        out.append(row)
    out.sort(key=lambda r: (not r["passes_sla"], r["month_brl_24x7"] or 1e9))
    p = DATA / "derived" / "gpu_cost_benefit_ranked.csv"
    keys = sorted({k for r in out for k in r}, key=lambda k: list(out[0]).index(k) if k in out[0] else 999)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(out)
    for r in out:
        print(f'{r["gpu"]:12} {r["variant"]:22} sla_users={r["sla_users"]:>3} sla_tps={r["sla_agg_tps"]:>7} peak={r["peak_agg_tps"]:>7}@{r["peak_at_users"]:<3} '
              f'R$/mes24x7={r["month_brl_24x7"]} $/Mtok={r["usd_per_m_out_tokens_full_util"]} ok={r["passes_sla"]}')


if __name__ == "__main__":
    main()
