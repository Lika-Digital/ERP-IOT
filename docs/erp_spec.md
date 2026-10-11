# ERP-IOT · Specifikacija za odobrenje

Što se gradi, u kojem redoslijedu, i svaka odluka izrečena tako da ispravak
košta jedan redak, a ne razgovor.

    Verzija 1 — prva specifikacija ovog repoa
    Datum 2026-10-11
    Status nijedna linija aplikacijskog koda nije napisana

Čita se uz `docs/inputs/odluke.md` (odluke, obvezujuće),
`docs/inputs/ormar_gateway_izvjestaj.md` (stvarni ugovor s ormarom, file:line),
`docs/inputs/erp_inventar.md` (stanje repoa 2026-10-10) i
`docs/inputs/ormar_ui_v2_spec.txt` (specifikacija ormara — uzor forme i izvor rječnika stanja).

**Sve u ovom dokumentu je ODLUČENO osim onoga u §1.**

Dvije stvari odsutne po odluci: **QR** — nema zaslona, nema polja; NFC je jedini put ulaska
korisnika (D6). **Vlastiti MQTT** — ERP ne gradi brokera (D12, D17).

---

## Napomena o metodi

Svaka tvrdnja o kodu niže nosi `file:line`, provjerenu u repou **danas, 2026-10-11**.
Putanje bez prefiksa su u `Lika-Digital/ERP-IOT`; putanje ormara nose prefiks `Cloud_IOT/`.
Repo ormara je **samo čitan** — nijedna izmjena, sve što ERP od njega traži je u §7 kao zahtjev.

Brojke su mjerene, ne procijenjene. Metoda je uz svaku brojku. Gdje je inventar od
2026-10-10 pogrešan, ispravak je u §0 i označen je kao ispravak, ne tiho primijenjen.

---

## §0 Ispravci ulaznih dokumenata

Tri tvrdnje iz ulaza ne drže se uz kod ili uz mjerenje. Navodim ih, ne primjenjujem tiho.

### §0.1 · ISPRAVAK — nema 7 testova koji padaju. Padaju nula.

`odluke.md` D17 faza 1 traži „7 testova koji padaju", a D13 navodi „HTTPBearer vraća 403
umjesto 401" među poznatim rupama. Inventar (`docs/inputs/erp_inventar.md:46-48`) tvrdi isto.

**Izmjereno danas:**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q
→ 96 passed in 5.75s
```

Nula padova. Uzrok nije ispravljen kod — `backend/app/routers/auth.py:21` je `_bearer = HTTPBearer()`
i **nepromijenjen od prvog commita** (`git log -- backend/app/routers/auth.py` → samo `cd838d9`;
`git show cd838d9:backend/app/routers/auth.py` ima isti redak). Promijenila se ovisnost:

```
fastapi 0.135.3  →  HTTPBase.make_not_authenticated_error()
                    raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, …)
```

(mjereno: `inspect.getsource(HTTPBearer.__call__)` i `HTTPBase.make_not_authenticated_error`
u `backend/.venv`). U travnju je ta ista linija davala 403; danas daje 401, jer
`backend/requirements.txt` ne pinuje ništa osim `bcrypt==4.0.1`.

**To je najjači argument za pinanje koji imamo, i nije hipotetski — već se dogodio.**
Ponašanje autentifikacije se promijenilo pod repoom bez ijednog commita. Ovaj put u korist.

Ostaje stvarni posao, i manji je od zapisanog: **dva testa tolerantna su na stari bug** i
moraju se pritegnuti na 401 — `backend/tests/test_auth.py:99` i
`backend/tests/test_pedestal_ext.py:300`, oba `assert r.status_code in (401, 403)`
(mjereno: `grep -rn "in (401, 403)" backend/tests/*.py` → 2 pogotka). Trinaest preostalih
`403` assertiona (`grep -rho '403' backend/tests/*.py | wc -l` → 13) su RBAC-403 —
`marina_manager` odbijen na tuđoj marini — i **ispravni su**; ne diraju se.

> **Odlučeno** · Faza 1 ne „popravlja 7 testova", nego pinuje ovisnosti i pritegne dva
> tolerantna assertiona na točan kod.
>
> **Zašto** · Bug koji se sam popravio promjenom ovisnosti popravit će se i pokvariti
> ponovno. Pinana lock datoteka čini ponašanje činjenicom repoa, a ne ishodom dana kad je
> netko zadnji pokrenuo `pip install`.
>
> **Ako griješim** · Ako je negdje verzija FastAPI-ja starija i 403 se vrati, pritegnuti
> testovi padaju odmah i glasno — što je upravo svrha. Jedan redak u `auth.py:21`
> (`HTTPBearer(auto_error=False)` + vlastiti 401) zatvara to neovisno o verziji.

### §0.2 · ISPRAVAK — build danas prolazi; boot gate ima što testirati

Inventar ne tvrdi suprotno, ali ni ne mjeri. Izmjereno:

```
frontend/node_modules/.bin/tsc --noEmit   → exit 0
frontend/node_modules/.bin/vite build     → exit 0, 908 modula
                                            dist/assets/index-*.js 646.34 kB (gzip 189.42 kB)
                                            dist/assets/index-*.css 23.27 kB
```

Znači: boot gate iz §9 gradi se na bundle koji danas postoji. `frontend/dist/` je u
`.gitignore:66`, pa build ne ostavlja praćene artefakte.

### §0.3 · ISPRAVAK — `odluke.md` nema D18; prompt ga citira

Prompt traži „mapiranje vez→priključak na obje strane s usporedbom (D18)" i opisuje ulaz kao
„dnevnik odluka v2.1, D0–D18". Datoteka u `docs/inputs/odluke.md` je **Verzija 2** i sadrži
**D0–D17** (mjereno: `grep -cE "^## D[0-9]+" docs/inputs/odluke.md` → 18 unosa, D0 do D17).
D18 ne postoji; `grep -n "D18"` → nula pogodaka.

Najbliži sadržaj je D1 + BLOK-1 opcija (c) „oba, s usklađivanjem". Gradim §4 tako da
**usporedba postoji kao stupac i kao test**, jer to prompt izrijekom traži — ali to
pretpostavlja da BLOK-1 završi kao (b) ili (c). Pod (a) je stupac mrtav teret.

> Ne odlučujem umjesto tebe: ovo je zapisano u §1.2, ne riješeno ovdje.

### §0.4 · Izmjerene brojke repoa (zamjenjuju procjene iz inventara)

| Mjera | Vrijednost | Mjereno kako |
|---|---|---|
| Praćene datoteke | 90 | `git ls-files \| wc -l` |
| Praćeni redci, ukupno | 10 572 | `git ls-files \| xargs wc -l` |
| py / tsx / ts | 5 432 / 3 082 / 581 | isto, po ekstenziji |
| sh / md / conf / yml / json / css | 485 / 478 / 88 / 68 / 61 / 59 | isto |
| Testne funkcije | 96 | `grep -c "def test_" backend/tests/*.py` |
| Testovi koji padaju | **0** | `pytest -q` (§0.1) |
| `Dockerfile` u repou | **0** | `git ls-files \| grep -i docker` → prazno |
| CI konfiguracija | **nema** | `ls .github` → ne postoji |
| Linter konfiguracija | **nema** | nema ruff/eslint konfiguracije; `run_tests.sh` ne zove ni jedan |
| Git gate | lokalni, neverzioniran | `.git/hooks/pre-push` postoji; `.githooks/` ne; `core.hooksPath` nije postavljen |
| Instalirani fastapi / sqlalchemy / pydantic | 0.135.3 / 2.0.49 / 2.12.5 | `pip list` u `backend/.venv` |
| Bandit: high / medium / low | **0 / 1 / 2** na 2 270 redaka | `tests/run_tests.sh` stage 2, pri commitu ove specifikacije; medium je B104 `config.py:16` → §8.1 |
| Zaštićene rute / ukupno ruta | 23 / 30 | `grep -rho "Depends(get_current_user)" backend/app/routers/*.py \| wc -l` |
| `try` blokova u `routers/controls.py` | **0** | `grep -c "try:"` — zato §2.5 |

---

## §1 Blokirajuće

Pet odluka. Nijedna ne blokira ovu specifikaciju; svaka blokira točno navedeni dio izvedbe.
Uz svaku je što blokira **i što ne blokira**, jer je to razlika između „stani" i „nastavi".

### §1.1 · BLOK-2 — ručno paljenje iz ERP dashboarda nakon 2026-11-30

Od `nfc_cross_check_required = True` svaki `socket_cmd activate` bez `nfc_tag_id` vraća **400**
(`Cloud_IOT/backend/app/config.py:194` — zastavica, danas `False`, komentar „REQUIRED FROM:
2026-11-30"; provjera u `Cloud_IOT/backend/app/routers/controls.py:600-606`). Na Krku
(`773bca6`) polje se danas **tiho odbacuje** — Pydantic `extra='ignore'` — pa ERP koji ga već
šalje ne dobiva nikakvu potvrdu da ga netko čita.

Pitanje: smije li operater marine iz ERP-a upaliti struju bez da je gost skenirao naljepnicu?

| Opcija | Što ERP radi | Cijena |
|---|---|---|
| **(a)** Dopušteno, ERP šalje tag iz vlastitog mapiranja | jedan redak u klijentu: `nfc_tag_id` iz `outlet_nfc_tags` za taj priključak | 1 redak koda + 1 polje u auditu (`actor_type`, `tag_source`) |
| **(b)** Nije dopušteno | kontrola se nakon tog datuma **ne iscrtava**, uz jednu rečenicu | 1 zastavica + 1 rečenica; osoblje koristi dashboard ormara |
| **(c)** Dopušteno, ali ormar razlikuje operaterski put | ERP šalje poseban zaglavlje/polje, ormar ne traži tag | zahtjev prema ormaru (§7.R6) — **ne možemo sami** |

**Preporuka: (a), uz audit koji ne laže.** Gost s praznom baterijom na mobitelu je stvarna
situacija na molu, a cross-check nikad nije bio dokaz prisutnosti — D6 to izrijekom kaže:
UID je objavljen u dokumentaciji (`odluke.md` D6.1, tablica Krk) i ISO 15693 se kopira. Slanje
mapiranog taga ne gubi ništa što je bilo stvarno. Ali audit tada mora zapisati
`tag_source = 'mapping'`, nikad `'scan'` — inače je zapis gori od ničega.

**Blokira:** jedno polje u `command_audit` i jednu kontrolu na stranici veza, **nakon
2026-11-30**.
**Ne blokira:** faze 1–6 u cijelosti; korisnički NFC tok (tamo tag uvijek dolazi iz stvarnog
skeniranja); ništa prije 2026-11-30.

### §1.2 · BLOK-1 (prenesen iz `odluke.md`) — tko je master mapiranja vez → priključak

Ormar na `main` ima `berth_assignments` i čarobnjak koji ga upisuje na licu mjesta
(`Cloud_IOT/docs/ui_v2_spec.md` §6; shema u `ormar_ui_v2_spec.txt:699-709`). D1 kaže da je ERP
master. Ext API tu vezu **ne izlaže** (`ormar_gateway_izvjestaj.md` NALAZ 4.2: `berth_assignment`
čita samo marina CORE, a nijedna `/api/marina/*` ruta nije u katalogu). Na `773bca6`
`models/berth_assignment.py` uopće ne postoji.

| Opcija | Cijena u ERP-u | Cijena izvan ERP-a |
|---|---|---|
| **(a)** ERP master, čarobnjak ormara čita iz ERP-a | mapiranje bez usporedbe; stupac `cabinet_reported_*` i cijeli §4.7 su mrtvi | ormar mora zvati ERP — obrnuti smjer od svega ostalog |
| **(b)** Ormar master ožičenja, ERP master komercijalnog identiteta | mapiranje u dvije tablice + usporedba + jedan status_code | **novi ext endpoint na ormaru** (§7.R1) |
| **(c)** Oba, s usklađivanjem | isto kao (b) | isto kao (b), plus pravilo tko pobjeđuje pri neslaganju |

**Preporuka: (b)**, ista kao tvoja u `odluke.md`. Ožičenje se zna samo na licu mjesta, a
retrofit ga mora unijeti isto tako; jedna činjenica ima jednog vlasnika.

**Blokira:** §4.7 (stupac usporedbe) i dio faze 3 — konkretno smjer sinkronizacije i tko
pobjeđuje pri neslaganju.
**Ne blokira:** faze 1 i 2; tablice `berths`, `outlets` i `outlet_nfc_tags` (one postoje pod
svakom opcijom); uvoz NFC CSV-a za Krk; sve u §2 i §3.

Do odluke faza 3 upisuje mapiranje s `source = 'erp_manual'` i usporedbu drži isključenom.

### §1.3 · NOVO — oblik tarife

D9 i D14 pretpostavljaju tarifu („iznos po tarifi", „VT/NT", „vršna snaga") ali je nigdje ne
definiraju. Treba mi **oblik**, ne brojke.

| Opcija | Što to znači u modelu |
|---|---|
| **(a)** Jedna cijena po marini i po mediju | `tariffs(marina_id, medium, unit_price, currency, vat_rate)` — 1 redak po mediju |
| **(b)** (a) + dnevno/noćno (VT/NT) | plus `time_band`, `band_from`, `band_to` |
| **(c)** (b) + cijena po ugovoru korisnika | plus `tariff_id` na `contracts`, s padom na marinsku |
| **(d)** (c) + fiksna dnevna naknada po priključku | plus `standing_charge_per_day` |

**Preporuka: (c).** VT/NT je stvarna poluga koju D14 nabraja, a cijena po ugovoru je razlika
između tranzitnog gosta i stalnog priveza, koju D9 već priznaje kao dvije skupine. (d) dodaje
redak u model koji marina možda nikad ne upotrijebi, a bez njega se ne može izvesti unaprijed.

**Blokira:** obračun u fazi 7 — pretvorba kWh/litara u iznos.
**Ne blokira:** faze 1–6; knjigu kredita (ona vodi iznose, ne cijene); mjerenje, prikupljanje
i prikaz potrošnje u kWh i litrama; sve u §2, §3, §5 osim koraka 9–12 NFC toka.

### §1.4 · NOVO — izdaje li ERP fiskalni račun

D4 kaže „računi su u ERP-u", D9 „račun pri kupnji kredita". To su dvije različite stvari u
pravnom smislu i razlika je skupa.

| Opcija | Što ERP gradi | Cijena ako je pogrešna |
|---|---|---|
| **(a)** ERP vodi samo obračunske zapise; račun izdaje postojeći marinin sustav, ERP mu šalje podatke | tablica `billing_records` + izvoz | nizak — izvoz se prepiše |
| **(b)** ERP izdaje fiskalizirani račun (HR fiskalizacija / SI davčno potrjevanje) | certifikati, potpisivanje, JIR/ZKI, obvezni ispisi, arhiva 11 g. | **visok** — to je projekt, ne značajka |

**Preporuka: (a) za pilot Krk.** Fiskalizacija je samostalan projekt s pravnim i certifikatnim
repom, a pilot je jedan ormar sa šest priključaka. (a) ne zatvara (b): `billing_records` je
ulaz u fiskalizaciju kad do nje dođe.

**Blokira:** korak 12 NFC toka („izda račun") i jedan zaslon.
**Ne blokira:** knjigu kredita, odbijanje kredita, auto-stop, sesije, obračunske zapise —
dakle sve što je potrebno da pilot radi i da se potrošnja točno pripiše.

### §1.5 · NOVO — kako se kupuje kredit

D9 traži kredit kao jedini izvor istine u ERP-u, ali ne kaže kako u njega ulazi novac.
Bez toga prepaid tok ima vratara, brojač i stikalo — ali nema ulaz.

| Opcija | Cijena |
|---|---|
| **(a)** Recepcija unosi dopunu u ERP-u (gotovina/kartica izvan ERP-a) | jedan zaslon, jedan redak u knjizi kredita, nula integracija |
| **(b)** (a) + kartično plaćanje u mobilnoj aplikaciji (Stripe/Monri) | PSP integracija, webhook plaćanja, povrati, PCI opseg |

**Preporuka: (a) za pilot.** Knjiga kredita je ista pod oboje; (b) samo dodaje izvor retka.
Mobilna aplikacija je ionako izvan ovog repoa.

**Blokira:** samo zaslon dopune i tko ga smije koristiti.
**Ne blokira:** knjigu kredita, odbijanje bez kredita (D11 test 3), auto-stop (D11 test 4).

### §1.6 · Zatvoreno čitanjem koda — bilo je „Otvoreno", nije više

Dvije stvari iz „Otvoreno" u `odluke.md` imaju odgovor u kodu ormara. Navodim ih da ne ostanu
otvorene bez potrebe; ispravak je prema `odluke.md`, ne prema kodu.

**1 · Pull endpoint za sesije postoji, ali nije po vremenskom rasponu.**
`odluke.md` pita: „Koji pull endpoint vraća sesije i potrošnju za vremenski raspon?"
Odgovor: **takav ne postoji.** Postoji po korisniku —
`GET /api/nfc/sessions/by-user/{user_id}?status=active|ended&limit=` s `X-API-Key`
(`Cloud_IOT/backend/app/routers/nfc.py:711-720`), koji vraća isti 16-ključni payload i
**čije čitanje samo po sebi broji kao usklađivanje** (`nfc.py:755`, `erp_reconciliation.mark_reconciled`).
Posljedica za §5.2: ERP usklađuje **iterirajući korisnike s otvorenim ili nedavno zatvorenim
sesijama**, ne pitajući za prozor.

Postoje i `GET /api/nfc/reconciliation` i `/reconciliation/divergence`
(`nfc.py:797`, `:830`) — drugi vraća završene a nepotvrđene sesije, najstarije prvo, što je
bolji izvor od iteracije po korisnicima. **Ali oba traže operaterski JWT**
(`require_any_role`, `Cloud_IOT/backend/app/auth/dependencies.py:54`), **ne** `X-API-Key`.
To je zahtjev u §7.R2, ne nešto što ERP danas može zvati.

**2 · Ugovor sesije ima 16 ključeva, ne 10, i polje se zove `socket_id`.**
D10 i PDF (`Navodila…` §8.3) opisuju payload s `outlet_id` i deset polja. Autoritativni
ugovor je `Cloud_IOT/docs/erp_session_payload_contract.md` (v3.47), pinan testom
`test_nfc_six_tag_model.py::test_tc_six_13g_the_payload_key_set_is_exactly_the_documented_contract`.
Razlike koje mijenjaju ERP kod, u §2.4.

---

## §2 Ugovor s ormarom

ERP razgovara s ormarom kroz **dva odvojena kanala koja se ne miješaju**.

### §2.1 · Pravilo putanje — jedno, i pokriva sve

> **Vanjska putanja = putanja iz kataloga s `/api/` zamijenjenim s `/api/ext/` — osim ako
> putanja u katalogu već počinje s `/api/ext/`, tada se koristi doslovno.**

Mehanizam: `internal_path = f"/api/{path}"`, gdje je `path` sve nakon `/api/ext/`
(`Cloud_IOT/backend/app/routers/external_api_gateway.py:278`, ruta na `:203`). Gateway ne
dodaje prefiks — **zamjenjuje ga**.

Dvije obitelji, dva pravila (`ormar_gateway_izvjestaj.md` NALAZ 1.1):

| | broj | putanja u katalogu | kako se poslužuje |
|---|---|---|---|
| **A — proxied** | 38 | `/api/…` | kroz gateway, self-proxy na 127.0.0.1 |
| **B — direktne** | 17 | `/api/ext/…` | vlastite rute (`Cloud_IOT/backend/app/main.py:904-906`), gateway nije u putu |

> **Odlučeno** · Klijent drži **jednu tablicu ključ → vanjska putanja**, generiranu iz
> kataloga po pravilu gore, i **nikad ne sastavlja putanju u pozivu**.
>
> **Zašto** · Današnji klijent prefiksira svaki poziv u kodu
> (`backend/app/services/pedestal_api.py:167-168`), pa je dvostruki `ext` jedan typo daleko —
> a dvostruki `ext` daje **401 koji nije poruka o kredencijalu** (NALAZ 1.2): matcha
> `pedestals.status_ext` u katalogu, prolazi gateway, i tek `_check_ext_auth` odbije interni
> admin JWT. Sat vremena traženja na pogrešnom mjestu.
>
> **Ako griješim** · Tablica je jedan modul; ako se pravilo promijeni, mijenja se generator,
> ne 17 poziva.

### §2.2 · Tablica poziva — kanal A (`/api/ext/`, Bearer `api_client`)

`tip ID` je ono što ERP **smije poslati**: `PK` = samo numerički primarni ključ,
`PK|display` = i `MAR_KRK_ORM_01` (`_resolve_pedestal`, `Cloud_IOT/backend/app/routers/ext_pedestal_endpoints.py:117-147`).
`bidir` = mora li operater u Gateway UI-u postaviti mod *bidirectional* da write prođe.

| ključ | met. | vanjska putanja | tip ID | bidir | ERP ga koristi za |
|---|---|---|---|---|---|
| `pedestals.health` | GET | `/api/ext/pedestals/health` | — | — | **`smart_mode`, `device_connected`, `last_seen`** — §3 |
| `pedestals.list` | GET | `/api/ext/pedestals` | — | — | popis ormara, otkrivanje novih |
| `pedestals.status_ext` | GET | `/api/ext/pedestals/{pedestal_id}/status` | PK\|display | — | `door_state` (D16), temp, vlaga |
| `water.status_ext` | GET | `/api/ext/pedestals/{pedestal_id}/water` | PK\|display | — | stanje ventila i zbrojevi |
| `berths.list` | GET | `/api/ext/berths` | — | — | **`state_code`, `match_ok_bit`, `match_score`, `last_analyzed`** — signal *plovilo* |
| `berths.occupancy_ext` | GET | `/api/ext/pedestals/{id}/berths/occupancy` | PK\|display | — | rezerva; samo `occupied` |
| `sessions.active` | GET | `/api/ext/sessions/active` | — | — | nadzorna ploča |
| `sessions.pending` | GET | `/api/ext/sessions/pending` | — | — | nadzorna ploča |
| `alarms.active` | GET | `/api/ext/alarms/active` | — | — | §3 alarmni kodovi |
| `alarms.acknowledge` | POST | `/api/ext/alarms/{id}/acknowledge` | PK | **da** | potvrda iz ERP-a |
| `analytics.daily` | GET | `/api/ext/analytics/consumption/daily` | — | — | kontrolni zbroj |
| `analytics.summary` | GET | `/api/ext/analytics/sessions/summary` | — | — | kontrolni zbroj |
| `sockets.config_list` | GET | `/api/ext/pedestals/{pedestal_id}/sockets/config` | PK | — | **otkrivanje mogućnosti** (D3) |
| `valves.config_list` | GET | `/api/ext/pedestals/{pedestal_id}/valves/config` | PK | — | **otkrivanje mogućnosti** (D3) |
| `load.pedestal_get_ext` | GET | `/api/ext/pedestals/{pedestal_id}/load` | **PK** | — | telemetrija po utičnici |
| `load.socket_get_ext` | GET | `/api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/load` | **PK** | — | telemetrija jedne utičnice |
| `load.socket_history_ext` | GET | `/api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/load/history` | **PK** | — | povijest za energetskog agenta |
| `load.pedestal_alarms_ext` | GET | `/api/ext/pedestals/{pedestal_id}/load/alarms` | **PK** | — | `auto_off_overload` |
| `load.marina_alarms_ext` | GET | `/api/ext/marinas/{marina_id}/load/alarms` | **PK** | — | isto, po marini |
| `breakers.pedestal_list_ext` | GET | `/api/ext/pedestals/{pedestal_id}/breakers` | **PK** | — | `breaker_tripped` |
| `breakers.socket_get_ext` | GET | `/api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/breaker` | **PK** | — | isto, po utičnici |
| `breakers.pedestal_history_ext` | GET | `/api/ext/pedestals/{pedestal_id}/breaker/history` | **PK** | — | dijagnostika |
| `breakers.marina_alarms_ext` | GET | `/api/ext/marinas/{marina_id}/breaker/alarms` | **PK** | — | isto, po marini |
| `camera.frame_ext` | GET | `/api/ext/pedestals/{id}/camera/frame` | PK\|display | — | slika veza na zahtjev |
| `camera.stream_ext` | GET | `/api/ext/pedestals/{id}/camera/stream` | PK\|display | — | RTSP URL |
| `usage.history` | GET | `/api/ext/pedestals/{pedestal_id}/usage/history` | PK | — | usklađivanje |
| `controls.socket_cmd` | POST | `/api/ext/controls/pedestal/{pedestal_id}/socket/{socket_name}/cmd` | PK | **da** | **operaterski put** (D3) |
| `controls.water_cmd` | POST | `/api/ext/controls/pedestal/{pedestal_id}/water/{valve_name}/cmd` | PK | **da** | operaterski put, voda |
| `controls.allow` | POST | `/api/ext/controls/{session_id}/allow` | PK | **da** | odobri sesiju |
| `controls.deny` | POST | `/api/ext/controls/{session_id}/deny` | PK | **da** | odbij sesiju |
| `controls.stop` | POST | `/api/ext/controls/{session_id}/stop` | PK | **da** | zaustavi sesiju |
| `diagnostics.run` | POST | `/api/ext/pedestals/{id}/diagnostics/run` | PK | **da** | servisni prozor |

Tijela: `socket_cmd` i `water_cmd` oba primaju `{action: "activate"|"stop", nfc_tag_id?}`
(`Cloud_IOT/backend/app/routers/controls.py:558-563`, `:752-756`). `action` je regex
`^(activate|stop)$` — **`maintenance` vraća 422**, premda docstring na `controls.py:762`
tvrdi suprotno (NALAZ 2.1). `controls.deny` prima `{reason?}` ≤500.
`allow`/`stop`/`socket_approve` nemaju tijelo.

`socket_cmd activate` traži **utaknut kabel**: bez njega
`409 "Socket has no plug inserted"` (`Cloud_IOT/backend/app/routers/controls.py:692-700`).
`stop` taj uvjet nema.

> **Odlučeno** · ERP za `load.*` i `breakers.*` **uvijek** koristi numerički PK; `display_id`
> se nikad ne šalje na te rute.
>
> **Zašto** · `ext_breaker_*` i `ext_meter_load_*` primaju `int`; `display_id` tamo daje
> **422 prije handlera**, bez ikakve poruke o autentifikaciji (NALAZ 3.1, tipska analiza pet
> od pet). Jedna tablica `pedestal_id → (pk, display_id)` u ERP-u rješava to na jednom mjestu.
>
> **Ako griješim** · Ako ormar ikad ujednači tipove, PK ostaje valjan — `_resolve_pedestal`
> prima i broj.

### §2.3 · Što uključiti u Gateway UI-u ormara

Operater ormara mora uključiti točno ovo, s točno ovim modom. **Ništa više** — svaki uključeni
write endpoint je površina.

**Monitor (read):**
`pedestals.health`, `pedestals.list`, `pedestals.status_ext`, `water.status_ext`,
`berths.list`, `berths.occupancy_ext`, `sessions.active`, `sessions.pending`,
`alarms.active`, `analytics.daily`, `analytics.summary`,
`sockets.config_list`, `valves.config_list`,
`load.pedestal_get_ext`, `load.socket_get_ext`, `load.socket_history_ext`,
`load.pedestal_alarms_ext`, `load.marina_alarms_ext`,
`breakers.pedestal_list_ext`, `breakers.socket_get_ext`, `breakers.pedestal_history_ext`,
`breakers.marina_alarms_ext`,
`camera.frame_ext`, `camera.stream_ext`, `usage.history`

**Bidirectional (write):**
`controls.socket_cmd`, `controls.water_cmd`, `controls.allow`, `controls.deny`,
`controls.stop`, `alarms.acknowledge`, `diagnostics.run`

**Izrijekom NE uključivati:**

| ključ | zašto ne |
|---|---|
| `breakers.socket_reset_ext` | NALAZ 2.3 — mod se **ne provjerava** na direktnim write rutama; „monitor" u UI-u ne čini ništa. Ne prije ormarovog popravka 2.3 (`odluke.md`, Otvoreno) |
| `load.auto_stop_ack_ext` | isto, i dodatno **nema Smart Mode gate** (NALAZ 2.2) — jedini write koji prolazi i kad je ormar samostalan |
| `berths.push_image_ext` | isto NALAZ 2.3; ERP ne piše slike |
| `led_schedule.get` / `.upsert` / `.delete` / `.test` | NALAZ 1.3 — gateway match **ignorira metodu**, pa uključen `.get` blokira `PUT`/`DELETE` s 403 „read-only". ERP ne upravlja LED-om |
| `mobile.*`, `qr.*` | nije ERP-ov posao (D6: NFC je jedini put) |
| `controls.reset`, `controls.led`, `sockets.config_patch`, `valves.config_patch` | ERP ne mijenja konfiguraciju ormara |
| `controls.socket_approve` / `socket_reject` | pokriveni s `allow`/`deny`; dva puta ista akcija |

> **Odlučeno** · Lista uključenih endpointa je **dio ERP konfiguracije po ormaru**, provjerena
> pri spajanju ormara, i neslaganje je vidljivo stanje, ne tiha 403.
>
> **Zašto** · ERP ne može pročitati `allowed_endpoints` (to je `/api/admin/ext-api/config`,
> nije u katalogu). Jedini način da sazna je da pozove i dobije 403. Bez evidencije očekivanog,
> svaka 403 izgleda kao greška u kodu.
>
> **Ako griješim** · Ako ormar ikad izloži svoju listu, provjera postaje poziv umjesto
> konfiguracije — jedan modul.

**Verifikacija u Gateway UI-u se ne koristi kao dokaz ničega.** `verified = any_pass and not
any_fail` (`Cloud_IOT/backend/app/routers/external_api_admin.py:291`) je trajno `False` ako je
ijedan parametrizirani endpoint uključen, zbog `has_param = "{id}" in ep["path"]` na `:241` —
podstring test koji ne hvata `{pedestal_id}`. Crveni badge ne sprječava aktivaciju
(`ApiGateway.tsx:627` nema `disabled`). NALAZ 3.1 i 3.2.

### §2.4 · Kanal B — NFC, izravno, `X-API-Key`, **nije** kroz `/api/ext`

NFC nije u `ENDPOINT_CATALOG` (specifikacija ormara, odgođeno D4) — `/api/ext/nfc/…` uvijek
daje 403. ERP do njega dolazi isključivo izravno.

| namjena | poziv | tijelo / parametri | file:line (ormar) |
|---|---|---|---|
| Pripremi priključak | `POST /api/nfc/scan` | `{nfc_tag_id, user_id}` | `routers/nfc.py:543` |
| Stanje sesije | `GET /api/nfc/session/{session_id}` | — | `routers/nfc.py:688` |
| Sesije korisnika | `GET /api/nfc/sessions/by-user/{user_id}` | `?status=active\|ended&limit=1..500` | `routers/nfc.py:711` |
| Zaustavi sesiju | `POST /api/nfc/session/{session_id}/stop` | — | `routers/nfc.py:762` |

Autentifikacija: `X-API-Key`, `require_erp_api_key`
(`Cloud_IOT/backend/app/auth/erp_api_key.py:20-33`) — `401` na nevaljali ili odsutni ključ,
`503` ako ključ nije konfiguriran na ormaru.

`POST /session/{id}/stop` vraća **409 „Session already ended by operator"**
(`nfc.py:782`) — osoblje marine ima prednost (D10). **To nije greška** i ne logira se kao greška.

**Ugovor sesije — 16 ključeva** (`Cloud_IOT/docs/erp_session_payload_contract.md`).
Ispravci prema D10 i PDF-u, navedeni a ne tiho primijenjeni:

| D10 / PDF kaže | Stvarni ugovor | Što to mijenja u ERP-u |
|---|---|---|
| `outlet_id` | **`socket_id`**, i to **string** `"Q1"`–`"Q4"` / `"V1"`–`"V2"` | **`V1` i `Q1` su oba `socket_id = 1` interno**; prefiks je jedino što ih razlikuje. ERP usklađuje na string, nikad na broj |
| 10 polja | 16 | plus `activated_at`, `meter_energy_start_kwh`, `meter_energy_end_kwh`, `meter_water_start_l`, `meter_water_end_l`, `consumption_source` |
| — | `estimated_cost` **uklonjen** u v3.47 | ERP ne smije očekivati cijenu od ormara; cijena je ERP-ov posao (D0) |
| `power_kw_current` broj | `null` = **mjerenje odbijeno kao fizički nemoguće** | `null ≠ 0.0`. Danas živo na ormaru 1: dvije od četiri utičnice javljaju 35–88× iznad granice i odbijaju se na izvoru |
| „poraba" | `energy_kwh` / `water_liters` su **razlike registra**, prije v3.47 su mogle biti **životni zbroj priključka** | ERP **preračunava**: `energy_kwh == meter_energy_end_kwh − meter_energy_start_kwh` |

> **Odlučeno** · ERP preračunava svaku brojku iz dvaju graničnih očitanja i **neslaganje
> prijavljuje kao nalaz**, ne prihvaća tiho.
>
> **Zašto** · Ormar to izrijekom traži („Recompute our figures — please"), a defekt koji je
> cijeli ovaj ugovor i izazvao bio je upravo brojka bez provjere: na utičnici 1 ormara 1
> životni zbroj **481,76 kWh** bio bi prijavljen kao jedna sesija. Dva neovisna zapisa iste
> činjenice vrijede daleko više od jednog.
>
> **Ako griješim** · Preračun je jedna funkcija i jedan test; ako se pokaže nepotrebnim,
> ostaje kao jeftina provjera.

### §2.5 · Rukovanje odgovorima — jedna tablica, bez iznimki

> **Odlučeno** · Klijent nikad ne pušta `httpx` iznimku u router. Svaki ishod ima kod i
> rečenicu za čovjeka.
>
> **Zašto** · Danas `controls.py` ima **nula `try` blokova** (mjereno:
> `grep -c "try:" backend/app/routers/controls.py` → 0), a klijent zove `resp.raise_for_status()`
> (`backend/app/services/pedestal_api.py:281`, `:295`, `:307`). Smart Mode OFF daje 409 koji
> se u ERP-u pretvori u **HTTP 500** — a `grep -rn "409"` po `backend/app` i `frontend/src`
> danas daje **nula pogodaka**. Operater koji klikne „Upali" na samostalnom ormaru vidi
> grešku servera.
>
> **Ako griješim** · Tablica je jedan `match` izraz; dodavanje koda je jedan redak.

| Ishod | Uzrok | Što ERP radi | Što korisnik vidi |
|---|---|---|---|
| **401** (kanal A) | token istekao | poništi keš tokena, **jedan** ponovni pokušaj | ništa, ako drugi prođe |
| **401** (kanal A, drugi put) | pogrešan servisni račun **ili dvostruki `ext` u putanji** | `cabinet_auth_failed`; logiraj **cijeli URL** | „Ormar ne prihvaća našu prijavu." |
| **401** (kanal B) | nevaljali `X-API-Key` | `cabinet_auth_failed`; ne ponavlja | isto |
| **403** | endpoint nije u `allowed_endpoints`, ili write u monitor modu | **ne ponavlja**; označi mogućnost `not_enabled`, prestani je zvati, ponovna proba za 1 h | „Ova funkcija nije uključena na ormaru." + ključ endpointa |
| **409** `detail` = Smart Mode | ormar radi samostalno | `standalone`; **ukloni kontrole** (§3) | „Ormar radi samostalno. Osoblje marine može upravljati kad se ponovno poveže." |
| **409** `detail` = no plug inserted | kabel nije utaknut | `awaiting_plug`; priprema ostaje | „Priklopite kabel za početak." |
| **409** `detail` = već u uporabi | jedna sesija po priključku | `outlet_busy` | „Ovaj priključak trenutno koristi netko drugi." |
| **409** (kanal B, `/stop`) | sesija već zatvorena (osoblje) | zatvori obračun po zadnjoj brojci; **nije greška** | ništa |
| **422** | tip path parametra — `display_id` poslan na PK-only rutu | **greška u ERP-u**; logiraj kao bug, ne ponavljaj | „Tehnička greška, prijavljena." |
| **503** | gateway neaktivan, ili mogućnost nije uključena/dostupna | `capability_unavailable` — **nije greška** | jedna rečenica, **nijedna kontrola** (D3) |
| **5xx / timeout / connect** | ormar ili mreža | 3 pokušaja, backoff 1/2/4 s; zatim keš s `is_stale=true` | sivo + „Podaci od HH:MM" |
| **nema odgovora, nema keša** | prvi poziv na tihi ormar | `no_contact` | „Nema veze s ovim ormarom." |

**ERP nikad ne prikazuje „spremno" ako naredba nije potvrđena** (D6, PDF §9).

---

## §3 Rječnik stanja

> **Odlučeno** · Status računa **server**, jednom, u jednom modulu. Frontend ga nikad ne
> računa. Uz `status_code` ide `status_sentence` za čovjeka i `berth_colour` za prikaz.
> **Testovi provjeravaju ključ, nikad tekst.**
>
> **Zašto** · Istovjetno s ormarom (§2 i §3 njegove specifikacije). Dvije strane koje isto
> stanje računaju različito su dva različita stanja. A tekst mora ostati uređiv bez padanja
> testova.
>
> **Ako griješim** · Preformuliraj rečenice slobodno; `status_code` je ono o čemu testovi
> govore.

### §3.1 · Četiri neovisna signala (D2), nikad spojena

| Signal | Vrijednosti | Izvor u ERP-u |
|---|---|---|
| **veza** | `ONLINE` / `STALE` / `OFFLINE` | ERP računa iz starosti `last_heartbeat` iz `pedestals.health` |
| **plovilo** | `NEMA` / `PRAVO` / `KRIVO` / `NEPOZNATO` | `state_code` 0/1/2 iz `berths.list`; `NEPOZNATO` kad `last_analyzed` fali ili je star |
| **struja** | `DA` / `NE` | aktivna **električna** sesija na utičnici tog veza; vode ne ulaze |
| **rezervacija** | `DA` / `NE` | ERP (`berth_reservations`) |

Pragovi: **`STALE` nakon 2× intervala heartbeata, `OFFLINE` nakon 10 min** (D2).
Svježina ML-a iz `last_analyzed`; prag **30 min**, nakon toga `plovilo = NEPOZNATO`.

> **Odlučeno** · `device_connected` (ERP-ovo ime za `opta_connected`) **nije dokaz da je
> uređaj živ**. Živost je isključivo starost `last_heartbeat`, koju ERP računa sam.
>
> **Zašto** · `opta_connected` i `last_heartbeat` punili su se iz retained MQTT poruka — ormar
> mrtav tri tjedna dostavlja zdrav `opta/status` svakom novom pretplatniku, a
> `PedestalConfig.opta_connected` kaže `1` (NALAZ 5.1; model to i priznaje:
> `Cloud_IOT/backend/app/models/pedestal_config.py:43-58`, „also serves as last_seen_at").
> `heartbeat_age` nije izložen — samo CORE ga ima.
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije. Zelen redak koji znači „ne
> vidimo vez 3" gori je od nepostojećeg prikaza.

### §3.2 · Tablica stanja veza — najviši rang pobjeđuje

Ključevi istovjetni ormaru gdje je pojam isti (†), ERP-ovi gdje pojam postoji samo ovdje (‡).
Spojio sam dva poretka: ormarov §3 (zdravlje ormara) i D2 (stanje veza). **To je spoj, nije
nalaz** — ormarov poredak ne poznaje rezervacije ni „struja bez plovila", a D2 ne poznaje
vlagu i temperaturu.

| Rang | `status_code` | `status` | `berth_colour` | Rečenica | Izvor |
|---|---|---|---|---|---|
| 1 | `no_contact` † | `unknown` | sivo | Nema veze s ovim ormarom | `last_heartbeat` stariji od 10 min |
| 2 | `standalone` † | `unknown` | sivo | Ormar radi samostalno | `smart_mode == false` iz `pedestals.health` |
| 2.5 | `outlet_silent` † | `unknown` | sivo | Ovaj priključak se nije javio | stanje priključka starije od 60 s |
| 3 | `water_leak` † | `attention` | crveno | Otkriveno curenje vode | alarm vlage, `status_ext` / `alarms.active` |
| 4 | `too_hot` † | `attention` | crveno | Ormar je pregrijan | alarm temperature |
| 5 | `auto_off_overload` † | `attention` | crveno | Struja se automatski isključila — preveliko trošenje | `load.*_alarms_ext` |
| 6 | `breaker_tripped` † | `attention` | crveno | Struja je iskočila — treba resetirati | `breakers.*_ext` |
| 7 | `measurement_missing` † | `attention` | crveno | Potrošnja nije izmjerena — treba pregled | `consumption_source == "unknown"` |
| 8 | `vessel_mismatch` † | `attention` | crveno | Plovilo ne odgovara slici | `state_code == 2` iz `berths.list` |
| 9 | `power_without_vessel` ‡ | `attention` | narančasto | Struja teče, a plovila nema | struja `DA` + plovilo `NEMA` |
| 10 | `reserved_empty` ‡ | `attention` | žuto | Rezervirano, vez je prazan | rezervacija `DA` + plovilo `NEMA` |
| 11 | `vessel_present` ‡ | `ok` | plavo | — | plovilo `PRAVO` (`state_code == 1`) |
| 12 | `free` ‡ | `ok` | zeleno | — | ništa iznad nije istina |

**Stanje bez unosa u ovoj tablici ne može se iscrtati** — postaje `unknown` /
„Nešto treba provjeriti". To je pošteno i tjera da se unos doda, umjesto da praznina prođe.

> **Odlučeno** · Rangovi 1, 2 i 2.5 su `unknown`, **ne** `attention`.
>
> **Zašto** · Istovjetno ormaru, i iz istog razloga: „treba pažnju" znači idi i učini nešto
> **na tom vezu**. Ormar bez veze ili u samostalnom radu traži nešto **na ormaru**, a stanje
> veza se tada **ne zna**. Tiho se ne iscrtava kao prazno.
>
> **Ako griješim** · Tri retka u tablici.

> **Odlučeno** · `status` ostaje trovrijedan (`ok` / `attention` / `unknown`), istovjetno
> ormaru, a sedam boja iz D2 nosi **zasebno polje `berth_colour`**.
>
> **Zašto** · D2 traži sedam boja; ormar ima tri statusa. Da sam proširio `status` na sedam
> vrijednosti, izgubio bih usklađenost rječnika koju D2 izrijekom traži. Dva polja, jedno
> usklađeno i jedno naše, drže oboje.
>
> **Ako griješim** · Spajanje je jedan serijalizator.

### §3.3 · Stanja priključka i uređaja

Vodni ispust: `idle | active | unknown` — **nema `pending`** (D3, ormarov §4.6; `pending`
znači „fizički priklopljen, čeka aktivaciju" i dolazi iz detekcije priklopa, koja za ventil
ne postoji). Utičnica: `idle | pending | active | fault | unknown`.

Veza ormar↔ERP, zasebno od veza-stanja: `online | stale | offline | auth_failed | not_enabled`.

---

## §4 Model podataka

PostgreSQL, Alembic. Postojeće migracije idu do `004`
(`backend/alembic/versions/004_pedestal_cache_readings.py`); nove počinju od `005`.
Postojećih tablica je osam (mjereno: `grep -c "__tablename__" backend/app/models/*.py` → 8):
`users`, `user_marina_access`, `marinas`, `pedestal_cache`, `alarm_log`, `session_log`,
`sync_log`, `audit_log`.

> **Odlučeno** · Novi model se **dodaje**, postojećih osam tablica se ne preimenuje ni ne briše
> u fazi 3.
>
> **Zašto** · `pedestal_cache` i `sync_log` nose jedini mehanizam otpornosti koji danas
> postoji. Rušenje i gradnja istovremeno su dvije promjene koje se ne mogu razdvojiti kad
> nešto pukne.
>
> **Ako griješim** · Brisanje nekorištene tablice je jedna migracija, u bilo kojem trenutku.

### §4.1 · Uređaji i mogućnosti (D3)

```
cabinets                        -- zamjenjuje jedno-URL model na `marinas`
  id              SERIAL PK
  marina_id       INT NOT NULL REFERENCES marinas(id) ON DELETE CASCADE
  pedestal_pk     INT NOT NULL          -- numerički PK NA ORMARU; load/breaker rute traže njega
  display_id      TEXT NOT NULL         -- 'MAR_KRK_ORM_01'; status/water/berths/camera primaju i njega
  device_type     TEXT NOT NULL         -- 'full' | 'retrofit'   (D3)
  base_url        TEXT NOT NULL         -- Tailscale adresa (D12)
  service_email   TEXT NOT NULL
  service_pw_enc  TEXT NOT NULL         -- Fernet; ključ NIJE na istom disku (§8)
  erp_api_key_enc TEXT                  -- kanal B; NULL dok BLOK iz §1.6 nije riješen
  dock            TEXT
  created_at      TIMESTAMPTZ NOT NULL
  UNIQUE (marina_id, display_id)
  UNIQUE (marina_id, pedestal_pk)

cabinet_capabilities            -- što uređaj STVARNO ima; puni se iz sockets/valves.config_list
  cabinet_id      INT NOT NULL REFERENCES cabinets(id) ON DELETE CASCADE
  capability      TEXT NOT NULL   -- 'power'|'water'|'vessel_detect'|'camera'|'door'|'breaker'|'load_meter'
  available       BOOLEAN NOT NULL
  checked_at      TIMESTAMPTZ NOT NULL
  PRIMARY KEY (cabinet_id, capability)

outlets                         -- priključci, uvijek pravim imenom (D3)
  id              SERIAL PK
  cabinet_id      INT NOT NULL REFERENCES cabinets(id) ON DELETE CASCADE
  outlet_name     TEXT NOT NULL   -- 'Q1'..'Q4' | 'V1' | 'V2'  — NIKAD gola znamenka
  medium          TEXT NOT NULL   -- 'electricity' | 'water'
  phases          INT             -- 3 za Q1, 1 za Q2-Q4, NULL za vodu
  rated_amps      INT             -- 32 | 16, NULL za vodu
  rated_lpm       INT             -- 20 za V1/V2, NULL za struju
  UNIQUE (cabinet_id, outlet_name)
```

> **Odlučeno** · `outlet_name` je tekst `'Q1'`/`'V1'`, a ne broj, i jedinstvenost je po
> `(cabinet_id, outlet_name)`.
>
> **Zašto** · Na ormaru su **`V1` i `Q1` oba `socket_id = 1`** interno, i prefiks je jedino
> što ih razlikuje (`Cloud_IOT/docs/erp_session_payload_contract.md`, redak `socket_id`).
> Cijeli broj kao ključ pripisao bi vodnu sesiju električnoj utičnici — i to bi se vidjelo
> samo na računu.
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije.

> **Odlučeno** · `phases` i oblik telemetrije su podatak, ne pretpostavka koda.
>
> **Zašto** · Q1 šalje `currentAmpsL1..L3` / `powerKwTotal`, Q2–Q4 `currentAmps` / `powerKw`
> (D3, ormarov §4.7). Komponenta koja pretpostavlja jedan oblik je greška, i to je greška koja
> se vidi samo na trofaznom priključku — dakle na jednom od šest.
>
> **Ako griješim** · Jedan parser, dva slučaja, jedan test po obliku.

### §4.2 · Vezovi i mapiranje

```
berths                          -- komercijalni identitet (D1)
  id              SERIAL PK
  marina_id       INT NOT NULL REFERENCES marinas(id) ON DELETE CASCADE
  berth_number    TEXT NOT NULL   -- ono što marina vidi
  svg_id          TEXT            -- id elementa u 2D karti (§6.1)
  created_at      TIMESTAMPTZ NOT NULL
  UNIQUE (marina_id, berth_number)

berth_outlets                    -- ERP-ova strana mapiranja vez → priključak
  berth_id        INT NOT NULL REFERENCES berths(id) ON DELETE CASCADE
  outlet_id       INT NOT NULL REFERENCES outlets(id) ON DELETE CASCADE
  source          TEXT NOT NULL   -- 'erp_manual' | 'cabinet' | 'confirmed'
  assigned_by     TEXT NOT NULL   -- e-mail; OBVEZNO, nikad default
  assigned_at     TIMESTAMPTZ NOT NULL
  PRIMARY KEY (berth_id, outlet_id)
  -- jedna električna utičnica služi najviše jednom vezu:
  -- djelomični unique indeks na (outlet_id) WHERE medium='electricity'
  -- NAMJERNO BEZ unique za vodu — ventil smije biti dijeljen (D1)
```

Pravila priključaka, istovjetna ormarovom §6 i D1:
jedan vez → najviše jedna električna utičnica; jedna utičnica → najviše jedan vez;
**vodni ispust smije biti dijeljen**; vez može biti bez vode ili bez struje; ormar pokriva
1–4 veza; **tko je mijenjao mora biti zapisan, nikad default**.

> **Odlučeno** · `assigned_by` je obvezan i **diže grešku** umjesto da uzme default.
>
> **Zašto** · Isti razlog kao `provisioned_by` na NFC tagovima i `assigned_by` na ormaru.
> Premještanje veza mijenja čija potrošnja gdje pada. Poziv bez aktera je bug; default ga
> skriva.
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije.

### §4.3 · Usporedba mapiranja na obje strane (prompt §4; vidi §0.3 i §1.2)

```
berth_outlets_cabinet            -- što ormar tvrdi; samo se čita, nikad ne piše iz ERP-a
  cabinet_id      INT NOT NULL REFERENCES cabinets(id) ON DELETE CASCADE
  outlet_name     TEXT NOT NULL
  cabinet_berth_id INT            -- Berth.id iz ormarove users.db, obični int
  fetched_at      TIMESTAMPTZ NOT NULL
  PRIMARY KEY (cabinet_id, outlet_name)

-- usporedba je POGLED, ne tablica: neslaganje se računa, ne pamti
-- v_berth_mapping_divergence: redci gdje se ERP i ormar ne slažu,
--   plus redci koje jedna strana ima a druga ne
```

> **Odlučeno** · Tablica ormarove strane i pogled usporedbe postoje od faze 3, ali se **pune
> samo kad postoji endpoint** iz §7.R1. Do tada su prazne i usporedba javlja
> `comparison_unavailable`, ne „sve se slaže".
>
> **Zašto** · Prazna usporedba koja izgleda kao uspješna je točno onaj oblik tihog pristanka
> koji D1 zabranjuje („Dva mastera iste činjenice nisu dopuštena"). Prazna tablica koja kaže
> da je prazna je pošteno stanje.
>
> **Ako griješim** · Ako BLOK-1 završi kao (a), ova tablica i pogled se brišu jednom
> migracijom. To je cijena koju prompt izrijekom traži da platim.

### §4.4 · NFC naljepnice — master je ERP (D6.1)

```
outlet_nfc_tags
  id              SERIAL PK
  outlet_id       INT NOT NULL REFERENCES outlets(id) ON DELETE CASCADE
  uid_primary     TEXT NOT NULL   -- '35:B2:5A:04:09:01:04:E0'
  uid_reversed    TEXT NOT NULL   -- 'E0:04:01:09:04:5A:B2:35'
  tag_standard    TEXT NOT NULL DEFAULT 'ISO15693'
  provisioned_by  TEXT NOT NULL   -- OBVEZNO
  provisioned_at  TIMESTAMPTZ NOT NULL
  active          BOOLEAN NOT NULL DEFAULT true
  UNIQUE (uid_primary)
  UNIQUE (uid_reversed)
  -- traženje IDE PO OBA STUPCA; indeks na svaki
```

> **Odlučeno** · Pretraga taga provjerava **oba zapisa**, i to je jedna funkcija s jednim
> testom po smjeru.
>
> **Zašto** · D6.1 i PDF §A.1: telefon javlja UID u jednom ili drugom redoslijedu bajtova,
> ovisno o aplikaciji. Ako ERP drži jedan zapis a telefon javi drugi, **nijedna naljepnica se
> nikad ne poklopi** — a greška ne izgleda kao greška u zapisu, nego kao „naljepnica nije
> prepoznana", pa se traži na pogrešnom mjestu.
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije.

Uvoz: `nfc_tags_<display_id>.csv`, **uvozom, ne prepisivanjem** (D6.1; PDF: „šesnaest znakova
na nalepko je dovolj, da se pri tipkanju zgodi napaka"). Pilot Krk `MAR_KRK_ORM_01` — šest
naljepnica iz tablice u D6.1.

**Test pri instalaciji provjerava točan priključak, ne samo da je tag prepoznat.** Pogrešno
prepoznata naljepnica je gora od neprepoznate (D6.1, PDF §A.3).

### §4.5 · Korisnici, ugovori, naplata, kredit

```
customers                        -- kupci; NISU operateri (users)
  id              SERIAL PK
  marina_id       INT NOT NULL REFERENCES marinas(id)
  external_ref    TEXT            -- 'erp-12345' iz mobilne aplikacije
  full_name       TEXT NOT NULL   -- NE prikazuje se na zaslonima marine (D15)
  email           TEXT
  created_at      TIMESTAMPTZ NOT NULL
  UNIQUE (marina_id, external_ref)

contracts
  id              SERIAL PK
  customer_id     INT NOT NULL REFERENCES customers(id) ON DELETE CASCADE
  billing_mode    TEXT NOT NULL DEFAULT 'prepaid'   -- 'prepaid' | 'postpaid'
  valid_from      DATE NOT NULL
  valid_to        DATE
  blocked         BOOLEAN NOT NULL DEFAULT false
  max_unpaid      NUMERIC(10,2)   -- postpaid granica
  max_kwh_session NUMERIC(10,3)
  max_session_min INT
  tariff_id       INT             -- NULL = marinska tarifa; oblik čeka §1.3

credit_ledger                    -- knjiga kredita; samo DODAVANJE, nikad UPDATE
  id              BIGSERIAL PK
  customer_id     INT NOT NULL REFERENCES customers(id)
  delta           NUMERIC(10,2) NOT NULL   -- + dopuna, − trošenje
  reason          TEXT NOT NULL   -- 'topup'|'consumption'|'adjustment'|'refund'
  session_id      BIGINT          -- kad je reason='consumption'
  balance_after   NUMERIC(10,2) NOT NULL
  created_by      TEXT NOT NULL
  created_at      TIMESTAMPTZ NOT NULL
```

> **Odlučeno** · `billing_mode` je svojstvo **korisnika (ugovora)**, s **defaultom
> `prepaid`**.
>
> **Zašto** · D9 i PDF §7 izrijekom: zaboravljena postavka nikad ne smije dati neograničenu
> potrošnju. Default `postpaid` znači da nova kartica bez ugovora troši besplatno do
> sljedećeg pregleda.
>
> **Ako griješim** · Jedan `server_default` u migraciji.

> **Odlučeno** · Kredit je **knjiga samo-dodavanja**; stanje je `balance_after` zadnjeg retka,
> nikad stupac koji se prepisuje.
>
> **Zašto** · ERP je jedini izvor istine o kreditu (D9). Stanje kao prepisivi stupac gubi
> povijest u trenutku kad zatreba — pri sporu oko iznosa. `balance_after` uz svaki redak čini
> svaki redak samostalno provjerljivim.
>
> **Ako griješim** · Materijalizirani stupac stanja je jedan trigger, dodan kad brojevi redaka
> postanu problem — a za pilot sa šest priključaka neće.

Minimalni iznos za početak sesije i dopušteni negativni saldo (D9: „npr. 1,00 €", „npr. do
2 €") su **konfiguracija po marini**, ne konstante u kodu:
`marina_billing_policy(marina_id, min_start_amount, allowed_negative, low_credit_warn_pct)`,
s izvedbenim defaultima **1,00 € / −2,00 € / 20 %**.

> **Odlučeno** · Brojke iz D9 ulaze kao konfiguracija s tim defaultima, a ne kao odluka koju
> tražim od tebe.
>
> **Zašto** · D9 ih piše s „npr.", što znači primjer, ne odluku. Konfigurabilno s razumnim
> defaultom ne blokira ništa i ne traži razgovor.
>
> **Ako griješim** · Promjena vrijednosti je jedan `UPDATE`, bez izdanja.

### §4.6 · Sesije i mjerenja (D10)

```
sessions                         -- ERP-ov zapis; ormarov session_id je vanjski ključ
  id              BIGSERIAL PK
  cabinet_id      INT NOT NULL REFERENCES cabinets(id)
  cabinet_session_id INT NOT NULL      -- ormarov PK
  outlet_id       INT NOT NULL REFERENCES outlets(id)
  customer_id     INT REFERENCES customers(id)
  session_type    TEXT NOT NULL        -- 'electricity' | 'water'  — ERP SE OSLANJA NA OVO
  status          TEXT NOT NULL        -- 'active' | 'ended'
  activated_at    TIMESTAMPTZ
  ended_at        TIMESTAMPTZ
  duration_min    NUMERIC(10,2)
  energy_kwh      NUMERIC(12,3)        -- NULL dopušten; NULL ≠ 0
  water_liters    NUMERIC(12,2)        -- NULL dopušten; NULL ≠ 0
  meter_e_start   NUMERIC(14,3)
  meter_e_end     NUMERIC(14,3)
  meter_w_start   NUMERIC(14,2)
  meter_w_end     NUMERIC(14,2)
  consumption_source TEXT              -- 'register'|'integrated_legacy'|'unknown'|NULL
  recompute_ok    BOOLEAN              -- je li end−start == brojka (§2.4)
  billing_state   TEXT NOT NULL        -- 'pending'|'billed'|'manual_review'|'not_billable'
  UNIQUE (cabinet_id, cabinet_session_id)

consumption_intervals            -- razlike registra; agregati zbrajaju OVO, ne polja sesije
  id              BIGSERIAL PK
  session_id      BIGINT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE
  from_at         TIMESTAMPTZ NOT NULL
  to_at           TIMESTAMPTZ NOT NULL
  energy_kwh      NUMERIC(12,3)
  water_liters    NUMERIC(12,2)
  source          TEXT NOT NULL
```

> **Odlučeno** · `consumption_source` se **sprema uz svaku sesiju i prikazuje uz svaku
> brojku**. `unknown` i `null` prikazuju se kao **—**, nikad kao `0,0`, i sesija ide u
> `manual_review`.
>
> **Zašto** · D10 i ormarov §4.3. „Nismo izmjerili" i „potrošio je nula" izgledaju isto ako
> ih se jednako obradi, a razlika **uvijek ide na štetu jedne od strana** (PDF §8.5). Brojka
> prikazana bez podrijetla je točno ono kako je stari workaround preživio tri mjeseca.
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije.

> **Odlučeno** · Agregati (povijest, analitika) zbrajaju `consumption_intervals`, **nikad**
> polja iz `sessions`.
>
> **Zašto** · D10 i ormarov §4.4. Intervalni redci su razlike registra, pa njihov zbroj
> jednak je brojci sesije **po konstrukciji**. Zbrajanje polja sesije radi isto dok ne radi, i
> tad se razlika ne može locirati.
>
> **Ako griješim** · Jedan upit po pogledu.

### §4.7 · Audit naredbi i retencija

```
command_audit                    -- SVAKA upravljačka naredba (D13 sloj 1)
  id              BIGSERIAL PK
  cabinet_id      INT NOT NULL REFERENCES cabinets(id)
  outlet_id       INT REFERENCES outlets(id)
  endpoint_key    TEXT NOT NULL   -- 'controls.socket_cmd'
  action          TEXT NOT NULL   -- 'activate' | 'stop' | …
  actor_type      TEXT NOT NULL   -- 'customer_nfc' | 'operator' | 'erp_auto'
  actor_ref       TEXT            -- user_id ili e-mail operatera
  tag_source      TEXT            -- 'scan' | 'mapping' | NULL      (BLOK-2, §1.1)
  request_url     TEXT NOT NULL   -- cijeli URL — hvata dvostruki ext (§2.5)
  http_status     INT
  detail          TEXT            -- ormarov `detail`, za razlikovanje 409
  source_ip       TEXT
  created_at      TIMESTAMPTZ NOT NULL
```

> **Odlučeno** · Retencija se piše **u istom commitu** kao prikupljanje, i to kao migracija +
> zadatak, ne kao bilješka.
>
> **Zašto** · D7 to izrijekom traži. Danas u repou **nema nijedne retencijske logike**
> (mjereno: `grep -rniE "retention|prune|purge|cleanup|vacuum|TTL"` po `backend/app` → nula
> pogodaka), a `sync_log` dobiva redak po pozivu — na uspjeh, na grešku **i opet na stale**
> (`backend/app/services/pedestal_api.py:231` pa `:236`, dva retka po jednom neuspjelom
> pozivu). Bez poller-a to je sitno; s pollerom iz faze 4 nije.
>
> **Ako griješim** · Prozor je jedan broj u konfiguraciji.

| Tablica | Prozor | Zašto taj |
|---|---|---|
| `sync_log` | **30 dana** | dijagnostika integracije; starije od mjesec nikad nije pogledano |
| `session_log` (sirovi webhook) | **90 dana** | trag za otklanjanje; mjerodavan zapis je `sessions` |
| `alarm_log` | **400 dana** | sezona na sezonu, s preklopom |
| `consumption_intervals` | **400 dana** sirovo, zatim mjesečni agregat | energetski agent (D14) traži povijest |
| `command_audit` | **2 godine** | sigurnosni dokaz (D13); kraće od toga nije dokaz |
| `sessions`, `credit_ledger`, `billing_records` | **trajno** | računovodstvo |
| slike kamere | **ne spremaju se** | već je tako: `pedestal_ext.py:114-118` proslijedi bajtove, `pedestal_api.py:397-399` izrijekom ne kešira |

### §4.8 · Popravci postojećeg modela (faza 1)

> **Odlučeno** · `pedestal_cache` prestaje ključati redove hashem; dobiva pravi stupac
> `cache_key TEXT` i `UNIQUE (marina_id, cache_key)`.
>
> **Zašto** · Danas je ključ `abs(hash(cache_key)) % (10**9)`
> (`backend/app/services/pedestal_api.py:483` i `:520`). Python randomizira hash stringova po
> procesu, a `PYTHONHASHSEED` nije postavljen nigdje u repou (mjereno: `grep -rn PYTHONHASHSEED`
> → nula pogodaka izvan `.venv`). Posljedica: **svaki restart izmisli novi skup sintetičkih
> `pedestal_id`-eva**, stari redci ostaju kao siročići s punim JSON odgovorom, i **stale
> fallback tiho prestaje raditi za sve keširano prije restarta**. Dodatno, taj stupac dijeli
> prostor s pravim `pedestal_id`-em koji upisuje webhook (`backend/app/routers/webhooks.py:130`)
> — dva različita prostora identiteta u jednom stupcu.
>
> **Ako griješim** · Ništa ne ovisi o starim redcima; migracija ih briše.

Uz to u fazi 1: `get_camera_detections` (`backend/app/services/pedestal_api.py:365-375`) se
**briše** — cilja `/api/camera/{id}/detections`, koja na ormaru ne postoji (mjereno:
`grep -rn "detections" Cloud_IOT/backend/app/routers/` → nema rute), nije u katalogu, i ima
**nula pozivatelja** u ERP-u (mjereno: `grep -rn "get_camera_detections" backend/app/routers/`
→ 0).

---

## §5 Tokovi

### §5.1 · NFC tok (D6) — od skeniranja do obračuna

```
1  Korisnik skenira naljepnicu NA PRIKLJUČKU        (mobilna app)
2  app → ERP  {nfc_tag_id, user_id}                 app NIKAD ne zove ormar
3  ERP: tag → (ormar, priključak)                   oba zapisa UID-a (§4.4)
4  ERP ODLUČUJE (§5.4). Ako išta fali:
     odbij s rečenicom za čovjeka na molu
     ORMARU SE NE ŠALJE NIŠTA
5  ERP → ormar  POST /api/nfc/scan                  kanal B, X-API-Key
6  ERP → app    "Priklopite kabel za početak"       samo ako je 5 uspio
7  Korisnik priklopi → ormar uključi, mjeri, javi
8  ormar → ERP  potrošnja ~60 s                     webhook, i/ili pull (§5.2)
9  ERP: prepaid odbija kredit | postpaid bilježi
10 Prepaid na nuli → ERP → ormar  POST /api/nfc/session/{id}/stop
11 Ormar isključi, zatvori sesiju, javi konačnu brojku
12 ERP zatvori obračun                              račun čeka §1.4
```

Priprema **istječe nakon 5 min** bez priklopa, bez posljedica (D3, PDF §4).

> **Odlučeno** · Korak 4 je **vratar**: ERP ne šalje ormaru ništa dok odluka nije pozitivna.
>
> **Zašto** · D6 korak 5 i PDF §5A izrijekom. Priprema poslana korisniku bez kredita znači da
> ormar drži rezervaciju za sesiju koja se ne smije dogoditi, a korisnik na molu vidi
> „spremno" pa čeka.
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije.

> **Odlučeno** · Skenirani tag **ne dokazuje fizičku prisutnost**; autorizacija je korisnik +
> ERP, tag kaže samo *koji priključak*.
>
> **Zašto** · D6: UID nije tajna — objavljen je u dokumentaciji koja ide marini, a ISO 15693
> se kopira. Ormar to isto kaže o svom ključu (`nfc.py:482`: „must be assumed known").
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije.

### §5.2 · Prikupljanje, pull-usklađivanje, retencija (D7)

> **Odlučeno** · Webhook je za **brzinu**; **naplata se usklađuje pullom**. Poller i retencija
> idu u **isti commit**.
>
> **Zašto** · D7. Ormarov webhook nema potpis — samo statični `X-API-Key` u zaglavlju, bez
> HMAC-a nad tijelom, bez noncea, i ako ključ nije postavljen šalje **prazan** `X-API-Key`
> umjesto nijednog (NALAZ 6.1, `Cloud_IOT/backend/app/services/webhook_service.py:93`). Nema
> retry-a: jedan POST, timeout 5 s, iznimka samo u log (NALAZ 6.2, `:99-109`). Propušten
> događaj je **trajno izgubljen i ERP ne može znati da je postojao**. A `timestamp` je vrijeme
> otpreme, ne nastanka.
>
> **Ako griješim** · Ako ormar dobije potpis i retry (§7.R3), pull ostaje kao jeftina provjera
> i interval mu se produži.

| Što | Interval | Zašto taj |
|---|---|---|
| `pedestals.health` | **60 s** | §3 traži `STALE` na 2× heartbeata i `OFFLINE` na 10 min; rjeđe od 60 s ne može dati taj prag |
| `sessions.active` | 60 s | aktivna sesija je ono što se naplaćuje |
| `load.*` (ormari s aktivnom sesijom) | 60 s | telemetrija za naplatu i §3 |
| `load.*` (ostali) | 300 s | povijest za energetskog agenta, bez troška |
| `pedestals.status_ext` | 120 s | `door_state` je sigurnosni signal (D16); kompromis s prometom |
| `berths.list` | 300 s | ML je sporiji od toga |
| `alarms.active` | 120 s | webhook alarma nije pouzdan (NALAZ 6.2) |
| **pull-usklađivanje sesija** | 15 min za korisnike s otvorenom ili nedavno zatvorenom sesijom; **noćni puni prolaz** | §1.6: nema endpointa po vremenskom rasponu, samo `by-user` |

Pull ide na `GET /api/nfc/sessions/by-user/{user_id}` — i **samo čitanje te rute broji kao
usklađivanje na ormaru** (`Cloud_IOT/backend/app/routers/nfc.py:755`). Dok §7.R2 ne postoji,
ERP ne može čitati `/api/nfc/reconciliation` (traži operaterski JWT) pa **sam vodi** evidenciju
„zadnje usklađeno" po ormaru i prikazuje je (§6.3).

Prijemnik webhooka: danas `X-API-Key`, **spreman za HMAC** — provjera potpisa je jedna
funkcija s zastavicom po ormaru, da uključenje ne traži izdanje ERP-a. Današnji
`_verify_signature` (`backend/app/routers/webhooks.py:30-36`) već radi HMAC-SHA256; ostaje, a
ormar ga još ne koristi.

### §5.3 · Upravljanje (D5)

Jedini preduvjet: **Smart Mode ON**. ERP ga čita iz `pedestals.health`
(`Cloud_IOT/backend/app/routers/pedestal_config.py:419`) — `pedestals.status_ext` ga **ne
vraća** (NALAZ 2.2), pa je `health` jedini izvor.

> **Odlučeno** · Kad je Smart Mode OFF, ERP **unaprijed uklanja kontrole** — ne siva ih — uz
> jednu rečenicu. Odčitanja se iscrtavaju normalno.
>
> **Zašto** · D5 i ormarov §5.2. Odčitanja su stvarna, došla su preko MQTT-a. Siva tipka je
> obećanje da nešto postoji; odsutna kontrola je istina. Pravilo je istovjetno pravilu za
> odsutnu mogućnost (D3): `available: false` ne iscrtava **nijedan** kontrolni element u DOM-u
> — ne `disabled`, ne `pointer-events: none`, **odsutan**.
>
> **Ako griješim** · Jedan uvjet u jednoj komponenti.

Svaka naredba piše redak u `command_audit` **prije** poziva i dopunjuje ga ishodom — da
naredba koja nikad nije dobila odgovor ostane vidljiva.

### §5.4 · Prepaid i postpaid (D9, D10)

Isti slijed pri **svakom** skeniranju; razlikuje se samo treći odgovor:

```
1  postoji li korisnik?                        → ne: odbij
2  važeći ugovor?                              → ne: odbij
3  billing_mode?
     PREPAID  → kredit ≥ min_start_amount?     → ne: odbij
                tijekom: svaka poruka → iznos po tarifi → odbij od kredita
                upozorenje na low_credit_warn_pct
                na nuli (ili allowed_negative) → ERP šalje STOP
     POSTPAID → nije blokiran, saldo < max_unpaid?  → ne: odbij
                tijekom: samo bilježi, prikaži rastući iznos
                stop samo na dogovorene granice (max_kwh, max_session_min)
4  pošalji ormaru pripremu priključka
```

> **Odlučeno** · Prekoračenje se prihvaća **svjesno**: ako ERP izgubi vezu, ormar nastavlja
> dovod jer nije dobio stop.
>
> **Zašto** · D9 i PDF §5. Ormar ne zna kredit i ne može ga znati (D0). Tvrda granica bez
> prekoračenja traži logiku na ormaru (unaprijed zadana gornja granica po sesiji) i **nije u
> trenutnoj izvedbi**. Kašnjenje između zadnje poruke i stopa je do ~60 s.
>
> **Ako griješim** · `allowed_negative` je jedan broj; tvrda granica je zahtjev prema ormaru,
> ne izmjena ERP-a.

> **Odlučeno** · Stop od osoblja marine ima prednost; ERP-ov stop na već završenu sesiju
> dobiva **409** i to **nije greška** — obračuna se po zadnjoj brojci.
>
> **Zašto** · D10 i `Cloud_IOT/backend/app/routers/nfc.py:782`. Logirati to kao grešku znači
> da će se u logu nakupiti normalan rad, a stvarne greške utopiti.
>
> **Ako griješim** · Jedan uvjet.

---

## §6 Stranice

Tri razine. Natrag je uvijek vidljiv. Nijedan overlay ne otvara drugi overlay.
**Odsutna mogućnost se ne iscrtava** — ni onemogućena kontrola — umjesto nje jedna rečenica (D3).
**Imena kupaca ne idu na zaslone marine** (D15).

```
L1  /marina/:id                   2D karta + popis vezova
     │
     ├── L2  /marina/:id/berth/:bid     Vez
     │        └── L3  …/history          Povijest potrošnje
     ├── L2  /marina/:id/sessions       Sesije
     ├── L2  /marina/:id/customers      Korisnici i kredit      (uloga koja naplaćuje)
     └── L2  /marina/:id/security       Sigurnost
```

### §6.1 · L1 — 2D karta marine

```
┌──────────────────────────────────────────────────────────────┐
│  Marina Krk                    [ Treba pažnju (2) ] [ Sve ] │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│      ╔═══════ POMOL A ═══════╗                               │
│      ║  ▓▓   ░░   ██   ▒▒    ║   ▓ crveno  vez 3            │
│      ║  A1   A2   A3   A4    ║   ░ sivo    vez 5            │
│      ╚═══════════════════════╝   █ plavo   vez 1            │
│         ◆ ORM_01                 ▒ zeleno  vez 2            │
│                                                              │
│   Nacrt je nacrtan JEDNOM. Svaki vez ima svoj id u SVG-u.   │
│   Aplikacija mijenja SAMO klasu elementa — nikad geometriju. │
├──────────────────────────────────────────────────────────────┤
│  ▲ VEZ 3          Otkriveno curenje vode                     │
│    Plovilo: odgovara slici · Struja: UKLJ 1 240 W           │
│    Voda: ISKLJ 0 L/min   (dijeli V1 s vezom 4)              │
│                                              2 alarma     › │
├──────────────────────────────────────────────────────────────┤
│  ? VEZ 5          Nema veze s ovim ormarom                   │
│    Trenutno ne vidimo ovaj vez.                              │
│    Podaci od 11:42                                        › │
├──────────────────────────────────────────────────────────────┤
│  ✓ VEZ 1          —                                          │
│    Plovilo: PRAVO · Struja: ISKLJ 0 W      [ Upali ]        │
│    Voda: na ovom vezu nema vodnog priključka                │
│                                                           › │
└──────────────────────────────────────────────────────────────┘
      Treba pažnju prvo, pa nepoznato, pa po broju veza
```

> **Odlučeno** · Nacrt marine je **statični SVG, nacrtan jednom**, s `svg_id` po vezu
> (`berths.svg_id`, §4.2). Aplikacija mijenja **samo CSS klasu** elementa.
>
> **Zašto** · D17 faza 6 to izrijekom traži. Generiranje geometrije iz podataka znači da
> promjena pomola postaje programski zadatak; crtež i podatak razdvojeni znače da marina
> pošalje novi SVG i ništa se ne kompajlira.
>
> **Ako griješim** · Ako marina nikad ne pošalje nacrt, popis vezova ispod karte je potpun
> zaslon sam za sebe — karta je dodatak, ne nosivi element.

> **Odlučeno** · Tihi ormar je **sivo, s vremenom zadnjeg podatka**, nikad zeleno.
>
> **Zašto** · D2 i ormarov §2.1. Tihi ormar nije prazan vez. Ovo je i jedini razlog zašto
> `is_stale` mora putovati do boje — danas ne putuje: `OccupancyEntry`
> (`frontend/src/pages/Dashboard.tsx:25-30`) i `OccupancyState`
> (`frontend/src/pages/PedestalDetail.tsx:43-48`) **nemaju polje `is_stale`**, premda ga
> ruter vraća (`backend/app/routers/pedestal_ext.py:70`) i tip ga deklarira
> (`frontend/src/api/pedestalExt.ts:26`).
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije.

### §6.2 · L2 — Vez

```
┌──────────────────────────────────────────────────────────────┐
│  ‹ Natrag        VEZ 3 · ORM_01 · pomol A    ▲ Curenje vode │
├──────────────────────────────────────────────────────────────┤
│  [ slika veza, obojena po stanju ]        [ Osvježi sliku ]  │
│  Analiza: 11:38 · podudaranje 0,81                           │
├──────────────────────────────────────────────────────────────┤
│  STRUJA · Q1 · 32 A trofazna                                 │
│    L1 5,2 A   L2 5,0 A   L3 5,1 A   ukupno 1,24 kW          │
│    Sesija #412 · 2,45 kWh · očitanje brojila                │
│                                       [ Isključi ]           │
├──────────────────────────────────────────────────────────────┤
│  VODA · V1 · 20 L/min        (dijeli s vezom 4)             │
│    Stanje: mirno · 0 L/min                                   │
│                                       [ Uključi ]            │
├──────────────────────────────────────────────────────────────┤
│  Trofazni Q1 iscrtava TRI vrijednosti; Q2-Q4 jednu.          │
│  Komponenta koja pretpostavlja jedan oblik je greška. (D3)   │
└──────────────────────────────────────────────────────────────┘
```

Pri Smart Mode OFF: odčitanja ostaju, **tipke nema**, umjesto njih rečenica iz §3.2 ranga 2.

### §6.3 · L2 — Sesije

```
┌──────────────────────────────────────────────────────────────┐
│  Sesije            [ Aktivne ] [ Za pregled (3) ] [ Sve ]   │
│  Zadnje usklađeno s ORM_01: 11:48  ✓                        │
├──────────────────────────────────────────────────────────────┤
│  #412  VEZ 3  Q1  struja   aktivna   2,45 kWh   očitanje    │
│  #411  VEZ 1  Q3  struja   završena  0,00 kWh   očitanje    │
│  #409  VEZ 2  V1  voda     završena     —       NIJE        │
│        ▲ Potrošnja nije izmjerena — treba pregled           │
│  #408  VEZ 4  Q2  struja   završena  1,10 kWh   procjena    │
├──────────────────────────────────────────────────────────────┤
│  "0,00" i "—" nisu isto. 0 je izmjereno. — nije izmjereno.   │
│  Uz svaku brojku stoji podrijetlo. (D10)                     │
└──────────────────────────────────────────────────────────────┘
```

### §6.4 · L2 — Korisnici i kredit (samo uloga koja naplaćuje)

```
┌──────────────────────────────────────────────────────────────┐
│  Korisnici                                   [ + Dopuna ]   │
├──────────────────────────────────────────────────────────────┤
│  erp-12345   prepaid    kredit 3,20 €   ▲ pri 20 %          │
│  erp-12901   prepaid    kredit 0,00 €   ✖ bez kredita       │
│  erp-10044   postpaid   saldo 128,40 €  granica 200,00 €    │
├──────────────────────────────────────────────────────────────┤
│  KNJIGA KREDITA · erp-12345                                  │
│   11:40  −0,42 €  potrošnja  sesija #412   stanje  3,20 €   │
│   09:12  +20,00 € dopuna     recepcija     stanje 23,88 €   │
│   Samo dodavanje. Nijedan redak se ne mijenja. (§4.5)        │
└──────────────────────────────────────────────────────────────┘
```

Ovaj zaslon je **jedino mjesto gdje se pojavljuje ime kupca**, i samo ulogama koje naplaćuju
(D15). Na L1, L2-vez i L2-sesije stoji `external_ref`, nikad ime.

### §6.5 · L2 — Sigurnost

```
┌──────────────────────────────────────────────────────────────┐
│  Sigurnost                        Slojevi 0-1: ✓   2: ✓     │
├──────────────────────────────────────────────────────────────┤
│  ▲ 11:31  ORM_01  Vrata otvorena izvan servisnog prozora    │
│  ▲ 11:31  ORM_01  Novi uređaj u LAN-u  (MAC a4:…)           │
│      → vrata + novi uređaj = KRITIČNO  (D16)                │
│  ·  10:02  VPS    42 blokirana IP-a (CrowdSec)              │
│  ·  09:55  ORM_01 Mamac dotaknut: /api/ext/admin/debug      │
├──────────────────────────────────────────────────────────────┤
│  SERVISNI PROZORI                        [ + Najavi ]       │
│  ORM_01   2026-10-14 08:00-12:00   Damir                     │
│  Bez najavljenog prozora signal vrata nije upotrebljiv.      │
└──────────────────────────────────────────────────────────────┘
```

---

## §7 Sigurnost

### §7.1 · ERP strana — slojevi 0–2 (D13)

**Sloj 0 · higijena** — dio postavljanja VPS-a, prije javnog izlaganja (§8):
MFA na ERP adminu, Tailscale i Teltonika RMS računu; Tailscale odobravanje uređaja + tailnet
lock; **Tailscale ACL** — ERP → ormar samo na port API-ja, ormar ↛ ERP, ormar ↛ ormar;
servisni račun **po ormaru** s minimalnim Gateway pravima (§2.3); **pinane verzije
ovisnosti**; automatska sigurnosna ažuriranja; backup; **tajne odvojene od diska aplikacije i
jedinstvene po ormaru**.

> **Odlučeno** · Fernet ključ (`ERP_ENCRYPTION_KEY`) i `JWT_SECRET` **ne stoje na istom disku**
> kao šifrirane lozinke, i učitavaju se iz `systemd` credentials, ne iz `.env` uz aplikaciju.
>
> **Zašto** · D13 ga navodi kao poznatu rupu. Ključ pored šifrata nije enkripcija nego
> odgađanje. Danas `backend/.env` drži oboje uz bazu.
>
> **Ako griješim** · Jedan put u konfiguraciji.

> **Odlučeno** · `JWT_SECRET` koji nije postavljen **zaustavlja podizanje** (fail-fast).
>
> **Zašto** · Danas se generira slučajan i upiše se CRITICAL u log
> (`backend/app/config.py:45-51`), a `docker-compose.yml:31` ga defaultira na
> `change-me-in-production`. Posljedica: svaki restart nevaljanim čini sve sesije, a nitko ne
> gleda log. Tiha degradacija sigurnosti je gora od odbijenog podizanja.
>
> **Ako griješim** · Jedan `raise` manje; razvoj dobiva `.env.example` s praznom vrijednošću
> i jednu naredbu za generiranje.

**Sloj 1 · klasična obrana:** `nftables` default-deny; SSH samo ključevi; CrowdSec (engine +
bouncer); Cloudflare ispred ERP UI-a (WAF, Access za admin); rate limiting; **audit log svake
upravljačke naredbe** (`command_audit`, §4.7); HMAC potpis webhooka (ERP strana spremna,
§5.2).

**Sloj 2 · mamci** — tiho bilježe, nitko legitiman ih ne dira:
lažni API ključ u konfiguraciji; lažni Gateway endpoint `/api/ext/admin/debug`; lažni servisni
račun; lažni ormar u Tailscale mreži.

**Signali iz D16** koje ERP prima i povezuje:
**novi uređaj u LAN-u** (nova MAC / DHCP zakup) i **vrata ormara** (`door_state` iz
`pedestals.status_ext`) izvan najavljenog servisnog prozora. Vrata + novi uređaj = **kritično**.

> **Odlučeno** · ERP ima pojam **najavljenog servisnog prozora po ormaru**
> (`service_windows(cabinet_id, from_at, to_at, announced_by)`), i bez njega signal vrata se
> prikuplja ali **ne diže alarm**.
>
> **Zašto** · D16 to izrijekom kaže: bez servisnog prozora signal vrata nije upotrebljiv.
> Alarm koji se diže svaki put kad serviser otvori ormar prestane se čitati u prvom tjednu.
>
> **Ako griješim** · Prozor je jedna tablica i jedan zaslon (§6.5).

> **Odlučeno** · Sadržaj logova, webhooka i odgovora ormara je **podatak, nikad uputa**.
> Detekciju radi kod; LLM samo trijažira i objašnjava; akcije su ograničene pravilima u kodu,
> ne promptom. Agent **ne mijenja vlastita pravila sam**: predlaže → pravilo radi u sjeni →
> čovjek odobrava → aktivno.
>
> **Zašto** · D13. Napadač kontrolira što piše u `User-Agent`, URL-u i korisničkom imenu, a
> ormarov webhook nije potpisan (NALAZ 6.1) pa se njegov sadržaj ne smije smatrati ni
> autentičnim.
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije.

### §7.2 · Što ERP traži od ormara — zahtjevi, ne izmjene

Repo ormara se ne dira. Ovo je lista koju nosim u njegov chat, po prioritetu.

| # | Zahtjev | Zašto ERP-u treba | Blokira |
|---|---|---|---|
| **R1** | Ext endpoint koji izlaže `berth_assignments` (vez → `socket_id`/`valve_id`) | NALAZ 4.2: veza vez→utičnica nije dostupna ni proxyjem ni direktno; `BerthOut` nosi `pedestal_id` ali ne `socket_id` | §4.3, dio faze 3 — **pod BLOK-1 (b) ili (c)** |
| **R2** | `/api/nfc/reconciliation` i `/reconciliation/divergence` dostupni s `X-API-Key` | danas traže operaterski JWT (`auth/dependencies.py:54`); to je jedini izvor „završeno a nepotvrđeno, najstarije prvo" | bolji pull u fazi 4; iteracija po korisnicima radi bez toga |
| **R3** | HMAC potpis + retry + dead-letter na webhooku | NALAZ 6.1, 6.2 | ništa — ERP već radi pullom (§5.2); ovo smanjuje promet, ne omogućuje funkciju |
| **R4** | Popravak 2.3 — mod se poštuje i na direktnim ext write rutama | „monitor" u UI-u danas ne čini ništa za tri write endpointa | uključivanje `breakers.socket_reset_ext` i `load.auto_stop_ack_ext` (§2.3) |
| **R5** | Popravak 1.3 — gateway match uspoređuje metodu | uključen `led_schedule.get` blokira `PUT`/`DELETE` | ništa za ERP (ne upravlja LED-om); prijavljeno jer je granica |
| **R6** | *(samo ako BLOK-2 završi kao (c))* operaterski put bez `nfc_tag_id` | §1.1 opcija (c) | ništa drugo |
| **R7** | `smart_mode` i u `pedestals.status_ext` | danas samo u `health` (NALAZ 2.2), pa ERP mora dva poziva gdje bi jedan dostajao | ništa — kozmetika prometa |
| **R8** | Zamagljivanje ljudi na slikama **prije** spremanja i slanja (`camera.frame_ext`) | D15 / GDPR: ML slike su obrada, ERP ih prikazuje | prikaz slike veza u §6.2 **nije blokiran**, ali je pravno izložen dok R8 ne postoji |

> **Odlučeno** · Dok R8 ne postoji, ERP **prikazuje sliku veza na zahtjev operatera i nikad je
> ne sprema**.
>
> **Zašto** · D15 traži zamagljivanje na ormaru, prije spremanja i slanja — to ERP ne može
> izvesti za ormar. Prikaz na zahtjev, bez spremanja, drži obradu na minimumu koji posao traži
> i ne stvara arhivu koju bi trebalo brisati. Već je tako u kodu
> (`backend/app/routers/pedestal_ext.py:114-118`).
>
> **Ako griješim** · Spremanje bi bila nova tablica i nova retencija; ne postojanje nečega je
> jeftinije od uklanjanja.

---

## §8 Isporuka i VPS

> **Odlučeno** · **systemd**, ne Docker. Jedan način, ne oba.
>
> **Zašto** · Tri mjerene činjenice i jedna posljedica. (1) U repou **nema nijednog
> Dockerfilea** (`git ls-files | grep -i docker` → prazno), a `docker-compose.yml:21-23` i
> `:40-42` referenciraju `backend/Dockerfile` i `frontend/Dockerfile` — `docker compose up`
> pada na build, kao što README tvrdi da radi. (2) VPS je **2 GB** (D13), a tamo se broji
> svaki MB: Docker daemon + tri sloja slika su režija koju ERP ne treba kad je jedan proces.
> (3) Slojevi 0 i 1 iz D13 su **domaćinski** — `nftables`, CrowdSec, `unattended-upgrades`,
> `systemd` credentials za tajne — i u Dockeru svaki od njih treba drugo rješenje. Posljedica:
> jedan `systemd` unit, jedan `nginx`, jedan Postgres, nijedan sloj između.
>
> **Ako griješim** · Dva Dockerfilea i `docker-compose.yml` koji već postoji; `systemd` unit se
> briše. Pola dana, i ništa u aplikacijskom kodu se ne mijenja.

`docker-compose.yml` se u fazi 5 **briše iz repoa**, jer datoteka koja ne radi a izgleda kao
način isporuke je gore od njenog nepostojanja.

### §8.1 · Što VPS treba

Ubuntu 24.04 LTS · Python 3.11+ · PostgreSQL 16+ · nginx · `cloudflared` (**samo za UI**) ·
Tailscale (**prema ormarima**, D12) · Node 18+ **samo za build**, ne za izvođenje.
**Ništa se ne kompajlira**: `psycopg2-binary`, `bcrypt` i `cryptography` dolaze kao wheel-ovi
(mjereno: instalirani u `backend/.venv` bez prevodioca).

> **Odlučeno** · uvicorn sluša na **`127.0.0.1`**, ne na `0.0.0.0`. Nginx je jedini javni
> slušatelj.
>
> **Zašto** · Danas je default `app_host = "0.0.0.0"` (`backend/app/config.py:16`), i to je
> **jedini medium nalaz bandita** u repou — B104, izmjeren pri commitu ove specifikacije
> (`tests/logs/bandit_last.log`: 0 high, 1 medium, 2 low na 2 270 redaka). Na 2 GB VPS-u s
> `nftables` default-deny to ne bi bilo iskorišteno, ali ovisiti o vatrozidu za nešto što je
> jedan redak konfiguracije znači da prvo pogrešno pravilo vatrozida izlaže aplikaciju
> izravno. Dva sloja koja kažu isto jeftinija su od jednog.
>
> **Ako griješim** · Jedan redak u `.env`; `docker-compose` varijanta (ako §8 ikad padne na
> Docker) traži `0.0.0.0` i tad se mijenja natrag.

### §8.2 · Veličina

| | Procjena | Obrazloženje |
|---|---|---|
| OS, minimalan | 150–250 MB | |
| PostgreSQL 16, `shared_buffers` 128 MB | 150–200 MB | |
| uvicorn, 1 worker | ~150 MB | FastAPI + SQLAlchemy + httpx |
| nginx | 10–20 MB | |
| CrowdSec engine + bouncer | 100–150 MB | D13 sloj 1 |
| **Ukupno u radu** | **~600–750 MB** | |

**RAM je vezujuće ograničenje, i veže pri buildu, ne u radu.** `npm install` + `vite build`
doseže 0,5–1 GB. Na **2 GB** oboje stane; na 1 GB aplikacija radi a build pada.

> **Odlučeno** · Frontend se **gradi na VPS-u**, u 2 GB, kao korak runbooka.
>
> **Zašto** · Build danas prolazi i mjeren je (§0.2): 21 s, 908 modula. Graditi drugdje i
> prenositi `dist/` znači drugo okruženje u lancu isporuke bez dobitka na 2 GB.
>
> **Ako griješim** · Ako build ikad prestane stati, `dist/` se gradi u CI-u i prenosi —
> jedan korak runbooka manje, jedan artefakt više.

Disk: **20 GB** (D13). OS ~2,5 GB, venv ~150 MB, `node_modules` ~110 MB (samo build),
Postgres baza ~50 MB na početku. Rast je ograničen retencijom iz §4.7; slike se ne spremaju.

### §8.3 · Tajne

**Nikad u repou.** `.env.example` s **praznim** vrijednostima; produkcijske tajne iz
`systemd` credentials (`LoadCredential=`), ne iz datoteke uz aplikaciju (§7.1).
Jedinstvene **po ormaru**: servisni račun, `X-API-Key`, webhook secret.

### §8.4 · Backup i runbook

`pg_dump` dnevno, šifrirano, **izvan VPS-a**; mjesečna probna obnova — backup koji nikad nije
obnovljen nije backup.

Runbook se izvodi **na čistom VPS-u** prije nego se ERP izloži, i taj prolaz je uvjet za
završetak faze 5:

```
1  OS, korisnik, SSH samo ključevi, nftables default-deny
2  Tailscale + ACL; provjeri ormar ↛ ERP
3  PostgreSQL, baza, korisnik
4  systemd credentials: JWT_SECRET, ERP_ENCRYPTION_KEY, DATABASE_URL
5  venv iz LOCK datoteke (ne iz requirements.txt)
6  alembic upgrade head
7  frontend build
8  nginx + cloudflared (SAMO UI) + Cloudflare Access na /admin
9  CrowdSec engine + bouncer
10 unattended-upgrades
11 backup cron + JEDNA probna obnova
12 bash scripts/verify_system.sh   → sve prolazi
13 TEK TADA javno izlaganje
```

---

## §9 Testovi, po redoslijedu

> **Odlučeno** · **Prvi test je da se aplikacija diže**, i **ne smije moći proći prazno**.
>
> **Zašto** · Ormarova specifikacija je to naučila na svoj račun:
> `tests/playwright_e2e.sh:41-45` izlazi s 0 kad backend nije na :8000, i to je točno i
> učinio na zadnjem pushu. Komponentni paket koji prolazi dok se aplikacija ne diže je isti
> propust na drugom mjestu. Ovdje je rizik isti: gate je lokalni i neverzioniran
> (`.git/hooks/pre-push` postoji, `.githooks/` ne, `core.hooksPath` nije postavljen), pa
> klon nema nikakav gate.
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije.

| # | Test | Što tvrdi | Mora pasti kad |
|---|---|---|---|
| **TC-ERP-BOOT-01** | aplikacija se diže | pravi `vite build`, pravi uvicorn, prava migracija; `GET /api/health` → 200; prijava → 200; `/marina/:id` iscrta redove vezova | bundle se ne gradi, migracija pada, ruta je pokvarena, `JWT_SECRET` fali |
| **TC-ERP-BOOT-02** | gate ne može proći prazno | ako backend nije podignut, stage **pada**, nikad `exit 0`; ispiše broj preskočenih | netko „popravi" gate preskakanjem |
| **TC-ERP-GATE-01** | gate je u repou | `.githooks/pre-push` postoji **i** `core.hooksPath` je postavljen; CI vrti isti skript | gate je samo lokalan |
| **TC-ERP-DEP-01** | ovisnosti su pinane | lock datoteka postoji; instalacija iz nje daje izmjerene verzije (§0.4) | netko doda nepinanu ovisnost |
| **TC-ERP-AUTH-01** | neautentificirano = **401** | sve **23** zaštićene rute (mjereno: `grep -rho "Depends(get_current_user)" backend/app/routers/*.py \| wc -l` → 23, od 30 ukupno); **strogo 401**, ne `in (401, 403)` | HTTPBearer se vrati na 403 (§0.1) |
| **TC-ERP-AUTH-02** | `JWT_SECRET` fail-fast | podizanje bez njega **pada** | netko vrati slučajno generiranje |
| **TC-ERP-CACHE-01** | keš preživi restart | `cache_key` kao stupac; dva procesa, isti ključ, isti redak | hash se vrati kao ključ |

### §9.1 · Ugovorni testovi protiv simulatora ormara

> **Odlučeno** · Ugovorni testovi **ne idu na pravi ormar**. Simulator ormara živi u ovom
> repou, građen iz **snimljenih odgovora Krka**.
>
> **Zašto** · D17 faza 2 to traži, i ormarova specifikacija §4.10 ima isti zaključak iz istog
> razloga: svaka konfiguracija koju ugovor mora podnijeti mora se moći pogledati bez puta na
> Krk. Dodatno, ugovorni test protiv pravog ormara **pali struju stvarnom gostu**.
>
> **Ako griješim** · Simulator koji se razilazi od ormara gori je od nikakvog — zato
> TC-ERP-SIM-00.

| # | Test | Scenarij |
|---|---|---|
| **TC-ERP-SIM-00** | simulator odgovara ugovoru | ključevi 16-ključnog payloada su **točno** oni iz `erp_session_payload_contract.md`; tri oblika occupancy odgovora iz NALAZ 4.1 |
| **TC-ERP-SIM-01** | **puni ormar** 4+2 | Q1–Q4, V1, V2; mapiranje, mogućnosti, NFC tagovi |
| **TC-ERP-SIM-02** | **retrofit** | samo utičnice; **voda se ne iscrtava nigdje** — ni kao onemogućena kontrola |
| **TC-ERP-SIM-03** | **trofazna Q1** | `currentAmpsL1..L3` + `powerKwTotal`; Q2–Q4 `currentAmps` + `powerKw`; nijedna komponenta ne pretpostavlja jedan oblik |
| **TC-ERP-SIM-04** | **dijeljeni ventil** | V1 služi vezove 3 i 4; „(dijeli V1 s vezom 4)" je **razjašnjenje nadzora, nikad napomena na računu** (ormarov §4.5) |
| **TC-ERP-SIM-05** | **tihi ormar** | `last_heartbeat` star 11 min, a retained stanje izgleda zdravo → **sivo**, `no_contact`, `is_stale` putuje do boje |
| **TC-ERP-SIM-06** | **Smart Mode OFF** | odčitanja se iscrtavaju; **kontrole odsutne iz DOM-a**, ne `disabled`; 409 → rečenica, nikad 500 |
| **TC-ERP-SIM-07** | tri različita 409 | Smart Mode / no plug / busy → tri različita `status_code` i tri rečenice |
| **TC-ERP-SIM-08** | 403 ne postaje greška | endpoint nije uključen → `capability not_enabled`, prestane se zvati, ponovna proba za 1 h |
| **TC-ERP-SIM-09** | 422 je bug u ERP-u | `display_id` na `load.*` → logira se kao bug, ne ponavlja |
| **TC-ERP-SIM-10** | dvostruki `ext` | `/api/ext/ext/…` → 401 s **cijelim URL-om u logu** (NALAZ 1.2) |
| **TC-ERP-SIM-11** | `null` nije 0 | `energy_kwh: null` → `manual_review`, prikaz **—**, **ne naplaćuje se** |
| **TC-ERP-SIM-12** | preračun brojke | `end − start ≠ brojka` → nalaz, ne tiho prihvaćanje (§2.4) |
| **TC-ERP-SIM-13** | `V1` ≠ `Q1` | oba su `socket_id = 1` interno; usklađivanje na string, nikad na broj |
| **TC-ERP-SIM-14** | oba zapisa UID-a | tag nađen i po `uid_primary` i po `uid_reversed` |
| **TC-ERP-SIM-15** | statusi se računaju na serveru | izvorni skan: nijedna `status_code` vrijednost se ne izvodi u `frontend/src/**` |
| **TC-ERP-SIM-16** | odsutna mogućnost | `available: false` → **nijedan** kontrolni element u DOM-u (traži se odsutnost, ne `disabled`) |

### §9.2 · Prihvatni testovi na pravom ormaru (D11)

Vrte se **jednom, na Krku, u fazi 7**, i njihov prolaz je definicija dovršenosti te faze.

| # | D11 | Što mora biti istina |
|---|---|---|
| **TC-ERP-ACC-01** | 1 | električna naljepnica: skeniranje → priklop → potrošnja → kraj; brojka se slaže **na obje strane** |
| **TC-ERP-ACC-02** | 2 | vodna naljepnica, isto, u litrama |
| **TC-ERP-ACC-03** | 3 | skeniranje bez kredita: ERP odbija, **naredba se ne šalje**, korisnik dobiva razlog |
| **TC-ERP-ACC-04** | 4 | kredit potrošen tijekom uporabe: ERP sam šalje stop, ormar gasi, korisnik obaviješten |
| **TC-ERP-ACC-05** | 5 | skeniranje bez priklopa: priprema istječe nakon 5 min **bez posljedica** |
| **TC-ERP-ACC-06** | 6 | stop od osoblja: ERP ispravno zatvara obračun, 409 nije greška |

---

## §10 Redoslijed izvedbe

Iz D17. Redoslijed je obvezujući; faza ne počinje dok prethodna nije prihvaćena. Svaka
završava zelenim gateom i ažuriranom ovom specifikacijom (verzija +1, što se promijenilo).

| # | Faza | Završava s |
|---|---|---|
| **1** | **Temelji koji ne lažu** — `.githooks` + `core.hooksPath`, CI, linter, **lock datoteka**, dva tolerantna assertiona pritegnuta na 401 (§0.1), **test podizanja koji ne može proći prazno**, `JWT_SECRET` fail-fast, `pedestal_cache` stupac umjesto hasha, brisanje `camera/detections` | gate koji **ne može proći ako se aplikacija ne diže**; TC-ERP-BOOT-01/02, GATE-01, DEP-01, AUTH-01/02, CACHE-01 zeleni |
| **2** | **Ugovor s ormarom + simulator** — tablica ključ→putanja, rukovanje 401/403/409/422/503/5xx po §2.5, Smart Mode iz `health`, PK vs `display_id`, `device_connected`, `berths.list`, `is_stale` do boje, kanal B s `X-API-Key`; simulator (puni, retrofit, trofazna Q1, dijeljeni ventil, tihi ormar, Smart Mode OFF) | TC-ERP-SIM-00..16 zeleni; **Berths/409/`is_stale` ispravljeni** |
| **3** | **Model podataka** — §4 u cijelosti, mapiranje po rješenju BLOK-1, NFC tagovi s dva zapisa + **CSV uvoz za Krk**, tip uređaja i mogućnosti, korisnici, ugovori, `billing_mode` default `prepaid`, knjiga kredita, `consumption_source` | migracije `005+`; **uvoz Krk CSV-a pogađa točan priključak** (ne samo „prepoznato") |
| **4** | **Prikupljanje + retencija u istom commitu** — poller po §5.2, pull-usklađivanje `by-user`, prijemnik webhooka (danas `X-API-Key`, spreman za HMAC), `command_audit` | podaci teku; **rast baze izmjeren i ograničen** — brojka prije i poslije 7 dana |
| **5** | **VPS** — systemd (§8), 2 GB / 20 GB, Postgres, nginx, `cloudflared` samo za UI, Tailscale prema ormarima, **slojevi 0 i 1 PRIJE javnog izlaganja**, backup + probna obnova, runbook; `docker-compose.yml` obrisan | ERP javno dostupan iza Cloudflare Accessa; **runbook proveden na čistom VPS-u** |
| **6** | **Zauzeće vezova + 2D SVG** — četiri signala iz §3.1, tablica stanja §3.2, statični SVG s `svg_id` po vezu | **Krk na karti, četiri signala, sivo za tiho** |
| **7** | **Poslovna logika i NFC tok** — §5.1, §5.4, tarifa po §1.3, obračunski zapisi po §1.4 | **TC-ERP-ACC-01..06 prolaze na pravom ormaru** |
| **8** | **Sigurnosni modul v1** — mamci, domenske detekcije, signali vrata i novog uređaja, servisni prozori, CVE/KEV prema **pinanim** verzijama, zaslon §6.5 | prvi stvarni nalazi na VPS-u i Krku |
| **9** | **Energetski agent** — tek kad postoji povijest iz faze 4 | — |

Faza 2 prije faze 6 ima isti razlog kao korak 1 prije koraka 4 u ormarovoj specifikaciji: s
ugovorom pokrivenim simulatorom, L1 je posao iscrtavanja nad fiksnim oblikom.

---

## §11 Odgođeno

Nađeno usput. Nije u izvedbi gore; tvoje je da odlučiš prioritet.

| # | Stvar | Zašto odgođeno |
|---|---|---|
| O1 | **`bcrypt==4.0.1` je jedini pin u cijelom `requirements.txt`, i nosiv je** — `passlib` 1.7.4 (`backend/app/routers/auth.py:8,20`, `backend/app/database.py:54,56`) puca s `bcrypt` ≥ 4.1. Dakle jedini pin u repou drži autentifikaciju, a nigdje nije zapisano zašto | faza 1 pinuje sve; ovaj redak postoji da se pri pinanju **ne** „počisti" kao suvišan. Prijelaz s `passlib` na `bcrypt` izravno je zasebna odluka, ne nusproizvod |
| O2 | `SecurityMiddleware` je **samo promatrač** (`backend/app/middleware/security.py:9`) — skenira, logira, nikad ne blokira. CrowdSec iz D13 sloja 1 pokriva isto bolje | preklapanje se rješava kad sloj 1 stane na VPS |
| O3 | Bundle je **646 kB** u jednom chunku (§0.2); Vite to i prijavljuje | radi; code-splitting je optimizacija bez korisnika koji se žali |
| O4 | `frontend/package-lock.json` je **nepraćen** u repou (`git status`) — a faza 1 traži lock datoteku | riješit će ga faza 1; navedeno da se ne izgubi |
| O5 | `erp_docs_inputs.zip` stoji u korijenu repoa, nepraćen | tvoja datoteka; nisam je brisao |
| O6 | 11 događaja se emitira na ormaru a nije u `EVENT_CATALOG`, među njima **`meter_telemetry_received`** (telemetrija brojila) i **`direct_cmd_sent`** (jedina push-potvrda da je naredba otišla) — NALAZ 6.3 | ERP ih **ne može pretplatiti**; pull ih pokriva. Zahtjev prema ormaru ako ikad zatrebaju |
| O7 | `usage.*`, `mobile.*`, `qr.*` rute: usmjeravanje je isto na `773bca6` i `main`, ali `usage_history.py` (+30/−7), `mobile.py` (+168/−28) i `qr.py` (+7/−2) su mijenjani — **oblik odgovora se može razlikovati** | izvještaj ormara to nije provjeravao polje po polje; ERP koristi samo `usage.history`, i to za usklađivanje |
| O8 | Postoji li brojilo na glavnom priključku marine (za vršnu snagu, D14) | energetski agent, faza 9 |
| O9 | Rotacija `X-API-Key` za kanal B — ključ je ugrađen u mobilnu aplikaciju i **mora se smatrati poznatim** (`Cloud_IOT/.../nfc.py:482`) | sekvencirano za ormarom; ERP strana je jedan stupac (`cabinets.erp_api_key_enc`) |
| O10 | Činjenice iz D16 „Najprije provjeriti" — Wi-Fi na routeru, javna IP na SIM-u, MQTT autentifikacija, enkripcija diska, jesu li tajne iste na oba ormara, verzija Teltonika firmwarea | nije ERP kod; potrebno prije faze 5 i 8 |

---

## §12 Što NE predlažem

- **Ne gradim vlastiti MQTT broker.** D12: Tailscale, ERP zove ormar izravno. Centralni
  broker ostaje opcija za kasnije, kao zaseban servis, nikad kao dio ERP-a.
- **Ne diram repo ormara.** Sve što ERP od njega treba je u §7.2 kao zahtjev s brojem.
- **Ne prikazujem imena kupaca na zaslonima marine.** Samo §6.4, samo ulogama koje naplaćuju.
- **Ne uključujem automatsko izvršavanje agenata.** D13: predlaže → sjena → čovjek odobri →
  aktivno. Faza 8 dolazi s mamcima i detekcijama, ne s autonomijom.
- **Ne gradim fiskalizaciju** dok §1.4 nije odlučen, i ne pravim „skoro fiskalni" račun koji
  izgleda kao račun a nije.
- **Ne radim tvrdu granicu potrošnje bez prekoračenja.** D9: traži logiku na ormaru; ERP ne
  može, i pretvaranje da može znači tihi gubitak.
- **Ne prepisujem postojećih osam tablica** u fazi 3. Dodaje se; briše se kasnije i odvojeno.
- **Ne uključujem `breakers.socket_reset_ext`, `load.auto_stop_ack_ext` ni
  `berths.push_image_ext`** prije ormarovog popravka 2.3 — kontrola koja izgleda isključena a
  poznati URL je doseže je točno oblik koji je zabranjen.
- **Ne koristim verifikaciju u Gateway UI-u kao dokaz** ničega (NALAZ 3.1, 3.2).
- **Ne gradim nove grafikone.** Energija dobiva dubinu u fazi 9, ne nove prikaze u fazi 6.
- **Ne radim multi-tenant ključeve.** Jedan servisni račun po ormaru, po postavljanju.
- **Ne radim QR.** NFC je jedini put ulaska korisnika (D6).

---

`docs/erp_spec.md` · verzija 1 · 2026-10-11

Odobri u jednom prolazu. Po odobrenju: faza 1, pa stop do tvog OK-a.
Pet odluka iz §1 blokira točno ono što je tamo navedeno — faze 1 i 2 ne čekaju nijednu.
