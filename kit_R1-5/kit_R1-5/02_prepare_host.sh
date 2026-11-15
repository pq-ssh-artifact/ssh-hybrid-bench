#!/usr/bin/env bash
# Réduit la variance : gouverneur "performance", turbo désactivé (x86), vérification thermique (Pi).
# Tous les réglages sont journalisés dans results/<plateforme>/host_settings.txt.
set -euo pipefail
cd "$(dirname "$0")"; . config/platform.env
OUT=results/$PLATFORM_ID; mkdir -p "$OUT"; LOG=$OUT/host_settings.txt; : > "$LOG"
say(){ echo "$*" | tee -a "$LOG"; }

say "date: $(date -Is)"
# 1. Gouverneur de fréquence
for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
  [[ -w "$g" ]] || sudo true
  echo performance | sudo tee "$g" >/dev/null 2>&1 || true
done
say "governors: $(cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null | sort | uniq -c | tr '\n' ' ')"

# 2. Turbo / boost (x86)
if [[ -f /sys/devices/system/cpu/intel_pstate/no_turbo ]]; then
  echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo >/dev/null
  say "intel_pstate no_turbo=$(cat /sys/devices/system/cpu/intel_pstate/no_turbo)"
elif [[ -f /sys/devices/system/cpu/cpufreq/boost ]]; then
  echo 0 | sudo tee /sys/devices/system/cpu/cpufreq/boost >/dev/null
  say "cpufreq boost=$(cat /sys/devices/system/cpu/cpufreq/boost)"
else
  say "turbo: pas de contrôle disponible (normal sur ARM64)"
fi

# 3. SMT (information seulement ; on épingle de toute façon sur des cœurs distincts)
[[ -f /sys/devices/system/cpu/smt/control ]] && say "smt: $(cat /sys/devices/system/cpu/smt/control)"

# 4. Raspberry Pi : étranglement thermique et refroidissement
if command -v vcgencmd >/dev/null; then
  say "pi throttled: $(vcgencmd get_throttled)  temp: $(vcgencmd measure_temp)"
  say "Vérifiez qu'un ventilateur actif (Active Cooler) est monté : get_throttled doit rester 0x0."
fi

# 5. Services susceptibles d'interférer
for s in unattended-upgrades apt-daily.timer apt-daily-upgrade.timer snapd; do
  sudo systemctl stop "$s" >/dev/null 2>&1 && say "stopped: $s" || true
done
say "Préparation terminée. Ne lancez rien d'autre sur la machine pendant les mesures."
