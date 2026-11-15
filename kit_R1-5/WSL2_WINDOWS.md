# Tout faire sur votre PC Windows avec WSL2 (Ubuntu 24.04)

WSL2 fait tourner un vrai noyau Linux sur votre processeur, dans une machine virtuelle légère (Hyper-V).
Les mesures sont valables, mais dans le Tableau 3, la plateforme doit être décrite comme
« WSL2 (Hyper-V) on [modèle du CPU], Windows 11 » et non comme une machine physique.

## 1. Installer Ubuntu 24.04 (une fois, environ 10 min)
Dans **PowerShell en administrateur** :
```powershell
wsl --install -d Ubuntu-24.04
```
Redémarrez si Windows le demande, puis ouvrez « Ubuntu 24.04 » dans le menu Démarrer et créez un utilisateur.

## 2. Réserver des ressources stables
Dans l'Explorateur, créez le fichier `C:\Users\<vous>\.wslconfig` avec :
```ini
[wsl2]
processors=4
memory=8GB
```
puis, dans PowerShell : `wsl --shutdown` (WSL redémarre avec ces réglages).

## 3. Côté Windows, pendant toute la mesure
- PC **branché sur secteur**, mode d'alimentation **« Meilleures performances »**.
- Fermez navigateur, Teams, antivirus en analyse, OneDrive, etc. Mise en veille désactivée.
- Ne touchez plus au PC pendant que les mesures tournent.

## 4. Lancer les mesures (dans le terminal Ubuntu)
Le kit (harnais inclus) doit être copié **dans le système de fichiers Linux** (`~/`), pas dans `/mnt/c/` : ce dossier est beaucoup plus lent.
```bash
cp -r /mnt/c/Users/<vous>/Downloads/kit_R1-5 ~/
cd ~/kit_R1-5
cp config/platform.env.example config/platform.env
nano config/platform.env       # PLATFORM_ID=x86
./00_install_deps.sh
./01_build_openssh.sh
./02_prepare_host.sh           # le gouverneur n'est pas réglable sous WSL : c'est noté, pas bloquant
./03_collect_env.sh
./04_run_benchmarks.sh all
cp -r results/x86 /mnt/c/Users/<vous>/Downloads/   # récupérer les résultats sous Windows
```
Faites **deux passes complètes** (par exemple un soir et le lendemain matin) pour vérifier la stabilité.

## 5. Si votre PC a un processeur ARM (Snapdragon X, etc.)
Exactement les mêmes étapes : WSL2 est alors une plateforme **ARM64**. Mettez `PLATFORM_ID=arm64`.
