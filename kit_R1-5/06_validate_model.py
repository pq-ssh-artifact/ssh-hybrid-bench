#!/usr/bin/env python3
"""Action 3 (R1-5) : validation hors échantillon du modèle additif ΔT ≈ ΔC + ΔB/b.

Principe
--------
Calibration (VM uniquement) : on mesure, sur la VM, le rapport k_κ entre le surcoût de
calcul observé en connexion (Δ KEX loopback) et le surcoût de calcul prédit par le
micro-benchmark des primitives (ΔC_ops). k_κ absorbe tout ce qui n'est pas de la crypto
(hachage SHA-512 vs SHA-256, sérialisation, copies mémoire…).

Prédiction (plateforme P, SANS aucune mesure de connexion de P) :
    ΔĈ_P,κ          = k_κ(VM) × ΔC_ops,P,κ           (seul le micro-benchmark de P est utilisé)
    ΔT̂_P,κ(c)       = ΔĈ_P,κ + ΔB_κ · 8 / b_c        (c = loopback, WAN, constrained)
Référence naïve (pour montrer que les temps absolus, eux, ne se transfèrent pas) :
    ΔT̂_naïf(c)      = ΔC_VM,κ + ΔB_κ · 8 / b_c

Usage
-----
  1) python3 06_validate_model.py predict x86      # après le micro-benchmark, AVANT les connexions
  2) python3 06_validate_model.py compare vm x86 arm64   # une fois les connexions mesurées

`predict` écrit results/<p>/predictions.csv, horodaté et haché (SHA-256) : c'est la
pré-déclaration. `compare` refuse de tourner si le fichier de prédictions a changé depuis.
Sorties de `compare` : results/merged/table8_ext.{md,csv} et results/merged/validation.md.
"""
import sys, json, hashlib, datetime, pathlib
import pandas as pd

R = pathlib.Path("results")

# ---- Constantes de l'article (§3.7, §5.3, Tableau 8) -----------------------------
EXTRA_BYTES = {"mlkem768x25519": 2272, "sntrup761x25519": 2200}      # octets en plus / curve25519
BANDWIDTH = {"loopback": None, "wan": 10e6, "constrained": 1e6}       # bit/s au goulot
KEX_ROW = {"mlkem768x25519": "KEX mlkem768x25519-sha256",
           "sntrup761x25519": "KEX sntrup761x25519-sha512",
           "curve25519": "KEX curve25519-sha256"}
KEM_OPS = {"mlkem768x25519": ["ML-KEM-768 KeyGen", "ML-KEM-768 Encaps",
                              "ML-KEM-768 Decaps", "ML-KEM-768 pk validation"],
           "sntrup761x25519": ["sntrup761 KeyGen", "sntrup761 Encaps", "sntrup761 Decaps"]}
LABEL = {"vm": "A (VM)", "x86": "B (x86-64)", "gh-x86": "B (x86-64)", "arm64": "C (ARM64)"}
COND = {"loopback": "Loopback", "wan": "WAN", "constrained": "Constrained"}

# Critère d'acceptation, fixé AVANT les mesures (à recopier tel quel dans l'article) :
TOL_ABS_MS, TOL_REL = 1.0, 0.05      # |erreur| ≤ max(1 ms ; 5 % de la valeur mesurée)


def ops(p):
    f = R / p / "ops_summary.csv"
    if f.exists():
        return pd.read_csv(f).set_index("operation")
    raw = R / p / "ops" / "ops.csv"          # données brutes du harnais (avant analyze.py)
    if not raw.exists():
        sys.exit(f"ERREUR : ni {f} ni {raw} n'existent : le benchmark d'opérations a-t-il tourné ?")
    r = pd.read_csv(raw)
    r["us"] = r.ns.astype(float) / 1e3
    d = r.groupby("op", sort=False).us.median().rename("median").to_frame()
    d["unit"] = "us"
    for m in KEX_ROW.values():               # même composition que analyze.py (Tableau 6)
        st = [f"{m} client keypair", f"{m} server", f"{m} client finish"]
        if all(x in d.index for x in st):
            d.loc[m] = [d.loc[st, "median"].sum() / 1e3, "ms"]
    return d


def dc_ops(d, method, mode):
    """Surcoût de calcul d'après le micro-benchmark (ms)."""
    if mode == "composed":
        return d.loc[KEX_ROW[method], "median"] - d.loc[KEX_ROW["curve25519"], "median"]
    return d.loc[KEM_OPS[method], "median"].sum() / 1000.0     # µs -> ms


def choose_mode(*frames):
    need = list(KEX_ROW.values())
    return "composed" if all(all(r in f.index for r in need) for f in frames) else "kem_sum"


def serial_ms(method, cond):
    b = BANDWIDTH[cond]
    return 0.0 if b is None else EXTRA_BYTES[method] * 8 / b * 1e3


def calibration(mode):
    v = ops("vm")
    e = pd.read_csv(R / "vm" / "e2e_summary.csv").set_index(["condition", "method"])
    cal = {}
    for m in EXTRA_BYTES:
        x = e.loc[("loopback", m)]
        o = dc_ops(v, m, mode)
        cal[m] = dict(dc_vm=x.dkex_ms, dc_vm_lo=x.dkex_lo, dc_vm_hi=x.dkex_hi, dc_ops_vm=o,
                      k=x.dkex_ms / o, k_lo=x.dkex_lo / o, k_hi=x.dkex_hi / o)
    return cal


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------
def predict(p):
    d = ops(p)
    mode = choose_mode(ops("vm"), d)
    cal = calibration(mode)
    if (R / p / "e2e_summary.csv").exists():
        print(f"ATTENTION : results/{p}/e2e_summary.csv existe déjà. La prédiction reste hors "
              "échantillon (aucune donnée de connexion de cette plateforme n'est lue), mais "
              "elle n'est pas pré-déclarée : dites-le dans la lettre de réponse.")
    rows = []
    for m, c in cal.items():
        o = dc_ops(d, m, mode)
        for cond in BANDWIDTH:
            s = serial_ms(m, cond)
            rows.append(dict(platform=p, method=m, condition=cond, serial_ms=round(s, 2),
                             dc_ops_ms=round(o, 3), k_vm=round(c["k"], 4),
                             pred_ms=round(c["k"] * o + s, 2),
                             pred_lo=round(c["k_lo"] * o + s, 2),
                             pred_hi=round(c["k_hi"] * o + s, 2),
                             naive_ms=round(c["dc_vm"] + s, 2)))
    out = R / p / "predictions.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    meta = dict(platform=p, created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                mode=mode, sha256=sha(out), 
                tolerance=f"|err| <= max({TOL_ABS_MS} ms, {TOL_REL:.0%} of measured)",
                calibration={m: {k: round(v, 4) for k, v in c.items()} for m, c in cal.items()})
    (R / p / "predictions.meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(pd.DataFrame(rows).to_string(index=False))
    print(f"\nPrédictions figées : {out}  sha256={meta['sha256'][:16]}…")
    print("Conseil : commitez ces deux fichiers (git) AVANT de lancer les mesures de connexion.")


# ---------------------------------------------------------------------------------
def compare(platforms):
    (R / "merged").mkdir(parents=True, exist_ok=True)
    mode = choose_mode(*[ops(p) for p in platforms])
    cal = calibration(mode)
    rows, txt = [], ["# Validation hors échantillon du modèle additif (à reporter en §5.6)\n",
                     f"Mode ΔC_ops : `{mode}`. Critère : |erreur| ≤ max({TOL_ABS_MS} ms ; "
                     f"{TOL_REL:.0%} de la valeur mesurée).\n",
                     "Calibration sur la VM : " + "; ".join(
                         f"{m} k = {c['k']:.3f} [{c['k_lo']:.3f}, {c['k_hi']:.3f}] "
                         f"(ΔC connexion {c['dc_vm']:.2f} ms / ΔC opérations {c['dc_ops_vm']:.2f} ms)"
                         for m, c in cal.items()) + "\n"]
    for p in platforms:
        e = pd.read_csv(R / p / "e2e_summary.csv").set_index(["condition", "method"])
        if p == "vm":
            pr = None
        else:
            f = R / p / "predictions.csv"
            meta = json.loads((R / p / "predictions.meta.json").read_text())
            if sha(f) != meta["sha256"]:
                sys.exit(f"ERREUR : {f} a été modifié après sa création ({meta['created_utc']}).")
            pr = pd.read_csv(f).set_index(["method", "condition"])
        for m in EXTRA_BYTES:
            for cond in BANDWIDTH:
                x = e.loc[(cond, m)]
                s = serial_ms(m, cond)
                if pr is None:                      # VM : en échantillon, loopback = calibration
                    pred = None if cond == "loopback" else cal[m]["dc_vm"] + s
                    plo = phi = naive = None
                    kind = "calibration" if cond == "loopback" else "in-sample"
                else:
                    q = pr.loc[(m, cond)]
                    pred, plo, phi, naive, kind = q.pred_ms, q.pred_lo, q.pred_hi, q.naive_ms, "out-of-sample"
                err = None if pred is None else x.dkex_ms - pred
                ok = None if err is None else bool(abs(err) <= max(TOL_ABS_MS, TOL_REL * abs(x.dkex_ms)))
                overlap = None if plo is None else bool(plo <= x.dkex_hi and phi >= x.dkex_lo)
                rows.append(dict(platform=p, method=m, condition=cond, kind=kind, serial=s,
                                 pred=pred, pred_lo=plo, pred_hi=phi, naive=naive,
                                 meas=x.dkex_ms, lo=x.dkex_lo, hi=x.dkex_hi, err=err,
                                 rel=None if err is None else err / x.dkex_ms,
                                 ok=ok, overlap=overlap,
                                 naive_err=None if naive is None else x.dkex_ms - naive))
    df = pd.DataFrame(rows)
    df.to_csv(R / "merged" / "table8_ext.csv", index=False)

    # ---- Table 8 étendue, prête à recopier --------------------------------------
    f2 = lambda v: "–" if v is None or pd.isna(v) else f"{v:.2f}"
    t = []
    for _, r in df.iterrows():
        t.append({"Platform": LABEL.get(r.platform, r.platform), "Method": r.method,
                  "Condition": COND[r.condition],
                  "Serial.": "–" if r.serial == 0 else f"{r.serial:.2f}",
                  "Predicted": f2(r.pred) if pd.isna(r.pred_lo) else f"{r.pred:.2f} [{r.pred_lo:.2f}, {r.pred_hi:.2f}]",
                  "Measured [95% CI]": f"{r.meas:.2f} [{r.lo:.2f}, {r.hi:.2f}]",
                  "Error": "–" if pd.isna(r.err) else f"{r.err:+.2f} ({r.rel:+.1%})",
                  "OK": "–" if pd.isna(r.ok) else ("✓" if r.ok else "✗")})
    t = pd.DataFrame(t)
    for col in ("Platform", "Method"):          # cellules fusionnées visuellement
        t[col] = t[col].where(t[col] != t[col].shift(), "")
    (R / "merged" / "table8_ext.md").write_text(t.to_markdown(index=False))

    # ---- Chiffres à citer --------------------------------------------------------
    oos = df[df.kind == "out-of-sample"]
    if len(oos):
        n_ok = int(oos.ok.astype(bool).sum())
        txt.append(f"## Global hors échantillon : {n_ok}/{len(oos)} prédictions dans la tolérance ; "
                   f"MAPE {oos.rel.abs().mean():.1%} ; erreur absolue max {oos.err.abs().max():.2f} ms "
                   f"({oos.loc[oos.err.abs().idxmax(), ['platform','method','condition']].tolist()})")
        txt.append(f"- Intervalle de prédiction recoupant l'IC 95 % de la mesure : {int(oos.overlap.astype(bool).sum())}/{len(oos)}")
        txt.append(f"- Référence naïve (temps de la VM recopiés) : MAPE {oos.naive_err.abs().div(oos.meas.abs()).mean():.1%}, "
                   f"erreur max {oos.naive_err.abs().max():.2f} ms\n")
        for p in oos.platform.unique():
            s = oos[oos.platform == p]
            txt.append(f"### {LABEL.get(p, p)}")
            for m in EXTRA_BYTES:
                sm = s[s.method == m]
                txt.append(f"- {m} : erreur max {sm.err.abs().max():.2f} ms, MAPE {sm.rel.abs().mean():.1%}, "
                           f"signe des erreurs {''.join('+' if v > 0 else '−' for v in sm.err)} "
                           f"(+ = sous-estimation), {int(sm.ok.astype(bool).sum())}/{len(sm)} ✓")
            bad = s[~s.ok.astype(bool)]
            for _, r in bad.iterrows():
                txt.append(f"  - ✗ {r.method} {r.condition} : prédit {r.pred:.2f}, mesuré {r.meas:.2f} → "
                           "à expliquer dans le texte (cause probable ?)")
            txt.append("")
    ins = df[df.kind == "in-sample"]
    txt.append(f"## Rappel VM (en échantillon) : erreur max {ins.err.abs().max():.2f} ms, MAPE {ins.rel.abs().mean():.1%}")
    (R / "merged" / "validation.md").write_text("\n".join(txt))
    print(t.to_markdown(index=False), "\n")
    print("\n".join(txt))


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("predict", "compare"):
        sys.exit(__doc__)
    predict(sys.argv[2]) if sys.argv[1] == "predict" else compare(sys.argv[2:])
