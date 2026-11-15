#!/usr/bin/env python3
"""analyze_netem.py -- statistiques de la §4.3 pour les conditions tc netem.

Usage : python3 analyze_netem.py RESULTS_DIR [RESULTS_DIR ...]
Chaque RESULTS_DIR contient des connections_<condition>.csv (sortie de run_netem.py).

Mêmes traitements que l'article : médianes, différences appariées par bloc par rapport
à curve25519-sha256, IC à 95 % par bootstrap (10 000 rééchantillonnages), Friedman puis
Wilcoxon signé avec correction de Holm. En plus, pour la perte : moyenne, 90e et 99e
centiles du temps total, part des connexions avec au moins une retransmission TCP,
et retransmissions moyennes par connexion.

Sorties dans chaque RESULTS_DIR :
  e2e_summary_netem.csv   (même format que e2e_summary.csv, pour 05_merge_tables.py)
  table7_netem.md         (lignes à ajouter à la Table 7)
  tails_netem.md          (queues de distribution et retransmissions)
"""
import glob, os, sys
import numpy as np, pandas as pd
from scipy import stats

BASE = "curve25519-sha256"
ORDER = ["mlkem768x25519-sha256", "sntrup761x25519-sha512", "curve25519-sha256",
         "ecdh-sha2-nistp256", "diffie-hellman-group14-sha256"]
LABEL = {"netem-clean": "WAN, tc netem (no loss)", "netem-lossy": "WAN, tc netem, 1% loss + jitter",
         "host-clean": "WAN, two hosts (no loss)", "host-lossy": "WAN, two hosts, 1% loss + jitter",
         "netns-test": "functional test (no emulation)"}
rng = np.random.default_rng(20251115)

def boot_ci(x, n=10000):
    x = np.asarray(x); x = x[~np.isnan(x)]
    if len(x) < 2:
        return np.nan, np.nan
    idx = rng.integers(0, len(x), (n, len(x)))
    med = np.median(x[idx], axis=1)
    return np.percentile(med, 2.5), np.percentile(med, 97.5)

def holm(p):
    p = np.asarray(p, float); order = np.argsort(p); m = len(p); adj = np.empty(m); run = 0
    for k, i in enumerate(order):
        run = max(run, min(1.0, (m - k) * p[i])); adj[i] = run
    return adj

def analyze(path):
    d = pd.read_csv(path); cond = d.condition.iloc[0]
    n_all, n_fail = len(d), int((d.returncode != 0).sum())
    ok = d[d.returncode == 0]
    # on ne garde que les blocs complets, pour l'appariement
    full = ok.groupby("block").method.nunique(); blocks = full[full == len(ORDER)].index
    ok = ok[ok.block.isin(blocks)]
    rows, tails, pvals = [], [], {}
    piv = {v: ok.pivot(index="block", columns="method", values=v) for v in ("kex_ms", "total_ms")}
    fr = stats.friedmanchisquare(*[piv["total_ms"][m] for m in ORDER]).pvalue
    for v in ("kex_ms", "total_ms"):
        ps = [stats.wilcoxon(piv[v][m], piv[v][BASE]).pvalue for m in ORDER if m != BASE]
        pvals[v] = dict(zip([m for m in ORDER if m != BASE], holm(ps)))
    for m in ORDER:
        g = ok[ok.method == m]; r = dict(condition=cond, method=m)
        for v, k in (("kex_ms", "kex"), ("total_ms", "total")):
            r[f"{k}_median_ms"] = g[v].median()
            if m == BASE:
                r[f"d{k}_ms"] = r[f"d{k}_lo"] = r[f"d{k}_hi"] = np.nan
            else:
                diff = (piv[v][m] - piv[v][BASE]).values
                r[f"d{k}_ms"] = np.median(diff); r[f"d{k}_lo"], r[f"d{k}_hi"] = boot_ci(diff)
        r["p_kex_holm"] = pvals["kex_ms"].get(m, np.nan); r["p_total_holm"] = pvals["total_ms"].get(m, np.nan)
        rows.append(r)
        rt = g.retrans_cli.fillna(0) + pd.to_numeric(g.retrans_srv, errors="coerce").fillna(0)
        tails.append(dict(method=m, n=len(g), total_mean=g.total_ms.mean(),
                          total_p90=g.total_ms.quantile(.9), total_p99=g.total_ms.quantile(.99),
                          kex_p90=g.kex_ms.quantile(.9), share_retrans=(rt > 0).mean() * 100,
                          retrans_mean=rt.mean(), c2s_kex_B=g.c2s_kex_B.median(),
                          s2c_kex_B=g.s2c_kex_B.median()))
    return cond, pd.DataFrame(rows), pd.DataFrame(tails), dict(
        n_all=n_all, n_fail=n_fail, blocks=len(blocks), friedman_p=fr)

def fmt(x, nd=1):
    return "–" if pd.isna(x) else f"{x:.{nd}f}"

def main(dirs):
    for rd in dirs:
        summ, md, tl = [], [], []
        for path in sorted(glob.glob(os.path.join(rd, "connections_*.csv"))):
            if "netem" not in path and "host-" not in path and "netns" not in path:
                continue
            cond, s, t, info = analyze(path); summ.append(s)
            lab = LABEL.get(cond, cond)
            md.append(f"\n**{lab}** ({info['blocks']} complete blocks; {info['n_fail']} failed "
                      f"connections out of {info['n_all']}; Friedman p = {info['friedman_p']:.2g})\n")
            md.append("| Method | KEX median (ms) | ΔKEX vs curve25519 [95% CI] | Total median (ms) | ΔTotal [95% CI] | Holm p (total) |")
            md.append("|---|---|---|---|---|---|")
            for _, r in s.iterrows():
                ci = lambda k: "ref." if pd.isna(r[f"d{k}_ms"]) else \
                    f"{r[f'd{k}_ms']:+.2f} [{r[f'd{k}_lo']:+.2f}, {r[f'd{k}_hi']:+.2f}]"
                md.append(f"| {r.method} | {fmt(r.kex_median_ms,2)} | {ci('kex')} | "
                          f"{fmt(r.total_median_ms,2)} | {ci('total')} | "
                          f"{'–' if pd.isna(r.p_total_holm) else f'{r.p_total_holm:.2g}'} |")
            tl.append(f"\n**{lab}**\n\n| Method | n | Total mean | Total p90 | Total p99 | KEX p90 | "
                      f"Connections with ≥1 TCP retransmission (%) | Retransmissions / connection | "
                      f"KEX msg C→S (B) | KEX msg S→C (B) |\n|---|---|---|---|---|---|---|---|---|---|")
            for _, r in t.iterrows():
                tl.append(f"| {r.method} | {r.n} | {fmt(r.total_mean)} | {fmt(r.total_p90)} | "
                          f"{fmt(r.total_p99)} | {fmt(r.kex_p90)} | {fmt(r.share_retrans)} | "
                          f"{fmt(r.retrans_mean,2)} | {r.c2s_kex_B:.0f} | {r.s2c_kex_B:.0f} |")
        if not summ:
            print(f"{rd}: aucun fichier connections_netem-*.csv"); continue
        allsum = pd.concat(summ)
        cols = ["condition", "method", "kex_median_ms", "dkex_ms", "dkex_lo", "dkex_hi",
                "total_median_ms", "dtotal_ms", "dtotal_lo", "dtotal_hi"]
        allsum[cols].to_csv(os.path.join(rd, "e2e_summary_netem.csv"), index=False, float_format="%.4f")
        open(os.path.join(rd, "table7_netem.md"), "w").write("\n".join(md) + "\n")
        open(os.path.join(rd, "tails_netem.md"), "w").write("\n".join(tl) + "\n")
        print("\n".join(md)); print("\n".join(tl))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
