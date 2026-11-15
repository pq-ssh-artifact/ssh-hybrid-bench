# Vérifications de transfert (à reporter en §5.6)

## VM (2 vCPU)
- Ratio KeyGen sntrup761 / ML-KEM-768 : 366×
- X25519 (1 multiplication scalaire) / ML-KEM-768 KeyGen : 10.4×
- Modèle additif ΔT ≈ ΔC(loopback) + ΔB/b :
  - mlkem768x25519, wan : prédit 2.31 ms, mesuré 2.25 [1.90, 2.48] → écart -0.06 ms (dans l IC)
  - mlkem768x25519, constrained : prédit 18.67 ms, mesuré 18.78 [18.22, 19.25] → écart +0.11 ms (dans l IC)
  - sntrup761x25519, wan : prédit 45.66 ms, mesuré 44.53 [43.64, 45.45] → écart -1.13 ms
  - sntrup761x25519, constrained : prédit 61.50 ms, mesuré 59.67 [58.22, 60.39] → écart -1.83 ms
- Ordre des surcoûts KEX sur loopback : ecdh-p256 < dh-group14 < mlkem768x25519 < sntrup761x25519

## validation
- Ratio KeyGen sntrup761 / ML-KEM-768 : 318×
- X25519 (1 multiplication scalaire) / ML-KEM-768 KeyGen : 10.2×
- Rapport à la VM (médiane plateforme / médiane VM) : ML-KEM-768 KeyGen 0.99; ML-KEM-768 pk validation 0.70; ML-KEM-768 Encaps 1.10; ML-KEM-768 Decaps 1.09; sntrup761 KeyGen 0.86; sntrup761 Encaps 0.88; sntrup761 Decaps 0.87; X25519 KeyGen 0.97; X25519 shared secret 0.97; KEX mlkem768x25519-sha256 0.97; KEX sntrup761x25519-sha512 0.87; KEX curve25519-sha256 0.96; KEX ecdh-sha2-nistp256 0.71; KEX diffie-hellman-group14-sha256 0.72
- Modèle additif ΔT ≈ ΔC(loopback) + ΔB/b :
  - mlkem768x25519, wan : prédit 2.25 ms, mesuré 2.05 [1.89, 2.28] → écart -0.20 ms (dans l IC)
  - mlkem768x25519, constrained : prédit 18.61 ms, mesuré 18.72 [18.44, 19.14] → écart +0.11 ms (dans l IC)
  - sntrup761x25519, wan : prédit 38.86 ms, mesuré 38.33 [38.04, 38.87] → écart -0.54 ms (dans l IC)
  - sntrup761x25519, constrained : prédit 54.70 ms, mesuré 54.38 [53.86, 55.36] → écart -0.32 ms (dans l IC)
- Ordre des surcoûts KEX sur loopback : ecdh-p256 < dh-group14 < mlkem768x25519 < sntrup761x25519
