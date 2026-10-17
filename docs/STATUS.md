# ERP-IOT · stanje za sutra

Zadnje ažuriranje: 2026-10-17 (nakon koraka 6; korak 7 pripremljen). Prioritet: **5b VPS**, korak po korak, prema `erp_spec.md` §10.15.

## Gdje smo

| Grana | Stanje | Što je na njoj |
|---|---|---|
| `main` | `b00ff59`, spec v25 | faza 6 zatvorena na 6b; na VPS-u u `/opt/erp-iot` |
| `faza/5b-vps` | pushana | spec **v25.2**, `deploy/01`–`07`, `slusaci.sh`, uklonjen `usage.history`, §2.3 = 17 |
| `spec/v3-moduli` | pushana | spec **v30** (v3 prijedlog, D32), odgovori mobilnoj v1 i v2, pitanja ormaru o kameri |

## 5b VPS — koraci

Redoslijed (v25.1, tvoja odluka): **1, 2, 5–12, 14–17 → ormar → 5d čitanje → 3, 4 → 17 → 5c.**
Nakon svakog koraka `slusaci.sh` (javno samo `:22`).

| # | Korak | Stanje |
|---|---|---|
| 1 | snimka stanja | ✔ 2026-10-16 |
| 2 | UTC, NTP, swap 1 GB, sigurnosna ažuriranja, DNS | ✔ 2026-10-16 |
| 5 | PostgreSQL 16: samo socket, peer, `erp` / `erp_agent`, `erp_iot`, bez TEMPORARY | ✔ 2026-10-17 |
| 6 | korisnici `erp` i `erp-agent`, `/opt/erp-iot` = `main` `b00ff59`, venv iz locka (57/57, `pip check` čist) | ✔ 2026-10-17, potvrđeno |
| **7** | **sljedeći:** `07_tajne.sh` — `JWT_SECRET` i `ERP_ENCRYPTION_KEY` generirani na stroju, šifrirani sa `systemd-creds` (`/etc/erp-iot/*.cred`, root 0700/0600), `erp-iot.env` s Tailscale IP-om; provjera da ih `erp` dobiva samo preko systemd-a | **čeka tvoj OK za pokretanje** |
| 8 | `alembic upgrade head` → 015, `alembic check`, probe sheme, AGT-01 | — |
| 9 | `erp-iot.service` na `127.0.0.1:8000`; P3 namjerno (`downgrade -1` → start pada → `upgrade head`) | — |
| 10 | agent D21 (`erp-agent.service`, bez mreže) | — |
| 11 | `dist` iz CI artefakta `main`a, `sha256` jednak CI-ju | — |
| 12 | nginx samo na Tailscale IP `:80` (ukloniti zadani site na `0.0.0.0:80`), O43 | — |
| 14 | prvi admin (`erp-setup-admin`), 2FA | — |
| 15–16 | backup `pg_dump` + `age`, probna obnova | — |
| 17 | `verify_system.sh` | — |
| 3, 4 | vatrozid (`03_vatrozid.sh`, **necommitan**, javno `:22` dopušten) i Tailscale ACL | **na kraju**, prije 5c |

Uloge: ti pokrećeš skriptu i šalješ ispis, ja provjeravam. Ja se na VPS ne spajam.

## Čeka tvoju odluku

- **Trojke v3** u `spec/v3-moduli`: T-1…T-22 (odgovor mobilnoj v1) i T-23…T-30 (v2), §14 i §10.16.
- **§1.5–§1.24**: dvadeset otvorenih pitanja v3.
- **Novi ulaz A–G** (D33 glavni dashboard, Environmental, termo kamera, simulator kao zasebna
  aplikacija, čuvar opterećenja, tri vrste alarma, Admin Config, zahtjevi kupaca i zaposlenika):
  moj komentar je poslan, spec se piše tek nakon tvog odobrenja.

## Čeka druge

- **Ormar:** odgovori na osam pitanja o `camera.live_*` (`docs/inputs/pitanja_ormaru_kamera_v1.md`
  na `spec/v3-moduli`); `api_client` račun i 17 ključeva za prvi test (§10.15 točka 5).
- **Mobilna:** odgovor na ERP v2 (H-1…H-15).

## Male stavke, zapisane

- **Prije 5c:** odvojeni produkcijski lock (v25.2), koraci 3 i 4.
- **Iz §10.15 točka 1, još otvoreno:** P-5 (ERP odbija upis vlasnika u pravoj marini dok O67 nije
  izveden), `scripts/live_check.py` (prolazi protiv simulatora), jednokratna CI provjera.
- `docs/inputs/odgovor_mobilne_v1.md` leži necommitan u `erp-iot-d21` (commitan je na
  `spec/v3-moduli`); može se obrisati.

## Pravila koja vrijede

Spec prvo (pregled → trojka → odobrenje → kod). Bez `--no-verify`. `main` samo `--ff-only` i
`CLOUD_IOT_RELEASE=1 git push origin main`. Simulator na 18080 je tvoj. Simulirani podaci nikad u
naplatu, izvještaje ni agenta kao stvarni (D28). Bez osobnih podataka u specu i testovima.
