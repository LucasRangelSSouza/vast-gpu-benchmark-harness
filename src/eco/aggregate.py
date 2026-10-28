# Aggregates raw per-request logs into the derived summary tables.
# Original harness script, copied unmodified apart from this header. Comments inside may be in Portuguese.
"""Agrega o bruto em tabelas derivadas (regeneraveis): data/derived/llm_summary.jsonl, libs_summary.jsonl.
Mapeia cada requests.jsonl para (GPU, preco/h, variante) via manifest da lease; GB10 e baseline local."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from eco.analyze_llm import analyze  # noqa: E402
from eco.common import DATA, RAW  # noqa: E402

DER = DATA / "derived"
DER.mkdir(parents=True, exist_ok=True)


def lease_info(run_id):
    p = RAW / "leases" / run_id / "manifest.json"
    if p.exists():
        m = json.loads(p.read_text(encoding="utf-8"))
        o = m.get("offer_snapshot", {})
        return {"gpu": o.get("gpu_name"), "dph_usd": o.get("dph_total"), "vram_gb": round(o.get("gpu_ram", 0) / 1024, 1),
                "geo": o.get("geolocation"), "host_reliability": o.get("reliability2")}
    return {}


def llm_rows():
    out = []
    for f in list((RAW / "sessions").glob("**/llm_*/requests.jsonl")) + list((RAW / "sessions").glob("**/b9speed/requests.jsonl")) + list((RAW / "sessions").glob("**/engine_*/requests.jsonl")):
        run_id = f.parts[f.parts.index("sessions") + 1]
        variant = f.parent.name.replace("llm_", "")
        model = "qwen3.5-9b" if f.parent.name in ("b9speed", "engine_vllm", "engine_sglang", "llm_q9_bf16") else "qwen3.8-27b-abliterated"
        if f.parent.name in ("llm_q9_bf16", "llm_q9bf16", "llm_q9fp8"):
            model, variant = "qwen3.5-9b", "qwen9b_bf16"
        elif f.parent.name == "llm_fp8_27":
            variant = "fp8_plain"
        elif f.parent.name == "llm_awq27":
            variant = "plain"
        info = lease_info(run_id)
        for a in analyze(f):
            out.append({"run_id": run_id, "variant": variant, "model": model, **info, **a, "source": str(f), "measurement_kind": "measured"})
    for f in (RAW / "gb10").glob("*/requests.jsonl"):
        name = f.parent.name
        variant = name.replace("gb10_", "")
        for a in analyze(f):
            out.append({"run_id": "gb10", "variant": variant, "model": "qwen3.5-9b" if "9b" in name else "qwen3.8-27b-abliterated", "gpu": "GB10",
                        "dph_usd": 0.4489, "vram_gb": 121, "geo": "Serbia, RS", **a, "source": str(f), "measurement_kind": "measured"})
    return out


def libs_rows():
    out = []
    for f in list((RAW / "libs").glob("**/libs.jsonl")) + list((RAW / "sessions").glob("**/libs/libs.jsonl")):
        parts = f.parts
        run_id = parts[parts.index("libs") + 1] if "libs" in parts and parts[parts.index("libs") + 1].startswith("2026") else parts[parts.index("sessions") + 1]
        info = lease_info(run_id)
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            r.update({"run_id": run_id, **{k: v for k, v in info.items() if k not in r}})
            out.append(r)
    return out


if __name__ == "__main__":
    for name, rows in (("llm_summary", llm_rows()), ("libs_summary", libs_rows())):
        p = DER / f"{name}.jsonl"
        seen, uniq = set(), []
        for r in rows:  # dedupe (a mesma sessao e baixada varias vezes)
            k = json.dumps({a: b for a, b in r.items() if a not in ("t_wall", "source")}, sort_keys=True, default=str)
            if k not in seen:
                seen.add(k)
                uniq.append(r)
        p.write_text("\n".join(json.dumps(r, default=str) for r in uniq) + "\n", encoding="utf-8")
        print(name, len(uniq), "linhas ->", p)
