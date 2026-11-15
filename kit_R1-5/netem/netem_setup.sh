#!/usr/bin/env bash
# Réseau émulé par le noyau (tc netem) entre un client et un serveur SSH.
#
# Mode "netns" (un seul hôte, ex. runner GitHub) : deux espaces de noms réseau
# distincts, "cli" et "srv", reliés par une paire veth. Chacun a sa propre pile
# TCP/IP ; tout le trafic SSH traverse netem dans les deux sens.
#
#   sudo ./netem_setup.sh up     PROFIL   # crée cli/srv et applique le profil
#   sudo ./netem_setup.sh apply  PROFIL   # change de profil sans tout recréer
#   sudo ./netem_setup.sh verify OUTDIR   # ping de contrôle + état des qdiscs
#   sudo ./netem_setup.sh stats  OUTDIR   # compteurs netem (paquets perdus)
#   sudo ./netem_setup.sh down
#
# Mode "host" (deux vraies machines) : à lancer sur CHAQUE machine, sur
# l'interface qui mène à l'autre machine :
#   sudo ./netem_setup.sh host IFACE PROFIL     |   sudo ./netem_setup.sh hostdown IFACE
#
# Profils (appliqués à la sortie de CHAQUE côté, donc dans chaque sens) :
#   none   : aucun (test fonctionnel uniquement)
#   clean  : 25 ms, 10 Mbit/s            -> RTT 50 ms, même condition que « WAN » du relais
#   lossy  : 25 ms ± 5 ms (normale), 10 Mbit/s, 1 % de perte par sens
set -euo pipefail
CLI_IP=10.10.0.1; SRV_IP=10.10.0.2

profile_args() {
  case $1 in
    clean) echo "delay 25ms rate 10mbit limit 10000" ;;
    lossy) echo "delay 25ms 5ms distribution normal loss 1% rate 10mbit limit 10000" ;;
    none)  echo "" ;;
    *) echo "profil inconnu : $1 (none|clean|lossy)" >&2; exit 2 ;;
  esac
}
# Avec "rate", netem programme chaque paquet après le précédent : la gigue
# ne provoque donc pas de réordonnancement artificiel.

offloads_off() { # segmentation matérielle désactivée : netem voit de vrais paquets de 1500 o
  local ns=$1 dev=$2
  if command -v ethtool >/dev/null; then
    ip netns exec "$ns" ethtool -K "$dev" tso off gso off gro off >/dev/null 2>&1 || true
  else
    echo "ATTENTION : ethtool absent, offloads non désactivés" >&2
  fi
}

apply_ns() {
  local args; args=$(profile_args "$1")
  for p in "cli veth-cli" "srv veth-srv"; do
    set -- $p
    ip netns exec "$1" tc qdisc del dev "$2" root 2>/dev/null || true
    if [[ -n $args ]]; then
      ip netns exec "$1" tc qdisc add dev "$2" root netem $args
    fi
  done
  echo "profil $PROFILE appliqué : ${args:-aucun}"
}

case ${1:-} in
  up)
    PROFILE=${2:?profil}
    ip netns del cli 2>/dev/null || true; ip netns del srv 2>/dev/null || true
    ip netns add cli; ip netns add srv
    ip link add veth-cli type veth peer name veth-srv
    ip link set veth-cli netns cli; ip link set veth-srv netns srv
    ip -n cli addr add $CLI_IP/24 dev veth-cli; ip -n srv addr add $SRV_IP/24 dev veth-srv
    for ns in cli srv; do ip -n $ns link set lo up; done
    ip -n cli link set veth-cli up; ip -n srv link set veth-srv up
    offloads_off cli veth-cli; offloads_off srv veth-srv
    apply_ns "$PROFILE" ;;
  apply)
    PROFILE=${2:?profil}; apply_ns "$PROFILE" ;;
  verify)
    OUT=${2:?répertoire}; mkdir -p "$OUT"
    {
      echo "# $(date -Is)"; uname -a
      for ns in cli srv; do echo "## qdisc $ns"; ip netns exec $ns tc qdisc show; done
      echo "## ping cli -> srv (1000 paquets, 10 ms d'intervalle)"
      ip netns exec cli ping -q -c 1000 -i 0.01 -s 56 $SRV_IP || true
    } | tee -a "$OUT/netem_verify.log" ;;
  stats)
    OUT=${2:?répertoire}; mkdir -p "$OUT"
    for ns in cli srv; do echo "## $ns"; ip netns exec $ns tc -s qdisc show; done | tee -a "$OUT/netem_stats.log" ;;
  down)
    ip netns del cli 2>/dev/null || true; ip netns del srv 2>/dev/null || true ;;
  host)
    IFACE=${2:?interface}; PROFILE=${3:?profil}; args=$(profile_args "$PROFILE")
    tc qdisc del dev "$IFACE" root 2>/dev/null || true
    command -v ethtool >/dev/null && ethtool -K "$IFACE" tso off gso off gro off || true
    [[ -n $args ]] && tc qdisc add dev "$IFACE" root netem $args
    tc qdisc show dev "$IFACE" ;;
  hostdown)
    tc qdisc del dev "${2:?interface}" root 2>/dev/null || true ;;
  *) sed -n '2,25p' "$0"; exit 2 ;;
esac
