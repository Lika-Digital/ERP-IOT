# deploy/ — instalacija ERP-IOT na VPS (faza 5b)

Skripte za ponovljivu instalaciju po runbooku iz `docs/erp_spec.md` §8.4.
Izvodi ih **operater** na VPS-u, kao korisnik `lika`, jedan korak u isto vrijeme;
ispis svakog koraka se provjeri prije sljedećeg.

Repo na VPS-u (javni, samo za čitanje):

    git clone --branch faza/5b-vps https://github.com/Lika-Digital/ERP-IOT.git ~/erp-iot
    git -C ~/erp-iot pull        # prije svakog sljedećeg koraka

| Korak | Skripta | Mijenja sustav? |
|---|---|---|
| 1 | `01_stanje.sh` — snimka stanja | ne, samo čita |
