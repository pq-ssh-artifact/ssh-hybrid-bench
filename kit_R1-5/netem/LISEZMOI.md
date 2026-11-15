# Action 4 : mesurer sur un vrai réseau (R1-5)

## Ce que fait ce dossier

Le client `ssh` et le serveur `sshd` ne communiquent plus par le relais en espace
utilisateur, mais à travers la **pile TCP/IP du noyau** et **`tc netem`** :

```
 espace de noms "cli"                               espace de noms "srv"
 ssh ─► sonde (0 délai) ─► veth-cli ══ netem ══► veth-srv ─► sshd
        (horodate KEXINIT/NEWKEYS)  ◄══ netem ══
```

- Chaque côté a sa propre pile réseau ; netem s'applique **à chaque paquet IP, dans les deux sens**.
- TCP réagit vraiment : retransmissions, délai de retransmission, contrôle de congestion.
- Client et serveur sont épinglés sur **deux cœurs différents**.
- La sonde n'ajoute aucun délai ; elle mesure la même chose que le relais de l'article
  (KEXINIT client → NEWKEYS client). Vérifié : tailles de messages identiques à l'octet près
  (48 / 1 232 / 1 208 o côté client ; 192 / 1 280 / 1 232 o côté serveur).

Deux conditions :

| Condition | netem (chaque sens) | Rôle |
|---|---|---|
| `netem-clean` | 25 ms, 10 Mbit/s | contrôle : doit retrouver la condition WAN du relais |
| `netem-lossy` | 25 ms ± 5 ms (loi normale), 10 Mbit/s, **1 % de perte** | **nouvelle condition de la Table 7** |

## Lancer sur GitHub

1. Déposez le dossier `netem` dans `kit_R1-5` (Add file → Upload files), et `netem.yml`
   dans `.github/workflows/`.
2. Actions → **netem** → Run workflow (laisser `gh-x86`, `150`, `300`).
3. Récupérez l'artefact `results-netem-gh-x86-pass1` (≈ 45 min).

## Lancer sur deux vraies machines (si un co-auteur en a)

Sur les deux machines : `01_build_openssh.sh`, puis netem sur l'interface reliant les machines :
```
sudo netem/netem_setup.sh host eth0 lossy
```
Serveur : `python3 netem/run_netem.py serve --prefix $HOME/opt/openssh-10.0p2 --bundle /tmp/bundle`
Copier `/tmp/bundle` sur le client, puis :
```
python3 netem/run_netem.py --condition host-lossy --blocks 300 --out results/host \
    --prefix $HOME/opt/openssh-10.0p2 --server-ip IP_DU_SERVEUR --bundle /tmp/bundle
python3 netem/analyze_netem.py results/host
```

## Fichiers produits

| Fichier | Contenu |
|---|---|
| `connections_netem-*.csv` | une ligne par connexion (mêmes colonnes que le harnais + retransmissions TCP) |
| `e2e_summary_netem.csv` | même format que `e2e_summary.csv` |
| `table7_netem.md` | lignes à ajouter à la Table 7 |
| `tails_netem.md` | moyenne, 90ᵉ/99ᵉ centiles, part des connexions retransmises |
| `netem-*/netem_verify.log` | ping de contrôle : preuve que délai, gigue et perte étaient actifs |
| `netem-*/netem_stats.log` | compteurs netem (paquets réellement perdus) |
