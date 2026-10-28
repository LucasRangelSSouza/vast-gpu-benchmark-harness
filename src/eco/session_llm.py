# Session recipe for the language model load tests.
# Original harness script, copied unmodified apart from this header. Comments inside may be in Portuguese.
"""Sessao paga do nosso LLM (e bibliotecas) numa GPU: python -m eco.session_llm <gpu> <tag> "<variantes>" "<libs>" [ttl_min]"""
import sys, time, traceback
sys.path.insert(0, ".")
from eco import vast
from eco.common import RAW, ROOT
from eco.lease import Lease

gpu, tag, variants, libs = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
ttl = float(sys.argv[5]) if len(sys.argv) > 5 else 110
levels = sys.argv[6] if len(sys.argv) > 6 else '1,2,4,8,16,32'
cands = [o for o in vast.search(min_vram_gb=0, max_dph=3.5, gpu_names=[gpu], limit=200)
         if o.get("reliability2", 0) >= 0.97 and o.get("inet_down", 0) >= 400 and o.get("cuda_max_good", 0) >= 13.0 and o.get("disk_space", 0) >= 200]
import json, os
BAD = RAW / "leases" / "bad_hosts.json"
bad = set(json.load(open(BAD))) if BAD.exists() else set()
cands = [o for o in cands if o.get("machine_id") not in bad]
if not cands:
    print("nenhuma oferta elegivel para", gpu); sys.exit(2)
dest = None
L = None
for offer in cands[:4]:
    print("tentando oferta", offer["id"], offer["gpu_name"], offer["dph_total"], offer.get("geolocation"), flush=True)
    L = Lease(tag, offer, "vastai/vllm:v0.30.0-cuda-13.0", 160, ttl)
    if L.open():
        break
    bad.add(offer.get("machine_id")); json.dump(sorted(b for b in bad if b), open(BAD, "w"))
    L.close("open_failed")
    L = None
if L is None:
    print("nenhuma oferta abriu"); sys.exit(1)
dest = RAW / "sessions" / L.run_id
try:
    L.sh("mkdir -p /workspace/eco/out", 60)
    L.put(str(ROOT / "remote"), "/workspace/")
    L.sh("cd /workspace && rm -rf eco_old; cp -rn remote/* eco/ 2>/dev/null || (mkdir -p eco && cp -r remote/* eco/); cd eco && sed -i 's/\r$//' *.sh; nohup nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,temperature.gpu,power.draw,clocks.sm --format=csv -l 1 > out/host_metrics.csv 2>&1 &", 90)
    env = L.sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader; /venv/main/bin/python -c 'import torch,vllm;print(torch.__version__,vllm.__version__)' 2>&1 | tail -1", 120)
    L.log.write({"event": "env", "out": env[1][-300:] if env else None})
    if variants.strip():
        L.sh(f"cd /workspace/eco && nohup bash run_variants.sh '{variants}' '{levels}' > out/variants.log 2>&1 &", 30)
        t0 = time.time()
        while time.time() - t0 < ttl * 60 - 600:
            time.sleep(60)
            r = L.sh("tail -c 300 /workspace/eco/out/variants.log", 60)
            L.log.write({"event": "variants_poll", "tail": (r[1][-200:] if r else None)})
            if r and "CHAIN_DONE" in r[1]:
                break
        L.get("/workspace/eco/out/", str(dest))
    for lib in [x for x in libs.split(",") if x]:
        t0 = time.time()
        r = L.sh(f"cd /workspace/eco && mkdir -p out/libs && OUT=/workspace/eco/out/libs timeout 1500 /venv/main/bin/python libs.py {lib} > out/libs/{lib}.log 2>&1; echo rc=$?", 1600)
        L.log.write({"event": "lib_done", "lib": lib, "wall_s": round(time.time() - t0), "rc": (r[1].strip()[-20:] if r else "timeout")})
        L.get("/workspace/eco/out/libs/", str(dest / "libs"))
except Exception:
    L.log.write({"event": "session_error", "tb": traceback.format_exc()[-800:]})
finally:
    L.get("/workspace/eco/out/", str(dest / "final"))
    L.close("done")
