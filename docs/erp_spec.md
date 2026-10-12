# ERP-IOT · Specifikacija za odobrenje

Što se gradi, u kojem redoslijedu, i svaka odluka izrečena tako da ispravak
košta jedan redak, a ne razgovor.

    Verzija 5.2 — dopuna v5: odgovor ormara na R14 (2026-10-12)
    Datum 2026-10-12
    Status faze 1 i 2 ZAVRŠENE, gate i CI zeleni (§10.1, §10.2); faza 3 čeka odobrenje;
           §1 je prazan, ali §0.7 donosi točke koje traže tvoju potvrdu

Čita se uz `docs/inputs/odluke.md` **v2.1** (odluke, obvezujuće — v2.1 dodaje **D18**),
`docs/inputs/ormar_gateway_izvjestaj.md` (ugovor s ormarom, file:line),
`docs/inputs/erp_inventar.md` (stanje repoa 2026-10-10) i
`docs/inputs/ormar_ui_v2_spec.txt` (specifikacija ormara — uzor forme i izvor rječnika stanja).

**Sve u ovom dokumentu je ODLUČENO. §1 je prazan — nema otvorenih blokatora.**

### Što se promijenilo u verziji 5.2

| | |
|---|---|
| **R14 prihvaćen** | ormar je odgovorio i prihvatio pojednostavljenje D6.2, s redoslijedom **a0 → a → b → c** (§7.2) |
| **R15 · NOVO — voda** | `/scan` pa izričito `water/{V}/cmd activate`; u ERP načinu ormar **odbija otvoriti ventil bez važeće rezervacije** |
| **Auto-otvaranje ventila** | ormar ga gasi u kodu (korak a0). Do tada: **provjera stanja na ormaru 1** — O28 |
| **`erp_ref`** | novi stupac na ormaru uz stare; povijest se ne prepisuje. ERP ga generira (§4.6) |
| **Usklađivanje po rasponu** | `ended_from` uključivo, `ended_to` isključivo, sa stranicama — zamjenjuje iteriranje po korisnicima (§5.2) |

### Što se promijenilo u verziji 5.1

| | |
|---|---|
| **D6.2 · NOVO — što ormar zna, a što ne** | tvoja odluka od 2026-10-12: ormar **zna sesije kao mjerenje**, ali **ne zna NFC mapiranje ni korisnike** (§2.4) |
| **§7.2 R14** | zahtjev ormaru: **zakomentirati (ne brisati)** registar naljepnica i MODE 2, `/scan` po priključku s `erp_ref`, sesija bez korisnika, čitanje bez nuspojava + izričit `ack` |
| **§11 O27** | prati R14; dok ormar ne odgovori, vrijedi stanje iz faze 2 (§0.7 #1) |

### Što se promijenilo u verziji 5

| | |
|---|---|
| **Faza 2 završena** | gate 6/6 i CI zeleni; izvještaj s brojkama u **§10.2** |
| **§0.7 · NOVO — ispravci iz koda ormara** | simulator je sagrađen iz **koda** ormara (`Cloud_IOT` `a709cf8`, samo `git show`), ne iz snimljenih odgovora — njih u repou nema. Čitanje je oborilo **devet** pretpostavki ove specifikacije; dvije traže tvoju potvrdu (⚠) |
| **§2.4 · `GET /session/{id}` nije siguran za prikaz** | i on piše `last_reconciled_at` — kao `by-user`. Oba su sada samo za usklađivanje (⚠ §0.7 #1) |
| **§2.5 · četiri nova retka** | 400 `session_state_changed`, 404 `not_found`, 409 `nfc_mapping_mismatch`; 503 „Not enabled" s direktnih ruta = `not_enabled` |
| **§3.1 / §3.2** | heartbeat 15 s → `STALE` nakon 30 s; novi redak `unclassified` (plovilo nepoznato, ništa drugo istina) — **nije zeleno** |
| **§4.1** | ormar **ne kaže ima li vode**; `device_type` i mapiranje vez→priključak su ERP podatak, do faze 3 iz `ERP_CABINETS_FILE` (⚠ §0.7 #3) |
| **§9** | BOOT-01b je stage gatea (pravi Chromium); SIM-00..16 zeleni, s napomenom što je od njih ugovorni dio a što čeka fazu 3/7 |
| **§7.2 / §11** | R2b, R12, R13 novi zahtjevi; O15, O16, O18, O19, O20 zatvoreni; O17 odlučen; novi O21–O26 |

### Što se promijenilo u verziji 4

| | |
|---|---|
| **Faza 1 završena** | gate zelen, izvještaj s brojkama u **§10.1**; 8 commitova `faza1(1/9)…(8/9)` + ovaj |
| **§9 TC-ERP-AUTH-01 ispravljen** | zaštićenih ruta je **27 od 31**, ne 23 od 30 — grep po `Depends(get_current_user)` promašuje rute zaštićene kroz `require_super_admin`/`require_any_operator`. Test uzima popis iz grafa ovisnosti aplikacije |
| **§11 O14 odlučeno i primijenjeno** | nepoznat e-mail, kriva lozinka i ugašen račun daju **isti 401 s istom porukom**; razlog samo u log |
| **§4 migracije** | faza 1 je potrošila `005` (`pedestal_cache.cache_key`); **faza 3 počinje od `006`** |
| **§11 novo** | O15 (vremenska enumeracija pri prijavi), O16 (lozinka u `alembic.ini`), O17 (modeli i migracije se razilaze u 9 indeksa), O18 (šira ruff pravila), O19 (`npm run lint` zove eslint koji nije instaliran), O20 (keš ignorira parametre upita) |

### Što se promijenilo u verziji 3

| | |
|---|---|
| **BLOK-3 zatvoren** | Ormar je popravljen prema svojoj specifikaciji: **ne naplaćuje i ne računa cijenu**, vraća stanje brojila za struju i vodu po ugovoru. Sva poslovna logika — potrošnja, cijena, kredit, naplata — je u ERP-u. **§1 je prazan** |
| **Faza 7 je jedna** | podjela na 7a/7b iz v2 je ukinuta (§10) |
| **Krk `773bca6` nije referenca** | §0.5 i §0.6 prepisani: ugovor je ugovor, ne commit. **Kad ERP prvi put stvarno spoji Krk, ugovorni test provjerava živi odgovor** (TC-ERP-LIVE-01), ne commit |
| **Cijena s ormara se ignorira** | pravilo ostaje i kad polja nema: ako u bilo kojem odgovoru ormara postoji polje s cijenom, ERP ga odbacuje pri parsiranju (§2.4, §12) |
| **TC-ERP-BOOT-01 podijeljen** | 01a backend+build+prijava u fazi 1; 01b iscrtavanje redova vezova u fazi 2, jer prije simulatora nema ormara koji bi odgovorio (§9) |

### Što se promijenilo u verziji 2

| | |
|---|---|
| **§1 · pet odluka odlučeno** | 1.1 → **(a)** uz uloge admin/operater, obvezan razlog, `tag_source='mapping'`. 1.2 → **D18**, ne (b). 1.3 → model podržava (c), pilot jedna cijena/kWh i /litru. 1.4 → **(a)**, fiskalni račun izdaje blagajna recepcije. 1.5 → **(a)**. Sve preseljeno u svoje sekcije kao odlučeno |
| **§1 · jedan nov blokator** | BLOK-3: kako faza 7 naplaćuje na Krku prije nadogradnje ormara (razlog u §0.6) |
| **§0.5 · NOVO — podrijetlo nalaza** | svi nalazi iz koda ormara čitani su na **`a709cf8`** (grana `develop`, 2026-10-11), **ne** na `773bca6` (Krk). Tablica po datoteci: što vrijedi za Krk, što ne |
| **§0.6 · NOVO — što Krk stvarno vraća** | NFC payload na Krku ima **10 ključeva, ne 16**; `socket_id` je **uvijek `"Qn"`** pa se vodna sesija ne može razlikovati; nema `session_type`, nema `water_liters`, nema `consumption_source`; `energy_kwh` pada na **životni zbroj brojila**; `estimated_cost` **postoji** i ormar cijeni |
| **§2.4 · prepisano** | dva ugovora sesije, Krk i `develop`, s posljedicama po ERP kod |
| **§4.3 · prepisano po D18** | mapiranje na obje strane, Admin unosi, ERP uspoređuje, neslaganje je stanje; bez endpointa za čitanje usporedba je **„nije moguće provjeriti"** |
| **§7.2 · prepisano** | zahtjevi R1–R11, svaki s commitom na kojem je utvrđen; **R2 je sada nalaz**: `GET /sessions/by-user` **mijenja stanje** na `develop` |
| **§9.1, §10, §11, §12** | testovi oblika Krka; faza 7 dobiva predkondiciju; dva nova odgođena |

Dvije stvari odsutne po odluci: **QR** — nema zaslona, nema polja; NFC je jedini put ulaska
korisnika (D6). **Vlastiti MQTT** — ERP ne gradi brokera (D12, D17).

---

## Napomena o metodi

Svaka tvrdnja o kodu niže nosi `file:line`, provjerenu u repou **danas, 2026-10-11**.
Putanje bez prefiksa su u `Lika-Digital/ERP-IOT`; putanje ormara nose prefiks `Cloud_IOT/`.
Repo ormara je **samo čitan** — nijedna izmjena, sve što ERP od njega traži je u §7 kao zahtjev.

**Svaki nalaz iz koda ormara nosi commit na kojem je utvrđen** — `a709cf8`, grana `develop`,
2026-10-11. Puna tablica po datoteci je §0.5. **Ali referenca za ponašanje ormara je ugovor,
ne commit**, i provjerava se živim odgovorom pri prvom spajanju (TC-ERP-LIVE-01, §9.1b).

Brojke su mjerene, ne procijenjene. Metoda je uz svaku brojku. Gdje je inventar od
2026-10-10 pogrešan, ispravak je u §0 i označen je kao ispravak, ne tiho primijenjen.

---

## §0 Ispravci ulaznih dokumenata

Pet tvrdnji iz ulaza ne drže se uz kod ili uz mjerenje. Navodim ih, ne primjenjujem tiho.
§0.5 i §0.6 su u v3 prepisani: od analize koda ormara ostala su **tri pravila**, a commit više
nije referenca.

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

### §0.3 · ZATVORENO u v2 — `odluke.md` je nadograđen na v2.1 i D18 postoji

U v1 sam zapisao da prompt citira D18 kojeg u `docs/inputs/odluke.md` nema: datoteka je bila
**Verzija 2** s **D0–D17** (mjereno: `grep -cE "^## D[0-9]+"` → 18 unosa, D0 do D17), a
`grep -n "D18"` → nula pogodaka. Nisam odlučio umjesto tebe, nego zapisao razliku.

**Riješeno:** prvi isporučeni zip sadržavao je stariju v2. D18 je u v2 dodan u
`docs/inputs/odluke.md:265` prema tekstu koji si dao, a dokument je označen kao **v2.1**
(`odluke.md:3-4`). Sada ima **19 unosa, D0–D18** (`grep -cE "^## D[0-9]+"` → 19).

D18 je primijenjen u **§4.3**, i mijenja ono što je v1 pretpostavljao: mapiranje nije „jedan
master", nego **obje strane s usporedbom**, uz pravilo da se neslaganje nikad tiho ne prepisuje
ni u jednom smjeru i da je bez endpointa za čitanje usporedba **„nije moguće provjeriti"**.

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

### §0.5 · Podrijetlo nalaza, i zašto commit nije referenca

Nalazi iz koda ormara u §2 i §7 čitani su na **`a709cf8`** (grana `develop`, 2026-10-11).
U v1 to nisam naveo i navodim od v2, jer tvrdnja o tuđem kodu bez commita nije provjerljiva.

Mjereno: `git diff --numstat 773bca6 a709cf8 --` po svakoj citiranoj datoteci. Deset od
osamnaest je identično između Krka i `develop`, osam se razlikuje — tablica je ostala u v2 i
tamo je i dalje točna.

**U v3 ta tablica više nije referenca ni za što.** Ormar je popravljen prema svojoj
specifikaciji i ugovor je ono što vrijedi: ormar **ne naplaćuje i ne računa cijenu**, vraća
stanje brojila za struju i vodu, a potrošnja, cijena, kredit i naplata su u ERP-u (D0, D4).

> **Odlučeno** · Referenca je **ugovor**, ne commit. Kad ERP prvi put stvarno spoji ormar,
> **ugovorni test provjerava živi odgovor** (TC-ERP-LIVE-01, §9.1), ne verziju koda.
>
> **Zašto** · Tvoja odluka, i točna je: commit koji smo čitali u listopadu bit će star na dan
> prvog spajanja, a ERP se ne spaja na commit nego na uređaj. Test koji čita živi odgovor
> hvata i konfiguraciju i verziju i stvarno stanje brojila — commit ne hvata ni jedno.
> Provjera koja se odnosi na nešto što ne možemo vidjeti u trenutku spajanja nije provjera.
>
> **Ako griješim** · Nijedan test se ne briše: simulator (§9.1) pokriva oblik, a
> TC-ERP-LIVE-01 pokriva stvarnost. Ako ikad zatreba verzija ormara, to je zahtjev prema
> njemu, ne izmjena ERP-a (§11 O11).

### §0.6 · Tri pravila koja je analiza payloada ostavila

Analiza ugovora sesije (v2 §0.6) dala je tri pravila koja vrijede neovisno o verziji ormara i
koja su jedino što je od nje preživjelo u v3. Svako je sada odluka, ne nalaz.

> **Odlučeno** · **`null` nije `0`.** Brojka koja nije izmjerena prikazuje se kao **—**, ide u
> `manual_review`, i **nikad se ne naplaćuje**. `0` je izmjereno i naplaćuje se kao nula.
>
> **Zašto** · D10 i ormarov §4.2/§4.3. „Nismo izmjerili" i „potrošio je nula" izgledaju isto
> ako ih se jednako obradi, a razlika **uvijek ide na štetu jedne od strana**. Ovo je pravilo
> koje je i natjeralo ormar da razdvoji `consumption_source`.
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije.

> **Odlučeno** · ERP **preračunava** svaku brojku iz dvaju graničnih očitanja brojila i
> **neslaganje prijavljuje kao nalaz**, ne prihvaća tiho.
>
> **Zašto** · Ormar to izrijekom traži („Recompute our figures — please"). Dva neovisna zapisa
> iste činjenice vrijede daleko više od jednog, a zapis koji drži samo jedna strana nije
> provjera ničega. Isto pravilo je i kontrola iz D10: zbroj obračunatih sesija po priključku
> mora odgovarati razlici kumulativnog stanja brojila.
>
> **Ako griješim** · Preračun je jedna funkcija i jedan test; ako se pokaže nepotrebnim,
> ostaje kao jeftina provjera.

> **Odlučeno** · **Ako u bilo kojem odgovoru ormara postoji polje s cijenom, ERP ga odbacuje
> pri parsiranju** — ne samo ne koristi.
>
> **Zašto** · Tvoja odluka, i D0/D4: ormar mjeri i izvršava, ERP odlučuje i naplaćuje. Ormar
> prema svojoj specifikaciji cijenu više ne šalje, ali pravilo je jeftinije od pretpostavke:
> polje koje samo ignoriramo ostaje u logu i u odgovoru, i prvi koji ga ugleda pomislit će da
> je mjerodavno. Odbačeno pri parsiranju znači da u ERP-u nikad ne postoji.
>
> **Ako griješim** · Jedan ključ u listi odbacivanja; ako ormar ikad legitimno pošalje cijenu,
> to je izmjena ugovora i ide kroz §1, ne kroz parser.

### §0.7 · ISPRAVCI iz koda ormara (faza 2)

Snimljenih odgovora Krka u repou nema. Simulator je zato sagrađen iz **koda koji te odgovore
proizvodi**: `Cloud_IOT` grana `develop`, commit **`a709cf8`**, čitan isključivo s `git show`
(radno stablo ondje ima tuđe necommitane izmjene i nije čitano). Svaki handler u
`backend/simulator/cabinet_sim.py` nosi file:line. Živi odgovor i dalje provjerava TC-ERP-LIVE-01.

| # | Pretpostavka u spec v4 | Što kod kaže (`a709cf8`) | Posljedica u ERP-u |
|---|---|---|---|
| **1** ⚠ | `GET /api/nfc/session/{id}` je put **za prikaz** (§2.4, SIM-00g) | **i on piše `last_reconciled_at`** kad nema korisničkog tokena (`nfc.py:688-708` → `erp_reconciliation.py:112-124`) — isto kao `by-user` | oba se zovu samo iz usklađivanja (`*_for_reconciliation`); prikaz sesija ide kanalom A (`sessions.active`). **Tvoja potvrda**, i R2b (§7.2) |
| 2 | ormarov token traje 8 h (stari klijent ga je keširao 7 h) | **120 min** (`config.py:21`), odgovor **nema `expires_in`** | stari klijent je na 401 brisao token **bez ponavljanja**: ~5 od svakih 7 sati ERP bi prikazivao keš. Sada `exp` iz JWT-a, 401 → jedna ponovna prijava |
| **3** ⚠ | `sockets/valves.config_list` služe za otkrivanje mogućnosti (§2.2, D3) | `valves/config` **uvijek** vraća dva ventila (`pedestal_config.py:551-572`), `/water` isto (`ext_pedestal_endpoints.py:325-377`) — i na retrofitu. Nema `available`, nema imena, nema faza | ormar **ne kaže ima li vode**. `device_type` je ERP podatak (§4.1 ga već ima); do faze 3 dolazi iz `ERP_CABINETS_FILE`. **Tvoja potvrda** privremenog izvora |
| 4 | Q1 šalje `currentAmpsL1..L3` / `powerKwTotal` (§4.1, D3, SIM-03) | ext API šalje **`current_l1..l3`** + `power_kw` (snake_case, `meter_load.py:64-107`); camelCase je MQTT | parser čita ext imena; SIM-03 testira njih |
| 5 | 409 „već u uporabi" na `socket_cmd` (§2.5) | na `socket_cmd` **ne postoji**; postoji samo na NFC `/scan` (`nfc.py:543-685`) i `approve_socket` | `outlet_busy` dolazi s kanala B; SIM-07 testira tamo |
| 6 | 403 = „endpoint nije uključen" (§2.5) | na proxiranim rutama da (`"Endpoint not allowed"`); na **direktnim** rutama je **503** `{"error":"Feature not available","reason":"Not enabled"}` **bez `detail`**; neaktivan gateway je 403/404, ne 503 | oba oblika → `not_enabled` |
| 7 | `allow/deny/stop` imaju samo 409 (§2.5) | vraćaju **400** `"Session is X, expected Y"` (`controls.py:176-319`) | novi kod `session_state_changed` |
| 8 | interval heartbeata nepoznat | **15 s** (`docs/architecture.md:67`); `opta_connected` se nakon starta **nikad ne vraća na false** (`main.py:600-603`) | `STALE` nakon 30 s; NALAZ 5.1 potvrđen još jače — `device_connected` je trajno `true` |
| 9 | `pedestals.list` nosi `display_id` (§2.2) | **ne** — `display_id` je `opta_client_id` u `pedestals.health` (ključan po PK-u) | tablica PK↔display gradi se iz `health` |

Usput, bez posljedice za ERP danas: `GET /api/berths` **stvara** vez za svaki ormar koji ga
nema (`berths.py:213-223`) — još jedan GET s nuspojavom (O22); `/water` `total_l` je brojač
sesije, a `session_l` je uvijek `null` (`ext_pedestal_endpoints.py:363`); alarm curenja je
`alarm_type: "moisture"`, ne `water_leak`.

## §1 Blokirajuće

**Prazno. Nema otvorenih blokatora.** Sve u ovom dokumentu je odlučeno.

Sekcija ostaje jer je mjesto kamo ide prva odluka koja mi zatreba. Pravilo iz prompta vrijedi
i dalje: odluku koja nedostaje ne izmišljam — dodajem je ovdje i nastavljam s onim što ne
blokira.

### §1.0 · Odlučeno — gdje je svaka otišla

| Bilo | Odluka | Primijenjeno u |
|---|---|---|
| v1 1.1 · BLOK-2, ručno paljenje | **(a)** — ERP šalje tag iz mapiranja, **samo uloge `admin`/`operator`**, **obvezan razlog**, audit `tag_source='mapping'` | §4.7, §5.3 |
| v1 1.2 · BLOK-1, master mapiranja | **D18** — mapiranje na obje strane, Admin unosi, ERP uspoređuje, neslaganje je stanje; **nije (b)** | §4.3, §7.2 R1/R10 |
| v1 1.3 · oblik tarife | model podržava (c); **pilot: jedna cijena po kWh i po litri za cijelu marinu**; VT/NT i ugovorne cijene su proširenje | §4.5 |
| v1 1.4 · fiskalni račun | **(a)** — ERP vodi obračunske zapise; **fiskalni račun za pilot izdaje blagajna recepcije** | §4.5, §6.4, §12 |
| v1 1.5 · dopuna kredita | **(a)** — recepcija unosi dopunu u ERP-u | §4.5, §6.4 |
| v2 1.1 · BLOK-3, naplata na Krku | **zatvoren** — ormar je popravljen prema specifikaciji, ne naplaćuje i ne računa cijenu; referenca je ugovor, ne commit | §0.5, §0.6, §2.4, §10 |

### §1.1 · Što je zatvoreno čitanjem koda, a ne odlukom

**Pull endpoint po vremenskom rasponu ne postoji.** Postoji po korisniku:
`GET /api/nfc/sessions/by-user/{user_id}?status=&limit=` s `X-API-Key`. Posljedica za §5.2:
ERP usklađuje **iterirajući korisnike**, ne pitajući za prozor.

**Ta ruta na `develop` mijenja stanje na ormaru** — `mark_reconciled` postavlja
`last_reconciled_at` i commita. Zahtjev je §7.2 R2; dok ne prođe, ERP je ne koristi za prikaz
(§7.2).

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

**Na Krku zastavica NFC cross-checka ne postoji.** `nfc_cross_check_required` je u
`a709cf8:backend/app/config.py:194` s komentarom „REQUIRED FROM: 2026-11-30", a na `773bca6`
je **nema uopće** (§0.5). Dakle datum iz §1.0/1.1 postaje relevantan **tek kad se Krk
nadogradi** — do tada `socket_cmd activate` bez `nfc_tag_id` prolazi, a poslani `nfc_tag_id`
se **tiho odbacuje** (Pydantic `extra='ignore'`). ERP ga ipak šalje od faze 2, i audit zapisuje
`tag_source`, da nadogradnja ne zahtijeva izmjenu ERP-a.

**Verifikacija u Gateway UI-u se ne koristi kao dokaz ničega.** `verified = any_pass and not
any_fail` (`Cloud_IOT/backend/app/routers/external_api_admin.py:291`) je trajno `False` ako je
ijedan parametrizirani endpoint uključen, zbog `has_param = "{id}" in ep["path"]` na `:241` —
podstring test koji ne hvata `{pedestal_id}`. Crveni badge ne sprječava aktivaciju
(`ApiGateway.tsx:627` nema `disabled`). NALAZ 3.1 i 3.2.

### §2.4 · Kanal B — NFC, izravno, `X-API-Key`, **nije** kroz `/api/ext`

> **Odlučeno (D6.2, 2026-10-12)** · **Ormar zna sesije, ali ne zna NFC mapiranje ni korisnike.**
>
> - **NFC mapiranje** (naljepnica → ormar + priključak) postoji **samo u ERP-u** (D6.1 doslovno).
>   Registar naljepnica na ormaru (`/api/nfc/tags`, `/tags/bulk`) i razrješavanje tag → priključak
>   u `/scan` su višak.
> - **Korisnik** postoji samo u ERP-u. Ormar ne treba `nfc_user_id` / `customer_id`, korisničke
>   tokene ni MODE 2 (`nfc_direct_client_mode`). Ormar bez ERP-a s mobilnom aplikacijom ne
>   razgovara nikad: aplikacija ide isključivo kroz ERP i njegovu poslovnu logiku (D6 korak 3).
> - **Sesija ostaje — kao mjerenje:** „priključak Q1, od t1 do t2, registar a → b,
>   `consumption_source`", označena **neprozirnom ERP referencom** (`erp_ref`) koju ERP pošalje
>   pri pripremi i koju ormar samo vrati.
>
> **Zašto ormar mora znati sesiju** · (1) granice sesije su fizički događaji na ormaru — priklop
> i isključenje — i samo ormar u tim trenucima može očitati registar brojila (D10: brojka sesije
> je razlika registra, ne zbroj iz snage; ERP vidi telemetriju tek svakih ~60 s); (2) ako ERP ili
> mreža padnu usred punjenja, ormar mora znati da je priključak u uporabi i zatvoriti ga
> pravilno; (3) ugovor sa 16 ključeva (potrošnja + oba registra) počiva na sesiji.
>
> **Zašto ne mapiranje i korisnik** · dva mjesta s mapiranjem znače dva mjesta koja se mogu
> razići, a pogrešno prepoznata naljepnica je gora od neprepoznate (D6.1). Korisnik na ormaru
> nema nikakvu ulogu: ormar ne odlučuje i ne naplaćuje (D0, D4).
>
> **Stanje** · na ormaru (`a709cf8`) danas postoji i registar naljepnica i korisnik na sesiji.
> Promjena je **zahtjev R14** (§7.2), ne izmjena koju ERP radi. Do odgovora ormara vrijedi
> ugovor ispod i privremena odluka §0.7 #1.

NFC nije u `ENDPOINT_CATALOG` (specifikacija ormara, odgođeno D4) — `/api/ext/nfc/…` uvijek
daje 403. ERP do njega dolazi isključivo izravno.

| namjena | poziv | tijelo / parametri | napomena |
|---|---|---|---|
| Pripremi priključak | `POST /api/nfc/scan` | `{nfc_tag_id, user_id}` | ne uključuje — uključuje se na priklop |
| Stanje sesije | `GET /api/nfc/session/{session_id}` | — | ⚠ **i ovo mijenja stanje** (§0.7 #1) — samo iz usklađivača |
| Sesije korisnika | `GET /api/nfc/sessions/by-user/{user_id}` | `?status=active\|ended&limit=1..500` | ⚠ **mijenja stanje** — samo iz usklađivača (§7.2 R2) |
| Zaustavi sesiju | `POST /api/nfc/session/{session_id}/stop` | — | 409 kad je osoblje već zatvorilo |

Autentifikacija: `X-API-Key`, `require_erp_api_key` — `401` na nevaljali ili odsutni ključ,
`503` ako ključ nije konfiguriran na ormaru. Linije u kodu ormara: §0.5 i §7.2.

`POST /session/{id}/stop` vraća **409 „Session already ended by operator"** — osoblje marine
ima prednost (D10). **To nije greška** i ne logira se kao greška.

#### Ugovor sesije — 16 ključeva

Ormar je popravljen prema svojoj specifikaciji. Ugovor je
`Cloud_IOT/docs/erp_session_payload_contract.md`, pinan testom
`test_nfc_six_tag_model.py::test_tc_six_13g_the_payload_key_set_is_exactly_the_documented_contract`.

| ključ | tip | što ERP s njim radi |
|---|---|---|
| `session_id` | int | ormarov PK → `sessions.cabinet_session_id` |
| `cabinet_id` | string \| null | `display_id`, npr. `MAR_KRK_ORM_01` |
| `socket_id` | string \| null | **`"Q1"`–`"Q4"` / `"V1"`–`"V2"`** — usklađuje se **na string, nikad na broj** |
| `session_type` | `electricity` \| `water` | **ERP se oslanja na ovo**, ne na to koje polje nije prazno (D10) |
| `customer_id` | string \| null | ERP-ov `user_id` poslan u `/scan` |
| `status` | `active` \| `ended` | |
| `activated_at` | ISO 8601 Z | |
| `duration_minutes` | float | |
| `energy_kwh` | float \| **null** | kWh ove sesije; `null` na vodnim sesijama |
| `water_liters` | float \| **null** | litre ove sesije; `null` na električnim |
| `meter_energy_start_kwh` / `_end_kwh` | float \| null | granična očitanja → **preračun** |
| `meter_water_start_l` / `_end_l` | float \| null | isto, za vodu |
| `consumption_source` | string \| null | `register` \| `integrated_legacy` \| `unknown` \| `null` |
| `power_kw_current` | float \| **null** | **samo za prikaz uživo**; `null` = mjerenje odbijeno, **nije** 0 |

> **Odlučeno** · `socket_id` se usklađuje kao **string s prefiksom**, nikad kao broj.
>
> **Zašto** · `V1` i `Q1` su na ormaru oba `socket_id = 1` interno, i prefiks je jedino što ih
> razlikuje — ugovor to izrijekom kaže. Cijeli broj kao ključ pripisao bi vodnu sesiju
> električnoj utičnici, i to bi se vidjelo samo na računu.
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije.

> **Odlučeno** · **Svako polje s cijenom u odgovoru ormara odbacuje se pri parsiranju.** Lista
> odbacivanja je eksplicitna (`estimated_cost`, `cost`, `price`, `amount`) i test tvrdi da
> nijedno **ne postoji** u ERP-ovom modelu nakon parsiranja.
>
> **Zašto** · Tvoja odluka, i D0/D4. Ormar po svojoj specifikaciji cijenu ne šalje, ali
> pravilo je jeftinije od pretpostavke, i traži se **odsutnost**, ne ignoriranje — polje koje
> samo ne koristimo ostaje u logu, i prvi koji ga ugleda pomislit će da je mjerodavno.
>
> **Ako griješim** · Jedan ključ u listi. Ako ormar ikad legitimno pošalje cijenu, to je
> izmjena ugovora i ide kroz §1, ne kroz parser.

> **Odlučeno** · ERP **preračunava** svaku brojku iz dvaju graničnih očitanja i **neslaganje
> prijavljuje kao nalaz**:
> `energy_kwh == meter_energy_end_kwh − meter_energy_start_kwh`,
> `water_liters == meter_water_end_l − meter_water_start_l`.
>
> **Zašto** · §0.6, drugo pravilo. Pri `consumption_source == "register"` to vrijedi po
> konstrukciji, pa svako neslaganje znači da nešto ne štima na jednoj od dvije strane — i to
> je nalaz koji ormar izrijekom traži da mu prijavimo.
>
> **Ako griješim** · Jedna funkcija, jedan test.

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
| **400** `Session is X, expected Y` | sesija je u međuvremenu promijenila stanje (`controls.py:176-319`) | `session_state_changed`; ne ponavlja | „Sesija je u međuvremenu promijenila stanje." |
| **404** | ormar ne poznaje zapis | `not_found` | „Ormar ne poznaje ovaj zapis." |
| **409** `NFC tag … is mapped to …` | naljepnica pripada drugom priključku | `nfc_mapping_mismatch`; ništa se ne uključuje | „Naljepnica ne odgovara ovom priključku." |
| **503** `{"reason":"Not enabled"}` | direktna ruta nije uključena (bez `detail`, §0.7 #6) | isto kao 403: `not_enabled`, ponovna proba za 1 h | isto kao 403 |
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

Pragovi: **`STALE` nakon 2× intervala heartbeata, `OFFLINE` nakon 10 min** (D2). Interval je
**15 s** (§0.7 #8), dakle `STALE` nakon 30 s.
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

> **Odlučeno (faza 2)** · To stanje ima ime: **`unclassified`** / `unknown` / sivo. Najčešći slučaj je
> **plovilo `NEPOZNATO`** (`last_analyzed` fali ili je starije od 30 min) bez ičeg drugog istinitog.
>
> **Zašto** · Rang 12 (`free`, zeleno) traži da „ništa iznad nije istina" — a za nepoznato plovilo
> to bi bilo zeleno za vez koji ne vidimo. Pravilo same tablice kaže da se to ne crta.
>
> **Ako griješim** · Jedan redak u `berth_status.py`.

Boje se prenose kao **ključevi** `grey | red | orange | yellow | blue | green` (`berth_colour`);
frontend ih samo pretvara u klasu.

`outlet_silent` (rang 2.5) **nema izvor na ext API-ju** — „stanje priključka starije od 60 s" zna
samo CORE ormara. U fazi 2 je uvijek neistinit (O24).

**Rang 7 (`measurement_missing`) okida se iz `consumption_source == "unknown"`** u ugovoru
sesije (§2.4), i dodatno iz ERP-ove provjere preračuna: ako se brojka ne slaže s razlikom
graničnih očitanja, sesija je za pregled. To je jedino mjesto na kojem čovjek sazna da
potrošnja nije izmjerena — ormar je prijavio pošteno, ERP mora to i pokazati.

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

PostgreSQL, Alembic. Postojeće migracije idu do `005`
(`backend/alembic/versions/005_pedestal_cache_key.py`, faza 1, §4.8); nove počinju od `006`.
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
  erp_api_key_enc TEXT                  -- kanal B; rotacija ključa je §11 O9
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

> **Odlučeno (faza 2, ⚠ potvrdi)** · `device_type` i mapiranje vez → priključak su **ERP podatak**:
> ormar ih ne izlaže (§0.7 #3, NALAZ 4.2). Do tablica faze 3 dolaze iz jedne JSON datoteke
> (`ERP_CABINETS_FILE`, `backend/app/cabinet/cabinet_config.py`). **Bez datoteke se ništa ne
> pogađa**: voda se ne crta, signal struje veza je `UNKNOWN`, a zaslon to i kaže.
>
> **Zašto** · Faza 2 ne smije dodavati migracije — `006` je tvojom odlukom O17 (faza 3).
> Alternativa — zaključivati iz `valves/config` — dala bi vodu svakom retrofitu.
>
> **Ako griješim** · Faza 3 preuzima isti oblik u tablice `cabinets` / `outlets`; datoteka se briše.

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

### §4.3 · Mapiranje na obje strane, s usporedbom (D18)

D18 je odlučen: mapiranje **postoji i u ERP-u i na ormaru**. Unosi ga **Admin (Lika)** prema
jednoj definiciji. ERP redovito uspoređuje svoje s ormarovim i **neslaganje prikazuje kao
stanje koje treba riješiti — nikad ga tiho ne prepisuje ni u jednom smjeru.**

```
berth_outlets_cabinet            -- što ormar tvrdi; ERP ovdje NIKAD ne piše
  cabinet_id      INT NOT NULL REFERENCES cabinets(id) ON DELETE CASCADE
  outlet_name     TEXT NOT NULL   -- 'Q1'..'Q4' | 'V1' | 'V2'
  cabinet_berth_id INT            -- Berth.id iz ormarove users.db, obični int
  assigned_by     TEXT            -- ormarov assigned_by, kad ga endpoint vrati
  assigned_at     TIMESTAMPTZ
  fetched_at      TIMESTAMPTZ NOT NULL
  PRIMARY KEY (cabinet_id, outlet_name)

mapping_comparison               -- ishod usporedbe; stanje, ne povijest
  cabinet_id      INT NOT NULL REFERENCES cabinets(id) ON DELETE CASCADE
  state           TEXT NOT NULL   -- 'unverifiable' | 'in_sync' | 'divergent'
  divergent_rows  JSONB           -- [{outlet_name, erp_berth, cabinet_berth}]
  checked_at      TIMESTAMPTZ NOT NULL
  PRIMARY KEY (cabinet_id)
```

> **Odlučeno** · Dok ext endpoint za **čitanje** mapiranja ne postoji, `state` je
> **`'unverifiable'`** i zaslon piše **„nije moguće provjeriti"** — nikad „usklađeno".
>
> **Zašto** · D18 to izrijekom traži, i to je ista zamka kao prazna usporedba koja izgleda
> uspješno. Danas endpointa nema: `berth_assignment` čita samo marina CORE, a nijedna
> `/api/marina/*` ruta nije u `ENDPOINT_CATALOG` (NALAZ 4.2; `api_catalog.py` je **identičan**
> na Krku i `develop`, §0.5). Na `773bca6` `models/berth_assignment.py` uopće ne postoji, pa
> na Krku danas druga strana usporedbe **ni ne postoji** — što je i dalje `'unverifiable'`,
> ne `'in_sync'`.
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije. „Usklađeno" bez provjere je
> tvrdnja koju nitko nije provjerio, prikazana kao da ju je netko provjerio.

> **Odlučeno** · Smjer upisa je **jednosmjeran i isključen** do zahtjeva R10: ERP čita
> ormarovo mapiranje i uspoređuje; **ne šalje** svoje. Čarobnjak na ormaru ostaje.
>
> **Zašto** · D18 cilj je „Admin unosi u ERP, ERP šalje ormaru", ali uz uvjet „kad se s
> marinom dogovori proces" i uz endpoint za upis koji ne postoji. Dotad je ERP master
> definicije i **prikazivač neslaganja**, a ne drugi pisac iste činjenice.
>
> **Ako griješim** · Kad R10 postoji, dodaje se jedan poziv i jedan audit zapis; usporedba
> ostaje jer D18 je traži i nakon toga.

> **Odlučeno** · **Svaka izmjena mapiranja ima autora i vrijeme**, na obje strane tablice, i
> `assigned_by` diže grešku umjesto da uzme default.
>
> **Zašto** · D18 i D1. Premještanje veza mijenja čija potrošnja gdje pada; poziv bez aktera
> je bug, a default ga skriva.
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije.

Interval usporedbe: **jednom dnevno** i **na svaku izmjenu mapiranja u ERP-u**. Neslaganje
ide na zaslon sigurnosti (§6.5) i u §3.3 kao stanje ormara, ne kao stanje veza — jer ne zna
se koji je vez pogrešan, nego da se dvije strane ne slažu.

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
  tariff_id       INT             -- NULL = marinska tarifa (pilot); proširenje, vidi niže

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

#### Tarifa — model (c), pilot jedna cijena

```
tariffs
  id              SERIAL PK
  marina_id       INT NOT NULL REFERENCES marinas(id) ON DELETE CASCADE
  medium          TEXT NOT NULL        -- 'electricity' | 'water'
  unit_price      NUMERIC(10,4) NOT NULL   -- EUR/kWh | EUR/litra
  currency        TEXT NOT NULL DEFAULT 'EUR'
  vat_rate        NUMERIC(5,2) NOT NULL
  time_band       TEXT                 -- NULL = cijeli dan (PILOT); 'VT'|'NT' = proširenje
  band_from       TIME                 -- NULL u pilotu
  band_to         TIME                 -- NULL u pilotu
  valid_from      DATE NOT NULL
  valid_to        DATE
  UNIQUE (marina_id, medium, time_band, valid_from)
```

> **Odlučeno** · **Model podržava (c)** — VT/NT pojasevi i cijena po ugovoru — ali **pilot
> koristi jednu cijenu po kWh i jednu po litri za cijelu marinu**: jedan redak po mediju,
> `time_band = NULL`, `contracts.tariff_id = NULL`.
>
> **Zašto** · Tvoja odluka 1.3 (§1.0). Stupci za VT/NT i `tariff_id` koštaju ništa dok su `NULL`,
> a njihovo dodavanje nakon prvih izdanih obračuna znači migraciju povijesnih redaka. Pilot
> pritom ne vidi ni jedan od njih na zaslonu — dva reda u tablici tarifa i to je sve.
>
> **Ako griješim** · Uključivanje VT/NT je upis redaka s `time_band`, bez migracije.
> Ugovorna cijena je upis `contracts.tariff_id`, bez migracije. Oboje bez izdanja.

> **Odlučeno** · Cijena za **vodu je po litri**, ne po m³, i tako se sprema.
>
> **Zašto** · Ormar mjeri i javlja litre (`water_liters`, V1/V2 20 l/min), pa pretvorba u m³
> pri obračunu uvodi zaokruživanje između mjerenja i računa — upravo tamo gdje mora biti
> provjerljivo. Prikaz smije biti u m³; zapis je u litrama.
>
> **Ako griješim** · Jedan djelitelj u serijalizatoru prikaza.

#### Fiskalni račun i dopuna kredita

```
billing_records                  -- ERP-ov obračunski zapis; NIJE fiskalni račun
  id              BIGSERIAL PK
  customer_id     INT NOT NULL REFERENCES customers(id)
  session_id      BIGINT REFERENCES sessions(id)
  medium          TEXT NOT NULL
  quantity        NUMERIC(12,3) NOT NULL   -- kWh ili litre
  unit_price      NUMERIC(10,4) NOT NULL
  vat_rate        NUMERIC(5,2) NOT NULL
  amount_net      NUMERIC(10,2) NOT NULL
  amount_gross    NUMERIC(10,2) NOT NULL
  tariff_id       INT NOT NULL REFERENCES tariffs(id)
  issued_at       TIMESTAMPTZ NOT NULL
  exported_at     TIMESTAMPTZ              -- kad je predan blagajni recepcije
```

> **Odlučeno** · ERP vodi **obračunske zapise**; **fiskalni račun za pilot izdaje blagajna
> recepcije**. ERP joj zapise izvozi i bilježi `exported_at`.
>
> **Zašto** · Tvoja odluka 1.4 (§1.0). Fiskalizacija je samostalan projekt s certifikatima,
> JIR/ZKI i arhivom; pilot je jedan ormar sa šest priključaka. `billing_records` je ulaz u
> fiskalizaciju kad do nje dođe, pa (a) ne zatvara (b).
>
> **Ako griješim** · Fiskalni modul čita `billing_records`; ništa u modelu se ne mijenja.

> **Odlučeno** · Kredit se dopunjuje **unosom na recepciji**, u ERP-u, uz obveznog autora
> (`credit_ledger.created_by`). Kartično plaćanje u aplikaciji nije u izvedbi.
>
> **Zašto** · Tvoja odluka 1.5 (§1.0). Knjiga kredita je ista pod oboje; PSP integracija samo
> dodaje izvor retka, a nosi povrate i PCI opseg koje pilot ne traži.
>
> **Ako griješim** · PSP dodaje `reason='topup_card'` i webhook plaćanja; knjiga se ne mijenja.

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
  tag_source      TEXT            -- 'scan' | 'mapping' | NULL      (§1.0 odluka 1.1)
  reason          TEXT            -- OBVEZAN kad actor_type='operator'; CHECK ga traži
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
12 ERP zatvori obračun                              fiskalni račun: blagajna recepcije
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
| **pull-usklađivanje sesija** | 15 min za korisnike s otvorenom ili nedavno zatvorenom sesijom; **noćni puni prolaz** | §1.2: nema endpointa po vremenskom rasponu, samo `by-user` — koji na `develop` **piše** (§7.2 R2) |

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

#### Ručno paljenje iz ERP-a — odlučeno kao (a), uz tri ograde

> **Odlučeno** · Operater smije upaliti priključak bez skeniranja. ERP tada šalje
> `nfc_tag_id` **iz vlastitog mapiranja** (`outlet_nfc_tags`), i vrijede tri ograde:
> **(1)** samo uloge **`admin`** i **`operator`** — `marina_manager` bez te uloge tu kontrolu
> **ne vidi**; **(2)** **razlog je obvezan** i unosi se u dijalogu, bez njega se naredba ne
> šalje (`command_audit.reason` ima `CHECK` za `actor_type='operator'`); **(3)** audit zapisuje
> **`tag_source='mapping'`**, nikad `'scan'`.
>
> **Zašto** · Tvoja odluka 1.1 (§1.0), i razlog zašto je obrana održiva: cross-check nikad nije
> bio dokaz prisutnosti — D6 to izrijekom kaže, UID je objavljen u dokumentaciji koja ide
> marini i ISO 15693 se kopira. Slanje mapiranog taga ne gubi ništa što je bilo stvarno. Ali
> **ako audit ne razlikuje mapiranje od skeniranja, zapis je gori od ničega** — tvrdio bi da
> je gost bio tamo. Obvezan razlog je drugi dio istog: akcija s fizičkom posljedicom na tuđem
> vezu mora imati rečenicu zašto, upisanu u trenutku, ne rekonstruiranu poslije.
>
> **Ako griješim** · Uloge su jedan uvjet, razlog je jedno polje i jedan `CHECK`, `tag_source`
> je jedan string. Ako odlučiš da operater ne smije — kontrola se ne iscrtava, i to je jedna
> zastavica (§1.1 opcija (b)).

Na Krku ta zastavica još ne postoji (§2.3), pa `nfc_tag_id` prolazi tiho odbačen. ERP ga
šalje od faze 2 svejedno, da nadogradnja ne traži izmjenu.

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

> **Odlučeno** · Pretvorba u iznos ide **jednom cijenom po mediju za cijelu marinu** u pilotu
> (§4.5), a svaki `billing_records` redak nosi `tariff_id` kojim je računat.
>
> **Zašto** · Tvoja odluka 1.3 (§1.0). `tariff_id` na zapisu znači da promjena cijene ne mijenja
> povijesne obračune — isti razlog zbog kojeg ormar ne prepisuje `energy_intervals.berth_ref`.
>
> **Ako griješim** · Nijedan povijesni redak se ne dira; novi nose novi `tariff_id`.

> **Odlučeno** · Sesija ulazi u `billing_records` **samo** kad ima izvedivu brojku:
> `consumption_source == "register"` **i** preračun se slaže. Sve ostalo je `manual_review`.
>
> **Zašto** · §0.6, prvo i drugo pravilo. Ormar sada pošteno razlikuje „nismo izmjerili" od
> „nula", pa ERP nema izgovora da to spoji. Naplatiti brojku koja se ne slaže s graničnim
> očitanjima znači naplatiti nešto što nijedna strana ne može obraniti.
>
> **Ako griješim** · Uvjet je jedan izraz; `manual_review` je zaslon koji ionako postoji (§6.3).

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

Gumb **[ + Dopuna ]** je unos na recepciji (odluka 1.5): iznos, način uplate kao tekst, i
**obvezan autor** — jedan redak u `credit_ledger` s `reason='topup'`. ERP ne prima karticu.

Obračunski zapisi imaju **[ Izvoz za blagajnu ]**: ERP ih preda blagajni recepcije, koja
izdaje fiskalni račun (odluka 1.4), i upiše `exported_at`. **ERP nikad ne ispisuje dokument
koji izgleda kao račun** — to je §12.

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

Repo ormara se ne dira. Ovo je lista koju nosim u njegov chat. **Uz svaki zahtjev je commit
na kojem je utvrđen**; metoda i tablica po datoteci su §0.5. Stupac „Na Krku?" opisuje stanje
na dan čitanja i služi prioritizaciji — **ugovorna provjera je TC-ERP-LIVE-01**, ne ovaj stupac.

| # | Zahtjev | Utvrđeno na | Na Krku? | Blokira |
|---|---|---|---|---|
| ~~R9~~ | ~~NFC payload po ugovoru sa 16 ključeva~~ — **ZATVOREN u v3**: ormar je popravljen prema specifikaciji, ne naplaćuje i ne računa cijenu, vraća stanje brojila. Provjerava se **živim odgovorom** pri spajanju (TC-ERP-LIVE-01), ne commitom | — | — | ništa; BLOK-3 je zatvoren |
| **R2** | **`GET /api/nfc/sessions/by-user` ne smije mijenjati stanje** — ili, ako mora, to mora biti dokumentirano i idempotentno, a `/reconciliation` i `/divergence` dostupni s `X-API-Key` | vidi okvir ispod | **djelomično** — na Krku ne piše; na `develop` piše | bolji pull u fazi 4; iteracija po korisnicima radi bez toga |
| **R15** | **Voda u ERP načinu** — ERP šalje `POST /api/nfc/scan`, zatim `water/{V}/cmd activate`; ormarov `OutletActivated` preuzima rezervaciju i upisuje `erp_ref`. **U ERP načinu ormar odbija otvoriti ventil bez važeće rezervacije.** Auto-otvaranje (`valve_configs.auto_activate`) se u smart modu + ERP načinu gasi u kodu | odgovor ormara 2026-10-12; `a709cf8:…/pedestal_config.py:551-572` (zadano `auto_activate = true`) | **provjeriti** — O28 | NFC tok za vodu (§5.1, faza 7) |
| **R14** | **Pojednostavljenje kanala B po D6.2** — (1) **zakomentirati u kodu, ne brisati** registar naljepnica (`/api/nfc/tags`, `/tags/bulk`) i MODE 2 (`nfc_direct_client_mode`, korisnički tokeni na `/api/nfc/*`), uz oznaku `D6.2 / R14` na svakom mjestu; (2) `POST /api/nfc/scan` prima `{cabinet_id, outlet: "Q1".."V2", erp_ref}` umjesto `{nfc_tag_id, user_id}` — priprema i 5-min čekanje na priklop ostaju; (3) sesija nosi `erp_ref` umjesto `customer_id`/`nfc_user_id`, sve ostalo u ugovoru ostaje; (4) **čitanje bez nuspojava** — `GET /session/{id}` ne upisuje `last_reconciled_at`; ERP potvrđuje obračun izričito, npr. `POST /api/nfc/sessions/ack {session_ids}`, i tek tada detektor `erp_reconciliation_silent` mjeri pravu stvar; (5) `by-user` se zamjenjuje čitanjem po `erp_ref` ili po vremenskom rasponu; (6) ugovor sa 16 ključeva, `test_tc_six_13g` i testovi koji pokrivaju zakomentirani kod usklađuju se u istom commitu, da suite ormara ostane zelen. **Zakomentirati, ne brisati** — tvoja odluka 2026-10-12: kod ostaje u repou ormara za slučaj da zatreba | `a709cf8:…/nfc.py` (11 ruta), `nfc.py:543-685` (`/scan` razrješava tag), `nfc.py:688-759` + `erp_reconciliation.py:112-124` (`mark_reconciled`) | **PRIHVAĆEN 2026-10-12** — redoslijed na ormaru: **a0** gašenje auto-otvaranja ventila (zaseban commit, prvi) → **a** popravak vode (R15), uključujući test za stop sa `socket_id=None` → **b** pojednostavljenje D6.2 s ugovorom i testovima → **c** `ack`. `erp_ref` je **novi stupac uz stare**, povijest se ne prepisuje. Raspon za usklađivanje: **po vremenu završetka**, `ended_from` uključivo, `ended_to` isključivo, **sa stranicama** | ništa danas; kad prođu b i c, otpadaju R2, R2b, O21, O23, §0.7 #1 i iteracija po korisnicima u §5.2 |
| **R2b** | **`GET /api/nfc/session/{id}` ne smije mijenjati stanje** — isto kao R2 (§0.7 #1) | `a709cf8:…/nfc.py:688-708` → `erp_reconciliation.py:112-124` | nije provjereno | bez toga ERP nema read-only put do pojedine sesije |
| **R12** | **`GET /api/berths` ne smije stvarati vezove** (O22) | `a709cf8:…/berths.py:213-223` | nije provjereno | ništa |
| **R13** | **`valves/config` neka kaže koliko ventila ormar STVARNO ima** (ili `available`) | `a709cf8:…/pedestal_config.py:551-572` | nije provjereno | ništa — ERP ima `device_type` |
| **R1** | **Ext endpoint za čitanje mapiranja** vez → `socket_id`/`valve_id` (D18, „odmah") | NALAZ 4.2; `api_catalog.py` identičan na oba | **ne** — nijedna `/api/marina/*` ruta nije u katalogu; na `773bca6` `berth_assignment.py` ni ne postoji | §4.3 prelazi iz `'unverifiable'` u stvarnu usporedbu |
| **R10** | **Ext endpoint za upis mapiranja** — bidirectional, s autorom i auditom (D18, „kasnije") | isto | **ne** | cilj iz D18 („Admin unosi u ERP, ERP šalje ormaru"); usporedba radi bez toga |
| **R4** | **Popravak 2.3** — mod se poštuje i na direktnim ext write rutama | `a709cf8:…/ext_breaker_endpoints.py:91-101`; **datoteka identična na Krku** | **da, isti problem** | uključivanje `breakers.socket_reset_ext` i `load.auto_stop_ack_ext` (§2.3) |
| **R3** | **HMAC potpis + retry + dead-letter na webhooku** | `a709cf8:…/webhook_service.py:93,99-109`; **identično na Krku** | **da, isti problem** | ništa — ERP već radi pullom (§5.2) |
| **R11** | **`load.auto_stop_ack_ext` dobiva Smart Mode gate** | NALAZ 2.2; `ext_meter_load_endpoints.py` identičan na Krku | **da** | ništa dok se endpoint ne uključi — a ne uključuje se (§2.3) |
| **R5** | **Popravak 1.3** — gateway match uspoređuje metodu | `a709cf8:…/external_api_gateway.py:287-293` → Krk `:282-288` (+15 pomak) | **da** | ništa za ERP (ne upravlja LED-om); prijavljeno jer je granica |
| **R7** | **`smart_mode` i u `pedestals.status_ext`** | NALAZ 2.2; `ext_pedestal_endpoints.py` identičan na Krku | **da** | ništa — kozmetika prometa |
| **R8** | **Zamagljivanje ljudi prije spremanja i slanja** (`camera.frame_ext`) | D15 / GDPR; `ext_pedestal_endpoints.py` identičan | **da** | prikaz slike veza nije blokiran, ali je pravno izložen |
| **R6** | *(bespredmetno dok Krk ne dobije zastavicu)* operaterski put bez `nfc_tag_id` | `a709cf8:…/config.py:194`; **`nfc_cross_check_required` ne postoji na Krku** | **ne postoji** | ništa — §1.1 je odlučen kao (a), pa R6 nije potreban |

#### R2 · Nalaz koji je u v2 prešao iz „odgovor" u „zahtjev"

Pitao si: **mijenja li `GET /api/nfc/sessions/by-user` stanje na ormaru?** Mjereno na oba
commita, i odgovor se razlikuje:

| | |
|---|---|
| **Krk `773bca6`** | **NE.** `nfc.py:264-292` je čisti read — nema `db.commit()`, nema `db.add()`, nema `mark_reconciled`. `git show 773bca6:…/nfc.py \| grep mark_reconciled` → prazno |
| **`develop a709cf8`** | **DA.** `nfc.py:755` zove `erp_reconciliation.mark_reconciled(db, rows)`, koji u `erp_reconciliation.py:112-124` postavlja `last_reconciled_at = now` na **svaku pročitanu sesiju** i radi `db.commit()` |

Dakle **GET koji piše u bazu**, i to na svaki strojni poziv. Namjera je legitimna i
dokumentirana u ormaru („a machine read of it is the reconciliation event itself") — detektor
tišine treba znati da je ERP čitao. Ali posljedica za ERP je stvarna:

> **Odlučeno** · ERP tretira `by-user` kao **poziv s nuspojavom** i ne koristi ga za običan
> prikaz — samo za usklađivanje, na intervalu iz §5.2. Prikaz uživo ide na
> `GET /api/nfc/session/{id}`.
>
> **Zašto** · Ako ERP pozove `by-user` svaki put kad operater otvori zaslon sesija, ormar
> zabilježi usklađivanje koje se nije dogodilo i **detektor tišine utihne upravo kad bi
> trebao javiti** da naplata ne stiže. Nuspojava u GET-u nije naša da ispravimo, ali je naša
> da je ne zlorabimo.
>
> **Ako griješim** · Ako R2 prođe i ruta prestane pisati, ograničenje se ukida i `by-user`
> postaje običan read — jedan redak.

Zahtjev prema ormaru ostaje jer je oblik problematičan neovisno o nama: GET koji mijenja
stanje nije idempotentan, pa svaki retry, cache ili probe mijenja mjerene podatke. Bolji oblik
je `POST /api/nfc/reconciliation/ack` s popisom `session_id`-eva, i `/reconciliation` dostupan
s `X-API-Key` za čitanje — što je drugi dio R2.

> **Odlučeno** · Dok R2 ne postoji, ERP **sam vodi** evidenciju „zadnje usklađeno po ormaru"
> i prikazuje je (§6.3), ne oslanja se na ormarov detektor.
>
> **Zašto** · Na Krku `/reconciliation` ne postoji uopće, a na `develop` traži operaterski
> JWT (`require_any_role`, `auth/dependencies.py:54` — identično na oba commita), koji ERP
> nema. Evidencija koju ERP sam vodi je ionako ona koju treba za svoj zaslon.
>
> **Ako griješim** · Kad R2 prođe, ormarov odgovor postaje druga strana usporedbe — dodaje se,
> ne zamjenjuje.

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
| **TC-ERP-BOOT-01a** | aplikacija se diže — **faza 1** | pravi `tsc` + `vite build`, prava migracija, pravi uvicorn; `GET /api/health` → 200; prijava → 200 + token; autentificirana ruta → 200 | bundle se ne gradi, migracija pada, ruta je pokvarena, `JWT_SECRET` fali, server se ne digne |
| **TC-ERP-BOOT-01b** | zasloni se iscrtavaju — **faza 2** | pravi browser nad pravim bundleom; `/marina/:id` iscrta redove vezova protiv **simulatora**; nema error boundaryja ni uncaught console errora | CORE oblik se promijenio, ruta je pokvarena, komponenta pukne |

> **Odlučeno** · Boot gate je podijeljen: **01a u fazi 1, 01b u fazi 2**.
>
> **Zašto** · 01b tvrdi da se **redovi vezova iscrtavaju**, a redovi vezova dolaze iz ormara.
> U fazi 1 nema ormara koji bi odgovorio ni simulatora koji bi ga zamijenio (simulator je
> faza 2, §10), pa bi 01b u fazi 1 morao imati stub napisan samo za njega — a stub napisan
> za test koji provjerava da aplikacija radi je točno ono prazno prolaženje koje gate mora
> spriječiti. 01a ipak tvrdi sve što faza 1 gradi: build, migraciju, server, prijavu, rutu.
>
> **Ako griješim** · Ako faza 2 zakasni, 01b se može privremeno vrtjeti protiv snimljenog
> odgovora — ali tada je to jedan test oblika, ne tvrdnja da sustav radi, i to se tako i zove.
| **TC-ERP-BOOT-02** | gate ne može proći prazno | ako backend nije podignut, stage **pada**, nikad `exit 0`; ispiše broj preskočenih | netko „popravi" gate preskakanjem |
| **TC-ERP-GATE-01** | gate je u repou | `.githooks/pre-push` postoji **i** `core.hooksPath` je postavljen; CI vrti isti skript | gate je samo lokalan |
| **TC-ERP-DEP-01** | ovisnosti su pinane | lock datoteka postoji; instalacija iz nje daje izmjerene verzije (§0.4) | netko doda nepinanu ovisnost |
| **TC-ERP-AUTH-01** | neautentificirano = **401** | sve **27** zaštićene rute od **31** (mjereno iz grafa ovisnosti aplikacije, ne grepom — grep po `Depends(get_current_user)` daje 23 jer promašuje rute zaštićene kroz `require_super_admin`/`require_any_operator`); javni skup je **imenovan** (login, refresh, webhook, health) i nova nezaštićena ruta pada; **strogo 401**, ne `in (401, 403)`, i bez tokena i s neispravnim tokenom | HTTPBearer se vrati na 403 (§0.1) |
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
| **TC-ERP-SIM-00** | simulator odgovara ugovoru | ključevi payloada su **točno** 16 iz `erp_session_payload_contract.md`; tri oblika occupancy odgovora iz NALAZ 4.1 |
| **TC-ERP-SIM-00c** | **polje s cijenom se odbacuje** | simulator pošalje `estimated_cost: 12.34` → **ne postoji** nigdje u ERP-u nakon parsiranja (traži se **odsutnost**, ne ignoriranje); isto za `cost`, `price`, `amount` |
| **TC-ERP-SIM-00d** | **voda se ne pripisuje struji** | sesija s `session_type: "water"` i `socket_id: "V1"` → pripisuje se **V1**, nikad Q1; pripisivanje ide po stringu |
| **TC-ERP-SIM-00e** | **preračun se provjerava** | `energy_kwh` koji se ne slaže s `meter_energy_end − start` → nalaz + `manual_review`, **nikad `billing_records`** |
| **TC-ERP-SIM-00g** | **`by-user` se ne zove za prikaz** | izvorni skan + test ponašanja: zaslon sesija zove `GET /session/{id}`; `by-user` se zove **samo** iz usklađivača (§7.2 R2) |
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

**Faza 2 — što je od ovoga ugovorni dio, a što čeka:** `billing_records` (faza 7) i tablice
mapiranja/naljepnica (faza 3) ne postoje. Zato SIM-00e/11/12 tvrde `billable == False` i
`manual_review`, ne odsutnost retka u `billing_records`; SIM-14 tvrdi pravilo traženja (oba
zapisa), ne indekse; SIM-04 tvrdi da je „dijeli V1" samo na prikazu priključka. Kad faze 3 i 7
dodaju tablice, isti testovi dobivaju po jednu tvrdnju više — ne nove testove.

DOM tvrdnje (SIM-01/02/05/06/07) vrti `scripts/browser_check.py` u pravom Chromiumu nad pravim
bundleom (stage 6 gatea, i u CI-ju). Provjereno mutacijom: frontend koji crta kontrolu bez
dopuštenja servera → SIM-06 pada.

### §9.1b · Prvi stvarni spoj — ugovor se provjerava na živom odgovoru

> **Odlučeno** · **TC-ERP-LIVE-01**: pri prvom stvarnom spajanju ormara, ERP provjerava
> **živi odgovor**, ne verziju koda. Test čita `pedestals.health`, `berths.list` i jedan
> `GET /api/nfc/session/{id}`, i tvrdi: ključni skup payloada je onaj iz §2.4; `socket_id`
> nosi prefiks; nema polja s cijenom; `smart_mode` je prisutan. Pada s imenom ključa koji
> fali, ne s „nešto ne radi".
>
> **Zašto** · Tvoja odluka (§0.5). Commit koji smo čitali bit će star na dan spajanja, a ERP
> se ne spaja na commit nego na uređaj. Živi odgovor hvata i verziju i konfiguraciju i stvarno
> stanje — commit ne hvata ni jedno.
>
> **Ako griješim** · Test je jedan skript s read-only GET-ovima; vrti se pri spajanju i u
> runbooku (§8.4), ne na svaki push.
>
> ⚠ **Faza 2:** `GET /api/nfc/session/{id}` **nije read-only** (§0.7 #1) — označi sesiju kao
> usklađenu. LIVE-01 ga smije zvati samo na **probnoj** sesiji stvorenoj za taj test (O23).

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
| **3** | **Model podataka** — §4 u cijelosti, mapiranje **po D18** (obje strane + usporedba), NFC tagovi s dva zapisa + **CSV uvoz za Krk**, tip uređaja i mogućnosti, korisnici, ugovori, `billing_mode` default `prepaid`, knjiga kredita, `consumption_source` | migracije `006+`; **uvoz Krk CSV-a pogađa točan priključak** (ne samo „prepoznato") |
| **4** | **Prikupljanje + retencija u istom commitu** — poller po §5.2, pull-usklađivanje `by-user`, prijemnik webhooka (danas `X-API-Key`, spreman za HMAC), `command_audit` | podaci teku; **rast baze izmjeren i ograničen** — brojka prije i poslije 7 dana |
| **5** | **VPS** — systemd (§8), 2 GB / 20 GB, Postgres, nginx, `cloudflared` samo za UI, Tailscale prema ormarima, **slojevi 0 i 1 PRIJE javnog izlaganja**, backup + probna obnova, runbook; `docker-compose.yml` obrisan | ERP javno dostupan iza Cloudflare Accessa; **runbook proveden na čistom VPS-u** |
| **6** | **Zauzeće vezova + 2D SVG** — četiri signala iz §3.1, tablica stanja §3.2, statični SVG s `svg_id` po vezu | **Krk na karti, četiri signala, sivo za tiho** |
| **7** | **Poslovna logika i NFC tok** — §5.1, §5.4, tarifa (§4.5), `billing_records`, izvoz za blagajnu, knjiga kredita u iznosima | **TC-ERP-ACC-01..06 prolaze na pravom ormaru**; potrošnja se slaže na obje strane |
| **8** | **Sigurnosni modul v1** — mamci, domenske detekcije, signali vrata i novog uređaja, servisni prozori, CVE/KEV prema **pinanim** verzijama, zaslon §6.5 | prvi stvarni nalazi na VPS-u i Krku |
| **9** | **Energetski agent** — tek kad postoji povijest iz faze 4 | — |

Faza 2 prije faze 6 ima isti razlog kao korak 1 prije koraka 4 u ormarovoj specifikaciji: s
ugovorom pokrivenim simulatorom, L1 je posao iscrtavanja nad fiksnim oblikom.

**Faza 7 je jedna** (v3): BLOK-3 je zatvoren, ormar vraća stanje brojila po ugovoru i ne
računa cijenu, pa naplata ne čeka ništa osim faza prije sebe. Pri prvom spajanju ormara vrti
se **TC-ERP-LIVE-01** (§9.1b), koji provjerava živi odgovor.

### §10.1 · Faza 1 — izvještaj (2026-10-11)

**Gate zelen.** `bash scripts/gate.sh` → `GATE (full): 5/5 stages passed`, 83 s na ovom stroju
(`--fast`, pre-commit: 3/3, ~40 s).

| Mjera | Prije faze 1 | Poslije | Kako izmjereno |
|---|---|---|---|
| Backend testova | 96 | **126**, 0 preskočenih | `PYTEST: collected=126 passed=126 skipped=0` iz `scripts/pytest_counts.py` |
| Tolerantnih `in (401, 403)` | 2 | **0** | `grep -rn "in (401, 403)" backend/tests` |
| Zaštićenih ruta pod strogim 401 | 0 sustavno | **27/27**, bez tokena i s lošim tokenom | TC-ERP-AUTH-01, popis iz grafa ovisnosti |
| Pinane izravne ovisnosti | 1 (`bcrypt`) | **sve**; lock tranzitivan; `package-lock.json` praćen | TC-ERP-DEP-01 |
| Boot provjera | nije postojala | **8/8**: migracija 001→005 na praznoj bazi, pravi uvicorn, health, prijava, `/me`, `/marinas`, 401 bez tokena, **odbijanje bez `JWT_SECRET`** | `scripts/boot_check.py` |
| ruff (E9 + F) | 21 nalaz | **0** | `ruff check --config backend/ruff.toml` |
| bandit high / medium / low | 0 / 1 / — | **0 / 0 / 2** (medium sada blokira) | gate, stage bandit |
| Bundle | 646,34 kB JS / 23,27 kB CSS | 646,47 kB / 23,27 kB (bez promjene, O3) | `vite build` u gateu |
| Načina da gate prođe prazno | 5 (sistemski Python, `pip install` bez pina, bandit „skipping", feature grane bez gatea, hook samo u `.git/hooks`) | **0** | TC-ERP-BOOT-02, TC-ERP-GATE-01 |

Testovi faze 1 iz §9: **BOOT-01a, BOOT-02, GATE-01, DEP-01, AUTH-01, AUTH-02, CACHE-01 — svi
zeleni.** Svaki koji tvrdi zaštitu provjeren je **mutacijom** — kvar je vraćen i test je pao:

| Mutacija | Rezultat |
|---|---|
| HTTPBearer vraćen na 403 | 9 testova pada, među njima AUTH-01 i oba pritegnuta |
| `pedestal_cache` vraćen na `hash()` ključ | CACHE-01 restart test pada (dva procesa, različit `PYTHONHASHSEED`) |
| test s `pytest.skip` + nekorišten import | gate `--fast` CRVEN, preskočeni test imenovan |
| nedostižna baza za boot | `BOOT: 0/8`, izlaz ≠ 0 |

**Što faza 1 nije mogla provjeriti:** CI workflow (`.github/workflows/gate.yml`) napisan je i
testom tvrđen da zove isti skript, ali **nije pokrenut na GitHubu** — grana nije pushana. Prvi push
je prva stvarna provjera; boot tamo ide protiv pravog Postgresa 16, lokalno protiv SQLite-a.

**Usput uočeno, nije mijenjano:** stari `.git/hooks/pre-commit` i `pre-push` i dalje postoje
lokalno, ali ih `core.hooksPath=.githooks` zaobilazi; zovu obrisani `tests/run_tests.sh`, pa bi
bez `hooksPath` pali, a ne prošli.

### §10.2 · Faza 2 — izvještaj (2026-10-12)

**Gate zelen, CI zelen.** Lokalno `bash scripts/gate.sh` → `GATE (full): 6/6`, 71 s. CI run
[`38212339841`](https://github.com/Lika-Digital/ERP-IOT/actions/runs/38212339841) na Linuxu, protiv
pravog Postgresa i s pravim Chromiumom; sažetak je javna anotacija:
`GATE (full): 6/6; PYTEST: collected=242 passed=242 skipped=0; BOOT: 8/8; BROWSER: 12/12`.

| Mjera | Kraj faze 1 | Kraj faze 2 | Kako izmjereno |
|---|---|---|---|
| Backend testova | 132 | **242**, 0 preskočenih | `scripts/pytest_counts.py` |
| od toga ugovorni (novi) | — | contract 47 · sim 38 · client 20 · units 32 | `pytest --co` po datoteci |
| Stageova gatea | 5 | **6** (+ browser, BOOT-01b) | `scripts/gate.sh` |
| Provjera u pravom pregledniku | ne postoji | **12/12** — login, 4 veza iz simulatora, SIM-01/02/05/06/07, nula page/console grešaka | `scripts/browser_check.py` |
| Mjesta koja sastavljaju putanju ormara | svaki poziv (`"/api/ext/" + path`) | **1** (`contract.build_path`); test skenira `app/` | `test_no_cabinet_path_is_built_outside_the_contract_module` |
| Redaka tablice §2.2 provjerenih protiv koda | 0 | **32/32** | test parsira spec |
| Ishod ormara → ERP 500 | Smart Mode 409 → **500** | **0** (5 kvarova × 6 ruta) | `test_no_cabinet_outcome_is_an_erp_500` |
| Vrijeme ERP-a na kešu zbog tokena | ~5 h od 7 (izračun, §0.7 #2) | **0** — 401 → ponovna prijava | `test_expired_token_relogin_once…` |
| Bundle | 646,47 kB | 647,73 kB | `vite build` |

**SIM-00..16: svi zeleni** (u pytestu i, gdje traže DOM, u pregledniku). **Berths / 409 /
`is_stale` ispravljeni:** Berths više ne računa ništa (SIM-15 skenira `frontend/src` na
`status_code` literale); 409 je rečenica ormara, ne „Failed to…" ni 500; keš putuje do sive boje
s „podaci od HH:MM".

**Mutacije:** test odsutnosti cijene uhvatio je ime polja u nalazu; frontend koji crta kontrolu
bez dopuštenja servera ruši SIM-06 u pregledniku.

**Simulator — iskreno:** šest profila (`full`, `three_phase`, `shared_valve`, `silent`,
`smart_off`, `retrofit`), ali `three_phase` i `shared_valve` su stanjem isti kao `full` — Q1 je
trofazna u punom ormaru, a dijeljeni ventil je ERP mapiranje, ne stanje ormara.

**Što faza 2 nije mogla:** provjeriti ugovor na **živom** ormaru (TC-ERP-LIVE-01, i treba O23);
dva tijela u simulatoru (`camera.stream_ext`, `analytics.*`) nisu izvađena iz koda — ERP ih samo
prosljeđuje i ne čita im ključeve (O25).

**Grana:** commitovi faze 2 `25b2d79` i `380b96b` otišli su i na `faza/1-temelji` (moja greška —
prihvaćenu granu nisam smio puniti). Faza 2 dalje živi na `faza/2-ugovor`; `faza/1-temelji` nisam
prepisivao jer bi to bio force-push (O26).

---

## §11 Odgođeno

Nađeno usput. Nije u izvedbi gore; tvoje je da odlučiš prioritet.

| # | Stvar | Zašto odgođeno |
|---|---|---|
| O1 | **`bcrypt==4.0.1` je jedini pin u cijelom `requirements.txt`, i nosiv je** — `passlib` 1.7.4 (`backend/app/routers/auth.py:8,20`, `backend/app/database.py:54,56`) puca s `bcrypt` ≥ 4.1. Dakle jedini pin u repou drži autentifikaciju, a nigdje nije zapisano zašto | faza 1 pinuje sve; ovaj redak postoji da se pri pinanju **ne** „počisti" kao suvišan. Prijelaz s `passlib` na `bcrypt` izravno je zasebna odluka, ne nusproizvod |
| O2 | `SecurityMiddleware` je **samo promatrač** (`backend/app/middleware/security.py:9`) — skenira, logira, nikad ne blokira. CrowdSec iz D13 sloja 1 pokriva isto bolje | preklapanje se rješava kad sloj 1 stane na VPS |
| O3 | Bundle je **646 kB** u jednom chunku (§0.2); Vite to i prijavljuje | radi; code-splitting je optimizacija bez korisnika koji se žali |
| O4 | `frontend/package-lock.json` je **nepraćen** u repou (`git status`) — a faza 1 traži lock datoteku | riješit će ga faza 1; navedeno da se ne izgubi |
| O5 | ~~`erp_docs_inputs.zip` u korijenu~~ — **obrisan u v2** na tvoj zahtjev | zatvoreno |
| O11 | **ERP nema način da iz API-ja sazna koju verziju ormar vrti** | u v3 ne treba: referenca je ugovor, a provjerava se živim odgovorom (TC-ERP-LIVE-01). Ako ikad zatreba, `pedestals.list` bi mogao nositi verziju — zahtjev, ne izmjena |
| O14 | ~~Prijava ugašenog računa s točnom lozinkom vraćala je 403 `Account is disabled`, a kriva lozinka 401 — razlika je otkrivala da račun postoji i da je lozinka točna~~ — **odlučeno i primijenjeno u fazi 1:** nepoznat e-mail, kriva lozinka i ugašen račun daju **isti 401 s istom porukom**; razlog ide samo u log (`backend/app/routers/auth.py`, test `test_inactive_user_login_is_indistinguishable_from_wrong_password`) | zatvoreno |
| O15 | ~~Nepoznat e-mail odgovarao je brže od krive lozinke~~ — **popravljeno nakon faze 1**: lažna bcrypt provjera istog cost faktora; test broji provjere (1 po odbijanju). Izmjereno: prije 2,6 ms / 220 ms, poslije 173 / 190 ms | zatvoreno |
| O12 | **`GET /api/nfc/sessions/by-user` na `develop` piše u bazu** (`erp_reconciliation.py:112-124`) | §7.2 R2 — zahtjev je podnesen; ERP se dotad samoograničava |
| O16 | ~~`backend/alembic.ini` nosio je lozinku baze u čistom tekstu~~ — **odlučeno i primijenjeno:** `alembic.ini` nema URL, `alembic/env.py` ga uzima iz `app.config`, `DATABASE_URL` je obvezan (fail-fast, bez zadanog URL-a — zadani je nosio drugu lozinku), `.env.example` prazan. Test: nijedna konfiguracijska datoteka ne sadrži URL s lozinkom. **Gdje se lozinka koristila:** `alembic.ini` od commita `b534175` (21 verzija u povijesti, repo je **javan**), spec v4 (citirana), lokalni `backend/.env` kao `DEFAULT_ADMIN_PASSWORD`, i **lokalni Postgres je prihvaća** za `erp_user` — mora se rotirati | zatvoreno u kodu; rotacija je na vlasniku baze |
| O17 | **Modeli i migracije se razilaze u 9 indeksa** (`alembic check`) — **odlučeno: faza 3, migracija `006`**; uz to `alembic check` ulazi u gate | faza 3 |
| O18 | ~~ruff s defaultima prijavljuje 327 nalaza~~ — **odlučeno:** uključena samo **DTZ** pravila; svih 36 `datetime.utcnow()` poziva i 8 `default=` stupaca ide kroz `app/utils/time.utcnow()` (naivan UTC, isti ugovor kao stupci). Ostala pravila (BLE001 ×18, UP…) kasnije | DTZ zatvoren; ostalo odgođeno |
| O19 | ~~`npm run lint` zove eslint koji nije instaliran~~ — **odlučeno i primijenjeno:** skripta `lint` uklonjena iz `frontend/package.json`; frontend gate je `tsc --noEmit` + `vite build` | zatvoreno |
| O20 | ~~API keš je ključan samo po `sync_type`~~ — **zatvoreno u fazi 2**: ključ je endpoint + putanja + parametri upita; test: drugi raspon datuma nikad ne dobije tuđi keš | zatvoreno |
| O21 | ⚠ **`GET /api/nfc/session/{id}` mijenja stanje** (§0.7 #1) — spec ga je birao za prikaz | **tvoja potvrda**: prikaz sesija kanalom A; R2b |
| O22 | `GET /api/berths` na ormaru **stvara** vez za ormar bez veza (`berths.py:213-223`) | R12; ERP to ne može spriječiti, samo ne ovisi o tome |
| O23 | TC-ERP-LIVE-01 čita `GET /api/nfc/session/{id}`, koji označi sesiju usklađenom | pri spajanju koristiti probnu sesiju; ili R2b |
| O24 | `outlet_silent` (rang 2.5) nema izvor na ext API-ju | zahtjev prema ormaru ako zatreba; do tada nikad istinit |
| O25 | tijela `camera.stream_ext` i `analytics.*` u simulatoru nisu izvađena iz koda | ERP ih prosljeđuje bez čitanja ključeva; LIVE-01 ih može dodati |
| O26 | `faza/1-temelji` na originu sadrži i dva commita faze 2 | vratiti granu na `ab87e8b` traži force-push — **tvoja odluka**; ništa ne ovisi o tome |
| O27 | ~~R14 poslan ormaru?~~ — **odgovoreno 2026-10-12, prihvaćen** (§7.2 R14, R15); što ERP mijenja i kada: O29 | zatvoreno |
| O28 | ⚠ **Ventili na ormaru 1 možda se otvaraju sami.** Zadano `valve_configs.auto_activate = true` (`a709cf8:…/pedestal_config.py:551-572`); ormar traži da se odmah pokrene `SELECT pedestal_id, valve_id, auto_activate FROM valve_configs;` na ormaru 1. Ako je `1`, voda može teći bez rezervacije i bez naplate | **netko s pristupom bazi ormara** — ERP nema pristup; rezultat upisati ovdje. Ormarov korak a0 to gasi u kodu |
| O29 | Kad ERP prelazi na novi ugovor kanala B | b (`erp_ref`, raspon) → klijent kanala B, simulator, parser i usklađivanje po rasponu (faza 4); `/scan` po priključku (faza 7). c (`ack`) → `ack` nakon obračuna (faza 4/7). a (voda) → NFC tok za vodu (faza 7). Faze 3 i 4 ne čekaju ormar; faza 4 privremeno koristi `by-user` samo iz usklađivača ako b i c još nisu na Krku |
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
- **Ne gradim fiskalizaciju.** Odluka 1.4 je (a): fiskalni račun za pilot izdaje blagajna
  recepcije. ERP **nikad ne ispisuje dokument koji izgleda kao račun** — izvozi obračunske
  zapise i time je gotov.
- **Ne prihvaćam cijenu od ormara.** Ormar mjeri i izvršava, ERP odlučuje i naplaćuje (D0, D4).
  Polje s cijenom se **odbacuje pri parsiranju**, i test traži njegovu **odsutnost** u modelu —
  ne ignoriranje.
- **Ne naplaćujem brojku koja se ne slaže sa svojim graničnim očitanjima.** Takva sesija ide u
  `manual_review`, i to je jedino mjesto na kojem čovjek sazna da nešto ne štima.
- **Ne računam potrošnju sam iz telemetrije snage.** D10: brojka sesije je razlika registra
  brojila, ne izračun iz snage. `power_kw_current` je samo za prikaz uživo.
- **Ne prepisujem ormarovo mapiranje.** D18: neslaganje je stanje koje treba riješiti, nikad
  tiho prepisivanje ni u jednom smjeru. Dok endpointa za čitanje nema, usporedba kaže
  **„nije moguće provjeriti"**, ne „usklađeno".
- **Ne zovem `by-user` za prikaz.** Na `develop` je to GET s nuspojavom; zlorabiti ga značilo bi
  utišati ormarov detektor tišine upravo kad bi trebao javiti (§7.2 R2).
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

`docs/erp_spec.md` · verzija 5.2 · 2026-10-12 · dopuna v5: odgovor ormara (R14, R15)

**§1 je prazan — nema otvorenih blokatora.** Šest odluka iz v1 i v2 je odlučeno i primijenjeno
(§1.0). Referenca za ormar je **ugovor**, a provjerava se **živim odgovorom pri spajanju**
(TC-ERP-LIVE-01), ne commitom.

**Faze 1 i 2 su završene** — gate i CI zeleni, izvještaji u §10.1 i §10.2. **Tri točke traže tvoju
potvrdu** (§0.7 #1, §0.7 #3, O26). **Faza 3 ne počinje bez odobrenja.**
