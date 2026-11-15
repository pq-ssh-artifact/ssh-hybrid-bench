# Textes à insérer dans l'article (R1-5)

Tous les passages entre crochets `[…]` sont à remplir avec vos mesures (`results/merged/checks.md`,
`table6.md`, `table7.md`, `results/<id>/table3_row.md`). Je n'ai mis aucun chiffre que vous n'ayez pas déjà
mesuré : les seules valeurs présentes sont celles de la VM, déjà publiées dans l'article.

Les passages marqués **[SI…]** sont deux variantes : gardez celle qui correspond à vos résultats.

---

## 1. Tableau 3 : une ligne par plateforme

Remplacez la ligne « Platform » par trois lignes :

| Component | Configuration |
|-----------|---------------|
| Platform A (VM) | Virtual machine, 2 vCPUs of an Intel Xeon processor at 2.10 GHz, 7 GB RAM; [hypervisor / instance type] |
| Platform B (x86-64, bare metal) | [modèle exact du CPU], [n] cores, [fréq.] GHz (turbo disabled), [RAM] GB RAM; Ubuntu 24.04 LTS, Linux [version] |
| Platform C (ARM64, virtual machine) | GitHub-hosted ubuntu-24.04-arm runner, 4 vCPUs of [modèle CPU d'après lscpu.txt], 16 GB RAM; Ubuntu 24.04 LTS, Linux [version] |

Pour la plateforme B, ajoutez « Ubuntu 24.04 LTS live session, no hypervisor ».

Ajoutez à la ligne « Timing » : *« performance governor on all platforms; operation-level harness pinned to one core; ssh, relay and sshd pinned to two cores on Platforms B and C to match the two vCPUs of Platform A »*.

Légende : *Experimental environment, tools and software versions. The same software stack (GCC 13.3.0, OpenSSL 3.0.13, OpenSSH 10.0p2 at commit 2593769f, default flags) was used on the three platforms.*

---

## 2. Tableau 6 : nouvelles colonnes

Structure proposée (le tableau actuel a déjà 4 colonnes : on remplace « IQR » et « Runs » par une colonne par plateforme au format *médiane [IQR]*) :

| Operation | A: VM (µs) | B: x86-64 (µs) | C: ARM64 (µs) |
|-----------|-----------|----------------|---------------|
| ML-KEM-768 KeyGen | 104.3 [98.1–111.8] | [ ] | [ ] |
| ML-KEM-768 Encaps | 99.1 [92.8–105.4] | [ ] | [ ] |
| ML-KEM-768 Decaps | 107.4 [100.9–114.2] | [ ] | [ ] |
| ML-KEM-768 pk validation | 3.0 [2.8–3.3] | [ ] | [ ] |
| sntrup761 KeyGen | 38 129.8 [36 041.9–39 759.6] | [ ] | [ ] |
| sntrup761 Encaps | 916.2 [864.5–959.3] | [ ] | [ ] |
| sntrup761 Decaps | 1 896.0 [1 788.1–1 980.5] | [ ] | [ ] |
| X25519 KeyGen | 1 082.6 [1 018.7–1 135.7] | [ ] | [ ] |
| X25519 shared secret | 1 076.5 [1 015.9–1 129.3] | [ ] | [ ] |
| **Composed key exchange, both sides (ms)** | | | |
| mlkem768x25519-sha256 | 4.64 | [ ] | [ ] |
| sntrup761x25519-sha512 | 45.39 | [ ] | [ ] |
| curve25519-sha256 | 4.31 | [ ] | [ ] |
| ecdh-sha2-nistp256 | 0.41 | [ ] | [ ] |
| diffie-hellman-group14-sha256 | 4.97 | [ ] | [ ] |

Légende : *Operation-level cost in OpenSSH 10.0p2 on the three platforms of Table 3: median [IQR] over 2 450 samples per operation and platform. The standard deviation of the five run medians was at most [x]% of their mean on every platform; per-run values are given in the supplementary material.*

> La colonne « Runs (mean ± std) » disparaît du tableau, mais l'information reste dans la légende (max %) et dans le matériel supplémentaire. Si la revue tolère un tableau en pleine largeur, vous pouvez la garder pour la VM seulement.

---

## 3. Tableau 7 : nouvelles colonnes

Le Tableau 7 a déjà 7 colonnes : ajouter deux plateformes × (KEX + total) le rendrait illisible. Je propose de
remplacer la colonne « p (KEX) » (à reporter dans la légende) et la colonne « Total median » (visible sur la Fig. 7)
par deux colonnes **Δ KEX** pour B et C :

| Condition | Method | KEX median A | Δ KEX A [95% CI] | Δ KEX B [95% CI] | Δ KEX C [95% CI] | Δ total A [95% CI] |
|-----------|--------|--------------|------------------|------------------|------------------|--------------------|
| Loopback | mlkem768x25519 | 12.94 | 0.49 [0.20, 0.77] | [ ] | [ ] | 0.53 [0.12, 1.05] |
| | sntrup761x25519 | 56.53 | 43.90 [43.50, 44.67] | [ ] | [ ] | 43.95 [43.43, 44.62] |
| | curve25519 (ref.) | 12.40 | – | – | – | – |
| | ecdh-p256 | 7.56 | −4.79 [−4.98, −4.56] | [ ] | [ ] | −4.67 [−5.27, −4.11] |
| | dh-group14 | 11.53 | −0.88 [−1.04, −0.65] | [ ] | [ ] | −0.80 [−1.16, −0.51] |
| WAN | … (mêmes lignes) | | | | | |
| Constrained | … | | | | | |

Légende : *End-to-end results. KEX median (ms) and paired median difference vs. curve25519-sha256 with 95% bootstrap CI, on Platform A and, for the key exchange, on Platforms B and C. All Holm-adjusted Wilcoxon p-values are below [2 × 10⁻⁴] except [à vérifier sur B et C]. The complete per-platform tables (medians, total times and p-values) are given in the supplementary material. Loopback: 300 blocks; WAN: 150 blocks; constrained: 100 blocks, on every platform.*

---

## 4. §4.1 Development environment : paragraphe à ajouter

> *To assess whether the measurements depend on the platform, all benchmarks were repeated on two additional machines (Table 3): a bare-metal x86-64 machine (Platform B), booted from an Ubuntu live image so that no hypervisor was involved, and a 64-bit ARM virtual machine (Platform C, a GitHub-hosted ubuntu-24.04-arm runner). Because Platform C runs on shared infrastructure, its benchmarks were repeated in [n] independent passes at different times; the medians of the passes differed by at most [x]%. The three platforms ran the same software stack (Ubuntu 24.04 LTS, GCC 13.3.0, OpenSSL 3.0.13 and OpenSSH 10.0p2 built from the same commit with the same default flags, without architecture-specific tuning), the same harness and the same numbers of runs and blocks. On Platform B, the CPU frequency governor was set to performance and turbo boost was disabled; on all platforms, the operation-level harness was pinned to one core, and the ssh client, the relay and sshd were pinned to two cores to match the two vCPUs of Platform A. CPU frequency and temperature were sampled every 2 s during each run; no thermal throttling occurred [à confirmer avec monitor/*.csv].*

(N'oubliez pas de remplacer aussi le passage surligné « [Authors: please specify the hypervisor…] » pour la plateforme A.)

---

## 5. §5.6 « Transfer to other platforms » : paragraphe de remplacement

Remplacez le paragraphe actuel, qui commence par « Because all measurements come from one two-vCPU virtual machine… », par :

> ***Transfer to other platforms.*** *Table 6 and Table 7 repeat the measurements on a bare-metal x86-64 machine (B) and an ARM64 virtual machine (C). Absolute times differ across platforms: relative to Platform A, the median cost of the primitives ranges from [×a] to [×b] on Platform B and from [×c] to [×d] on Platform C. The structure of the cost, however, is preserved. On every platform, sntrup761 key generation is the most expensive operation, [x]× (A: 366×; B: [y]×; C: [z]×) the cost of ML-KEM-768 key generation, and the ML-KEM hybrid is dominated by X25519 rather than by its KEM operations. The ordering of the methods by key-exchange overhead on loopback is identical on the three platforms ([ordre]). The additive model of Section 3.7 also transfers: using each platform's own loopback difference and the same serialization times, it predicts the WAN and constrained overheads of the ML-KEM hybrid within [x] ms on Platform B and [y] ms on Platform C, and slightly overestimates those of the sntrup761 hybrid (by at most [x] ms), as on Platform A. An operator can therefore still estimate the overhead on an unmeasured platform by timing one sntrup761 or ML-KEM key generation locally and adding the serialization time of about 2.2 KB on the link of interest.*

**[SI l'ordre ou le modèle additif ne se vérifient PAS sur une plateforme]** remplacez les deux phrases concernées par une description factuelle de l'écart et de sa cause probable (par exemple : sur ARM64, OpenSSL utilise une implémentation assembleur de P-256, alors que X25519 reste la version portable d'OpenSSH ; cela peut déplacer `ecdh-p256` par rapport à `curve25519`). Un écart expliqué honnêtement vaut mieux qu'un résultat lissé.

---

## 6. §6.5 Limitations : passage à modifier

Supprimez l'idée « all measurements come from one virtual machine / other CPU architectures may change the magnitudes » et remplacez-la par :

> *The measurements cover three platforms and two architectures (x86-64 and ARM64), one of them bare metal, but all use the portable C implementations shipped with OpenSSH. Vectorized implementations of either KEM (e.g., AVX2 on x86-64 or NEON on ARM64), microcontroller-class devices, and links with packet loss may change the magnitudes and are left for future work.*

---

## 7. Résumé / contributions : une phrase à ajuster

Là où le résumé ou la liste des contributions mentionne la mesure, ajoutez : *« …measured on three platforms (two x86-64 platforms, one of them bare metal, and an ARM64 platform)… »*.

---

## 8. Lettre de réponse : R1, point 5

> **Response.** *We thank the reviewer for this comment. In addition to the transfer method of Section 5.6, we have now repeated every benchmark, at the operation level and for complete connections under the three network conditions, on two additional platforms: a bare-metal x86-64 machine and an ARM64 virtual machine (Table 3). The same software stack, harness and sample sizes were used, CPU frequency was fixed on the bare-metal machine, the ARM64 runs were repeated to control for shared-infrastructure noise, and CPU frequency and temperature were monitored. The new results are reported as additional columns in Tables 6 and 7, and the complete per-platform data are provided in the supplementary material. Absolute times vary by a factor of [range] across platforms, but the conclusions of the paper hold on all three: [the ordering of the methods is unchanged, sntrup761 key generation remains [y–z]× more expensive than ML-KEM key generation, and the additive model predicts the overhead on the emulated links within [x] ms]. Sections 4.1, 5.6 and 6.5 have been updated accordingly.*
