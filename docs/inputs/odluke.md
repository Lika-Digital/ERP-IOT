# ERP-IOT — dnevnik odluka

**Verzija 2.6 · 2026-10-15** — zamjenjuje v2.5.
v2.6 dodaje **D23–D27** (glavni dashboard; moduli Electricity & Water, Safety & Security i Occupancy; konfiguracija veza i usporedba plovila) i **D28** (demo marina: 2 prava ormara, ostalo simulirano) i proširuje fazu 6; **D24 vraća energetskog agenta** (ispravak D22). v2.5 dodaje **D21** (sigurnosni agent samo čita; mijenja slojeve 3 i 4 u D13 i D14) i **D22** (provjera slike s ormara; zamjenjuje energetskog agenta, koji se briše iz plana), i novi redoslijed faze 5 (5a–5e; faza 4.5 se briše, prvo spajanje na Krk je s VPS-a). v2.4 dodaje **D20** (korisnici, prijava i tajne). v2.3 ispravlja mrežna pravila u **D13** (ormar → ERP samo webhook; bez statične IP). v2.2 dodaje **D19** (ventili i utičnice prema Smart Modeu). v2.1 je dodao **D18** (mapiranje na obje strane); prvi isporučeni zip sadržavao je stariju v2 bez njega.
Ormar (Cloud_IOT) je druga strana ugovora; ovdje se bilježe odluke koje se tiču ERP-a i ono što ERP traži od ormara.

Izvori, redom po težini:
1. Ovaj dokument — odluke.
2. *Cloud_IOT — Marina Monitoring & Control profile*, `docs/ui_v2_spec.md` v2, 2026-10-01 (specifikacija ormara) — što ormar radi i kako to zove.
3. *Izvještaj ERP ↔ Gateway*, 2026-10-10 (Code na repou ormara, 773bca6 vs 282cea5) — stvarni ugovor s file:line.
4. *Navodila za integracijo … MarinaMaster ERP*, v1.0, 2026-10-03 — uloga ERP-a. Naš ERP preuzima ulogu MarinaMastera.
5. Inventar ERP-a, 2026-10-10 — stanje repoa `Lika-Digital/ERP-IOT`.

Kad se izvori razilaze, razilaženje se piše ovdje, ne rješava se šutke.

---

## D0 · Načelo podjele uloga
**Ormar mjeri i izvršava. ERP odlučuje i naplaćuje.** Ormar nikad ne odlučuje smije li korisnik trošiti, ne zna kredit, ne izdaje račun, ne čuva imena korisnika.
Potvrđeno i u specifikaciji ormara (§1.4: "the pedestal reports consumption and the ERP bills").

## D1 · Identitet veza i mapiranje vez → priključak  ⚠ BLOK (vidi "Blokirajuće")
ERP ima tablicu `berths`: komercijalni identitet veza (broj veza, rezervacije, korisnik, SVG id za 2D prikaz), veza na ormar (numerički PK **i** `display_id`, npr. `MAR_KRK_ORM_01`).
Pravila priključaka (usklađeno sa specifikacijom ormara §6):
- jedan vez → najviše jedna električna utičnica; jedna utičnica → najviše jedan vez;
- vodni ispust **smije biti dijeljen** između vezova (nema jedinstvenosti); vez može biti bez vode ili bez struje;
- ormar pokriva 1–4 veza;
- tko je mijenjao mapiranje mora biti zapisan (nikad default).

**Razilaženje:** ormar na `main` već ima vlastitu tablicu `berth_assignments` i čarobnjak za instalaciju koji tu vezu upisuje na licu mjesta. Ext API je ne izlaže (izvještaj 4.2). Dva mastera iste činjenice nisu dopuštena — vidi BLOK-1.

## D2 · "Vez je zauzet" = četiri neovisna signala, nikad spojena
| Signal | Vrijednosti | Izvor |
|---|---|---|
| veza | ONLINE / STALE / OFFLINE | ERP računa iz starosti `last_heartbeat` (pedestals.health / status_ext) |
| plovilo | NEMA / PRAVO / KRIVO / NEPOZNATO | `state_code` 0/1/2 iz `berths.list` (`GET /api/ext/berths`) |
| struja | DA / NE | aktivna električna sesija na utičnici veza (vode ne ulaze) |
| rezervacija | DA / NE | ERP (D4) |

Prioritet boje: OFFLINE/STALE (sivo) > Smart Mode OFF (sivo, "ormar radi samostalno") > KRIVO plovilo (crveno) > struja bez plovila (narančasto) > rezervirano a prazno (žuto) > PRAVO plovilo (plavo) > slobodno (zeleno).
Pragovi: STALE nakon 2× intervala heartbeata, OFFLINE nakon 10 min. Svježina ML-a iz `last_analyzed`.
`opta_connected` se NE koristi kao dokaz da je uređaj živ (punio se iz retained MQTT). U ERP-u se polje zove `device_connected`.

**Usklađivanje rječnika s ormarom.** Ormar ima tablicu stanja sa stabilnim ključevima `status_code` (§3: `no_contact`, `standalone`, `outlet_silent`, `water_leak`, `too_hot`, `auto_off_overload`, `breaker_tripped`, `guard_unreviewed`, `measurement_missing`, `vessel_mismatch`, `ok`). Gdje ERP prikazuje isti pojam, **koristi isti ključ**. Status se računa na serveru, jednom; frontend ga nikad ne računa. Uz ključ ide rečenica za čovjeka; testovi provjeravaju ključ, ne tekst.
"Nema veze" i "Smart Mode OFF" su **nepoznato**, ne "treba pažnju" — stanje veza se tada ne zna.

## D3 · Tipovi uređaja — model mogućnosti
- **Puni ormar**: 4 utičnice (Q1 32 A trofazna, Q2 32 A, Q3/Q4 16 A) + 2 vodna ispusta (V1, V2, 20 l/min), ABB brojila i vodomjeri, detekcija plovila, kamera, senzor vrata, NFC naljepnica na svakom priključku (6 po ormaru), Teltonika 5G router.
- **Retrofit box** (u tuđim ormarima): SAMO struja po utičnicama (mjerenje, uključi/isključi) + NFC naljepnice na utičnicama, mapirane na isti način.
- UI prikazuje samo ono što uređaj ima. Odsutna mogućnost se **ne iscrtava** (ni onemogućena kontrola) — umjesto nje jedna rečenica.
- Priključci se uvijek pišu pravim imenom (`Q1`–`Q4`, `V1`, `V2`), nikad golom znamenkom.
- Oblik telemetrije nije jednak za sve utičnice: Q1 šalje fazne vrijednosti (`currentAmpsL1..L3`, `powerKwTotal`), Q2–Q4 jednu (`currentAmps`, `powerKw`). Komponenta koja pretpostavlja jedan oblik je greška.
- Vodni ispust ima stanja `idle | active | unknown` — **nema `pending`**.
- Dva puta paljenja:
  - **Korisnički (NFC) put**: `POST /api/nfc/scan` — *priprema* priključak; uključuje se tek na fizički priklop, priprema istječe nakon 5 min. Zaustavljanje `POST /api/nfc/session/{id}/stop`. **NFC nije u Gateway katalogu** (specifikacija ormara D4): ERP do njega dolazi isključivo izravnim kanalom s `X-API-Key`, ne kroz `/api/ext`.
  - **Operaterski put**: `controls.socket_cmd` (`POST /api/ext/controls/pedestal/{pedestal_id}/socket/{socket_name}/cmd`, `{action: activate|stop, nfc_tag_id?}`) — odmah, traži utaknut kabel (inače 409).

## D4 · Komercijalna logika živi u ERP-u
Rezervacije, kredit, naplata i računi su u ERP-u. Retrofit box ih nema, pa ERP mora. Ormar je izvršitelj i mjerni uređaj. Billing moduli na ormaru su ostatak demo vremena i isključuju se na strani ormara kad je spojen ERP.

## D5 · ERP čita I upravlja
Jedini preduvjet za upravljanje: **Smart Mode ON**. ERP čita Smart Mode iz `pedestals.health` i unaprijed **uklanja** kontrole (ne siva ih) uz rečenicu.
409 se razlikuje po `detail`: Smart Mode OFF / "Socket has no plug inserted" / priključak već u uporabi. Nikad 500.
Na ormaru se upravljački endpointovi uključuju u Gateway UI-u kao *bidirectional* (popis: izvještaj, i D16).

## D6 · NFC tok — od skeniranja do računa
1. NFC naljepnica je fizički na **priključku** (utičnica ili vodni ispust; puni ormar i retrofit jednako).
2. Korisnik se prijavi u mobilnu aplikaciju i skenira naljepnicu.
3. Aplikacija šalje ERP-u `{nfc_tag_id, user_id}`. Aplikacija nikad ne razgovara s ormarom izravno.
4. ERP iz mapiranja zna **tag → (ormar, priključak)**.
5. ERP odlučuje (D9). Ako išta fali, odbija s razlogom razumljivim čovjeku na molu; ormaru se ništa ne šalje.
6. ERP → ormar: `POST /api/nfc/scan` (pripremi priključak za tog korisnika).
7. Korisnik priklopi kabel/crijevo → ormar uključuje, mjeri, javlja početak sesije.
8. Ormar → ERP: potrošnja otprilike svakih 60 s.
9. ERP: prepaid odbija kredit, postpaid samo bilježi.
10. Prepaid na nuli → ERP šalje stop.
11. Ormar isključuje, zatvara sesiju, šalje konačnu potrošnju.
12. ERP zatvara obračun, po potrebi izdaje račun.

Ako ormar nije dostupan, ERP nikad ne prikazuje "spremno".
**Skenirani tag ne dokazuje fizičku prisutnost** — UID nije tajna (objavljen je u dokumentaciji, ISO 15693 se lako kopira). Tag kaže *koji priključak*; autorizacija je korisnik + ERP.

### D6.1 · Mapiranje NFC naljepnica — master je ERP
- Mapiranje se upisuje **u ERP pri instalaciji**, uvozom CSV-a (`nfc_tags_<ormar>.csv`), ne prepisivanjem.
- Svaki UID ima dva zapisa (obrnuti redoslijed bajtova). **ERP pri traženju provjerava oba.**
- Pogrešno prepoznata naljepnica je gora od neprepoznate — test pri instalaciji provjerava točan priključak.
- Naljepnice su ISO 15693 (Android NfcV, iOS iso15693 od iOS 13).
- Pilot Krk `MAR_KRK_ORM_01`:

| Priključek | Opis | UID | Obrnuti zapis |
|---|---|---|---|
| Q1 | 32 A, trofazna | 35:B2:5A:04:09:01:04:E0 | E0:04:01:09:04:5A:B2:35 |
| Q2 | 32 A, jednofazna | 05:97:5A:04:09:01:04:E0 | E0:04:01:09:04:5A:97:05 |
| Q3 | 16 A, jednofazna | A3:93:5A:04:09:01:04:E0 | E0:04:01:09:04:5A:93:A3 |
| Q4 | 16 A, jednofazna | 96:B6:5A:04:09:01:04:E0 | E0:04:01:09:04:5A:B6:96 |
| V1 | voda, 20 l/min | 64:A8:5A:04:09:01:04:E0 | E0:04:01:09:04:5A:A8:64 |
| V2 | voda, 20 l/min | 34:95:5A:04:09:01:04:E0 | E0:04:01:09:04:5A:95:34 |

## D7 · Webhook nije izvor istine
Ormarov webhook nema potpis (samo statični X-API-Key) ni retry — propušten događaj je trajno izgubljen; `timestamp` je vrijeme otpreme, ne nastanka. ERP prima događaje (početak, potrošnja, kraj, alarm) za brzinu, ali **naplata se usklađuje pullom**. Tko doda polling, u istom commitu dodaje retenciju (sync_log, session_log, alarm_log).

## D8 · Tehnička pravila ugovora
- Vanjska putanja = katalog s `/api/` → `/api/ext/`; ako već počinje s `/api/ext/`, doslovno. Dvostruki `ext` daje lažni 401.
- load/breaker rute traže **numerički PK**; status/water/berths/camera primaju i `display_id`.
- Occupancy odgovor: `note` i `last_analyzed` su opcionalni ključevi.
- Servisni token: `POST /api/auth/service-token`, uloga `api_client`, ormarov vijek 8 h; ERP kešira kraće.
- Verifikacija u Gateway UI-u je savjetodavna i daje lažne 401/422 — ne koristi se kao dokaz ničega.
- Od 2026-11-30 (`nfc_cross_check_required`) `socket_cmd activate` bez `nfc_tag_id` vraća 400.

## D9 · Poslovna logika — prepaid i postpaid
Način naplate je **svojstvo korisnika** (ugovor), ne ormara ni veza. Polje na korisniku, **default `prepaid`** — zaboravljena postavka nikad ne daje neograničenu potrošnju.

Redoslijed pri svakom skeniranju:
1. postoji li korisnik? → ne: odbij
2. važeći ugovor? → ne: odbij
3. način:
   - **PREPAID** → kredit ≥ minimalni iznos za početak (npr. 1,00 €)? → ne: odbij
   - **POSTPAID** → nije blokiran (neplaćeni saldo ispod granice)? → ne: odbij
4. pošalji ormaru pripremu priključka

| | Prepaid (trenutno svi na Krku) | Postpaid |
|---|---|---|
| Tijekom uporabe | svaka poruka o potrošnji → iznos po tarifi → odbij od kredita, prikaži | samo bilježi, prikaži rastući iznos |
| Upozorenje | pri ~20 % preostalog kredita | — |
| Automatsko gašenje | na nuli ERP šalje stop | samo na dogovorene granice |
| Granice | dopušten mali negativni saldo (npr. do 2 €) ili stop malo prije nule — zbog ~60 s kašnjenja | max kWh po sesiji (npr. 100), max neplaćeni saldo, max trajanje sesije |
| Račun | pri kupnji kredita | pri odlasku / periodično |

Kredit: ERP je jedini izvor istine. Ako ERP izgubi vezu, ormar nastavlja dovod (nema stopa) — prekoračenje se prihvaća svjesno. Tvrda granica bez prekoračenja traži logiku na ormaru i nije u trenutnoj izvedbi.

## D10 · Ugovor sesije i mjerenja
Poruka o sesiji: `session_id, cabinet_id, outlet_id (Q1–Q4 | V1–V2), session_type (electricity|water), customer_id, status (active|ended), energy_kwh, water_liters, power_kw_current, duration_minutes`.
- ERP se oslanja na `session_type`, ne na to koje polje nije prazno.
- **`null` = nije izmjereno → nikad ne obračunati kao 0; sesija ide u ručni pregled.** `0` = izmjereno, ništa potrošeno.
- Brojka sesije je **razlika registra brojila** (kraj − početak), ne izračun iz snage. `power_kw_current` je samo za prikaz uživo.
- **`consumption_source`** je dio ugovora: `register` → "očitanje brojila"; `integrated_legacy` → "procjena — brojilo nedostupno"; `unknown` → "nije izmjereno", brojka se prikazuje kao —, nikad 0,0. ERP ga sprema uz svaku sesiju i prikazuje uz svaku brojku.
- Agregati (povijest, analitika) zbrajaju intervalne retke, ne polja sesije.
- Mjerodavna je konačna brojka na kraju sesije; izgubljene međuporuke se ne procjenjuju.
- Kumulativno stanje brojila po priključku služi za usklađivanje: zbroj obračunatih sesija mora odgovarati razlici stanja.
- Stop od osoblja marine ima prednost; ERP-ov stop na već završenu sesiju vraća grešku — to nije problem.

## D11 · Prihvatni testovi (na pravom ormaru)
1. Električna naljepnica: skeniranje → priklop → potrošnja → kraj; potrošnja se slaže na obje strane.
2. Vodna naljepnica: isto, u litrama.
3. Skeniranje bez kredita: ERP odbija, naredba se ne šalje, korisnik dobiva razlog.
4. Kredit potrošen tijekom uporabe: ERP sam šalje stop, ormar gasi, korisnik obaviješten.
5. Skeniranje bez priklopa: priprema istječe nakon 5 min bez posljedica.
6. Stop od osoblja: ERP ispravno zatvara obračun.

## D12 · Povezivanje ERP ↔ ormari: Tailscale
ERP VPS je član Tailscale mreže; svaki ormar (puni i retrofit) je adresa u toj mreži, ERP ga zove izravno. Novi ormar = dodati u Tailscale + jedan redak u ERP-u (adresa, servisni račun). Ništa od ormara nije javno izloženo prema ERP-u.
Izgubljeni webhook događaji rješavaju se periodičkim upitom iz ERP-a (sesije od zadnje provjere) — ERP kod, ne nova infrastruktura.
Centralni MQTT ostaje opcija za kasnije (vrlo velik broj uređaja, vanjski partneri traže jednu adresu), ne obaveza. Ako ikad: zaseban servis od ERP-a, vanjski sustavi dobivaju HTTP API + potpisani webhook, nikad izravan pristup brokeru.

---

## POZICIONIRANJE PROIZVODA
**Digitalna, pametna i sigurna marina.** Sigurnost nije dodatak nego treći stup ponude: zaštita koja razumije marinu i njezine uređaje, umjesto skupog generičkog firewalla i skupog SOC-a. Za ozbiljan incident (forenzika, 24/7 odgovor) telco SOC (Combis/HT, A1) je partner za eskalaciju, ne konkurent.

## D13 · Sigurnosni modul (prioritetni agent)
Modul platforme, s laganim klijentom na svakom ormaru. Prodaje se kao značajka platforme, ne kao samostalni IDS (vidi D15).

### Načela
- **Enkripcija je higijena, ne zaštita.** TLS/WireGuard štite kanal; ne štite od ukradenog ključa, provaljenog VPS-a ni kompromitiranog ormara. Glavni rizik je **radijus štete**: ERP drži pristup svim ormarima.
- **Reakcija po posljedici:**
  - šum (skeniranje, brute force, poznati loši IP) → blokada odmah, automatski, bez agenta;
  - uspjeli napad ili dodir fizičkog upravljanja → **odmah zadržati** (opoziv tokena, gašenje endpointa), istražiti poslije;
  - nejasno i novo → agent šuti, promatra, slaže dokaze, javlja s cijelom pričom.
- **Sadržaj logova i weba je podatak, nikad naredba.** Napadač kontrolira što piše u logovima (User-Agent, URL, korisničko ime). Detekciju radi kod; LLM samo trijažira i objašnjava; akcije su ograničene pravilima u kodu, ne promptom.
- **Agent ne mijenja vlastita pravila sam.** Predlaže → pravilo radi u sjeni (samo bilježi) → čovjek odobrava → aktivno.

### Slojevi
| Sloj | Sadržaj | Reagira |
|---|---|---|
| 0 Higijena | TLS/WireGuard; MFA na ERP adminu, Tailscale i Teltonika RMS računu; Tailscale odobravanje uređaja + tailnet lock; **Tailscale ACL** (ERP → ormar samo nginx :80, nikad :8000; ormar → ERP **samo port webhook prijemnika**; ormar ↛ ormar — *ispravak 2026-10-12*, spec §7.0); servisni račun po ormaru s minimalnim Gateway pravima; **pinane verzije ovisnosti**; automatska sigurnosna ažuriranja; backup; tajne odvojene od diska aplikacije i jedinstvene po ormaru | — |
| 1 Klasična obrana | nftables default-deny; SSH samo ključevi; CrowdSec (engine + bouncer) na VPS-u i ormarima; Cloudflare ispred ERP UI-a (WAF, Access za admin); rate limiting; audit log svake upravljačke naredbe; HMAC potpis webhooka | odmah, automatski |
| 2 Mamci | lažni API ključ u konfiguraciji; lažni Gateway endpoint (npr. `/api/ext/admin/debug`); lažni servisni račun; lažni ormar u Tailscale mreži. Nitko legitiman ih ne dira — svaki dodir je napadač | tiho bilježi |
| 3 Agent *(izmijenjeno D21)* | ponašanje servisnih računa i naredbi **po domeni marine**: `socket_cmd` u neobično vrijeme ili s nove adrese, serija nepoznatih NFC tagova (pogađanje), Smart Mode izvan radnog vremena, račun koji zove endpointe koje nikad nije zvao, vrata ormara + novi uređaj u LAN-u (D16); povezivanje događaja preko slojeva. **Samo čita interne podatke; jedini upis je alarm s dokazima; akciju izvršava ili naređuje Admin (D21)** | šuti, slaže slučaj, **otvara alarm s dokazima i čeka Admina** |
| ~~4 Živo znanje~~ *(otpada, D21)* | ~~strukturirani izvori s weba: CISA KEV, NVD / GHSA, CrowdSec blocklista, abuse.ch~~ — agent ne izlazi na internet. Ako zatreba, **Admin ručno uvozi datoteku** (npr. KEV JSON), agent je čita kao interni podatak | — |

**Izmjena D21 (2026-10-13).** Reakciju „uspjeli napad → odmah zadržati" (opoziv tokena, gašenje endpointa) ne izvršava agent: agent otvara alarm s dokazima, korak izvršava ili naređuje Admin. Automatska blokada šuma ostaje u sloju 1 (CrowdSec, rate limiting — kod i konfiguracija, ne agent).

**Ispravak 2026-10-12 · mreža.** Statična IP nije potrebna: ERP ↔ ormar preko Tailscalea (stalne 100.x adrese, radi iza NAT-a/5G-a), javni UI kroz Cloudflare tunel (odlazna veza, nema otvorenih ulaznih portova). ERP → ormar samo nginx :80 na Tailscale adresi ormara, nikad izravno :8000. Ormar → ERP samo port webhook prijemnika preko Tailscale adrese ERP-a; sve ostalo zabranjeno. Ormar ↛ ormar. SSH na VPS samo preko Tailscalea; na VPS-u javno nema otvorenih ulaznih portova. Detalji: spec §7.0.

### Klijent na ormaru (i retrofitu, ako ima snage)
Šalje logove (prijave, API, Gateway, DHCP zakupe, vrata) preko Tailscalea u ERP; prati izmjene datoteka koda i konfiguracije; lokalni CrowdSec bouncer; heartbeat sigurnosnog stanja.

### Poznate rupe koje treba zatvoriti (i prvi demo agenta)
ERP: `JWT_SECRET` mina, Fernet ključ na istom disku kao šifrirane lozinke, nepinane ovisnosti, HTTPBearer vraća 403 umjesto 401.
Ormar: Gateway ne poštuje mod na direktnim write rutama (2.3), match ne gleda metodu (1.3), webhook bez potpisa, statični JWT secret, anonimni MQTT, kamera stream bez autentifikacije, OTP podložan pogađanju (specifikacija ormara D7), `X-API-Key` ugrađen u mobilnu aplikaciju — mora se smatrati poznatim (D1 ormara).

### Veličina
Wazuh (4–8 GB RAM za server) ne stane uz ERP na 2 GB VPS-u. CrowdSec + vlastiti agent stanu. Slojevi 0 i 1 su dio postavljanja VPS-a — VPS se ne izlaže bez njih.

## D14 · Zajednička platforma agenata  *(izmijenjeno D21 i D22, 2026-10-13)*
Sigurnosni agent (D21) i agent za provjeru slike (D22) dijele: registar izvora, sloj pravila (policy) **u kodu**, odobrenje čovjeka (Admin), audit log. Gradi se jednom.
~~Razine autonomije: savjetuje → čovjek odobri pa izvrši → samostalno samo unutar granica za niskorizične akcije.~~ **Nema samostalnog izvršavanja:** agent savjetuje (alarm, ocjena); korak izvršava ili naređuje isključivo Admin.
Brojke računa kod, ne LLM; LLM povezuje, prioritizira i objašnjava.

### ~~Energetski agent (drugi po redu)~~ — briše se iz plana (D22, 2026-10-13)
*(2026-10-15)* **Vraća se — D24.** Energetski agent je ponovno u planu, kad postoji povijest s Krka; pravila kao D21 (samo čita, predlaže s dokazom i procjenom, ništa ne izvršava; brojke računa kod, LLM objašnjava).
Drugi agent je provjera slike s ormara (D22). Što ostaje od podataka koje je energetski agent tražio, s novim razlogom:
- retencija `consumption_intervals` 400 dana — **ostaje**: naplata i sporovi s gostima;
- polling `load.*` svakih 300 s — **ostaje**: stanje struje uživo za 2D prikaz i signal „struja bez plovila" (D2);
- `load.socket_history_ext` — **nije u uporabi**;
- brojilo na glavnom priključku marine (vršna snaga) — **odgođeno**.

## D15 · Regulatorni okvir
| Sustav | CRA status (procjena, potvrditi s laboratorijem/pravnikom) | Napomena |
|---|---|---|
| Ormar (NUC, Opta, NFC, kamera, Teltonika 5G) | proizvod s digitalnim elementima, Lika = proizvođač; vjerojatno **zadana kategorija → samoprocjena (Modul A)** | CE komponente (Teltonika RED) su dokaz, ne sukladnost cijelog ormara. Ranjivosti komponenti (firmware rutera) su naša obveza prijave i održavanja |
| Retrofit box | isto, zadana kategorija | NFC = radio |
| ERP | "obrada na daljinu" ormara → dio sukladnosti ormara; ako se prodaje kao instalacija, vlastiti proizvod, zadana kategorija | |
| Mobilna aplikacija | proizvod, zadana kategorija | |
| **Sigurnosni modul** | **ugrađen u platformu → ne mijenja kategoriju; samostalno prodan kao IDS/IPS/firewall → Klasa II, obavezno prijavljeno tijelo; kao SIEM → Klasa I** | **Odluka: sigurnost se prodaje kao značajka platforme (ERP + ormari), ne kao samostalni IDS.** |

- **CRA prijave** (aktivno iskorištene ranjivosti, ozbiljni incidenti, 24 h, ENISA platforma) vrijede **od 11.9.2026 — već teku**. Potrebno: registracija na ENISA SRP, sigurnosni kontakt, politika otkrivanja ranjivosti. Puni zahtjevi od 11.12.2027.
- **RED (2022/30)** vrijedi od 1.8.2025 za radijsku opremu spojenu na internet; od 11.12.2027 zamjenjuje ga CRA. Provjeriti CE izjavu ormara/retrofita (NFC). Ciljne norme: EN 18031-1/-2/-3 → EN 40000 / EN 50770 (temeljena na IEC 62443-4-2).
- **NIS2**: marina vjerojatno nije izravni obveznik; neizravno kroz lanac nabave kupaca koji jesu.
- **DORA**: nije relevantna.
- **GDPR / videonadzor (HR)**: oznaka vidljiva najkasnije pri ulasku u perimetar snimanja; snimke najviše 6 mjeseci. Oznaka je obveza informiranja, ne privola — pravna osnova je obično legitimni interes. Marina = voditelj obrade, Lika = izvršitelj → ugovor o obradi.
  - **ML detekcija / referentne slike** → zamagliti ljude **na ormaru, prije spremanja i slanja** (`camera.frame_ext`); **sigurnosna snimka** → ne zamagljuje se, ide pod režim videonadzora (oznaka, 6 mj., evidencija pristupa).
  - **Imena korisnika se ne prikazuju na zaslonima marine** (usklađeno s ormarom, BLOK-2 ormara). ERP ih čuva jer naplaćuje, ali ih pokazuje samo ulogama koje naplaćuju.

## D16 · Sigurnost ormara — model prijetnji i osnovna zaštita
Ormar je na javnom molu. Lokalni LAN iza Teltonika routera je **mreža po lokaciji**: tko fizički dođe do ormara, unutra je. "Privatni LAN" nije granica povjerenja.

### Prijetnje, po riziku
| # | Prijetnja | Posljedica |
|---|---|---|
| 1 | Netko otvori ormar i utakne laptop u LAN | ravni LAN: izravne naredbe Opti preko anonimnog MQTT-a — zaobilazi ERP, Gateway, Smart Mode i NFC; kamera bez lozinke |
| 2 | Wi-Fi na Teltonika routeru uključen (često s lozinkom s naljepnice) | ulaz u LAN bez otvaranja ormara |
| 3 | Ukraden ili kopiran NUC | disk bez enkripcije → tajne i podaci kupaca; ista tajna na svim ormarima → svi kompromitirani |
| 4 | Javni tunel (`marina*.lika.solutions`) | sve iza tunela dostupno internetu; poznate rupe 2.3, admin UI samo lozinkom |
| 5 | Teltonika upravljanje | WAN web/SSH, zastarjeli firmware, **RMS račun upravlja svim routerima** |
| 6 | Nadogradnje (`upgrade.sh` s GitHuba) | preuzet repo ili račun → svaki ormar instalira tuđi kod |
| 7 | NFC UID nije tajna | tag nije dokaz prisutnosti (D6) |
| 8 | Pad 5G veze | ormar nastavlja dovod bez stopa — poslovni rizik prekoračenja |

### Osnovna zaštita (posao na strani ormara — zahtjevi koje ERP očekuje)
- **Router:** VLAN-ovi (NUC / Opta / kamera), samo NUC smije do Opte i kamere; Wi-Fi isključen ili gostujući bez pristupa LAN-u; WAN upravljanje isključeno, zadana lozinka promijenjena, firmware ažuran, RMS s 2FA; firewall default-deny.
- **NUC:** `nftables` default-deny (samo tunel, Tailscale, VLAN Opte); SSH samo ključevi, bez root prijave; CrowdSec; `unattended-upgrades`; `auditd` + AIDE; LUKS + TPM, BIOS lozinka, `usbguard`; Mosquitto s autentifikacijom, sluša samo na VLAN-u Opte; **tajne jedinstvene po ormaru**.
- **Vanjski link:** Cloudflare Access ispred admin UI-a; prema van samo `/api/ext`; rate limiting.
- **Nadogradnje:** potpisani tagovi/commitovi, deploy ključ samo za čitanje.

### Dvije gotovo besplatne detekcije (signal u ERP)
1. **Novi uređaj u LAN-u** (nova MAC adresa / DHCP zakup) — u ormaru s četiri poznata uređaja svaka promjena je signal, gotovo bez lažnih alarma.
2. **Vrata ormara** (`door_state` u status endpointu) otvorena izvan najavljenog servisa → alarm; vrata + novi uređaj → kritično.
ERP mora imati pojam **najavljenog servisnog prozora** po ormaru, inače signal vrata nije upotrebljiv.

### Najprije provjeriti (činjenice, ne pretpostavke)
Wi-Fi na routeru; javna IP na SIM-u; MQTT autentifikacija; enkripcija diska NUC-a; jesu li tajne iste na oba ormara; verzija Teltonika firmwarea; što je sve izloženo kroz tunel.

## D17 · Plan izvedbe ERP-a
Redoslijed je obvezujući. Svaka faza završava nečim što se može provjeriti, gate je zelen, a specifikacija u repou (`docs/erp_spec.md`) ažurirana. Faza ne počinje dok prethodna nije prihvaćena.

| # | Faza | Završava s |
|---|---|---|
| 0 | **Specifikacija** u repou, po uzoru na `docs/ui_v2_spec.md` ormara | `docs/erp_spec.md` odobren; nijedna linija koda prije toga |
| 1 | **Temelji koji ne lažu**: gate u repou (`.githooks` + `core.hooksPath`), CI, linter, pinane ovisnosti (lock datoteka), 7 testova koji padaju, **test da se aplikacija diže** (prvi, ne može proći prazno), `JWT_SECRET` fail-fast, HTTPBearer 401, `pedestal_cache` hash bug, brisanje `camera/detections` | gate koji ne može proći ako se aplikacija ne diže |
| 2 | **Ugovor s ormarom**: klijent prema D8; rukovanje 409 po `detail`; Smart Mode iz health; PK vs `display_id`; `device_connected`; `berths.list`; `is_stale`; NFC kanal s `X-API-Key`; **stub/simulator ormara** iz snimljenih odgovora Krka (puni ormar 4+2, retrofit samo utičnice, trofazna Q1, dijeljeni ventil, tihi ormar) | ugovorni testovi zeleni protiv simulatora; Berths/409/is_stale ispravljeni |
| 3 | **Model podataka**: vezovi, priključci, mapiranje (prema rješenju BLOK-1), NFC tagovi s dva zapisa + CSV uvoz, tip uređaja i mogućnosti, korisnici, ugovori, način naplate (default prepaid), knjiga kredita, `consumption_source` | migracije; uvoz Krk CSV-a pogađa točan priključak |
| 4 | **Prikupljanje + retencija** u istom commitu: poller (health, sesije, berths.list, potrošnja), pull-usklađivanje sesija, prijemnik webhooka (danas X-API-Key, pripremljen za HMAC), audit log naredbi | podaci teku; rast baze izmjeren i ograničen |
| 5 | **VPS**: način isporuke odlučen u specifikaciji (Docker s ispravnim Dockerfileovima ili systemd — jedan, ne oba), 2 GB / 20 GB, Postgres, nginx, cloudflared samo za UI, Tailscale prema ormarima, **slojevi 0 i 1 iz D13 prije javnog izlaganja**, backup, runbook. *Od 2026-10-13 u pet koraka:* **5a** D20 lokalno (prvo, prije svega) → **5b** VPS onboarding, samo Tailscale → **5c** Cloudflare tunel, tek kad je 5a zelen i na VPS-u → **5d** priprema Krka + spajanje VPS → Krk (LIVE-01 samo čitanje, poller preko noći, kontrolni testovi samo na OK) → **5e** tjedan stvarnog rada, uz fazu 6 lokalno. **Faza 4.5 (LIVE s PC-a) se briše**; njezina priprema prelazi u 5d | ERP javno dostupan iza Cloudflare Accessa; runbook proveden na čistom VPS-u |
| 6 | **Zauzeće vezova** (D2) + **2D SVG prikaz** marine (plan nacrtan jednom, svaki vez ima id, aplikacija mijenja klasu). *(2026-10-15)* **Proširena D23–D27:** 6a glavni dashboard + karta, 6b konfiguracija veza (D27), 6c–6e moduli D24–D26 | Krk na karti, četiri signala, sivo za tiho |
| 7 | **Poslovna logika i NFC tok** (D6, D9, D10), prihvatni testovi D11 | D11 1–6 prolaze na pravom ormaru |
| 8 | **Sigurnosni agent (D21)**: mamci, domenske detekcije, signali vrata i novog uređaja (kad ih ormar šalje), prikaz "sigurnost"; samo čita interne podatke, jedini upis je alarm. ~~CVE/KEV prema pinanim verzijama~~ (otpada s weba; ručni uvoz datoteke ako zatreba). Implementacija smije krenuti nakon 5a, na vlastitoj grani, samo na internim podacima | prvi stvarni nalazi na VPS-u i Krku |
| 9 | ~~**Energetski agent**~~ → **Provjera slike s ormara (D22)** — nakon 5e | — |
| 10 | **Energetski agent (D24)** — kad postoji povijest s Krka *(2026-10-15)* | prvi prijedlozi na stvarnim podacima |

Agenti (faze 8 i 9) dolaze nakon 5e, kad ERP stabilno radi s pravim ormarom.

Što ERP ne radi: ne gradi vlastiti MQTT, ne mijenja kod ormara (zahtjevi prema ormaru idu kroz zaseban chat), ne prikazuje imena kupaca na zaslonima marine, ne uključuje automatsko izvršavanje agenata.

## D18 · Mapiranje vez → priključak postoji na obje strane
Sada: mapiranje postoji i u ERP-u i na ormaru (`berth_assignments`). Unosi ga Admin (Lika) prema jednoj definiciji. ERP redovito uspoređuje svoje mapiranje s ormarovim i neslaganje prikazuje kao stanje koje treba riješiti — nikad ga tiho ne prepisuje ni u jednom smjeru. Svaka izmjena ima autora i vrijeme.

Cilj (kad se s marinom dogovori proces): Admin unosi u ERP, ERP šalje ormaru preko ext API-ja; čarobnjak na ormaru ostaje za servis.

Zahtjev prema ormaru: ext endpoint za čitanje mapiranja (odmah) i za upis (kasnije, bidirectional, s autorom i auditom).

Dok endpoint za čitanje ne postoji, usporedba je **„nije moguće provjeriti"**, ne „usklađeno".

## D19 · Ventili i utičnice prema Smart Modeu
Ovako ormar radi (odluka 2026-10-12; zatvara pitanje o samostalnom otvaranju ventila):
- **Smart Mode OFF:** ormar radi samostalno, priključci se otvaraju ručno na ormaru. ERP tu ne upravlja i ne naplaćuje; prikazuje „ormar radi samostalno" (`status_code` `standalone`).
- **Smart Mode ON:** korisnik može fizički okrenuti ili priklopiti, ali ništa se ne dogodi dok ERP ne pošalje naredbu ili dok se ne pokrene iz UI-a ormara. Nema samostalnog otvaranja.
- Potrošnja iz Smart Mode OFF razdoblja **nije ERP-ova sesija i ne ide u naplatu.**

## D20 · Korisnici, prijava i tajne
Odluka 2026-10-12. Mora biti gotovo i u gateu **prije** nego je ERP UI javno dostupan preko Cloudflarea.

1. **Dvije uloge.**
   - **Admin** — sve konfiguracije u ERP-u: ormari, vezovi, mapiranje, NFC uvoz, tarife, servisni računi ormara, korisnici.
   - **Marina Manager** — svakodnevni rad: vezovi, sesije, kredit (dopuna), upravljanje utičnicama i ventilima, ručno paljenje uz razlog (1.1). Ne vidi i ne mijenja konfiguraciju ni korisnike.
   - Postojeće uloge se mapiraju na ove dvije (mapiranje u specifikaciji §5.3). Zatvara O38.
2. **Prijava:** korisnik + lozinka, zatim **obavezan 2FA** (TOTP, RFC 6238, aplikacija za autentifikaciju), za obje uloge.
   - ograničenje pokušaja za lozinku i za 2FA kod, privremeno zaključavanje, zapis u audit;
   - jednokratni rezervni kodovi, spremljeni kao hash;
   - Admin može resetirati 2FA drugom korisniku, uz audit;
   - isti odgovor za sve neuspjele prijave (O14), i u 2FA koraku.
3. **Prvi admin:** nema `DEFAULT_ADMIN_PASSWORD`. Instalacija ispiše jednokratni, vremenski ograničen link za postavljanje; prvi admin postavlja lozinku i povezuje 2FA prije ičega drugog.
4. **Baza bez lozinke:** na VPS-u Postgres sluša samo Unix socket (bez TCP porta), backend radi kao sistemski korisnik `erp`, peer autentifikacija. Nema lozinke baze ni u `.env` ni igdje. Lokalni razvoj i CI smiju imati testnu lozinku, nikad u repou.
5. **Ljudske lozinke postoje samo za prijavu u UI.** Sve ostale tajne (servisni računi ormara, ključ šifriranja, JWT tajna) su strojne: generiraju se pri instalaciji ili ih Admin unosi kroz UI, spremaju se šifrirano, nikad se ne prikazuju natrag.

Redoslijed: ~~D20 se radi zajedno s kodom faze 5, dok traje noćno mjerenje faze 4.5.~~ *(2026-10-13)* D20 je korak **5a** — kreće odmah, prije svega ostalog, lokalno, gate zelen.

## D21 · Sigurnosni agent — samo čitanje
Odluka 2026-10-13. Mijenja D13 (slojevi 3 i 4) i D14.

- Agent je primarno **read-only**: analizira interne ulaze — audit log naredbi, logove prijava, ERP logove, poller/sync podatke, logove ormara koje ERP već prima, mamce iz sloja 2.
- **Jedini dopušteni upis:** otvaranje alarma u bazi ERP-a, s dokazima (koji podaci, kada, zašto). Agent zatim **čeka** — konkretan korak izvršava ili naređuje isključivo korisnik (Admin).
- **Strogo zabranjeno i izvan opsega:** otvaranje portova, mrežnih veza ili linkova; mijenjanje firewalla, konfiguracije, korisnika ili ormara; bilo kakav odlazni mrežni promet. Agent ne izlazi na internet.
- Agent radi isključivo na internim podacima. **Sloj 4 iz D13 (CVE/KEV s weba) otpada**; ako zatreba, Admin ručno uvozi datoteku.
- **Ograničenje provodi KOD, ne prompt:** agent ima samo DB pravo čitanja na izvore + INSERT u tablicu alarma; nema mrežnih alata. Test pada ako agent ima bilo koji drugi upis ili odlazni poziv.
- Sadržaj logova je podatak, nikad uputa (prompt injection).
- Prodaje se kao značajka platforme, ne samostalni IDS (D15/CRA).

## D22 · Drugi agent — provjera slike s ormara
Odluka 2026-10-13. **Zamjenjuje energetskog agenta; energetski agent se briše iz plana.** *(Ispravljeno D24, 2026-10-15: energetski agent se vraća.)*

Proširenje agenta na ormaru (detekcija plovila, guard, zauzeće veza). Kad je agent na ormaru nesiguran u ocjenu:
1. Ormar javi ERP-u događaj **„nesigurna ocjena"** (vez, vrijeme, razlog, ocjena) — mali podatak, bez slike, bez streama.
2. ERP u 2D prikazu marine otvara **zahtjev za pregled** na tom vezu.
3. **Admin odobrava** (na početku isključivo uz odobrenje Admina; odobrenje i odbijanje idu u audit).
4. Tek nakon odobrenja ERP **povlači** snimljenu media datoteku s ormara (ERP → ormar, nginx :80). Ormar nikad ne šalje stream ni datoteku sam; ACL ormar → ERP ostaje samo webhook.
5. ERP vlastitim modelom na VPS-u provjeri što je na slici i prikaže rezultat u 2D prikazu, uz ocjenu ormara.
6. ERP ništa ne šalje natrag ormaru — istina o zauzeću se gleda u ERP-u, ne na ormaru.

- **Premisa:** VPS ima više podataka i CPU-a od ormara. Trenutni VPS nije dovoljan; proširuje se kad dođe do implementacije.
- **Model:** otvoren i lokalan (vision model, npr. Pixtral / Qwen-VL, ili namjenski detektor). **Odluka o modelu: otvoreno, kasnije.**
- Slike ne napuštaju naš VPS (bez vanjskih AI servisa).
- **GDPR (D15):** ljudi na datoteci zamagljeni na ormaru prije slanja; retencija datoteka na ERP-u ograničena i zapisana; pristup u audit.
- **Zahtjevi prema ormaru:** događaj „nesigurna ocjena" u katalogu webhooka; ext endpoint za dohvat snimljene datoteke po ID-u događaja (GET, monitor), s autentifikacijom `api_client`.

**Raspored agenata:** dolaze nakon 5e (ERP stabilno radi s pravim ormarom). Implementacija D21 smije krenuti nakon 5a, na vlastitoj grani, u vremenu čekanja na VPS — samo dijelovi na internim podacima, bez utjecaja na 5b.

## D23 · Glavni dashboard
Odluka 2026-10-15. Početni zaslon nakon prijave (Admin i Marina Manager): **2D karta marine** (SVG, vezovi) gore, ispod **tri velike kartice**. Svaka kartica je grupa; klik vodi u modul s detaljima (D24, D25, D26).

```
┌──────────────────────────────────────────────┐
│           2D KARTA MARINE (SVG, vezovi)      │
├──────────────┬────────────────┬──────────────┤
│ Electricity  │ Safety &       │ Occupancy    │
│ & Water      │ Security       │              │
│ [broj]       │ [broj]         │ [ % ]        │
└──────────────┴────────────────┴──────────────┘
```

Svaka kartica ima jasnu definiciju broja, vrijeme zadnjeg osvježenja i **sivo stanje kad su podaci stari** (isto pravilo kao tihi ormar — stari broj se ne prikazuje kao svjež):
- **Electricity & Water:** današnja potrošnja cijele marine (kWh i m³ ili L), uz usporedbu s jučer / istim danom prošli tjedan.
- **Safety & Security:** broj **otvorenih** upozorenja (ne svih događaja), s bojom najtežeg (critical / warning / info).
- **Occupancy:** % zauzetih vezova = zauzeti / (svi vezovi s poznatim stanjem). Vezovi u stanju Unknown se ne računaju u nazivnik i broje se zasebno („2 unknown"). Rezervirani se prikazuju zasebno.

Status i brojeve računa server; frontend ih samo prikazuje.

2D karta — boje vezova (postojeći rječnik, jedna riječ = jedna boja):
- Free (zelena)
- Occupied — correct vessel (plava)
- Reserved (žuta)
- Wrong vessel (crvena) — plovilo na vezu nije ono koje treba biti; izvor je značajka zauzeća s ormara (match), odnosno D27
- Power without vessel (narančasta)
- Unknown (siva) — nema svježih podataka

Klik na vez otvara detalj veza i konfiguraciju veza (D27).

## D24 · Modul Electricity & Water
Odluka 2026-10-15.
- Klik na karticu vodi izravno na **sve mjerne točke** s ormara (utičnice i ventili), s detaljima.
- Pregledi: po vezu, po doku, po ormaru, cijela marina.
- Povijest i analitika: dnevno / tjedno / mjesečno, vršna snaga, VT/NT, „struja bez plovila", nenaplaćeno (osoblje, `origin = staff`), null nije 0 (D10).
- **„Improvements": ovdje živi energetski agent** — vraća se u plan (**ispravak D22**, koji ga je uklonio). Agent je kao D21: samo čita interne podatke, predlaže uštede s dokazom i procjenom, ništa ne izvršava sam; brojke računa kod, LLM objašnjava (D14). Agent dolazi **nakon** što postoji povijest podataka s pravog ormara.

## D25 · Modul Safety & Security
Odluka 2026-10-15. Modul za fizičku sigurnost marine. Danas ima malo izvora; dizajnira se tako da se budući IoT uređaji dodaju bez prepravljanja.

Sadržaj:
- **Pametni pristup (smart access):** vrata / rampe s NFC čitačima.
  - Mapiranje NFC skeniranja na lokaciju vrata (isti princip kao NFC na priključcima, D6.1).
  - Grupe korisnika i prava pristupa po vratima i vremenu.
  - Izvještaj i upozorenje kod neovlaštenog pristupa (vrata otvorena bez valjanog skeniranja, skeniranje bez prava, izvan vremena).
- **Senzori:** otvaranje vrata, brojanje ljudi (koliko osoba prolazi) — statistika i upozorenja.
- **Kamere:** IR / termalne kamere za ranu detekciju požara.
- **Guard na ormarima:** konfiguracija postojeće guard značajke ormara (ERP prikazuje i konfigurira ono što ormar već ima).
- **Veza s D21:** sigurnosni agent prima i ovaj modul kao izvor i javlja anomalije. Posebna vrijednost je **povezivanje fizičkog i digitalnog**: npr. vrata ormara otvorena + novi uređaj u mreži + naredba utičnici izvan radnog vremena = jedan slučaj, ne tri alarma. Pravila D21 ostaju: samo čita, otvara alarm, čeka čovjeka.

Arhitektura (obavezno):
- **Generički registar uređaja:** uređaj, tip, lokacija (vez / dok / vrata / zona), mogućnosti (čitanje / upravljanje), izvor podataka, adapter. Novi tip IoT uređaja = novi adapter, bez promjene modela (D14).
- Za sada: model, zasloni s praznim stanjem („No devices connected yet") i simulator za 1 vrata + 1 senzor; pravi uređaji kasnije.

Sigurnosne napomene:
- **Požar:** ERP **nije** sustav za dojavu požara i ne smije biti jedini put alarma. IR kamere u ERP-u služe za prikaz i obavijest; zakonski i životno kritična dojava ide kroz certificirani vatrodojavni sustav. ERP ga samo prikazuje / prima signal ako postoji integracija.
- **Brojanje ljudi:** samo anonimni brojevi, bez prepoznavanja lica.
- **Kontrola pristupa:** otvaranje vrata iz ERP-a je upravljačka radnja — ista pravila kao kod utičnica (uloga, razlog, audit); sigurnosni agent nikad ne otvara / zaključava vrata.

## D26 · Modul Occupancy
Odluka 2026-10-15.
- Izvještaj o zauzeću u stvarnom vremenu iz zauzeća s ormara (D2).
- Povijest: zauzeće po danu / doku, prosjek, vršni dani, koliko dugo je vez bio „Wrong vessel" ili „Power without vessel".
- Izvoz (CSV) za upravu marine.

## D27 · Konfiguracija veza i usporedba plovila (match)
Odluka 2026-10-15. Klik na vez → konfiguracija (Admin; Marina Manager čita):
- Glavno plovilo veza: ime, registracija, vlasnik, fotografija.
- Fotografija služi za usporedbu: odgovara li plovilo koje je sada na vezu spremljenom plovilu (match / mismatch → „Wrong vessel").

Gdje se sprema referentna fotografija — **konfigurabilno po marini** (i po potrebi po vezu):
- **PEDESTAL** — fotografija se šalje na ormar (postojeći `berths.push_image_ext`); ormar sam radi usporedbu i ERP-u javlja rezultat (`match_ok_bit` / `state_code` / `match_score`). Ovo je i način rada kad marina NEMA naš ERP.
- **ERP** — fotografija je samo u ERP-u; ERP traži od ormara trenutnu sliku veza i usporedbu radi svojim modelom (D22).
- **BOTH** — fotografija je na oba mjesta; **ocjena ERP-a ima prednost**, ocjena ormara se prikazuje uz nju; razlika između njih je signal za pregled.

Razlog: konačno rješenje još nije odlučeno, a ormar mora raditi i bez našeg ERP-a.

*(2026-10-15, odgovori na specifikaciju §1)* Boja veza = samo zauzeće (crvena = Wrong vessel); alarm ormara je zasebna oznaka na vezu. Slanje fotografije ormaru uključuje se po ormaru, tek kad živa provjera potvrdi popravak 2.3. Način ERP: da, uz tri uvjeta iz §1.4 (R8 potvrđen na ormaru; rutinski kadar se ne sprema; čeka model i veći VPS).

Pravila:
- **GDPR (D15):** na svakoj slici s ormara ljudi su zamagljeni NA ORMARU prije slanja. Retencija slika na ERP-u ograničena i zapisana. Pristup slikama ide u audit.
- Podaci o vlasniku su osobni podaci: vidljivi u detalju veza ulogama Admin i Marina Manager; NE prikazuju se na karti, na dashboardu ni na javnim / zidnim zaslonima.
- **Odnos prema D22:** u načinu ERP rutinska usporedba (kad se zauzeće promijeni) radi se automatski sa zamagljenom slikom; D22-ovo odobrenje Admina vrijedi za eskalacije „nesigurna ocjena". *(Prijedlog s uvjetima: specifikacija §1.4.)*
- Zahtjevi prema ormaru (specifikacija §7.2): dohvat trenutne slike veza za usporedbu (`camera.frame_ext`, uz zamagljivanje — R8), potvrda da `push_image_ext` radi s fotografijom plovila (R19), i da ormar javlja match rezultat po vezu (R20); guard preko ext API-ja (R21, D25).

## D28 · Demo marina
Odluka 2026-10-15 (konačno).
- Slika `docs/ui/marina-demo.png` je predložak 2D karte: **150 vezova**. Pontoni A–E po 20 vezova (A 20 m, B i C 15 m, D i E 10 m), obala: sjeverna 25, južna 10, istočna 15. SVG sa stabilnim id-em svakog veza (shema bez sudara pontona E i istočne obale — specifikacija §6.11); slika smije biti pozadina.

**Pravi ormari (bez simulacije)** — rade preko pravog ext API-ja, kao i do sada:
- `MAR_KRK_ORM_01` (Krk) → početak pontona A (A-01, A-02);
- drugi ormar (marina-iot) → početak pontona B (B-01, B-02).

**Simulirano u ERP-u (sve što nemamo):**
- ostali vezovi i ormari demo marine — postojeći simulator ormara iz faze 2 proširen na isti ext API, ~74 virtualna ormara;
- jedna nadzorna kamera i jedna IR (požarna) kamera;
- Safety & Security: par vrata s NFC pristupom, senzor otvaranja, brojač ljudi.

Realni i ponovljivi podaci (seed): dnevni profil struje i vode, brojila koja samo rastu, zauzeće ~70–85 %, rezervacije, povremeno wrong vessel / power without vessel, alarmi. Scenariji na naredbu za demo: ormar offline, IR alarm, neovlašteni pristup, prepaid na nuli, krivi brod.

Pravila:
- Svaki uređaj / ormar ima oznaku real / simulated; Admin na karti vidi znak „SIM". *(2026-10-15: vide ga i Admin i Marina Manager.)*
- Simulirano **nikad** ne ide u naplatu, izvještaje za upravu ni u sigurnosnog agenta kao stvarno.
- Simulator radi lokalno i na VPS-u (zaseban systemd servis), može se ugasiti jednom naredbom i ne dira prave ormare.

**Redoslijed (2026-10-15):** implementacija D23–D28 ide u **fazu 6 (proširenu)**. Smije se raditi lokalno protiv simulatora u vremenu čekanja dok traje 5b — **jedna stvar u isto vrijeme**: D28 demo marina, D23 dashboard + 2D karta, pa D27 konfiguracija veza, zatim detalji D24–D26. Energetski agent (D24) tek kad postoji povijest s Krka.

---

## Blokirajuće (moja odluka, ne blokira specifikaciju)
- **BLOK-1 · Tko je master mapiranja vez → priključak.** Ormar ga upisuje čarobnjakom na licu mjesta (`berth_assignments`, `main`), a D1 je rekao da je ERP master. Opcije: (a) ERP master, čarobnjak na ormaru čita/šalje u ERP; (b) ormar master fizičkog ožičenja (koja utičnica služi kojem vezu), izložen novim ext endpointom, ERP master komercijalnog identiteta (broj veza, rezervacija, korisnik) i javlja neslaganje; (c) oba, s usklađivanjem. **Preporuka: (b)** — ožičenje se zna samo na licu mjesta, a retrofit ga mora unijeti isto tako; jedna činjenica ima jednog vlasnika. Traži novi ext endpoint na ormaru.
- **BLOK-2 · Ručno paljenje iz ERP dashboarda nakon 2026-11-30** (NFC cross-check na `socket_cmd`): dopušteno ili ne? Ako da, ERP šalje tag iz mapiranja i to se zapisuje u audit kao operatorska akcija.

## Otvoreno (ne blokira)
- Dokument MarinaMaster kaže da ERP potrošnju za vrijeme prekida "dobije naknadno"; webhook nema retry. Koji pull endpoint vraća sesije i potrošnju za vremenski raspon?
- Koji EVENT_CATALOG id-evi odgovaraju početku sesije, potrošnji ~60 s i kraju sesije? `meter_telemetry_received` se emitira, ali nije u katalogu.
- Kojom ulogom i ključem ERP zove `/api/nfc/*` (izravni kanal s `X-API-Key`) i kad se taj ključ rotira (ugrađen je u mobilnu aplikaciju)?
- ~~Postoji li brojilo na glavnom priključku marine ili podaci s računa (za vršnu snagu)?~~ — **odgođeno** (energetski agent obrisan, D22). *(2026-10-15: ponovno otvoreno — D24 traži vršnu snagu.)*
- Model za provjeru slike (D22) — otvoreno, odlučuje se pri implementaciji.
- Status veze po ormaru na dashboardu (spec O51) — rješava se u fazi 6 (D23).
- Ventili su uvijek „Unknown" (ERP ne čita stanje ventila) — otvoreno; zatvara se kad ERP čita stanje ventila (R15/R16 s ormara).
- Ormar: popravci 2.3, 1.3, 3.1, 2.1. `breakers.socket_reset_ext` i `load.auto_stop_ack_ext` ne uključivati prije 2.3.
- Činjenice iz D16 "Najprije provjeriti".
