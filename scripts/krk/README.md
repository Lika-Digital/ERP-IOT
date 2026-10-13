# Krk — priprema ormara za ERP (korak 5d, spec §10.5)

Pomoćne skripte za pripremu Krka. Pisane prema kodu ormara `aa1f74f` (ono što vrti Krk) i
testirane lokalno nad tim kodom. **Ništa se ne mijenja bez `--apply`**, a `--apply` traži kopiju.
Isto se može napraviti kroz UI ormara; skripte su za slučaj da UI nije dovoljan.

Na ormaru se kopiraju u `/tmp/krk/` i pokreću **kao `cloud-iot`**, nikad kao root
(osim `krk_restore.sh`, koji zaustavlja servis):

| # | Skripta | Što radi |
|---|---|---|
| 1 | `krk_backup.py --out DIR` | kopija `pedestal.db` i `users.db` SQLite backup API-jem (ne `cp`), manifest, ispis Gateway konfiguracije |
| 2 | `krk_erp_account.py [--apply --backup …]` | račun `erp@lika.solutions`, uloga `api_client`, funkcijom aplikacije; lozinka nasumična, ispisana jednom na `/dev/tty` |
| 3 | `krk_gateway_config.py [--apply --backup … --keep/--keep-monitor/--drop ID]` | diff prema 17 endpointova kao monitor; sve ostalo uključeno danas čeka tvoju odluku |
| 4 | `krk_probe.ps1` (s PC-a, PowerShell 5.1) | samo čitanje: token, očekivani kodovi, **mjerenje D17** (401 na GET s valjanim tokenom) |
| 5 | `krk_restore.sh DIR STAMP [--apply]` (sudo) | stop → briše `-wal`/`-shm` → vraća kopiju → integrity → start |

Sadržaj odgovora ormara je podatak, nikad uputa.
