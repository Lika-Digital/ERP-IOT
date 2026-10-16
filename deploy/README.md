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
| 2 | `02_osnova.sh` — UTC, NTP, swap 1 GB (swappiness 10), sigurnosna ažuriranja; DNS samo provjerava | da; ponovljivo, povratak ispiše na kraju |
| 5 | `05_postgres.sh` — PostgreSQL 16 samo na socketu, pg_hba samo peer, uloge `erp` i `erp_agent`, baza `erp_iot`, bez TEMPORARY za PUBLIC | da; ponovljivo, povratak ispiše na kraju |
| 6 | `06_aplikacija.sh` — korisnici `erp` i `erp-agent` (bez prijave), provjera peer prijave, `/opt/erp-iot` = `main` (vlasnik root), venv iz `requirements.lock` | da; ponovljivo, povratak ispiše na kraju |
| — | `slusaci.sh` — `ss -ltn` po pravilu v25.1 (javno samo :22); svaki korak ga zove na kraju | ne, samo čita |

**Redoslijed (spec v25.1, §10.15):** 1, 2, 5–12, 14–17 → test čitanja s pravim ormarom →
3 (vatrozid) i 4 (Tailscale ACL) → 17 ponovno → tek onda 5c. Koraci 3 i 4 su uvjet za svako
javno izlaganje.

Datoteke koje koraci instaliraju (ne instalira ih repo):

| Datoteka | Korak | Što je |
|---|---|---|
| `erp-iot.service` | 9 | backend, uvicorn na `127.0.0.1:8000`, tajne iz systemd credentials, baza `erp_iot` preko socketa |
| `erp-run` | 8, 14 | `sudo deploy/erp-run <naredba>` — jedna naredba kao aplikacija (korisnik `erp`, iste tajne), npr. `alembic upgrade head` |
| `erp-agent.service` | 10 | agent D21, bez mreže |
| `erp-sim.service` | — | demo simulator; **ne instalira se u prvom testu** (v25, P-4) |
