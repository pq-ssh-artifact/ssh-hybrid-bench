#!/usr/bin/env bash
# Installe les mêmes outils que sur la VM (Ubuntu 24.04 LTS : GCC 13.3, OpenSSL 3.0.13).
set -euo pipefail
. /etc/os-release
if [[ "${VERSION_ID:-}" != "24.04" ]]; then
  echo "ATTENTION : Ubuntu $VERSION_ID détecté ; l'article utilise Ubuntu 24.04 LTS." >&2
  echo "Les versions de GCC/OpenSSL risquent de différer : notez-le dans le Tableau 3." >&2
fi
sudo apt-get update
sudo apt-get install -y build-essential autoconf automake git zlib1g-dev libssl-dev \
  python3 python3-venv python3-pip linux-tools-common cpufrequtils util-linux \
  lm-sensors dmidecode jq
gcc --version | head -1
openssl version
