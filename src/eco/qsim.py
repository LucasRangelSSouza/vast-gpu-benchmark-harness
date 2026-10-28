# Queue simulator calibrated with measured service times.
# Original harness script, copied unmodified apart from this header. Comments inside may be in Portuguese.
"""M10/M4: simulador de fila externa (VPS) + GPUs, calibrado com tempos de servico MEDIDOS (requests.jsonl).
Tudo que sai daqui e measurement_kind=simulated. Politicas: GPU fixa, base+burst com cold start medido, scale-to-zero.
uso: python -m eco.qsim <requests.jsonl> <slots_medidos> [cold_start_s] [usd_h]"""
import heapq
import json
import random
import statistics as st
import sys

from eco.common import DATA, Jsonl


def load_service_times(path, level):
    rs = [json.loads(line) for line in open(path, encoding="utf-8")]
    return [r["total_s"] for r in rs if r["level"] == level and r["status"] == 200 and not r["error"] and not r["thinking"]]


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else None


def simulate(arrivals, service, slots, replicas_fn=None, horizon=None, seed=7):
    """arrivals: lista de instantes (s). service: amostras de tempo de servico a `slots` concorrentes. Fila FIFO global."""
    rnd = random.Random(seed)
    free = [0.0] * slots  # instante em que cada slot libera
    heapq.heapify(free)
    waits, e2e = [], []
    for t in sorted(arrivals):
        s = heapq.heappop(free)
        start = max(t, s)
        dur = rnd.choice(service)
        heapq.heappush(free, start + dur)
        waits.append(start - t)
        e2e.append(start - t + dur)
    end = max(free)
    return {"n": len(arrivals), "wait_p50": pct(waits, .5), "wait_p95": pct(waits, .95), "wait_p99": pct(waits, .99),
            "e2e_p50": pct(e2e, .5), "e2e_p95": pct(e2e, .95), "drain_s": round(end - min(arrivals), 1), "max_wait": max(waits)}


def closed_loop(users, think_s, duration, service, slots, seed=7):
    rnd = random.Random(seed)
    arr = []
    for _ in range(users):
        t = rnd.uniform(0, think_s)
        while t < duration:
            arr.append(t)
            t += rnd.expovariate(1 / think_s) + rnd.choice(service)  # espera aproximada pela resposta
    return arr


def scenarios(service, slots, cold_s, usd_h):
    out = []
    for users in (50, 100, 200):
        for name, arr in (("burst", [random.Random(1).uniform(0, 5) for _ in range(users)]),
                          ("sustentado_think30s", closed_loop(users, 30, 600, service, slots)),
                          ("sustentado_think10s", closed_loop(users, 10, 600, service, slots))):
            for reps in (1, 2, 3, 4):
                r = simulate(arr, service, slots * reps)
                horizon_h = max(r["drain_s"], 600) / 3600
                out.append({"users": users, "scenario": name, "replicas": reps, "slots_per_replica": slots, **r,
                            "cost_usd_gpu_hours": round(reps * usd_h * horizon_h, 3), "measurement_kind": "simulated"})
    return out


if __name__ == "__main__":
    path, slots = sys.argv[1], int(sys.argv[2])
    cold = float(sys.argv[3]) if len(sys.argv) > 3 else 600
    usd_h = float(sys.argv[4]) if len(sys.argv) > 4 else 0.449
    svc = load_service_times(path, slots)
    res = scenarios(svc, slots, cold, usd_h)
    log = Jsonl(DATA / "derived" / "qsim_results.jsonl")
    for r in res:
        log.write({**r, "source": path, "service_samples": len(svc), "service_p50": st.median(svc)})
    for r in res:
        print(json.dumps(r))
