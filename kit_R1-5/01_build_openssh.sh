#!/usr/bin/env bash
# Compile OpenSSH 10.0p2 depuis le même commit et avec la configuration par défaut,
# comme pour la VM (tag V_10_0_P2, commit 2593769f).
set -euo pipefail
cd "$(dirname "$0")"; . config/platform.env
EXPECTED=2593769f
if [[ ! -d "$OPENSSH_SRC/.git" ]]; then
  git clone https://github.com/openssh/openssh-portable.git "$OPENSSH_SRC"
fi
cd "$OPENSSH_SRC"
git fetch --tags --quiet
git checkout --quiet V_10_0_P2
HEAD=$(git rev-parse --short=8 HEAD)
[[ "$HEAD" == "$EXPECTED" ]] || { echo "Commit $HEAD != $EXPECTED" >&2; exit 1; }
autoreconf -i
./configure --prefix="$OPENSSH_PREFIX" | tail -n 25   # options par défaut, comme dans l'article
make -j"$(nproc)" >/dev/null || { echo "ÉCHEC de make" >&2; make 2>&1 | tail -n 40; exit 1; }
# "make install" crée /var/empty (répertoire de séparation de privilèges) : il faut les droits root
[[ -d /var/empty ]] || sudo mkdir -p -m 0755 /var/empty
make install-nokeys >/dev/null
grep -E '^CFLAGS=' Makefile | tee "$OPENSSH_PREFIX/BUILD_CFLAGS.txt"
for k in mlkem768x25519-sha256 sntrup761x25519-sha512 curve25519-sha256 \
         ecdh-sha2-nistp256 diffie-hellman-group14-sha256; do
  "$OPENSSH_PREFIX/bin/ssh" -Q kex | grep -qx "$k" && echo "OK  $k" || { echo "ABSENT $k" >&2; exit 1; }
done
"$OPENSSH_PREFIX/bin/ssh" -V
# Harnais d'opérations, compilé contre CE build
bash "$HARNESS_DIR/build.sh" "$OPENSSH_SRC"
