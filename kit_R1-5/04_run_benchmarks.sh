#!/usr/bin/env bash
# Lance VOTRE harnais (commandes définies dans config/platform.env) avec épinglage,
# surveillance fréquence/température et empreintes des binaires utilisés.
# Usage : ./04_run_benchmarks.sh [ops|loopback|wan|constrained|all]
set -euo pipefail
cd "$(dirname "$0")"; KIT=$PWD; . config/platform.env
WHAT=${1:-all}
OUT=$KIT/results/$PLATFORM_ID; mkdir -p "$OUT/ops" "$OUT/e2e" "$OUT/monitor"
export OUT OPENSSH_PREFIX PATH="$OPENSSH_PREFIX/bin:$OPENSSH_PREFIX/sbin:$PATH"

sha256sum "$OPENSSH_PREFIX/bin/ssh" "$OPENSSH_PREFIX/sbin/sshd" > "$OUT/binaries.sha256"

monitor(){ # échantillonne fréquence et température toutes les 2 s
  local f=$1; echo "ts,cpu_mhz,temp_c,throttled" > "$f"
  while true; do
    mhz=$(awk '{s+=$1;n++} END{if(n) printf "%.0f", s/n/1000}' /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq 2>/dev/null)
    t=$(awk '{printf "%.1f", $1/1000; exit}' /sys/class/thermal/thermal_zone0/temp 2>/dev/null)
    th=$(command -v vcgencmd >/dev/null && vcgencmd get_throttled | cut -d= -f2 || echo na)
    echo "$(date +%s.%N),${mhz:-na},${t:-na},$th" >> "$f"; sleep 2
  done
}

run(){ # nom, cpus, commande
  local name=$1 cpus=$2 cmd=$3
  echo "== $name ($PLATFORM_ID) sur CPU $cpus — $(date -Is)"
  monitor "$OUT/monitor/$name.csv" & local mpid=$!
  ( cd "$HARNESS_DIR" && taskset -c "$cpus" bash -c "$cmd" ) 2>&1 | tee "$OUT/$name.log"
  kill $mpid 2>/dev/null || true
  python3 - "$OUT/monitor/$name.csv" <<'PY'
import csv,sys
r=list(csv.DictReader(open(sys.argv[1])))
f=[float(x['cpu_mhz']) for x in r if x['cpu_mhz'] not in ('na','')]
t=[float(x['temp_c']) for x in r if x['temp_c'] not in ('na','')]
th={x['throttled'] for x in r}
fs = f"{min(f):.0f}/{max(f):.0f} MHz" if f else "non disponible (VM)"
ts = f"{max(t):.1f} °C" if t else "non disponible (VM)"
print(f"   fréquence min/max : {fs} ; température max : {ts} ; throttled : {sorted(th - {'na'}) or 'n/a'}")
if any(v not in ('na','0x0') for v in th): print("   !!! ÉTRANGLEMENT DÉTECTÉ : relancez après avoir amélioré le refroidissement")
PY
}

case $WHAT in
  ops)          run ops "$OPS_CPU" "$OPS_CMD" ;;
  loopback)     run loopback "$CONN_CPUS" "$CONN_LOOPBACK_CMD" ;;
  wan)          run wan "$CONN_CPUS" "$CONN_WAN_CMD" ;;
  constrained)  run constrained "$CONN_CPUS" "$CONN_CONSTRAINED_CMD" ;;
  all) run ops "$OPS_CPU" "$OPS_CMD"
       run loopback "$CONN_CPUS" "$CONN_LOOPBACK_CMD"
       run wan "$CONN_CPUS" "$CONN_WAN_CMD"
       run constrained "$CONN_CPUS" "$CONN_CONSTRAINED_CMD" ;;
  *) echo "usage: $0 [ops|loopback|wan|constrained|all]"; exit 2 ;;
esac
echo "== Analyse statistique"
python3 "$HARNESS_DIR/analyze.py" "$OUT" | tee "$OUT/analyze.log"
echo "Terminé. Résultats dans $OUT (ops_summary.csv, e2e_summary.csv, e2e_tests.csv + données brutes)"
