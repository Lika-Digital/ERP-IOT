NOVI TOK: ERP (erp-iot). Ormar (Cloud_IOT) vodim u zasebnom chatu — ovdje ga
ne diramo osim kao drugu stranu ugovora.

═══ 1 · ŠTO GRADIM ═══

Pametni privezni ormar za marine. Uz njega vlastiti ERP koji centralno
upravlja ormarima — za marine koje nemaju MarinaMaster. Postavit ću ga na VPS
(Linux, moj hosting) kao demonstracijski ERP. Cilj je probiti se na to
tržište; prednost mi je hardver koji šalje podatke u stvarnom vremenu.

Tri IOT instance hardvera:
  - naš ormar (MAR_KRK_ORM_01, Krk)
  - retrofit box koji se ugrađuje u TUĐE ormare, da mjerimo i kontroliramo
    struju u ormarima koji nisu naši — princip integracije je isti API
  - treća instanca

═══ 2 · ŠTO TRAŽIM ═══

  1. Je li ERP u skladu s API-jem koji smo definirali na ormaru; ako nije,
     ažurirati ERP stranu
  2. Princip instalacije, u kojem je obliku SW, kojim koracima na VPS, i
     koliko prostora zakupiti
  3. Što ormar vraća za zauzeće veza i kako
  4. Poslovna logika koju očekujemo (prepaid / postpaid)
  5. ČETVRTA FUNKCIJA: UI kao digitalna replika marine — 2D, lijepa pozadina,
     vezovi u stvarnom vremenu, bojama zauzeće / slobodno / pravi brod.
     Brzo i jednostavno za vrtjeti i mijenjati u pregledniku.

═══ 3 · STANJE ERP-a (read-only inventar, s file:line) ═══

C:\Users\dopse\Projects\erp-iot · github.com/Lika-Digital/ERP-IOT

FastAPI + React 18/TS/Vite/Tailwind/zustand/Recharts. PostgreSQL preko
SQLAlchemy+Alembic (config.py:13) — PAZI: ERP je Postgres, ormar je SQLite.
90 datoteka, ~10 300 linija. 9 commitova, 2026-04-06 do 04-12 — sedmodnevni
build, šest mjeseci hladan. main i dev identični.

NE MOŽE SE DEPLOYATI KAKO JE DOKUMENTIRANO
  docker-compose.yml definira 4 servisa, ali backend/Dockerfile i
  frontend/Dockerfile NE POSTOJE. `docker compose up -d` iz READMEa pada na
  buildu. systemd je samo predložak u dokumentaciji.
  Gate postoji ali je lokalan (.git/hooks, nema .githooks ni core.hooksPath) —
  ne preživi klon. Nema CI. Nema lintera uopće. Backend ovisnosti nepinane
  osim bcrypt — `pip install` danas povlači druge major verzije nego u travnju.

96 testova, 7 pada. ATRIBUCIJA U DOKUMENTACIJI JE KRIVA: nije
SecurityMiddleware (security.py:9 kaže da nikad ne blokira) nego
`HTTPBearer()` s auto_error=True na auth.py:21 — vraća 403 umjesto 401 za
nedostajući header.

KAKO RAZGOVARA S ORMAROM
  JWT servisni račun, ne API ključ. POST /api/auth/service-token s
  {email,password} → access_token, keširan 7 h protiv ormarovih 8 h
  (pedestal_api.py:95-144). Podaci po marini u Postgresu, lozinka
  Fernet-šifrirana (marina.py:17-23, ERP_ENCRYPTION_KEY).
  KLJUČNO: pedestal_api.py:167-168 PRISILNO prefiksira svaki put s /api/ext/.
  Nema puta koji to zaobilazi.

  17 metoda, 16 spojeno, 1 mrtva (camera/detections — ruta nikad nije
  postojala, obrisati).

TRI STVARI KOJE SU POKVARENE

  (a) BERTHS STRANICA LAŽE. /api/berths vraća BerthOut sa status,
      detected_status, occupied_bit, match_ok_bit, state_code, alarm,
      match_score — NEMA polja `occupied`. Berths.tsx:53-54 filtrira po
      b.occupied, što je undefined za svaki red. Cijela stranica prikazuje
      SVAKI vez zeleno "Free", s uvjerljivim brojem u "Available". Ne baca
      grešku, ne upozorava. Samo laže.

  (b) KONTROLE VRAĆAJU 500. Gateway vraća 409 kad je Smart Mode OFF
      (external_api_gateway.py:329-338). ERP za 409 nikad nije čuo — grep
      kroz cijeli backend i frontend: nula pogodaka. controls.py:46 zove
      allow_session nezaštićeno, pedestal_api.py:281 radi raise_for_status.
      409 postane nehvaćeni HTTPStatusError → HTTP 500 u UI-u.

  (c) is_stale SE IZRAČUNA, VRATI I BACI. pedestal_ext.py:70 ga vraća;
      OccupancyEntry i OccupancyState ga nemaju; fetchOccupancy ga ispusti.
      Kad ormar utihne, _get_cache servira zadnje poznato (pedestal_api.py:
      233-237) i UI nacrta samouvjereno crveno "Occupied" ili zeleno
      "Available" BEZ IKAKVE OZNAKE. Ništa ne istječe — sat vremena staro i
      mjesec dana staro izgledaju identično.

ZAUZEĆE VEZA — ODGOVOR: samo (c), i to djelomično
  Nema tablice veza u ERP-u uopće. Osam tablica, nijedna nije berths. Nema
  berth↔socket, nema berth↔korisnik, nema identiteta veza koji ERP posjeduje.
  /api/ext/pedestals/{id}/berths/occupancy vraća occupied = bool(occupied_bit)
  (ext_pedestal_endpoints.py:202). occupied_bit je pod komentarom "Last ML
  output fields" — to je RT-DETR bit detekcije plovila.
  Dakle jedina boja koju ERP crta znači: ML je detektirao NEKO plovilo.

  - (a) struja se vuče na vezu → NE. ERP nikad ne spaja sesije s vezovima.
  - (b) rezervirano → NE, i podaci su na krivoj strani žice. Rezervacije žive
        NA ORMARU (BerthReservation, check_in/out, customer_id). ERP nema
        tablicu rezervacija. To je obrnuto od priče o proizvodu.
  - (c) pravi brod → NE, samo "neki" brod. Ormar ZNA razliku preko
        match_ok_bit i state_code (0=FREE 1=OCCUPIED_CORRECT 2=OCCUPIED_WRONG)
        — a occupancy endpoint ne šalje ništa od toga. Ormar zna "krivi brod
        na vezu 3" i ERP to strukturno ne može čuti.

POSLOVNA LOGIKA: NE POSTOJI. Nije stub — nema je.
  grep billing|tariff|invoice|customer|prepaid|postpaid|credit|price|payment:
  nula pogodaka. Nema tablice, modela, rute, TODO-a.
  A ORMAR ima billing.py, customer_invoices.py, contracts.py,
  customer_auth.py, customer_sessions.py — i emitira invoice_created koji ERP
  ne sluša. SVA komercijalna logika živi na uređaju. Za proizvod koji se
  prodaje kao ERP sloj iznad ormara, to je naopako.

UI: nema grafičkog prikaza vezova. Kartice i redovi. Nema karte, canvasa,
  d3, leafleta. Svaki <svg> je ikona. Jedini pravi graf je Recharts u Energy.

DEPLOY I VELIČINA
  Danas: ručno, dva procesa, na dev boxu. Javno je bilo preko Cloudflare
  tunela na erp.lika.solutions.
  VPS treba: Python 3.11+, Node 18+ (samo za build), PostgreSQL 16+, nginx,
  cloudflared. Ništa se ne kompajlira. Bez GPU-a, bez ML-a.
  MINA: config.py:45-51 generira SLUČAJAN JWT_SECRET kad nije postavljen i
  logira CRITICAL. Svaki restart tiho poništi sve sesije. docker-compose ga
  defaultira na "change-me-in-production".

  RAM u radu ≈ 500–600 MB. Disk instalirano 4–6 GB.
  RAM VEŽE NA BUILDU, NE U RADU: vite build doseže 0,5–1 GB. VPS od 1 GB
  pokreće aplikaciju i ubije build. Dakle 2 GB / 20 GB, ili ostani na 1 GB i
  gradi dist/ drugdje pa rsync.

  ŠTO RASTE: sync_log (red po pozivu, dva po neuspjelom, bez retencije),
  session_log (neograničen, ~0,6 MB/dan po sesiji), alarm_log.
  NEMA RETENCIJE NIGDJE — nula pogodaka na retention|prune|purge|TTL.
  Danas nema pollinga uopće (nula pogodaka na apscheduler|celery|
  repeat_every) — ERP dira ormar samo kad čovjek otvori stranicu. Doda li se
  poller na 30 s, sync_log postane ~1,7 GB/godinu. Tko doda polling mora u
  istom commitu dodati retenciju.

  BUG: pedestal_cache ključa redove s abs(hash(cache_key)) % 10**9. Python
  randomizira hash stringova po procesu, PYTHONHASHSEED nije nigdje postavljen
  → svaki restart izmisli nove sintetičke pedestal_id-eve, stari redovi
  ostanu siročad, i stale-fallback tiho prestane raditi za sve keširano prije
  restarta.

VEZANOST NA HARDVER: PLITKA — dobra vijest.
  PedestalAPIClient prima samo (marina_id, base_url, email, password). Nula
  pogodaka na mqtt|arduino|onvif|modbus|smart_mode|breaker|valve|firmware.
  Nema device_type ni vendor polja.
  Jedino stvarno curenje: `opta_connected`, 5 pogodaka, vozi Online/Offline
  čip, i PedestalDetail.tsx:392 doslovno piše "OPTA Connected". Retrofit box
  bez Arduino Opte prikazuje se kao trajno Offline i imenuje komponentu koju
  nema. Popravak ~5 linija: preimenovati u device_connected uz fallback.

═══ 4 · ODGOVOR NA BLOKIRAJUĆE PITANJE ═══

Code nije mogao pročitati živu konfiguraciju Krka. Ja jesam — ispis od
2026-10-10. external_api_config ima jedan red, i u njemu:

  webhook_url    = None          ← ništa se ne gura prema van
  allowed_events = ["heartbeat", "temperature_reading"]
  active         = 1

  allowed_endpoints — 23 stavke, SVE u mode:"monitor":
    pedestals.list, pedestals.health, pedestals.status_ext, water.status_ext,
    sessions.active, sessions.pending, analytics.daily, analytics.summary,
    alarms.active, camera.snapshot, camera.stream, load.socket_get_ext,
    load.marina_alarms_ext, load.pedestal_alarms_ext, load.socket_history_ext,
    usage.history, usage.reports_list, usage.report_download,
    breakers.marina_alarms_ext, load.pedestal_get_ext, berths.occupancy_ext,
    camera.frame_ext, camera.stream_ext

UNAKRSNO S ERP-ovih 16 POZIVA:

  OMOGUĆENO (10): pedestals.list, pedestals.health, sessions.active,
    sessions.pending, analytics.daily, analytics.summary, alarms.active,
    berths.occupancy_ext, camera.frame_ext, camera.stream_ext

  NIJE NA POPISU (6): controls.allow, controls.deny, controls.stop,
    alarms.acknowledge, berths.list, diagnostics.run

I NADASVE: sve 23 su "monitor", a gateway za ne-GET traži "bidirectional".
Dakle SVAKA OPERACIJA PISANJA JE BLOKIRANA DVAPUT — nije na popisu, i
konfiguracija je samo za čitanje.

ERP je na Krku danas READ-ONLY PO KONFIGURACIJI. Kontrole ne mogu raditi.
Ono 409 na Smart Modeu je sljedeći problem, ne prvi — 409 bar pretpostavlja
da je poziv prošao vrata.

Verifikacija od 2026-08-21 u istom redu pokazuje 401 na
/api/ext/pedestals/{id}/status, /water, /marinas/{id}/load/alarms,
/marinas/{id}/breaker/alarms. ERP ne zove nijedan od ta četiri — ali njegova
tri izravna poziva (berths/occupancy, camera/frame, camera/stream) dijele
isti _check_ext_auth u istoj datoteci. Nerazriješeno.

═══ 5 · ODLUKE I NAČELA ═══

"VEZ JE ZAUZET" SU TRI STVARI, NIKAD SPOJENE, PLUS ČETVRTA:
  a) netko vuče struju na utičnici tog veza   — ormar to zna
  b) vez je rezerviran                        — ormar to danas zna, ERP ne
  c) na vezu je PRAVI brod                    — ormar zna, endpoint ne šalje
  d) NEMA VEZE S ORMAROM                      — tihi ormar nije prazan vez
Taj četvrti bug smo već jednom našli u ormarovom vlastitom dashboardu.

ERP RAZGOVARA S UGOVOROM, NE S ORMAROM. Inače retrofit box postaje poseban
slučaj posvuda i svaki sljedeći tip uređaja košta kao prvi. Inventar kaže da
je to već skoro tako — ostaje preimenovati opta_connected.

2D PRIKAZ MARINE → SVG. Plan se nacrta jednom u vektorskom alatu, svaki vez
dobije id, aplikacija mijenja samo klasu. Nema engine-a, radi svugdje, i
mijenja ga netko tko nije programer — presudno za demo koji se prilagođava
svakoj marini. Leaflet s image overlayem ako treba pan/zoom preko snimke.
Canvas/Pixi tek kod tisuća elemenata — nema ih (50–500 vezova).

═══ 6 · PLAN, ŠEST KORAKA ═══

  1. Inventar — GOTOVO
  2. Provjera ugovora — gotovo, uz nalaz iz §4
  3. Definicija zauzeća veza — odluka moja, pa tek onda kod
  4. VPS
  5. Poslovna logika — prepaid i postpaid
  6. 2D prikaz marine

═══ 7 · OTVORENO ═══

  - Odluka: što ERP prikazuje kao zauzeće, i odakle to dolazi
  - Gdje žive rezervacije — danas na ormaru, a trebale bi u ERP-u
  - Gdje živi naplata — danas sva na ormaru
  - Hoće li se Krk konfiguracija prebaciti u bidirectional i dodati onih 6
    endpointova, ili ERP ostaje read-only demo
  - Ona tri pokvarena mjesta (Berths.tsx, 409, is_stale)

SSH tunel do živog ormara, ako zatreba čitanje:
  ssh -L 8080:localhost:80 cloud-iot@100.65.235.29
  → http://localhost:8080 je cijeli ormar, isti origin, read-only GET-ovi