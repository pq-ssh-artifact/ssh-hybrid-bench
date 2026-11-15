#!/usr/bin/env python3
"""analyze.py -- statistics of Section 4.3 for one platform.

Reads   DIR/ops/ops.csv and DIR/e2e/connections_*.csv
Writes  DIR/ops_summary.csv   (operation,unit,median,q1,q3,run_median_mean,run_median_sd)
        DIR/e2e_summary.csv   (paired differences vs curve25519-sha256, bootstrap 95% CI)
        DIR/e2e_tests.csv     (Friedman per condition/metric, Holm-adjusted Wilcoxon p)
Usage:  analyze.py DIR
"""
import os, sys
import numpy as np, pandas as pd
from scipy import stats

D = sys.argv[1]
REF = "curve25519-sha256"
SHORT = {"mlkem768x25519-sha256": "mlkem768x25519", "sntrup761x25519-sha512": "sntrup761x25519",
         "curve25519-sha256": "curve25519", "ecdh-sha2-nistp256": "ecdh-p256",
         "diffie-hellman-group14-sha256": "dh-group14"}
RNG = np.random.default_rng(12345)
B = 10_000

# ------------------------------------------------------------------ operations
opsf = os.path.join(D, "ops", "ops.csv")
ops = pd.read_csv(opsf) if os.path.exists(opsf) else pd.DataFrame(columns=["run", "op", "ns"])
ops["us"] = ops.ns.astype(float) / 1e3
rows = []
for op, g in ops.groupby("op", sort=False):
    runmed = g.groupby("run").us.median()
    rows.append(dict(operation=op, unit="us", median=g.us.median(), q1=g.us.quantile(.25),
                     q3=g.us.quantile(.75), n=len(g), run_median_mean=runmed.mean(),
                     run_median_sd=runmed.std(ddof=1) if len(runmed) > 1 else 0.0))
summ = pd.DataFrame(rows, columns=["operation", "unit", "median", "q1", "q3", "n",
                                   "run_median_mean", "run_median_sd"])
# composed key exchange, both sides (ms) = sum of the three step medians, as in Table 6
for m in SHORT:
    steps = [f"KEX {m} client keypair", f"KEX {m} server", f"KEX {m} client finish"]
    sub = summ.set_index("operation").reindex(steps)
    if sub["median"].notna().all():
        client = (sub.loc[steps[0], "median"] + sub.loc[steps[2], "median"]) / 1e3
        server = sub.loc[steps[1], "median"] / 1e3
        summ.loc[len(summ)] = dict(operation=f"KEX {m}", unit="ms", median=client + server,
                                   q1=np.nan, q3=np.nan, n=np.nan, run_median_mean=np.nan,
                                   run_median_sd=np.nan, client_ms=client, server_ms=server)
if len(summ):
    summ.to_csv(os.path.join(D, "ops_summary.csv"), index=False)
    cv = (summ[summ.unit == "us"].run_median_sd / summ[summ.unit == "us"].run_median_mean * 100)
    print(f"[ops] {len(summ)} rows; max run-to-run CV of medians: {cv.max():.2f}%")

# ------------------------------------------------------------------ end-to-end
def boot_median(x):
    idx = RNG.integers(0, len(x), size=(B, len(x)))
    meds = np.median(x[idx], axis=1)
    return np.percentile(meds, [2.5, 97.5])

def holm(p):
    p = np.asarray(p, float); o = np.argsort(p); adj = np.empty_like(p); run = 0
    for k, i in enumerate(o):
        run = max(run, (len(p) - k) * p[i]); adj[i] = min(1, run)
    return adj

summary, tests = [], []
for cond in ["loopback", "wan", "constrained"]:
    f = os.path.join(D, "e2e", f"connections_{cond}.csv")
    if not os.path.exists(f):
        continue
    e = pd.read_csv(f)
    bad = (e.returncode != 0).sum()
    e = e[e.returncode == 0]
    for metric in ["kex_ms", "total_ms"]:
        wide = e.pivot_table(index="block", columns="method", values=metric).dropna()
        chi, pf = stats.friedmanchisquare(*[wide[m] for m in wide.columns])
        others = [m for m in SHORT if m != REF and m in wide]
        pw = [stats.wilcoxon(wide[m] - wide[REF]).pvalue for m in others]
        for m, p, pa in zip(others, pw, holm(pw)):
            tests.append(dict(condition=cond, metric=metric, method=SHORT[m], friedman_chi2=chi,
                              friedman_p=pf, wilcoxon_p=p, holm_p=pa, blocks=len(wide)))
    for m in SHORT:
        g = e[e.method == m]
        row = dict(condition=cond, method=SHORT[m], kex_median_ms=g.kex_ms.median(),
                   total_median_ms=g.total_ms.median())
        for metric, key in [("kex_ms", "dkex"), ("total_ms", "dtotal")]:
            if m == REF:
                row.update({f"{key}_ms": np.nan, f"{key}_lo": np.nan, f"{key}_hi": np.nan}); continue
            wide = e.pivot_table(index="block", columns="method", values=metric)[[m, REF]].dropna()
            d = (wide[m] - wide[REF]).to_numpy()
            lo, hi = boot_median(d)
            row.update({f"{key}_ms": np.median(d), f"{key}_lo": lo, f"{key}_hi": hi})
        summary.append(row)
    print(f"[e2e] {cond}: {e.block.nunique()} blocks, failed connections: {bad}")

cols = ["condition", "method", "kex_median_ms", "dkex_ms", "dkex_lo", "dkex_hi",
        "total_median_ms", "dtotal_ms", "dtotal_lo", "dtotal_hi"]
if summary:
    pd.DataFrame(summary)[cols].to_csv(os.path.join(D, "e2e_summary.csv"), index=False)
    pd.DataFrame(tests).to_csv(os.path.join(D, "e2e_tests.csv"), index=False)
print("written:", ", ".join(x for x in ["ops_summary.csv", "e2e_summary.csv", "e2e_tests.csv"]
                            if os.path.exists(os.path.join(D, x))))
