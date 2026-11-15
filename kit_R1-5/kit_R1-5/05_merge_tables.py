#!/usr/bin/env python3
"""Fusionne les résumés par plateforme en nouvelles colonnes pour les Tableaux 6 et 7,
et vérifie les hypothèses de transfert de la §5.6 sur chaque plateforme.

Entrées (une par plateforme, produites à partir de VOTRE script d'analyse) :
  results/<id>/ops_summary.csv  : operation,unit,median,q1,q3
  results/<id>/e2e_summary.csv  : condition,method,kex_median_ms,dkex_ms,dkex_lo,dkex_hi,
                                  total_median_ms,dtotal_ms,dtotal_lo,dtotal_hi
results/vm/ contient déjà les valeurs publiées de l'article (référence).

Usage : python3 05_merge_tables.py vm x86 arm64
Sorties dans results/merged/ : table6.md, table7.md, checks.md (+ CSV).
"""
import sys, os
import pandas as pd

PLATS = sys.argv[1:] or ["vm", "x86", "arm64"]
LABEL = {"vm": "VM (2 vCPU)", "x86": "x86-64 bare metal", "arm64": "ARM64"}
EXTRA_BYTES = {"mlkem768x25519": 2272, "sntrup761x25519": 2200}   # §5.3, identiques partout
BANDWIDTH = {"wan": 10e6, "constrained": 1e6}                       # bit/s
os.makedirs("results/merged", exist_ok=True)

def load(p, name):
    f = f"results/{p}/{name}"
    if not os.path.exists(f):
        print(f"[absent] {f}"); return None
    return pd.read_csv(f)

def fmt(x, nd=1):
    if pd.isna(x): return "–"
    return f"{x:,.{nd}f}".replace(",", " ")

ops = {p: load(p, "ops_summary.csv") for p in PLATS}
e2e = {p: load(p, "e2e_summary.csv") for p in PLATS}
avail = [p for p in PLATS if ops[p] is not None]

# ---------- Tableau 6 ----------
base = ops[avail[0]][["operation", "unit"]]
rows = []
for _, r in base.iterrows():
    line = {"Operation": r.operation + (" (ms)" if r.unit == "ms" else "")}
    for p in avail:
        d = ops[p].set_index("operation")
        if r.operation in d.index:
            m, q1, q3 = d.loc[r.operation, ["median", "q1", "q3"]]
            nd = 2 if r.unit == "ms" else 1
            line[LABEL.get(p, p)] = fmt(m, nd) + ("" if pd.isna(q1) else f" [{fmt(q1, nd)}–{fmt(q3, nd)}]")
        else:
            line[LABEL.get(p, p)] = "–"
    rows.append(line)
t6 = pd.DataFrame(rows)
t6.to_csv("results/merged/table6.csv", index=False)
open("results/merged/table6.md", "w").write(t6.to_markdown(index=False))

# ---------- Tableau 7 (colonnes Δ KEX par plateforme) ----------
availe = [p for p in PLATS if e2e[p] is not None]
ref = e2e[availe[0]]
rows = []
for _, r in ref.iterrows():
    line = {"Condition": r.condition, "Method": r.method}
    for p in availe:
        d = e2e[p].set_index(["condition", "method"])
        k = (r.condition, r.method)
        if k in d.index and not pd.isna(d.loc[k, "dkex_ms"]):
            x = d.loc[k]
            line[f"Δ KEX {LABEL.get(p, p)}"] = f"{x.dkex_ms:.2f} [{x.dkex_lo:.2f}, {x.dkex_hi:.2f}]"
        elif k in d.index:
            line[f"Δ KEX {LABEL.get(p, p)}"] = f"ref. ({d.loc[k, 'kex_median_ms']:.2f})"
        else:
            line[f"Δ KEX {LABEL.get(p, p)}"] = "–"
    rows.append(line)
t7 = pd.DataFrame(rows)
t7.to_csv("results/merged/table7.csv", index=False)
open("results/merged/table7.md", "w").write(t7.to_markdown(index=False))

# ---------- Vérifications pour le texte ----------
out = ["# Vérifications de transfert (à reporter en §5.6)\n"]
for p in avail:
    d = ops[p].set_index("operation")["median"]
    out.append(f"## {LABEL.get(p, p)}")
    try:
        ratio = d["sntrup761 KeyGen"] / d["ML-KEM-768 KeyGen"]
        out.append(f"- Ratio KeyGen sntrup761 / ML-KEM-768 : {ratio:.0f}×")
        out.append(f"- X25519 (1 multiplication scalaire) / ML-KEM-768 KeyGen : {d['X25519 KeyGen']/d['ML-KEM-768 KeyGen']:.1f}×")
    except KeyError as e:
        out.append(f"- opération manquante : {e}")
    if p != "vm" and "vm" in avail:
        v = ops["vm"].set_index("operation")["median"]
        common = [o for o in d.index if o in v.index]
        out.append("- Rapport à la VM (médiane plateforme / médiane VM) : " +
                   "; ".join(f"{o} {d[o]/v[o]:.2f}" for o in common))
    if e2e.get(p) is not None:
        e = e2e[p].set_index(["condition", "method"])
        out.append("- Modèle additif ΔT ≈ ΔC(loopback) + ΔB/b :")
        for m, nbytes in EXTRA_BYTES.items():
            if ("loopback", m) not in e.index: continue
            dc = e.loc[("loopback", m), "dkex_ms"]
            for c, b in BANDWIDTH.items():
                if (c, m) not in e.index: continue
                pred = dc + nbytes * 8 / b * 1e3
                x = e.loc[(c, m)]
                inside = x.dkex_lo <= pred <= x.dkex_hi
                out.append(f"  - {m}, {c} : prédit {pred:.2f} ms, mesuré {x.dkex_ms:.2f} "
                           f"[{x.dkex_lo:.2f}, {x.dkex_hi:.2f}] → écart {x.dkex_ms - pred:+.2f} ms"
                           f"{' (dans l IC)' if inside else ''}")
        lb = e.xs("loopback")
        order = lb.dropna(subset=["dkex_ms"]).sort_values("dkex_ms").index.tolist()
        out.append(f"- Ordre des surcoûts KEX sur loopback : {' < '.join(order)}")
    out.append("")
open("results/merged/checks.md", "w").write("\n".join(out))
print(open("results/merged/table6.md").read(), "\n")
print(open("results/merged/table7.md").read(), "\n")
print("\n".join(out))
