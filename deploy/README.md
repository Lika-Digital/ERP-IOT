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

Datoteke koje koraci instaliraju (ne instalira ih repo):

| Datoteka | Korak | Što je |
|---|---|---|
| `erp-iot.service` | 9 | backend, uvicorn na `127.0.0.1:8000`, tajne iz systemd credentials, baza `erp_iot` preko socketa |
| `erp-run` | 8, 14 | `sudo deploy/erp-run <naredba>` — jedna naredba kao aplikacija (korisnik `erp`, iste tajne), npr. `alembic upgrade head` |
| `erp-agent.service` | 10 | agent D21, bez mreže |
| `erp-sim.service` | — | demo simulator; **ne instalira se u prvom testu** (v25, P-4) |
