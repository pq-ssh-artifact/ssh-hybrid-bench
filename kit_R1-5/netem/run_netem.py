#!/usr/bin/env python3
"""run_netem.py -- connexions SSH à travers un réseau émulé par le noyau (tc netem).

Le client (ssh) et le serveur (sshd) ont chacun leur propre pile réseau : deux
espaces de noms sur un même hôte (mode netns) ou deux machines (mode host). Les
paquets traversent netem dans les deux sens : délai, gigue, débit et perte sont
appliqués par paquet IP, et TCP réagit (retransmissions, contrôle de congestion).

Mesure : comme dans l'article, la durée totale (lancement à fin du processus ssh)
et la phase d'échange de clés (KEXINIT client -> NEWKEYS client). Ces messages sont
horodatés par une sonde de transfert SANS délai placée côté client (127.0.0.1),
juste avant le lien émulé ; elle n'ajoute aucun délai artificiel.

Mode netns (lancé par netem_run.sh, en root, dans l'espace de noms "cli") :
  python3 run_netem.py --condition netem-lossy --blocks 300 --out OUT \
      --prefix /opt/openssh-10.0p2 --server-ip 10.10.0.2 --sshd-netns srv \
      --sshd-cpu 3

Mode host (deux machines) :
  serveur : python3 run_netem.py serve  --prefix P --bundle DIR [--port 22990]
            puis copiez DIR sur le client
  client  : python3 run_netem.py --condition host-lossy --blocks 300 --out OUT \
            --prefix P --server-ip IP_SERVEUR --bundle DIR

Aucun résultat n'est inventé : une connexion échouée est enregistrée avec son code
de retour, et le script s'arrête si la mise en route échoue.
"""
import argparse, csv, os, random, shutil, signal, socket, struct, subprocess, sys
import tempfile, threading, time

METHODS = ["mlkem768x25519-sha256", "sntrup761x25519-sha512", "curve25519-sha256",
           "ecdh-sha2-nistp256", "diffie-hellman-group14-sha256"]
SEEDS = {"netem-clean": 4, "netem-lossy": 5, "host-clean": 6, "host-lossy": 7, "netns-test": 9}
FIELDS = ["condition", "block", "position", "method", "total_ms", "kex_ms", "client_ms",
          "server_ms", "finish_ms", "c2s_kexinit_B", "s2c_kexinit_B", "c2s_kex_B",
          "s2c_kex_B", "retrans_cli", "retrans_srv", "returncode"]
SSH_MSG_KEXINIT, SSH_MSG_NEWKEYS = 20, 21


# ---------------------------------------------------------------- sonde sans délai
class Direction(threading.Thread):
    """Transfère les octets immédiatement et horodate les paquets SSH en clair
    (jusqu'au NEWKEYS de ce sens ; ensuite le flux est chiffré)."""
    def __init__(self, src, dst, events):
        super().__init__(daemon=True)
        self.src, self.dst, self.events = src, dst, events
        self.buf, self.banner_done, self.parsing = b"", False, True

    def parse(self, t):
        if not self.banner_done:
            i = self.buf.find(b"\r\n")
            if i < 0:
                return
            self.buf = self.buf[i + 2:]; self.banner_done = True
        while self.parsing and len(self.buf) >= 6:
            plen = struct.unpack(">I", self.buf[:4])[0]
            if len(self.buf) < 4 + plen:
                return
            mtype = self.buf[5]
            self.events.append((mtype, t, 4 + plen))   # taille du paquet binaire complet
            self.buf = self.buf[4 + plen:]
            if mtype == SSH_MSG_NEWKEYS:
                self.parsing = False; self.buf = b""

    def run(self):
        try:
            while True:
                data = self.src.recv(65536)
                t = time.perf_counter_ns()
                if not data:
                    break
                if self.parsing:
                    self.buf += data; self.parse(t)
                self.dst.sendall(data)
        except OSError:
            pass
        finally:
            for s in (self.dst,):
                try: s.shutdown(socket.SHUT_WR)
                except OSError: pass


class Tap(threading.Thread):
    def __init__(self, listen_port, server_ip, server_port):
        super().__init__(daemon=True)
        self.server = (server_ip, server_port)
        self.ls = socket.socket(); self.ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.ls.bind(("127.0.0.1", listen_port)); self.ls.listen(8)
        self.last = None

    def run(self):
        while True:
            c, _ = self.ls.accept()
            try:
                s = socket.create_connection(self.server, timeout=60)
                s.settimeout(None)
            except OSError:
                c.close(); continue
            for x in (c, s):
                x.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            ev_c2s, ev_s2c = [], []
            up, down = Direction(c, s, ev_c2s), Direction(s, c, ev_s2c)
            up.start(); down.start()
            self.last = (ev_c2s, ev_s2c, up, down, c, s)


# ---------------------------------------------------------------- compteurs TCP
def retrans_from_snmp(text):
    lines = [l.split() for l in text.splitlines() if l.startswith("Tcp:")]
    return int(lines[1][lines[0].index("RetransSegs")])

def retrans_local():
    with open("/proc/net/snmp") as f:
        return retrans_from_snmp(f.read())

def retrans_netns(ns):
    if not ns:
        return None
    out = subprocess.run(["ip", "netns", "exec", ns, "cat", "/proc/net/snmp"],
                         capture_output=True, text=True, check=True).stdout
    return retrans_from_snmp(out)


# ---------------------------------------------------------------- sshd
def make_keys(prefix, work):
    kg = os.path.join(prefix, "bin", "ssh-keygen")
    hk, ck = os.path.join(work, "host_ed25519"), os.path.join(work, "client_ed25519")
    for k in (hk, ck):
        if not os.path.exists(k):
            subprocess.run([kg, "-q", "-t", "ed25519", "-N", "", "-f", k], check=True)
    shutil.copy(ck + ".pub", os.path.join(work, "authorized_keys"))
    with open(os.path.join(work, "known_hosts"), "w") as f:
        f.write("[127.0.0.1]:* " + open(hk + ".pub").read())
    return hk, ck

def write_sshd_config(work, hk, listen_ip, port):
    cfg = os.path.join(work, "sshd_config")
    with open(cfg, "w") as f:
        f.write(f"""Port {port}
ListenAddress {listen_ip}
HostKey {hk}
HostKeyAlgorithms ssh-ed25519
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
AuthorizedKeysFile {work}/authorized_keys
StrictModes no
UsePAM no
PidFile {work}/sshd.pid
KexAlgorithms {",".join(METHODS)}
Ciphers chacha20-poly1305@openssh.com
MaxStartups 100:30:200
LoginGraceTime 120
LogLevel ERROR
""")
    return cfg

def start_sshd(prefix, work, cfg, netns=None, cpu=None):
    cmd = [os.path.join(prefix, "sbin", "sshd"), "-D", "-e", "-f", cfg]
    if cpu is not None:
        cmd = ["taskset", "-c", str(cpu)] + cmd
    if netns:
        cmd = ["ip", "netns", "exec", netns] + cmd
    return subprocess.Popen(cmd, stderr=open(os.path.join(work, "sshd.log"), "w"))

def wait_port(ip, port, tries=200):
    for _ in range(tries):
        try:
            socket.create_connection((ip, port), timeout=1).close(); return True
        except OSError:
            time.sleep(0.1)
    return False

def ssh_cmd(prefix, work, key, port, method, user):
    return [os.path.join(prefix, "bin", "ssh"), "-F", "none", "-p", str(port), "-i", key,
            "-o", f"KexAlgorithms={method}", "-o", "HostKeyAlgorithms=ssh-ed25519",
            "-o", "Ciphers=chacha20-poly1305@openssh.com",
            "-o", f"UserKnownHostsFile={work}/known_hosts", "-o", "StrictHostKeyChecking=yes",
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ControlMaster=no",
            "-o", "ConnectTimeout=60", "-o", "LogLevel=ERROR", f"{user}@127.0.0.1", "true"]


# ---------------------------------------------------------------- une connexion
def first(events, mtype):
    for m, t, size in events:
        if m == mtype:
            return t, size
    return None, None

def one(tap, cmd, srv_ns):
    r_cli, r_srv = retrans_local(), retrans_netns(srv_ns)
    t0 = time.perf_counter_ns()
    try:
        rc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, timeout=300).returncode
    except subprocess.TimeoutExpired:
        rc = 124
    total = (time.perf_counter_ns() - t0) / 1e6
    if tap.last is None:
        return dict(total_ms=total, returncode=rc or 98)
    c2s, s2c, up, down, c, s = tap.last; tap.last = None
    up.join(timeout=10); down.join(timeout=10)
    for x in (c, s):
        try: x.close()
        except OSError: pass
    time.sleep(0.05)   # laisse passer les derniers segments avant de relire les compteurs
    rcli = retrans_local() - r_cli
    rsrv = (retrans_netns(srv_ns) - r_srv) if srv_ns else ""
    t_ckex, b_ckex = first(c2s, SSH_MSG_KEXINIT); t_skex, b_skex = first(s2c, SSH_MSG_KEXINIT)
    t30, b30 = first(c2s, 30); t31, b31 = first(s2c, 31); t21, _ = first(c2s, SSH_MSG_NEWKEYS)
    ok = None not in (t_ckex, t_skex, t30, t31, t21)
    ms = lambda a, b: (b - a) / 1e6 if ok else float("nan")
    return dict(total_ms=total, kex_ms=ms(t_ckex, t21), client_ms=ms(t_skex, t30),
                server_ms=ms(t30, t31), finish_ms=ms(t31, t21), c2s_kexinit_B=b_ckex,
                s2c_kexinit_B=b_skex, c2s_kex_B=b30, s2c_kex_B=b31,
                retrans_cli=rcli, retrans_srv=rsrv,
                returncode=rc if ok else (rc or 99))


# ---------------------------------------------------------------- modes
def serve(a):
    """Mode host, côté serveur : clés + sshd à l'écoute sur toutes les interfaces."""
    os.makedirs(a.bundle, exist_ok=True)
    hk, ck = make_keys(a.prefix, a.bundle)
    cfg = write_sshd_config(a.bundle, hk, "0.0.0.0", a.port)
    sshd = start_sshd(a.prefix, a.bundle, cfg, cpu=a.sshd_cpu)
    print(f"sshd en écoute sur le port {a.port}. Copiez le dossier {a.bundle} sur le client "
          f"(fichiers client_ed25519, known_hosts). Ctrl+C pour arrêter.", flush=True)
    try:
        sshd.wait()
    except KeyboardInterrupt:
        sshd.terminate()

def client(a):
    seed = a.seed if a.seed is not None else SEEDS.get(a.condition, 1)
    os.makedirs(a.out, exist_ok=True)
    if a.bundle:                       # mode host : clés fournies par le serveur
        work = a.bundle; key = os.path.join(work, "client_ed25519"); sshd = None
        os.chmod(key, 0o600)
    else:                              # mode netns : sshd lancé dans l'autre espace de noms
        work = tempfile.mkdtemp(prefix="sshnetem-"); os.chmod(work, 0o755)
        hk, key = make_keys(a.prefix, work)
        cfg = write_sshd_config(work, hk, a.server_ip, a.port)
        sshd = start_sshd(a.prefix, work, cfg, netns=a.sshd_netns, cpu=a.sshd_cpu)
    if not wait_port(a.server_ip, a.port):
        sys.exit(f"sshd injoignable sur {a.server_ip}:{a.port}; voir {work}/sshd.log")
    tap = Tap(a.tap_port, a.server_ip, a.port); tap.start()
    user = a.user or os.environ.get("USER") or "root"
    rng = random.Random(seed)
    path = os.path.join(a.out, f"connections_{a.condition}.csv")
    fails = 0
    try:
        for m in METHODS:                                  # échauffement, non enregistré
            r = one(tap, ssh_cmd(a.prefix, work, key, a.tap_port, m, user), a.sshd_netns)
            if r["returncode"] != 0:
                sys.exit(f"échauffement en échec pour {m} (code {r['returncode']}); "
                         f"voir {work}/sshd.log")
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
            for b in range(1, a.blocks + 1):
                order = METHODS[:]; rng.shuffle(order)
                for pos, m in enumerate(order, 1):
                    r = one(tap, ssh_cmd(a.prefix, work, key, a.tap_port, m, user), a.sshd_netns)
                    fails += r["returncode"] != 0
                    w.writerow(dict(condition=a.condition, block=b, position=pos, method=m, **r))
                if b % 25 == 0 or b == a.blocks:
                    f.flush(); print(f"{a.condition}: bloc {b}/{a.blocks}", flush=True)
    finally:
        if sshd:
            sshd.terminate()
    print(f"écrit {path} ; connexions en échec : {fails}")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        ap = argparse.ArgumentParser(prog="run_netem.py serve")
        ap.add_argument("serve"); ap.add_argument("--prefix", required=True)
        ap.add_argument("--bundle", required=True); ap.add_argument("--port", type=int, default=22990)
        ap.add_argument("--sshd-cpu"); serve(ap.parse_args()); return
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", required=True)
    ap.add_argument("--blocks", type=int, required=True)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--prefix", default=os.environ.get("OPENSSH_PREFIX"), required=False)
    ap.add_argument("--out", required=True)
    ap.add_argument("--server-ip", default="10.10.0.2")
    ap.add_argument("--port", type=int, default=22990)
    ap.add_argument("--tap-port", type=int, default=22991)
    ap.add_argument("--sshd-netns", default=None, help="espace de noms du serveur (mode netns)")
    ap.add_argument("--sshd-cpu", default=None)
    ap.add_argument("--bundle", default=None, help="dossier copié depuis le serveur (mode host)")
    ap.add_argument("--user", default=None)
    a = ap.parse_args()
    if not a.prefix:
        sys.exit("--prefix (ou OPENSSH_PREFIX) requis")
    client(a)

if __name__ == "__main__":
    main()
