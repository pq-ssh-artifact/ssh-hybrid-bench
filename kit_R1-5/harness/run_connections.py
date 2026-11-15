#!/usr/bin/env python3
"""run_connections.py -- message-level measurement (Algorithm 2 of the paper).

The real ssh client connects to the real sshd through a relay. Until NEWKEYS the
SSH packets are unencrypted (RFC 4253), so the relay parses them and timestamps
KEXINIT (20), KEX_ECDH_INIT / KEXDH_INIT (30), KEX_ECDH_REPLY / KEXDH_REPLY (31)
and NEWKEYS (21) in each direction, on arrival at the relay.

Path emulation (store-and-forward, no loss): a chunk of l bytes received at time t
in one direction is delivered at  max(t, t_free) + l/b + d,  where t_free is the
end of the previous transmission in that direction, b the bottleneck bandwidth and
d the one-way delay. Each direction has its own delivery thread, which waits with
clock_nanosleep (TIMER_ABSTIME) on CLOCK_MONOTONIC.

Usage:
  run_connections.py --condition {loopback,wan,constrained} --blocks N --seed S --out DIR
"""
import argparse, csv, ctypes, ctypes.util, os, random, shutil, socket, struct
import subprocess, sys, tempfile, threading, time, collections

CONDITIONS = {                       # one-way delay (s), bandwidth (bit/s) per direction
    "loopback":    (0.0,   None),
    "wan":         (0.025, 10e6),
    "constrained": (0.050, 1e6),
}
DEFAULT_SEEDS = {"loopback": 1, "wan": 2, "constrained": 3}
METHODS = [
    "mlkem768x25519-sha256",
    "sntrup761x25519-sha512",
    "curve25519-sha256",
    "ecdh-sha2-nistp256",
    "diffie-hellman-group14-sha256",
]

# ---------------------------------------------------------------- precise sleeping
_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
class _timespec(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_nsec", ctypes.c_long)]
CLOCK_MONOTONIC, TIMER_ABSTIME = 1, 1

def sleep_until(t_ns):
    """Absolute sleep on CLOCK_MONOTONIC with clock_nanosleep (no epoll rounding)."""
    ts = _timespec(t_ns // 1_000_000_000, t_ns % 1_000_000_000)
    while _libc.clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, ctypes.byref(ts), None) == 4:
        pass  # EINTR

def now_ns():
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)

# ---------------------------------------------------------------- SSH plaintext parser
class Parser:
    """Follows one direction of the plaintext phase and records (type, t, size)."""
    def __init__(self, sink):
        self.buf = b""
        self.banner_done = False
        self.done = False           # after NEWKEYS, traffic is encrypted
        self.sink = sink

    def feed(self, data, t):
        if self.done:
            return
        self.buf += data
        if not self.banner_done:
            # Identification string ("SSH-2.0-...\r\n"), possibly preceded by other lines
            while b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                if line.startswith(b"SSH-"):
                    self.banner_done = True
                    break
            if not self.banner_done:
                return
        while len(self.buf) >= 6:
            plen = struct.unpack(">I", self.buf[:4])[0]
            if len(self.buf) < 4 + plen:
                return
            mtype = self.buf[5]
            self.sink.append((mtype, t, 4 + plen))
            self.buf = self.buf[4 + plen:]
            if mtype == 21:          # NEWKEYS
                self.done = True
                return

# ---------------------------------------------------------------- relay
class Direction(threading.Thread):
    """Reads from src, parses, and hands chunks to a delivery thread with the emulated timing."""
    def __init__(self, src, dst, delay, bw, events):
        super().__init__(daemon=True)
        self.src, self.dst, self.delay, self.bw = src, dst, delay, bw
        self.parser = Parser(events)
        self.q = collections.deque()
        self.cv = threading.Condition()
        self.t_free = 0
        self.closed = False
        self.sender = threading.Thread(target=self._deliver, daemon=True)

    def run(self):
        self.sender.start()
        try:
            while True:
                data = self.src.recv(65536)
                t = now_ns()
                if not data:
                    break
                self.parser.feed(data, t)
                if self.bw is None and self.delay == 0:
                    due = t
                else:
                    start = max(t, self.t_free)
                    tx = int(len(data) * 8 / self.bw * 1e9) if self.bw else 0
                    self.t_free = start + tx
                    due = self.t_free + int(self.delay * 1e9)
                with self.cv:
                    self.q.append((due, data)); self.cv.notify()
        except OSError:
            pass
        with self.cv:
            self.closed = True; self.cv.notify()
        self.sender.join()

    def _deliver(self):
        while True:
            with self.cv:
                while not self.q and not self.closed:
                    self.cv.wait()
                if not self.q:
                    break
                due, data = self.q.popleft()
            if due > now_ns():
                sleep_until(due)
            try:
                self.dst.sendall(data)
            except OSError:
                break
        try:
            self.dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass

class Relay(threading.Thread):
    def __init__(self, listen_port, target_port, delay, bw):
        super().__init__(daemon=True)
        self.delay, self.bw, self.target_port = delay, bw, target_port
        self.ls = socket.socket(); self.ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.ls.bind(("127.0.0.1", listen_port)); self.ls.listen(8)
        self.last = None
        self.ready = threading.Event()

    def run(self):
        while True:
            c, _ = self.ls.accept()
            s = socket.create_connection(("127.0.0.1", self.target_port))
            for x in (c, s):
                x.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            ev_c2s, ev_s2c = [], []
            up = Direction(c, s, self.delay, self.bw, ev_c2s)
            down = Direction(s, c, self.delay, self.bw, ev_s2c)
            up.start(); down.start()
            self.last = (ev_c2s, ev_s2c, up, down)

# ---------------------------------------------------------------- sshd setup
def setup_sshd(prefix, workdir, port):
    kg = os.path.join(prefix, "bin", "ssh-keygen")
    hk = os.path.join(workdir, "host_ed25519"); ck = os.path.join(workdir, "client_ed25519")
    for k in (hk, ck):
        subprocess.run([kg, "-q", "-t", "ed25519", "-N", "", "-f", k], check=True)
    shutil.copy(ck + ".pub", os.path.join(workdir, "authorized_keys"))
    with open(os.path.join(workdir, "known_hosts"), "w") as f:
        f.write("[127.0.0.1]:* " + open(hk + ".pub").read())
    cfg = os.path.join(workdir, "sshd_config")
    with open(cfg, "w") as f:
        f.write(f"""Port {port}
ListenAddress 127.0.0.1
HostKey {hk}
HostKeyAlgorithms ssh-ed25519
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthorizedKeysFile {workdir}/authorized_keys
StrictModes no
UsePAM no
PidFile {workdir}/sshd.pid
KexAlgorithms {",".join(METHODS)}
Ciphers chacha20-poly1305@openssh.com
MaxStartups 100:30:200
LogLevel ERROR
""")
    sshd = subprocess.Popen([os.path.join(prefix, "sbin", "sshd"), "-D", "-e", "-f", cfg],
                            stderr=open(os.path.join(workdir, "sshd.log"), "w"))
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close(); break
        except OSError:
            time.sleep(0.05)
    else:
        sys.exit("sshd did not start; see " + workdir + "/sshd.log")
    return sshd, ck

def ssh_cmd(prefix, workdir, key, port, method):
    return [os.path.join(prefix, "bin", "ssh"), "-F", "none", "-p", str(port), "-i", key,
            "-o", f"KexAlgorithms={method}", "-o", "HostKeyAlgorithms=ssh-ed25519",
            "-o", "Ciphers=chacha20-poly1305@openssh.com",
            "-o", f"UserKnownHostsFile={workdir}/known_hosts", "-o", "StrictHostKeyChecking=yes",
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ControlMaster=no",
            "-o", "LogLevel=ERROR", f"{os.environ.get('USER') or 'root'}@127.0.0.1", "true"]

# ---------------------------------------------------------------- one connection
FIELDS = ["condition", "block", "position", "method", "total_ms", "kex_ms", "client_ms",
          "server_ms", "finish_ms", "c2s_kexinit_B", "s2c_kexinit_B", "c2s_kex_B", "s2c_kex_B",
          "returncode"]

def first(events, mtype):
    for m, t, size in events:
        if m == mtype:
            return t, size
    return None, None

def one(relay, cmd):
    t0 = time.perf_counter_ns()
    rc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE).returncode
    total = (time.perf_counter_ns() - t0) / 1e6
    c2s, s2c, up, down = relay.last
    up.join(timeout=5); down.join(timeout=5)
    t_ckex, b_ckex = first(c2s, 20); t_skex, b_skex = first(s2c, 20)
    t30, b30 = first(c2s, 30); t31, b31 = first(s2c, 31); t21, _ = first(c2s, 21)
    ok = None not in (t_ckex, t_skex, t30, t31, t21)
    ms = lambda a, b: (b - a) / 1e6 if ok else float("nan")
    return dict(total_ms=total, kex_ms=ms(t_ckex, t21), client_ms=ms(t_skex, t30),
                server_ms=ms(t30, t31), finish_ms=ms(t31, t21), c2s_kexinit_B=b_ckex,
                s2c_kexinit_B=b_skex, c2s_kex_B=b30, s2c_kex_B=b31,
                returncode=rc if ok else (rc or 99))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", choices=CONDITIONS, required=True)
    ap.add_argument("--blocks", type=int, required=True)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--prefix", default=os.environ.get("OPENSSH_PREFIX"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--sshd-port", type=int, default=22990)
    ap.add_argument("--relay-port", type=int, default=22991)
    a = ap.parse_args()
    seed = a.seed if a.seed is not None else DEFAULT_SEEDS[a.condition]
    delay, bw = CONDITIONS[a.condition]
    os.makedirs(a.out, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sshbench-")
    sshd, key = setup_sshd(a.prefix, work, a.sshd_port)
    relay = Relay(a.relay_port, a.sshd_port, delay, bw); relay.start()
    rng = random.Random(seed)
    path = os.path.join(a.out, f"connections_{a.condition}.csv")
    fails = 0
    try:
        for m in METHODS:                                      # warm-up, not recorded
            r = one(relay, ssh_cmd(a.prefix, work, key, a.relay_port, m))
            if r["returncode"] != 0:
                sys.exit(f"warm-up failed for {m}; see {work}/sshd.log")
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
            for b in range(1, a.blocks + 1):
                order = METHODS[:]; rng.shuffle(order)
                for pos, m in enumerate(order, 1):
                    r = one(relay, ssh_cmd(a.prefix, work, key, a.relay_port, m))
                    fails += r["returncode"] != 0
                    w.writerow(dict(condition=a.condition, block=b, position=pos, method=m, **r))
                if b % 25 == 0 or b == a.blocks:
                    f.flush(); print(f"{a.condition}: block {b}/{a.blocks}", flush=True)
    finally:
        sshd.terminate()
    print(f"written {path}; failed connections: {fails}")

if __name__ == "__main__":
    main()
