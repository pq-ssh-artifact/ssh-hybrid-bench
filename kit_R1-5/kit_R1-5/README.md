# Kit R1-5 : réplication des mesures sur deux plateformes supplémentaires

Objectif (point 5 du relecteur 1) : relancer **exactement les mêmes benchmarks** que sur la VM
(opérations + connexions) sur :

| ID | Plateforme | Recommandation |
|----|-----------|----------------|
| `vm` | VM existante (2 vCPU Xeon 2,10 GHz) | déjà mesurée, valeurs de l'article fournies dans `results/vm/` |
| `x86` | **x86-64 physique** (bare metal) | **votre PC Windows démarré sur une clé USB Ubuntu 24.04 live** → voir `LIVE_USB_WINDOWS.md` |
| `arm64` | **ARM64** (VM cloud) | **runner GitHub Actions `ubuntu-24.04-arm`** (gratuit, 4 vCPU, 16 Go) → voir ci-dessous |

> **Pas de WSL2 pour la plateforme x86** : WSL2 tourne dans une VM Hyper-V, ce qui reproduirait la critique
> du relecteur. La clé USB live, elle, s'exécute directement sur le processeur.
>
> **La plateforme ARM64 est virtualisée** : il faut l'écrire honnêtement dans le Tableau 3. Ce n'est pas un problème,
> car ce point du relecteur porte surtout sur le fait d'avoir mesuré une seule plateforme : l'article couvrira alors
> deux architectures, et une plateforme bare metal plus deux virtualisées.

## Plateforme ARM64 via GitHub Actions (aucun matériel nécessaire)

1. **Anonymat (double aveugle)** : les runners arm64 gratuits n'existent que pour les dépôts **publics**.
   Créez un compte GitHub sans votre nom (ou un dépôt au nom neutre), ne mettez dans le dépôt que ce kit et le harnais
   anonymisé, et supprimez le dépôt après avoir récupéré les résultats.
2. Arborescence du dépôt : le contenu de ce kit à la racine + votre harnais dans `harness/`.
3. Ouvrez `.github/workflows/bench-arm64.yml` et adaptez **les deux lignes marquées « à adapter »** :
   l'étape de compilation du harnais, et les commandes `*_CMD` de `config/platform.env.example`.
4. Sur GitHub, ouvrez **Actions > bench-arm64 > Run workflow**. À la fin, téléchargez l'artefact `results-arm64-pass1`.
5. **Faites 2 ou 3 passes** (champ « Numéro de passe »), à des heures différentes. Ces runners sont partagés : si les
   médianes de deux passes diffèrent de plus de quelques %, dites-le dans l'article et retenez la passe à la variance la plus faible,
   ou mieux, rapportez-les toutes en matériel supplémentaire.

Sur ces VM, le gouverneur et le turbo ne sont pas réglables : `02_prepare_host.sh` le note sans échouer.

## Règles de comparabilité (à respecter, et à décrire dans la §4.1)

1. **Même logiciel partout** : Ubuntu 24.04 LTS (donc GCC 13.3 et OpenSSL 3.0.13 depuis les paquets),
   OpenSSH 10.0p2 au commit `2593769f`, `./configure` par défaut. Pas de `-march=native`.
2. **Même harnais, mêmes paramètres** : 5 runs × 500 itérations (10 de chauffe) ; 300/150/100 blocs
   randomisés pour loopback/WAN/contraint ; même relais Python.
3. **Même empreinte CPU** : benchmark d'opérations épinglé sur 1 cœur ; `ssh` + relais + `sshd`
   épinglés sur 2 cœurs (comme les 2 vCPU de la VM).
4. **Fréquence stabilisée** : gouverneur `performance`, turbo désactivé sur x86 ; sur Pi, pas
   d'étranglement thermique (`vcgencmd get_throttled` = `0x0` pendant toute la mesure).
5. **Machine au repos** : rien d'autre ne tourne, pas de session graphique, mises à jour automatiques arrêtées.

## Étapes (sur chaque nouvelle machine)

```bash
# 0. Copier ce kit ET votre harnais (matériel supplémentaire de l'article) sur la machine
cp config/platform.env.example config/platform.env
nano config/platform.env          # PLATFORM_ID=x86 ou arm64, chemins, commandes de VOTRE harnais

./00_install_deps.sh              # dépendances (identiques à la VM)
./01_build_openssh.sh             # OpenSSH 10.0p2, vérifie le commit et les 5 méthodes KEX
# -> recompilez aussi votre harnais d'opérations contre CE build (même commande que pour la VM)
./02_prepare_host.sh              # gouverneur, turbo, services ; journalisé
./03_collect_env.sh               # produit results/<id>/env.json et la ligne du Tableau 3
./04_run_benchmarks.sh all        # ops + loopback + WAN + contraint, avec surveillance thermique
```

Pour chaque phase, `04_run_benchmarks.sh` affiche la fréquence min/max et la température max relevées, et
signale tout étranglement. **Si un étranglement est signalé, la phase est à relancer.**

Puis lancez **votre script d'analyse habituel** sur les données brutes de chaque plateforme et
exportez deux petits résumés au format attendu (les fichiers de `results/vm/` servent d'exemple) :

- `results/<id>/ops_summary.csv` : `operation,unit,median,q1,q3`
- `results/<id>/e2e_summary.csv` : `condition,method,kex_median_ms,dkex_ms,dkex_lo,dkex_hi,total_median_ms,dtotal_ms,dtotal_lo,dtotal_hi`

Enfin, sur n'importe quelle machine :

```bash
python3 05_merge_tables.py vm x86 arm64
```

→ `results/merged/table6.md`, `table7.md` (nouvelles colonnes) et `checks.md`. Ce dernier calcule, pour chaque
plateforme, le ratio de KeyGen sntrup761/ML-KEM, le rapport des médianes à la VM, l'ordre des surcoûts et la
validation du modèle additif ΔT ≈ ΔC + ΔB/b : ce sont exactement les chiffres à reporter dans le texte.
Sur les données de la VM, le script retrouve à l'identique les valeurs du Tableau 8 de l'article.

## Planning indicatif (3 à 5 jours)

| Jour | Tâche |
|------|-------|
| J1 | Clé USB live + mesures x86 sur votre PC ; création du dépôt GitHub anonyme |
| J2 | Workflow ARM64 : 2 à 3 passes à des heures différentes ; relance si anomalie |
| J3 | Analyse avec votre script, résumés CSV, `05_merge_tables.py` |
| J4 | Mise à jour des Tableaux 3, 6, 7, de la §4.1, de la §5.6, de la §6.5 et de la lettre de réponse (voir `INSERTIONS_ARTICLE.md`) |
| J5 | Marge : seconde passe complète pour vérifier la stabilité d'un jour à l'autre (recommandé) |

## À conserver pour le matériel supplémentaire

Pour chaque plateforme, gardez tout le dossier `results/<id>/` : `env.json`, `lscpu.txt`, `host_settings.txt`,
`binaries.sha256`, les journaux, les relevés `monitor/*.csv` et les données brutes. Ces fichiers prouvent au
relecteur que les mesures ont été faites dans des conditions contrôlées.
