#!/usr/bin/env bash
# Compile bench_ops contre l'arbre OpenSSH 10.0p2 déjà configuré et compilé.
# Usage : bash build.sh /chemin/vers/openssh-portable
set -euo pipefail
SRC=${1:?chemin vers openssh-portable}
HERE=$(cd "$(dirname "$0")" && pwd)
CFLAGS=$(sed -n 's/^CFLAGS=//p' "$SRC/Makefile")
CPPFLAGS=$(sed -n 's/^CPPFLAGS=//p' "$SRC/Makefile")
LIBS=$(sed -n 's/^LIBS=//p' "$SRC/Makefile")
CHANNELLIBS=$(sed -n 's/^CHANNELLIBS=//p' "$SRC/Makefile")
CPPFLAGS=$(echo "$CPPFLAGS" | sed "s|\$(PATHS)||; s|-I\$(srcdir)||; s|-I\. ||")
gcc $CFLAGS -I"$SRC" -I"$SRC/openbsd-compat" $CPPFLAGS \
    -o "$HERE/bench_ops" "$HERE/bench_ops.c" "$SRC/ssh-sk-client.o" \
    -L"$SRC" -L"$SRC/openbsd-compat" -lssh -lopenbsd-compat $CHANNELLIBS $LIBS -lcrypto -lz
echo "bench_ops compilé : $HERE/bench_ops"
