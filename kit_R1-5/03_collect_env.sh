#!/usr/bin/env bash
# Relève tout ce qu'il faut pour la ligne de la plateforme dans le Tableau 3.
set -uo pipefail
cd "$(dirname "$0")"; . config/platform.env
OUT=results/$PLATFORM_ID; mkdir -p "$OUT"
cpu_model=$(lscpu | awk -F: '/Model name/{gsub(/^ +/,"",$2); print $2; exit}')
[[ -z "$cpu_model" && -f /proc/device-tree/model ]] && cpu_model=$(tr -d '\0' </proc/device-tree/model)
board=$( [[ -f /proc/device-tree/model ]] && tr -d '\0' </proc/device-tree/model || sudo dmidecode -s system-product-name 2>/dev/null || echo "n/a")
virt=$(systemd-detect-virt 2>/dev/null || echo "unknown")
maxmhz=$(lscpu | awk -F: '/CPU max MHz/{gsub(/ /,"",$2); print $2; exit}')
ram_gb=$(awk '/MemTotal/{printf "%.1f", $2/1048576}' /proc/meminfo)
. /etc/os-release
cat > "$OUT/env.json" <<JSON
{
  "platform_id": "$PLATFORM_ID",
  "arch": "$(uname -m)",
  "cpu_model": "$cpu_model",
  "board_or_system": "$board",
  "virtualization": "$virt",
  "cores_online": $(nproc),
  "cpu_max_mhz": "${maxmhz:-n/a}",
  "ram_gb": $ram_gb,
  "os": "$PRETTY_NAME",
  "kernel": "$(uname -r)",
  "gcc": "$(gcc -dumpfullversion 2>/dev/null)",
  "openssl": "$(openssl version | awk '{print $2}')",
  "openssh": "$("$OPENSSH_PREFIX/bin/ssh" -V 2>&1 | awk -F, '{print $1}')",
  "python": "$(python3 -V | awk '{print $2}')",
  "clocksource": "$(cat /sys/devices/system/clocksource/clocksource0/current_clocksource 2>/dev/null)"
}
JSON
lscpu > "$OUT/lscpu.txt"
echo "Ligne proposée pour le Tableau 3 :"
echo "| Platform ($PLATFORM_ID) | $board; $cpu_model, $(nproc) cores, max ${maxmhz:-?} MHz, $ram_gb GB RAM; $( [[ $virt == none ]] && echo bare metal || echo "virtualized ($virt)" ); $PRETTY_NAME, Linux $(uname -r) |" | tee "$OUT/table3_row.md"
