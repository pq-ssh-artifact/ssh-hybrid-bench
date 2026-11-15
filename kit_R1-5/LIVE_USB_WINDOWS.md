# Mesures x86 « bare metal » depuis votre PC Windows (clé USB Ubuntu live)

Ubuntu démarre depuis la clé et s'exécute directement sur votre processeur, sans hyperviseur.
Rien n'est installé sur le disque : au redémarrage, vous retrouvez Windows tel quel.

## Matériel
- Une clé USB de 8 Go ou plus (son contenu sera effacé).
- Une **deuxième** clé USB (ou un compte en ligne) pour récupérer les résultats : la session live s'efface à l'extinction.
- PC **branché sur secteur** (sur batterie, la fréquence du processeur varie).

## Préparation sous Windows (environ 20 min)
1. **BitLocker** : si votre disque est chiffré (Paramètres > Confidentialité et sécurité > Chiffrement de l'appareil),
   notez votre **clé de récupération** (https://account.microsoft.com/devices/recoverykey). Démarrer sur une clé USB
   peut la faire demander au retour sous Windows.
2. Téléchargez l'image **Ubuntu 24.04 LTS Desktop** (https://ubuntu.com/download/desktop).
3. Écrivez-la sur la clé avec **Rufus** (https://rufus.ie) : sélectionnez l'ISO, schéma GPT, cible UEFI, puis Démarrer.
4. Copiez sur la **deuxième** clé : ce kit (`kit_R1-5`, harnais inclus).

## Démarrage
5. Redémarrez en maintenant **Maj** : Dépannage > Options avancées > Changer les paramètres du microprogramme UEFI,
   ou appuyez sur la touche du menu de démarrage du fabricant au démarrage (F12, F9, Échap…).
   Choisissez la clé USB, puis **« Try Ubuntu »** (surtout pas « Install »).
6. Connectez-vous au réseau, ouvrez un terminal (Ctrl+Alt+T) et copiez le kit dans `~/` depuis la deuxième clé.

## Mesures
```bash
cd ~/kit_R1-5
cp config/platform.env.example config/platform.env
nano config/platform.env      # PLATFORM_ID=x86
sudo add-apt-repository -y universe
./00_install_deps.sh
./01_build_openssh.sh
./02_prepare_host.sh          # gouverneur performance + turbo désactivé
./03_collect_env.sh
./04_run_benchmarks.sh all    # ne touchez plus au PC pendant la mesure ; désactivez la mise en veille avant
```
Désactivez la mise en veille avant de lancer : Paramètres > Énergie > Écran vide = Jamais.

7. **Copiez `results/x86/` sur la deuxième clé avant d'éteindre.**

## Remarques
- Avec 8 Go de RAM ou plus, la session live suffit largement (la compilation d'OpenSSH prend quelques minutes).
- Si le PC est un portable, choisissez le mode d'alimentation « Performance » et surveillez les messages d'étranglement thermique de `04_run_benchmarks.sh`.
- Dans le Tableau 3, indiquez le modèle exact du processeur (`results/x86/lscpu.txt`) et « bare metal, Ubuntu 24.04 live session ».
