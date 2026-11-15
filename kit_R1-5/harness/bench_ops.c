/*
 * bench_ops.c -- operation-level harness (Algorithm 1 of the paper).
 *
 * Links OpenSSH 10.0p2's own static libraries and calls the exact functions
 * used by the key exchange: libcrux ML-KEM-768 (header embedded in OpenSSH),
 * the SUPERCOP-derived sntrup761, OpenSSH's portable X25519, and the
 * OpenSSL-backed ECDH P-256 / DH group14 code paths of kexecdh.c / kexdh.c.
 *
 * Times 9 primitives and, for each of the 5 methods, the 3 composed steps
 * (client keypair, server encapsulation incl. DH + hash, client decapsulation
 * incl. DH + hash): 24 operations. Correctness is checked at every iteration.
 *
 * Usage: bench_ops RUNS ITERS WARMUP OUT.csv
 * Output CSV: run,iter,op,ns     (warm-up iterations are not written)
 */
#include "includes.h"
#include <sys/types.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <signal.h>
#include <time.h>
#ifdef HAVE_ENDIAN_H
# include <endian.h>
#endif
#include <openssl/objects.h>
#include "sshkey.h"
#include "kex.h"
#include "sshbuf.h"
#include "digest.h"
#include "ssherr.h"
#include "log.h"
#include "crypto_api.h"
#include "libcrux_mlkem768_sha3.h"

void cleanup_exit(int i) { _exit(i); }
int crypto_scalarmult_curve25519(u_char a[CURVE25519_SIZE], const u_char b[CURVE25519_SIZE], const u_char c[CURVE25519_SIZE]);

static FILE *out;
static int cur_run, cur_iter, recording;

static inline uint64_t now_ns(void) {
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
	return (uint64_t)ts.tv_sec * 1000000000ull + ts.tv_nsec;
}
static void rec(const char *op, uint64_t ns) {
	if (recording)
		fprintf(out, "%d,%d,%s,%llu\n", cur_run, cur_iter, op,
		    (unsigned long long)ns);
}
static void die(const char *what, int r) {
	fprintf(stderr, "FAIL %s (r=%d: %s)\n", what, r, ssh_err(r));
	exit(1);
}
#define T(op, stmt) do { uint64_t _t0 = now_ns(); stmt; rec(op, now_ns() - _t0); } while (0)

/* ---------- primitives ---------- */
static void prim_mlkem(void) {
	uint8_t rnd[64], rnd2[32], k_dec[32];
	struct libcrux_mlkem768_keypair kp;
	struct libcrux_mlkem768_enc_result enc;
	bool ok;
	arc4random_buf(rnd, sizeof rnd);
	arc4random_buf(rnd2, sizeof rnd2);
	T("ML-KEM-768 KeyGen", kp = libcrux_ml_kem_mlkem768_portable_generate_key_pair(rnd));
	T("ML-KEM-768 pk validation", ok = libcrux_ml_kem_mlkem768_portable_validate_public_key(&kp.pk));
	if (!ok) die("mlkem pk validation", 0);
	T("ML-KEM-768 Encaps", enc = libcrux_ml_kem_mlkem768_portable_encapsulate(&kp.pk, rnd2));
	T("ML-KEM-768 Decaps", libcrux_ml_kem_mlkem768_portable_decapsulate(&kp.sk, &enc.fst, k_dec));
	if (memcmp(k_dec, enc.snd, 32) != 0) die("mlkem shared secret mismatch", 0);
}
static void prim_sntrup(void) {
	static u_char pk[crypto_kem_sntrup761_PUBLICKEYBYTES], sk[crypto_kem_sntrup761_SECRETKEYBYTES];
	static u_char ct[crypto_kem_sntrup761_CIPHERTEXTBYTES];
	u_char k1[32], k2[32];
	T("sntrup761 KeyGen", crypto_kem_sntrup761_keypair(pk, sk));
	T("sntrup761 Encaps", crypto_kem_sntrup761_enc(ct, k1, pk));
	T("sntrup761 Decaps", crypto_kem_sntrup761_dec(k2, ct, sk));
	if (memcmp(k1, k2, 32) != 0) die("sntrup761 shared secret mismatch", 0);
}
static void prim_x25519(void) {
	u_char a[CURVE25519_SIZE], A[CURVE25519_SIZE], b[CURVE25519_SIZE], B[CURVE25519_SIZE];
	u_char s1[CURVE25519_SIZE], s2[CURVE25519_SIZE];
	T("X25519 KeyGen", kexc25519_keygen(a, A));
	kexc25519_keygen(b, B);
	T("X25519 shared secret", crypto_scalarmult_curve25519(s1, a, B));
	crypto_scalarmult_curve25519(s2, b, A);
	if (memcmp(s1, s2, sizeof s1) != 0) die("x25519 mismatch", 0);
}

/* ---------- composed key exchange, both sides ---------- */
typedef int (*kp_fn)(struct kex *);
typedef int (*enc_fn)(struct kex *, const struct sshbuf *, struct sshbuf **, struct sshbuf **);
typedef int (*dec_fn)(struct kex *, const struct sshbuf *, struct sshbuf **);
struct method { const char *name; u_int type; int hash; kp_fn kp; enc_fn enc; dec_fn dec; int every; };

static struct kex *mkkex(const struct method *m, int server) {
	struct kex *k = kex_new();
	if (k == NULL) die("kex_new", SSH_ERR_ALLOC_FAIL);
	k->kex_type = m->type;
	k->hash_alg = m->hash;
	k->ec_nid = NID_X9_62_prime256v1;
	k->we_need = 64;            /* chacha20-poly1305 key length, as in the paper's setup */
	k->server = server;
	return k;
}
static void composed(const struct method *m) {
	struct kex *c = mkkex(m, 0), *s = mkkex(m, 1);
	struct sshbuf *sblob = NULL, *sshared = NULL, *cshared = NULL;
	char lbl[128];
	int r;
	snprintf(lbl, sizeof lbl, "KEX %s client keypair", m->name);
	T(lbl, r = m->kp(c));
	if (r) die(lbl, r);
	snprintf(lbl, sizeof lbl, "KEX %s server", m->name);
	T(lbl, r = m->enc(s, c->client_pub, &sblob, &sshared));
	if (r) die(lbl, r);
	snprintf(lbl, sizeof lbl, "KEX %s client finish", m->name);
	T(lbl, r = m->dec(c, sblob, &cshared));
	if (r) die(lbl, r);
	if (sshbuf_cmp(sshared, 0, sshbuf_ptr(cshared), sshbuf_len(cshared)) != 0 ||
	    sshbuf_len(sshared) != sshbuf_len(cshared))
		die("composed shared secret mismatch", 0);
	sshbuf_free(sblob); sshbuf_free(sshared); sshbuf_free(cshared);
	kex_free(c); kex_free(s);
}

static const struct method methods[] = {
	{ "mlkem768x25519-sha256", KEX_KEM_MLKEM768X25519_SHA256, SSH_DIGEST_SHA256,
	  kex_kem_mlkem768x25519_keypair, kex_kem_mlkem768x25519_enc, kex_kem_mlkem768x25519_dec, 1 },
	{ "sntrup761x25519-sha512", KEX_KEM_SNTRUP761X25519_SHA512, SSH_DIGEST_SHA512,
	  kex_kem_sntrup761x25519_keypair, kex_kem_sntrup761x25519_enc, kex_kem_sntrup761x25519_dec, 1 },
	{ "curve25519-sha256", KEX_C25519_SHA256, SSH_DIGEST_SHA256,
	  kex_c25519_keypair, kex_c25519_enc, kex_c25519_dec, 1 },
	{ "ecdh-sha2-nistp256", KEX_ECDH_SHA2, SSH_DIGEST_SHA256,
	  kex_ecdh_keypair, kex_ecdh_enc, kex_ecdh_dec, 1 },
	/* finite-field DH is timed every tenth iteration because of its cost (paper, Sec. 4.3) */
	{ "diffie-hellman-group14-sha256", KEX_DH_GRP14_SHA256, SSH_DIGEST_SHA256,
	  kex_dh_keypair, kex_dh_enc, kex_dh_dec, 10 },
};

int main(int argc, char **argv) {
	if (argc != 5) { fprintf(stderr, "usage: %s RUNS ITERS WARMUP OUT.csv\n", argv[0]); return 2; }
	int runs = atoi(argv[1]), iters = atoi(argv[2]), warm = atoi(argv[3]);
	if ((out = fopen(argv[4], "w")) == NULL) { perror(argv[4]); return 1; }
	fprintf(out, "run,iter,op,ns\n");
	for (cur_run = 1; cur_run <= runs; cur_run++) {
		for (cur_iter = 0; cur_iter < iters; cur_iter++) {
			recording = cur_iter >= warm;
			prim_mlkem();
			prim_sntrup();
			prim_x25519();
			for (size_t i = 0; i < sizeof methods / sizeof methods[0]; i++)
				if (cur_iter % methods[i].every == 0)
					composed(&methods[i]);
		}
		fflush(out);
		fprintf(stderr, "run %d/%d done\n", cur_run, runs);
	}
	fclose(out);
	return 0;
}
