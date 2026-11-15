# Harnais de mesure (réimplémentation conforme à la §3 de l'article)

| Fichier | Rôle | Correspondance dans l'article |
|---------|------|-------------------------------|
| `bench_ops.c` | Harnais C lié aux bibliothèques statiques d'OpenSSH 10.0p2 (`libssh.a`) : 9 primitives (libcrux ML-KEM-768, sntrup761, X25519) et, pour les 5 méthodes, les 3 étapes composées (keypair client, encapsulation serveur avec DH et hachage, décapsulation client avec DH et hachage) = 24 opérations, correction vérifiée à chaque itération, `CLOCK_MONOTONIC_RAW`, DH group14 chronométré une itération sur dix | Algorithme 1, Tableau 6 |
| `build.sh` | Compile `bench_ops` avec les mêmes CFLAGS que l'arbre OpenSSH | §4.2 |
| `run_connections.py` | Vrai `ssh` → relais → vrai `sshd` (clé hôte Ed25519, auth. par clé Ed25519, chacha20-poly1305). Le relais analyse les paquets en clair jusqu'à NEWKEYS, horodate les messages 20/30/31/21, mesure leur taille, et émule le chemin en store-and-forward (`max(t, t_free) + l/b + d`) avec un fil de livraison par sens et `clock_nanosleep` absolu. Blocs complets randomisés, graines 1/2/3, une connexion de chauffe par méthode | Algorithme 2, Tableaux 7 et 8 |
| `analyze.py` | Médianes et IQR, variabilité entre runs ; Friedman, Wilcoxon apparié par bloc avec correction de Holm, différence médiane appariée avec IC bootstrap à 95 % (10 000 rééchantillonnages) | §4.3 |

Utilisation autonome :
```bash
bash build.sh ~/src/openssh-portable
taskset -c 1 ./bench_ops 5 500 10 out/ops/ops.csv
taskset -c 0,1 python3 run_connections.py --condition loopback --blocks 300 --seed 1 --prefix ~/opt/openssh-10.0p2 --out out/e2e
python3 analyze.py out
```
