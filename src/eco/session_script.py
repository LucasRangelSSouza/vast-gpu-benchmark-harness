# Offer filter and launcher for a generic session (reliability, bandwidth, CUDA, disk filters).
# Original harness script, copied unmodified apart from this header. Comments inside may be in Portuguese.
"""Sessao paga generica: python -m eco.session_script <gpu> <tag> <script.sh> <ttl_min> [image] [min_cuda]"""
import os, sys, time, traceback, json
sys.path.insert(0, ".")
from eco import vast
from eco.common import RAW, ROOT
from eco.lease import Lease

gpu, tag, script, ttl = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
image = sys.argv[5] if len(sys.argv) > 5 else "vastai/vllm:v0.30.0-cuda-13.0"
min_cuda = float(sys.argv[6]) if len(sys.argv) > 6 else 13.0
BAD = RAW / "leases" / "bad_hosts.json"
bad = set(json.load(open(BAD))) if (BAD.exists() and not os.environ.get("IGNORE_BAD")) else set()
cands = [o for o in vast.search(min_vram_gb=0, max_dph=3.5, gpu_names={"RTX PRO 6000": ["RTX PRO 6000 WS", "RTX PRO 6000 S"]}.get(gpu, [gpu]), limit=200)
         if o.get("reliability2", 0) >= 0.97 and o.get("inet_down", 0) >= 400 and o.get("cuda_max_good", 0) >= min_cuda and o.get("disk_space", 0) >= float(os.environ.get("MIN_DISK", 150))
         and o.get("machine_id") not in bad and "China" not in str(o.get("geolocation"))]
# HuggingFace/GitHub a 14-22 MB/s em hosts asiaticos reprovaram 5x seguidas: preferir America/Europa (mais rapido e menos tentativas pagas)
WEST = (", US", ", CA", ", DE", ", FR", ", NL", ", GB", ", PL", ", CZ", ", SE", ", FI", ", NO", ", ES", ", IT", ", BG", ", RO", ", LT", ", LV", ", IS", ", IE", ", BR", ", AT", ", CH", ", DK", ", BE")
# Vast COBRA download por host (0 a US$ 41/TB!): uma 5090 a US$ 40/TB gastou US$ 0,67 em 5 min. Custo estimado = hora + GB baixados x US$/TB.
DL_GB = float(os.environ.get("DL_GB", 150)); HRS = ttl / 60 * 0.85
cands = [o for o in cands if o.get("internet_down_cost_per_tb", 0) <= float(os.environ.get("MAX_DL_USD_TB", 10))]
for o in cands:
    o["_est"] = o["dph_total"] * HRS + DL_GB / 1000 * o.get("internet_down_cost_per_tb", 0)
cands.sort(key=lambda o: (0 if any(str(o.get("geolocation") or "").endswith(w) for w in WEST) else 1, o["_est"]))
print("candidatas (custo estimado US$):", [(o["id"], round(o["_est"], 2), o.get("geolocation")) for o in cands[:6]], flush=True)
L = None
for offer in cands[:8]:
    print("tentando", offer["id"], offer["gpu_name"], offer["dph_total"], offer.get("geolocation"), flush=True)
    L = Lease(tag, offer, image, int(os.environ.get("DISK_GB", 120)), ttl)
    if L.open():
        if os.environ.get("PREFLIGHT", "1") == "1":
            pf = L.sh("for u in https://github.com https://huggingface.co; do curl -s -m 15 -o /dev/null -w '%{http_code} ' $u; done; echo; curl -sL -m 60 -r 0-199999999 -o /dev/null -w 'SPEED %{speed_download}\n' https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/resolve/main/model.safetensors; df -BG / | tail -1", 120)
            txt = pf[1] if pf else ""
            L.log.write({"event": "preflight", "out": txt[-300:]})
            import re
            m = re.search(r"SPEED ([0-9.]+)", txt)
            ok = ("000" not in txt.split("SPEED")[0]) and m and float(m.group(1)) >= float(os.environ.get("MIN_SPEED_MBS", 40)) * 1e6
            if not ok:
                print("preflight reprovou:", txt[-200:].replace(chr(10), " "), flush=True)
                bad.add(offer.get("machine_id")); json.dump(sorted(b for b in bad if b), open(BAD, "w"))
                L.close("preflight_failed"); L = None
                continue
        break
    if L.iid is not None:
        bad.add(offer.get("machine_id")); json.dump(sorted(b for b in bad if b), open(BAD, "w"))
    L.close("open_failed"); L = None
if L is None:
    print("nenhuma oferta abriu"); sys.exit(1)
dest = RAW / "sessions" / L.run_id
try:
    L.sh("mkdir -p /workspace/eco/out", 60)
    L.put(str(ROOT / "remote"), "/workspace/")
    L.sh("cd /workspace && cp -rn remote/* eco/ 2>/dev/null || (mkdir -p eco && cp -r remote/* eco/); cd eco && sed -i 's/\r$//' *.sh; nohup nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,temperature.gpu,power.draw,clocks.sm --format=csv -l 1 > out/host_metrics.csv 2>&1 &", 90)
    L.log.write({"event": "env", "out": (L.sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader; /venv/main/bin/python -c 'import torch,vllm;print(torch.__version__,vllm.__version__)' 2>&1 | tail -1", 120) or (0, ""))[1][-300:]})
    tok = ""
    if os.environ.get("PASS_HF") == "1":
        tok = "export HF_TOKEN=" + json.load(open(os.path.join(os.environ.get("SECRETS_DIR", "secrets"), "huggingface.json")))["HF_TOKEN"] + "; export HUGGING_FACE_HUB_TOKEN=$HF_TOKEN; "
    L.sh(f"cd /workspace/eco && {tok}nohup bash {script} > out/script.log 2>&1 &", 30)
    t0 = time.time()
    while time.time() - t0 < ttl * 60 - 420:
        time.sleep(60)
        r = L.sh("tail -c 400 /workspace/eco/out/script.log", 60)
        L.log.write({"event": "script_poll", "tail": (r[1][-250:] if r else None)})
        npoll = globals().get("npoll", 0) + 1
        globals()["npoll"] = npoll
        if npoll % 4 == 0:
            try:
                L.get("/workspace/eco/out/", str(dest / "out"))  # resultado sai da maquina a cada ~4 min: sessao morta perde pouco
            except Exception:  # noqa: BLE001
                pass
        if r and "SCRIPT_DONE" in r[1]:
            break
except Exception:
    L.log.write({"event": "session_error", "tb": traceback.format_exc()[-800:]})
finally:
    L.get("/workspace/eco/out/", str(dest / "out"))
    L.close("done")
