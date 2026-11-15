#!/usr/bin/env bash
# Campagne complète « vrai réseau » (action 4, R1-5), sur un hôte Linux avec sudo.
#   bash netem/netem_run.sh [BLOCS_CLEAN] [BLOCS_LOSSY]     (défaut : 150 et 300)
# Prérequis : 01_build_openssh.sh déjà lancé (OpenSSH 10.0p2 dans $OPENSSH_PREFIX).
# Sortie : results/$PLATFORM_ID/netem/
set -euo pipefail
cd "$(dirname "$0")/.."; KIT=$PWD; . config/platform.env
N_CLEAN=${1:-150}; N_LOSSY=${2:-300}
OUT=$KIT/results/$PLATFORM_ID/netem; mkdir -p "$OUT"
NS=$KIT/netem/netem_setup.sh

# 1. Module netem (sur les runners GitHub, il peut être dans linux-modules-extra)
if ! sudo modprobe sch_netem 2>/dev/null; then
  sudo apt-get install -y "linux-modules-extra-$(uname -r)" >/dev/null 2>&1 || true
  sudo modprobe sch_netem || { echo "ÉCHEC : sch_netem indisponible sur ce noyau ($(uname -r))."; exit 1; }
fi
command -v ethtool >/dev/null && command -v ping >/dev/null || sudo apt-get install -y ethtool iputils-ping >/dev/null

# 2. Utilisateur de séparation de privilèges de sshd (sshd tourne en root dans "srv")
getent passwd sshd >/dev/null || sudo useradd -r -s /usr/sbin/nologin sshd
sudo mkdir -p /var/empty && sudo chmod 755 /var/empty

# 3. Cœurs : client (ssh + sonde) et serveur (sshd) sur deux cœurs différents
NCPU=$(nproc); if (( NCPU >= 4 )); then CPU_CLI=2; CPU_SRV=3; else CPU_CLI=0; CPU_SRV=1; fi
echo "cœurs : client=$CPU_CLI serveur=$CPU_SRV (nproc=$NCPU)" | tee "$OUT/cpus.txt"
{ uname -a; lscpu; tc -V; } > "$OUT/env_netem.txt" 2>&1

run_condition() { # nom profil blocs
  local cond=$1 prof=$2 blocks=$3
  echo "== $cond ($prof, $blocks blocs) — $(date -Is)"
  sudo "$NS" up "$prof"
  sudo "$NS" verify "$OUT/$cond"
  # contrôle : netem doit être actif, sinon on s'arrête (aucune donnée non émulée)
  sudo ip netns exec cli tc qdisc show dev veth-cli | grep -q netem || { echo "netem absent"; exit 1; }
  sudo ip netns exec cli taskset -c "$CPU_CLI" python3 "$KIT/netem/run_netem.py" \
      --condition "$cond" --blocks "$blocks" --out "$OUT" --prefix "$OPENSSH_PREFIX" \
      --server-ip 10.10.0.2 --sshd-netns srv --sshd-cpu "$CPU_SRV" --user root \
      2>&1 | tee "$OUT/$cond.log"
  sudo "$NS" stats "$OUT/$cond"
  sudo "$NS" down
}

run_condition netem-clean clean "$N_CLEAN"
run_condition netem-lossy lossy "$N_LOSSY"
sudo chown -R "$(id -u):$(id -g)" "$OUT"

echo "== Analyse"
python3 "$KIT/netem/analyze_netem.py" "$OUT" | tee "$OUT/analyze_netem.log"
echo "Terminé : $OUT"
