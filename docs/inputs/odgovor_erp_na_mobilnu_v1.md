# Odgovor ERP-a na odgovor mobilne v1

| | |
|---|---|
| Od | ERP (`Lika-Digital/ERP-IOT`, `docs/erp_spec.md` **v29**, grana `spec/v3-moduli`) |
| Za | Marina Mobile (`docs/mobile_spec.md` v0.3) |
| Na | `odgovor_mobilne_v1.md` (2026-10-16) |
| Datum | 2026-10-16 |
| Status | **Prijedlog ERP-a.** Odluke vlasnika su ugrađene, ne otvaraju se. Ostalo postaje obvezujuće tek kad vlasnik odobri izmjene `erp_spec.md` iz §2 (§0.0). Oblici u §3 i §4 su **ugovor za mock**, označen `contract: proposed`, dok ih vlasnik ne odobri |

Oznake:
- **PRIHVAĆAM** — ERP to radi kako je predloženo, ili uz navedenu dopunu.
- **NE PRIHVAĆAM** — uz razlog i zamjenu.
- **TREBA ORMAR** — ide na popis u §5.
- **ODLUKA VLASNIKA** — ugrađuje se; navedeno je gdje i što mijenja u `erp_spec.md`.

`ERP §x` je `erp_spec.md` v29. `v3 §14.x` je novi dio speca (moduli i višemarinski model, prijedlog).

---

## 1. Odgovor po točkama

### 1. Pristup, identitet i prijava

**1.1 Javni pristup samo za `/api/mobile/v1/*`** — ODLUKA VLASNIKA, ugrađuje se.
- **M19** je zaseban router `/api/mobile/v1`. Ne dodaje pravila, nego zove iste servise kao web
  rute, s istom provjerom marine (`tenant()`, v3 §14.1) i istim auditom.
- nginx na VPS-u, iza tunela, propušta **samo** `^/api/mobile/v1/` (plus Stripe webhook, točka
  3.4). Sve ostalo dobiva 404 bez tijela. Test sa svakom rutom iz popisa ruta (v3 §14.1.2,
  MT-05) dokazuje da je izvan tunela nedostupna.
- M1 i M5 preformulirani su na prefiks (§3).
- **Mijenja `erp_spec.md`:**
  - §8.4 korak 5c: tunel nosi samo mobilni prefiks, admin UI ostaje na Tailscaleu;
  - §7.1: sloj 1 se ne mijenja; CrowdSec (5c) gleda i mobilni prefiks;
  - novi §14.9: mobilni API.
- **Posljedica koju bilježim:** upravljačke radnje osoblja (Allow/Deny/Stop, utičnice) tada su
  javno dosežne, iza lozinke, TOTP-a, zaključavanja (D20) i CrowdSeca. To je posljedica odluke,
  ne prigovor. Zato M3 (rate limit) mora biti gotov prije prvog javnog zahtjeva.

**1.2 `kind ∈ {staff, customer}`, admin je uloga** — ODLUKA VLASNIKA, ugrađuje se.
- Oblik `/me` je u §3.3.
- U v3 (§14.1.3, §1.7) uloga prelazi na članstvo u marini. Tada `/me` za osoblje dobiva
  `memberships[]`, a `role` ostaje kao platformska uloga (`admin` ili `null`).
- Mobilna mora nepoznatu ulogu tretirati kao **najmanja prava**.
- **Mijenja:** §4.9 i §14.1.3 (oblik `/me`).

**1.3 `permissions[]` u `/me`** — PRIHVAĆAM za v3, kao **M21**.
- Vlasnik je odlučio da v1 radi s ulogama `admin` i `marina_manager`.
- U v3 se `permissions[]` generira iz **iste tablice matrice** iz koje se generira provjera na
  serveru (v3 §14.1.3). Klijent i server zato ne mogu imati dvije različite matrice.
- U v1 polje ne postoji. Mobilna mora ignorirati nepoznata polja.

**1.4 Jedan kupčev račun, više marina** — ODLUKA VLASNIKA, ugrađuje se.
- Token kupca nosi `sub = account_id` i `scope = customer`, bez marine.
- Svaka kupčeva ruta ima `{marina_id}` u putanji. `tenant()` provjerava aktivno članstvo
  računa u toj marini, pa tek onda postavlja `erp.marinas` (RLS, v3 §14.1.1).
- Sve staff ovisnosti (`get_current_user`, `require_admin`, WS) odbijaju `scope = customer`.
  Kupčeve ovisnosti odbijaju staff token. Test pokriva svaku rutu iz popisa.
- **Mijenja:** v3 §14.1.2. `customer_accounts` je **platformska** tablica, bez `marina_id`
  (kao `users`). `customer_members` je tablica **marine**, s RLS-om.

**1.5 Dvije prijave za istu osobu** — ODLUKA VLASNIKA (= `erp_spec` §1.29, odlučeno 2026-10-16),
ugrađuje se.
- Odvojeni su `POST …/auth/staff/login` i `POST …/auth/customer/login` (§3.4). Isti e-mail smije
  postojati u `users` i u `customer_accounts`.
- Refresh tokeni su odvojeni po (vrsta računa, račun, uređaj).

**1.6 Trajanja i refresh** — ODLUKA VLASNIKA, ugrađuje se.
- Model je prihvaćen, uz tri dopune:
  1. refresh token se sprema **samo kao sha256**;
  2. refresh je vezan uz `device_id` (drugi uređaj s istim tokenom → obitelj se opoziva);
  3. **12 h osoblja je apsolutni rok obitelji** od prijave s TOTP-om, ne klizni.
- Access token (15 min) je JWT i ne opoziva se pojedinačno. Server ipak na **svakom** zahtjevu
  provjerava je li račun aktivan i je li token u skladu s računom, kao danas za osoblje
  (`routers/auth.py`, `get_current_user`). Ugašen račun ili promijenjena lozinka zato prestaju
  vrijediti odmah, a ne za 15 min.
- **Moje čitanje odluke za kupca:** „rotirajući refresh 30 d" znači da svaki novi refresh vrijedi
  30 d od izdavanja (klizno, dok se koristi), bez apsolutnog roka. Ako je mišljen apsolutni rok,
  to je jedna konstanta.
- Oblik je u §3.5.
- Web (danas JWT 8 h, `config.py:27`) ostaje kakav je. Usklađivanje weba je zaseban prijedlog.
- **Mijenja:** §4.9 (tablica `refresh_tokens`), §7.1 (trajanja).

**1.7 2FA povezivanje na mobitelu** — ODLUKA VLASNIKA, ugrađuje se.
- `enroll/start` na mobilnom prefiksu vraća `secret` i `otpauth_uri`, **bez `qr_svg`**.
- `auth_audit` bilježi kanal iz `X-Client`.
- Rezervni kodovi stižu u `confirm`, kao danas (`schemas/auth.py`, `EnrollDone`). Oblik je u §3.4.

**1.8 Setup link i zaboravljena lozinka osoblja (M23)** — PRIHVAĆAM.
- Do uloge Owner (v3 M0) link izdaje samo Admin.
- Link ide na `https://lika.digital/setup#token=…`. Token ostaje u **fragmentu**, kao danas
  (`erp_spec` §4.9), pa ga ni web stranica `lika.digital` ne vidi u logu.
- Aplikacija hvata link universal linkom i zove `POST …/auth/staff/setup/check` i
  `POST …/auth/staff/setup` (isti oblik kao web `/api/auth/setup/check` i `/api/auth/setup`).
- Bez aplikacije, stranica nudi download ili nastavak na ERP webu preko Tailscalea.

### 2. NFC

**2.1 Identitet kupca kroz token, ne kroz tijelo** — ODLUKA VLASNIKA, ugrađuje se.
- **Mijenja §5.1 korak 2** (trojka T-9, §2).
- Ostali koraci se ne mijenjaju: korak 4 je i dalje vratar, ormaru se ne šalje ništa dok
  odluka nije pozitivna, a `erp_ref` prema ormaru ostaje.
- Odgovor `scan` i rute sesija su M11 (faza 7). Oblik iz točke 2.1 prihvaćam kao smjer, a točan
  ugovor dolazi s fazom 7.

**2.2 Pravilo zaustavljanja iz aplikacije** — PRIHVAĆAM, uz pravilo:
- kupac smije zaustaviti **svoju** aktivnu sesiju;
- nositelj organizacije smije zaustaviti i sesije svojih članova;
- član smije zaustaviti samo svoju;
- osoblje zaustavlja kroz upravljanje (razlog, `command_audit`), ne kroz kupčevu rutu;
- ERP vraća `can_stop` po sesiji i odbija stop koji ne smije: 403 `stop_not_allowed`.

Ormar ne treba ništa novo: ERP zaustavlja kanalom B (`/api/nfc/session/{id}/stop`), kao kod
prepaida na nuli. Trojka T-10, §2.

**2.3** → 3.1.

**2.4 UID na iOS-u i format** — PRIHVAĆAM; **normalizacija već postoji**.
- `backend/app/cabinet/nfc_uid.py` uklanja razmake, `:` i `-`, pretvara u velika slova i
  provjerava hex. ERP sprema i traži **oba redoslijeda bajtova** (`uid_primary`, `uid_reversed`,
  `erp_spec` §4.4, TC-ERP-SIM-14).
- Mobilna šalje sirovi hex, bilo kojim separatorom.
- Pogrešan UID dobiva 422 `uid_invalid` „This tag could not be read. Hold the phone still on the
  tag and try again."
- **Vrste naljepnica po ormarima: TREBA ORMAR** (§5, točka 6).

### 3. Kupac v1

**3.1 Organizacija kupca (M18)** — ODLUKA VLASNIKA (članovi imaju vlastitu prijavu i pune istim
tokom), ugrađuje se. Model PRIHVAĆAM, **spojen s v3 §14.3.1**: jedna tablica `customer_members`, ne
dvije.

```
customer_accounts   (platforma)  id, email UNIQUE, password_hash, status, email_verified_at,
                                 failed_count, locked_until, created_at
customers           (marina)     postoji — nositelj ugovora po marini (v3 §14.3.1)
customer_members    (marina)     marina_id, customer_id, account_id NULL (član bez računa smije
                                 postojati, npr. posada), full_name, relation, member_role
                                 ('holder'|'member'), can_access (D32 kamera, D25 vrata),
                                 spend_limit NULL, invited_by, invited_at, consent_at,
                                 removed_at
```

Otvorena pravila su prijedlog ERP-a (trojka T-12, §2):

| Pravilo | Prijedlog |
|---|---|
| Vidi li nositelj sesije članova? | **da** |
| Vidi li član tuđe sesije u organizaciji? | **ne** |
| Ograničenje potrošnje po članu | **postavka nositelja** (`spend_limit`, zadano bez ograničenja), u okviru ugovora nositelja (prepaid/postpaid ostaje svojstvo ugovora, D9) |
| Maloljetni članovi | **nema računa ispod 16 godina** u v1 (dob za privolu u HR); član se smije voditi bez računa |
| Kamera veza | **da, ako ga nositelj ovlasti** (`can_access`), po `erp_spec` §1.25, odlučeno |
| Kad ugovor istekne | članstvo ostaje, ali **prava** (NFC, kamera, vrata) traže važeći ugovor, kao kod nositelja; ništa ne treba čistiti ručno |
| GDPR rok | O67: podaci člana brišu se **90 dana nakon uklanjanja** iz organizacije; račun ostaje ako je član i drugdje |

**3.2 Kupčevo čitanje prije CRM-a (M17)** — PRIHVAĆAM DJELOMIČNO. Prije CRM-a ERP nema podatak koji
bi ovo nosio:
- **Prije M2 ne postoji veza kupac → vez.** Ugovora za vez nema (CRM, v3 M2), a vlasnika
  plovila u pravoj marini ERP po P-5 ne smije upisati.
- Vlasnik je za kameru već odlučio isto (`erp_spec` §1.31: kupci ne gledaju prije CRM ugovora).
- Zato M17 dolazi u tri koraka:

| Ruta | Kada | Izvor |
|---|---|---|
| `…/me/credit`, `…/me/sessions?from&to`, `…/me/consumption` (obračunski zapisi, ne računi), procjena troška iz tarife | **s fazom 7** (NFC tok) | `credit_ledger`, `sessions`, `billing_records`, `tariffs` |
| `…/me/vessel`, `…/me/berth`, `…/me/contract` (+PDF) | **s M2** (CRM ugovori) | `contracts`, `vessels` |
| `…/me/invoices` (+PDF) | **s M5** (ERP izdaje eRačun) | izdani računi |

Do M5 račune izdaje blagajna recepcije (`erp_spec` §1.0, 1.4). „Računi" u aplikaciji prije M5 bili
bi izmišljeni dokumenti. Trojka T-13, §2.

**3.3 `features[]`** — PRIHVAĆAM. `features[]` je **jedini** mehanizam uključivanja modula po
marini. Ključevi za v1:
- `nfc_charging` — NFC punjenje kupca (faza 7);
- `camera_live` — D32; za osoblje od L1, za kupce po kameri (`erp_spec` §1.25);
- `customer_accounts` — prijava kupca (M9);
- `customer_signup` — samoregistracija uz odobrenje marine (M10);
- `organization` — članovi (M18);
- `payments` — Stripe (M14).

Kasnije, s v3: `services`, `bookings`, `access`, `chat`, `work_orders`. Nepoznat ključ mobilna
ignorira. Trojka T-14, §2.

**3.4 Plaćanje: Stripe** — ODLUKA VLASNIKA, ugrađuje se s M14.
- PaymentIntent se stvara na ERP-u, a aplikacija dobiva samo `client_secret` (PaymentSheet).
- Potvrda plaćanja dolazi **Stripe webhookom** na ERP. To je javna ruta
  `POST /api/webhooks/stripe`, s provjerom potpisa (`Stripe-Signature`), kao jedina iznimka uz
  mobilni prefiks u tunelu (1.1). Uplata postaje redak u knjizi kredita (`credit_ledger`) ili u
  `payments` (v3 §14.3.1), nikad izmjena salda.
- **Mijenja:**
  - `erp_spec` §4.5: „Kartično plaćanje u aplikaciji nije u izvedbi" postaje „s M14, Stripe";
    `reason='topup_card'` je već predviđen;
  - §12.

### 4. Domena, email, build

**4.1 `lika.digital` i `api.lika.digital`** — ODLUKA VLASNIKA, ugrađuje se.
- `PUBLIC_APP_BASE_URL=https://lika.digital` je nova postavka u `/etc/erp-iot/erp-iot.env`.
  Postojeći `PUBLIC_BASE_URL` ostaje za ERP web (Tailscale).
- Putanje su prihvaćene: `/marina/<public_code>` *(ispravljeno u v2, H-11)*, `/invite`, `/reset`, `/verify`, `/setup`.
- **Svaki jednokratni token ide u fragment** (`#token=…`), nikad u query.
- **Mijenja:** §8.3 (env), §8.4 (5c: `api.lika.digital` → tunel → nginx → samo prefiks).

**4.2 E-mail preko Google Workspace SMTP relaya** — ODLUKA VLASNIKA, ugrađuje se kao **M20**.
- Servis za slanje je `app/services/mail.py`, **izvan** `app/agent/`. TC-ERP-AGT-03 zabranjuje
  `smtplib` samo u agentu (D21) i ostaje nepromijenjen.
- Izlaz je `smtp-relay.gmail.com:587`, uz STARTTLS (obavezan; bez TLS-a nema slanja).
- **Prijedlog za autentikaciju relaya:** SMTP AUTH (lozinka aplikacije u systemd credentials,
  kao `jwt_secret`) **i** dopuštena izlazna IP adresa VPS-a u Workspace adminu. VPS ima stalnu
  javnu adresu (178.218.168.17), pa je IP ograničenje besplatan drugi zid.
- SPF, DKIM i DMARC za `lika.digital` su DNS posao vlasnika domene.
- Predlošci su na engleskom: pozivnica (kupac, član), verifikacija, reset.
- Ograničenje: najviše 5 poruka po primatelju na sat.
- Audit bilježi vrstu, primatelja (hash) i vrijeme, bez sadržaja.
- **Mijenja:**
  - §8.3: nova tajna `smtp_password`;
  - §7.1: izlaz 587 u vatrozidu VPS-a (5b korak 3 danas filtrira samo ulaz);
  - novi zahtjev M20.

**4.3 Zajednički `tokens.json` (M22)** — PRIHVAĆAM.
- Izvor je `frontend/src/theme/tokens.json`.
- `tokens.css` se generira skriptom u buildu, a CI provjerava da je generirani `tokens.css`
  jednak praćenom.
- Putanja je stabilna od M22. Do tada vrijedi `frontend/src/theme/tokens.css`.

### 5. Live kamera (D32, M16)

D32 je odlučen. `erp_spec` v28–v29, §14.8 i §1.25–§1.31, sve **odlučeno 2026-10-16**.

**5.1 D32 nije u ERP specu, test D30 ga zabranjuje** — **ZATVORENO u v28.**
- D32 je u §14.8.
- Test D30 (`tests/test_d30.py`) se sužava na analizu i slike. Jedini dopušteni kamerni pozivi
  su `camera.live_*`, samo iz modula D32.
- M16 je faza **L1** (osoblje) i **L2** (kupci) u §10.16.

**5.2 Jedna kamera po ormaru** — **ODLUČENO (vlasnik, 2026-10-16), nije više otvoreno.**
- Jedna kamera po ormaru, **bez rezanja**. Slika pokazuje sve vezove ormara.
- Pravo kupca: „kupac s važećim ugovorom za vez koji služi ovaj ormar", i dok na njegovu vezu
  nije tuđe plovilo (signal NIJE KRIVO).
- Kupcu se to kaže rečenicom prije pokretanja i trajno na slici (§4.1, polje `notice`).
- Gledanje kupaca se uključuje **po kameri**, kad postoji maska (R37) i DPIA marine.
- Opcije (a) i (b) otpadaju; (c) ostaje kao maska.

**5.3 Stream na ormaru je danas bez autentikacije** — TREBA ORMAR.
- Put je odlučen: ERP kao `api_client` zove `camera.live_start/keepalive/stop/status`, a lista i
  segmenti traže token.
- Na ormaru (`origin/main` `5ec542e`) to još ne postoji. Popis je u §5, točke 1–3, uključujući
  zatvaranje starog `GET /api/camera/{id}/stream` bez autentikacije.

**5.4 Zaštita od snimke zaslona** — PRIHVAĆAM tekst, uz prijedlog za audit:
- Android: `FLAG_SECURE` na zaslonu prijenosa (blokira snimku i snimanje zaslona).
- iOS: snimka zaslona se **ne može spriječiti**. Za vrijeme snimanja zaslona sadržaj se
  prekriva.
- **Prijedlog:** otkrivena snimka (iOS) ili pokušaj (Android, ako se dozna) šalje se ERP-u
  (§4.3) i upisuje u dnevnik gledanja. Ne prekida gledanje i nema posljedica. Trojka T-20, §2.

**5.5 Format i API** — PRIHVAĆAM, uz dvije izmjene prema odlukama:
1. **HLS, ne LL-HLS:** vlasnik je odlučio HLS s 8–12 s do mobitela i bez nižeg kašnjenja bez
   njegove odluke. `expo-video` pušta HLS bez nativnog modula.
2. **Nema 409 „viewer limit":** jedan stream s ormara, koliko god ljudi gledalo (ERP povlači
   svaki segment jednom). Granica je **kvota prometa po marini** (§1.30), 429 `quota`.

Točan oblik je u §4.

### 6. Ostalo

**6.1 Ulazni dokumenti u gitu** — PRIHVAĆAM, izvedeno.
- `moduli_v3_ulaz.md` i `.docx`, `mobilna_zahtjevi_iz_ERP.md`, `odgovor_mobilne_v1.md` i ovaj
  dokument su u `docs/inputs/` na grani `spec/v3-moduli`.
- Na `main` idu kad vlasnik prihvati spec v3.

**6.2 Ugovor za mock** — PRIHVAĆAM.
- Oblici M2, M4, M5, M19 i kamere su u §3 i §4 ovog dokumenta.
- Nakon odobrenja ulaze u `erp_spec` kao **§14.9 Mobilni API**, od tada s brojem verzije ugovora.
- Do tada mobilna ih mockira ovako i označava `contract: proposed`.

**6.3 Rotacija `ERP_API_KEY` i gašenje customer ruta** — TREBA ORMAR (§5, točke 4–5).
- Na strani ERP-a: novi ključ živi samo u `cabinets.erp_api_key_enc` (šifrirano, D20 t. 5) i
  nikad se ne vraća u odgovoru.

**6.4 Radni nalozi (M13)** — PRIHVAĆAM kao informaciju za v3 M4.
- `client_op_id` (idempotentnost: isti ID dvaput = jedna promjena) i `version` (optimistično
  zaključavanje: zastarjela verzija → 409 s trenutnim stanjem) ulaze u model naloga
  (v3 §14.4.1).
- GPS se briše na uređaju (odluka). **ERP i sam uklanja EXIF s primljene fotografije**, istom
  funkcijom kao za referentne slike (`app/services/reference_photo.py`). Dva zida, ne jedan.

**6.5 Prihvaćeno bez komentara** — potvrđujem: M2, M3, M6, M7 (uz 1.1), M8, M12, M14 (uz 3.4), M15,
te ulaz §0, §3.3, §4.1, §4.2, §5, §6. Oblici M7 (overview, berths) dolaze u §14.9. Polje
`camera` iz §4.4 je već ovdje.

---

## 2. Izmjene `erp_spec.md` — trojke (polazište: tablica §8 ulaza)

Redak je izmjena iz tablice §8 ulaza.
- **ODLUKA** znači da je vlasnik odlučio i da se samo upisuje.
- **TROJKA** znači da je prijedlog ERP-a i čeka odobrenje.

| # | Izmjena | Vrsta | Gdje u `erp_spec.md` |
|---|---|---|---|
| 1 | M19 `/api/mobile/v1`, tunel samo za prefiks | ODLUKA (+ T-1 za način) | §8.4 5c, §7.1, novi §14.9 |
| 2 | `kind = staff \| customer` | ODLUKA | §4.9, §14.9 |
| 3 | M21 `permissions[]` | TROJKA T-3 | §14.1.3, §14.9 |
| 4 | `customer_accounts`, `customer_members`, token bez marine | ODLUKA (+ T-4 za spajanje s CRM-om) | §14.1.2, §14.3.1 |
| 5 | Odvojene prijave | ODLUKA (§1.29) | §14.9 |
| 6 | `refresh_tokens`, trajanja, opoziv | ODLUKA (+ T-6 za tri dopune) | §4.9, §7.1 |
| 7 | 2FA na mobitelu bez `qr_svg` | ODLUKA | §4.9 |
| 8 | M23 setup link od Ownera | TROJKA T-8 | §14.1.3 |
| 9 | §5.1 korak 2 | ODLUKA (tekst T-9) | §5.1 |
| 10 | Pravilo zaustavljanja, `can_stop` | TROJKA T-10 | §5.1, §5.4 |
| 11 | Normalizacija UID-a | **već izvedeno** (`nfc_uid.py`) | §4.4, samo referenca |
| 12 | M18 organizacija | ODLUKA + TROJKA T-12 (pravila) | §14.3.1 |
| 13 | M17 u tri koraka | TROJKA T-13 | §14.9 |
| 14 | `features[]` | TROJKA T-14 | §14.9 |
| 15 | Stripe | ODLUKA | §4.5, §12 |
| 16 | `lika.digital`, `PUBLIC_APP_BASE_URL` | ODLUKA | §8.3, §8.4 |
| 17 | M20 e-mail | ODLUKA (+ T-17 za autentikaciju relaya) | §8.3, §7.1 |
| 18 | M22 `tokens.json` | TROJKA T-18 | §6.0 |
| 19 | D32, test D30, M16 | **već u v28–v29** | §14.8 |
| 20 | Snimka zaslona | TROJKA T-20 | §14.8.4 |
| 21 | Ulazi u gitu | izvedeno | — |
| 22 | Oblici M2, M4, M5, M19 | TROJKA T-22 | §14.9 |

**T-1 · Način fasade**
> **Odlučeno (prijedlog)** · `/api/mobile/v1` je tanak router nad istim servisima. Ne kopira
> pravila, ne zove web rute preko HTTP-a. Ima **vlastite oblike odgovora** (§3.1), a nginx ispred
> tunela propušta samo prefiks.
>
> **Zašto** · Pravilo koje postoji na dva mjesta razići će se. Vlastiti oblici znače da web smije
> mijenjati svoje odgovore bez nove verzije aplikacije u trgovinama.
>
> **Ako griješim** · Fasada je sloj serijalizacije. Ako se pokaže suvišnom, rute web i mobilne
> spajaju se bez promjene servisa.

**T-3 · `permissions[]` (v3)**
> **Odlučeno (prijedlog)** · U v3 `/me` vraća `permissions[]` generiran iz iste tablice kao
> serverska provjera (§14.1.3). U v1 ga nema.
>
> **Zašto** · Nova uloga ne smije tražiti novu verziju aplikacije. Jedna tablica za klijenta i
> server ne može se razići.
>
> **Ako griješim** · Polje se dodaje; nepoznata polja se ignoriraju (§3.1).

**T-4 · Jedna tablica članova**
> **Odlučeno (prijedlog)** · Mobilni `customer_members` i CRM-ova „Organizacija" (v3 §14.3.1) su
> **ista tablica**, s `account_id NULL` za člana bez prijave.
>
> **Zašto** · Dvije tablice za iste ljude dale bi dva popisa posade, a O67 bi morao brisati na
> dva mjesta.
>
> **Ako griješim** · Pogled po vrsti člana je jedan `WHERE`.

**T-6 · Tri dopune trajanja**
> **Odlučeno (prijedlog)** · Refresh token se sprema kao sha256 i vezan je uz `device_id`;
> obitelj osoblja ima **apsolutni** rok 12 h; ugašen račun prestaje odmah, jer se stanje računa
> provjerava na svakom zahtjevu.
>
> **Zašto** · Ukraden zapis baze ne smije biti upotrebljiv token. Klizni rok od 12 h bez
> apsolutne granice nikad ne bi tražio TOTP.
>
> **Ako griješim** · Svaka dopuna je jedan stupac ili jedna usporedba.

**T-8 · M23**
> **Odlučeno (prijedlog)** · Setup link osoblju izdaje Admin, a od v3 M0 i Owner za svoju marinu.
> Link vodi na `lika.digital/setup#token=…`.
>
> **Zašto** · Owner stvara korisnike svoje marine (v3 §14.1.3). Fragment drži token izvan logova.
>
> **Ako griješim** · Pravo je redak matrice.

**T-9 · §5.1 korak 2 (tekst odluke)**
```
2  app → ERP  POST /api/mobile/v1/marinas/{marina_id}/nfc/scan {tag_uid}
              Authorization: Bearer <access token kupca, scope=customer>
              identitet = račun iz tokena; tijelo NE nosi ID kupca ni korisnika.
              ERP odbija ako marina taga ≠ {marina_id} ili račun nije aktivan član te marine.
```
> **Zašto** · ID u tijelu klijent može podmetnuti. Upravo to je bila rupa starog toka ormara.
>
> **Ako griješim** · Nema verzije ovoga koju bih izveo drukčije.

**T-10 · Zaustavljanje** — pravilo iz točke 2.2.
> **Zašto** · Kupac plaća svoju sesiju, a nositelj odgovara za članove. Osoblje ima vlastiti put
> s razlogom i auditom (§5.3).
>
> **Ako griješim** · `can_stop` računa jedna funkcija.

**T-12 · Pravila organizacije** — tablica iz točke 3.1.
> **Zašto** · Nositelj plaća i odgovara. Član vidi samo svoje (D15). Dob 16 je granica privole u
> HR. Prava slijede ugovor, pa istek ne traži ručno čišćenje.
>
> **Ako griješim** · Svako pravilo je provjera u jednoj funkciji.

**T-13 · M17 u tri koraka** — tablica iz točke 3.2.
> **Zašto** · Prije CRM-a ERP nema vezu kupac → vez, a prije M5 ne izdaje račune. Ruta koja to
> pokazuje izmislila bi podatak.
>
> **Ako griješim** · Rute se dodaju, a oblici ostaju.

**T-14 · `features[]`** — popis iz točke 3.3, i jedini mehanizam.
> **Zašto** · Jedan prekidač po modulu i marini, vidljiv i serveru i aplikaciji.
>
> **Ako griješim** · Ključ više u popisu.

**T-17 · Relaj: SMTP AUTH i IP ograničenje, oboje.**
> **Zašto** · Lozinka u credentials može procuriti, a stalna IP adresa VPS-a ne može se ukrasti.
>
> **Ako griješim** · Jedna postavka u Workspace adminu.

**T-18 · `tokens.json` je izvor**, a CI provjerava da je generirani CSS jednak praćenom.
> **Zašto** · Dvije kopije boja razilaze se tiho.
>
> **Ako griješim** · Generator je jedna skripta.

**T-20 · Snimka zaslona u dnevniku gledanja** — točka 5.4.
> **Zašto** · Owner vidi je li netko snimao susjedne vezove (D15). Prekid gledanja bio bi kazna za
> nešto što iOS ne može spriječiti.
>
> **Ako griješim** · Događaj se prestaje upisivati; ruta ostaje i vraća 204.

**T-22 · Oblici iz §3 i §4 postaju §14.9.**
> **Zašto** · Mock po ugovoru vrijedi samo ako je ugovor jedan i zapisan.
>
> **Ako griješim** · Svaka promjena oblika prije isporuke ide kroz §0.0 i javlja se mobilnoj.

---

## 3. Ugovor: M19, M2, M4, M5 (`contract: proposed`)

### 3.1 M19 — pravila cijelog prefiksa

| Pravilo | Vrijednost |
|---|---|
| Baza | `https://api.lika.digital/api/mobile/v1`; u razvoju `http://<erp>/api/mobile/v1` |
| Verzija | `v1` mijenja se **samo dodavanjem** (novo polje, nova ruta, novi ključ greške). Uklanjanje ili promjena značenja = `v2`, a `v1` živi još **90 dana** uz zaglavlje `Deprecation` |
| Zaglavlja (svaki zahtjev) | `X-Client: marina-mobile/<semver> (<ios\|android>)`; `X-Device-Id: <UUID v4, stalan po instalaciji>`. Nedostaje → **400** `client_headers_missing` |
| Prijava | `Authorization: Bearer <access_token>` |
| Format | JSON, UTF-8. Vrijeme je ISO 8601 UTC s `Z` (`2026-10-16T21:05:00Z`). Novac je **string** s dvije decimale + `currency` (`"12.40"`, `"EUR"`). `null` = nije izmjereno ili nepoznato, nikad 0 (`erp_spec` §0.6) |
| Nepoznata polja | klijent ih **ignorira**; server odbija nepoznata polja u tijelu (**422**) |
| Stranice | `?limit=1..100` (zadano 50) i `&cursor=<neprozirni niz>`; odgovor `{"items": [...], "next_cursor": "..."\|null}` |
| Greška (uvijek isti oblik) | `{"error": {"code": "<stabilni_ključ>", "message": "<rečenica za čovjeka, engleski>", "retry_after_s": <int, samo kod 429/503>}}`. Klijent prikazuje `message`, a odlučuje po `code` |
| Opće greške | **400** `client_headers_missing` · **401** `token_missing` / `token_invalid` / `token_expired` („Your session has expired. Please sign in again.") · **403** `wrong_account_kind` („This account cannot use this part of the app.") · **403** `marina_forbidden` („You don't have access to this marina.") · **404** `not_found` („Not found.") · **422** `invalid_request` („Some information is missing or not valid.") + `fields: {"<polje>": "<razlog>"}` · **429** `rate_limited` („Too many attempts. Please wait a moment and try again.") + `Retry-After` · **500** `internal` („Something went wrong on our side. Please try again.") · **503** `maintenance` |
| Rate limit (M3) | javni lookup 10/min i 100/h po IP-u; prijave 5/min po IP-u i po e-mailu (uz zaključavanje D20: 5 neuspjeha = 15 min); refresh 30/h po uređaju; ostalo 120/min po računu |
| Audit (M15) | `X-Client` i `X-Device-Id` idu u `auth_audit` i `audit_log` |
| Izvan prefiksa | tunel / nginx: **404 bez tijela** |

### 3.2 M2 — javni lookup marine

Model: `marinas.public_code TEXT UNIQUE NOT NULL`, 6 znakova iz `ABCDEFGHJKMNPQRSTUVWXYZ23456789`
(bez 0/O, 1/I/L). Generira se slučajno pri stvaranju marine, a Admin ga može zamijeniti (stari
prestaje vrijediti). Na QR-u u marini je `https://lika.digital/marina/<public_code>` *(ispravljeno u v2, H-11 — odluka vlasnika)*.

```
GET /api/mobile/v1/public/marinas/{public_code}
    bez prijave; zaglavlja X-Client i X-Device-Id obavezna; public_code neovisan o velikim/malim slovima

200 {
  "public_code": "K7RM2Q",
  "name": "Marina Primjer",
  "logo_url": "https://api.lika.digital/api/mobile/v1/public/marinas/K7RM2Q/logo" | null,
  "timezone": "Europe/Zagreb",
  "features": ["nfc_charging", "camera_live"],
  "sign_in": { "staff": true, "customer": true, "customer_signup": false }
}

GET /api/mobile/v1/public/marinas/{public_code}/logo   → 200 image/png ili image/svg+xml; 404 not_found

404 marina_not_found   "We couldn't find a marina with this code. Check the code on the sign at the marina."
                       (isti odgovor za nepostojeću, neaktivnu i demo marinu — ne odaje postojanje)
429 rate_limited
```

Ne vraća nikad: ID marine, adrese ormara, kontakte, broj vezova ni ništa iz `marinas` osim
gornjeg. `marina_id` aplikacija dobiva tek prijavom (`/me`).

### 3.3 M5 — `/me`

```
GET /api/mobile/v1/auth/me                          Authorization: Bearer <access>

200 (osoblje)
{
  "kind": "staff",
  "id": 12,
  "email": "manager@example.test",
  "full_name": "Test Manager" | null,
  "role": "admin" | "marina_manager",
  "marina_ids": [1, 3],                      // admin: [] — popis marina dolazi iz /marinas
  "mfa_enrolled": true
}

200 (kupac)
{
  "kind": "customer",
  "account_id": 501,
  "email": "guest@example.test",
  "email_verified": true,
  "memberships": [
    { "marina_id": 1, "marina_name": "Marina Primjer", "customer_id": 44,
      "member_role": "holder" | "member",
      "status": "active" | "invited" | "removed" }
  ]
}

401 token_missing | token_invalid | token_expired
```

`role` dobiva nove vrijednosti s v3 (§1.2). Nepoznata uloga znači najmanja prava.

### 3.4 Prijava (potrebna za M4)

```
POST /api/mobile/v1/auth/staff/login
     { "email": "...", "password": "..." }
200  { "mfa_token": "<5 min>", "mfa_enrolled": true | false }
401  bad_login   "Email or password is incorrect."
                 (ISTI odgovor za nepoznat e-mail, krivu lozinku, ugašen i zaključan račun — O14)
429  rate_limited

POST /api/mobile/v1/auth/staff/mfa/verify
     { "mfa_token": "...", "code": "123456" }       // ili rezervni kod
200  <TokenPair, kind "staff">
401  bad_code          "That code didn't work. Check the time on your phone and try again."
401  mfa_token_expired "Sign-in took too long. Please start again."
409  mfa_not_enrolled  "Two-factor authentication is not set up yet."

POST /api/mobile/v1/auth/staff/mfa/enroll/start
     { "mfa_token": "..." }
200  { "secret": "BASE32...", "otpauth_uri": "otpauth://totp/Lika:...?secret=...&issuer=Lika" }
409  mfa_already_enrolled "Two-factor authentication is already set up."

POST /api/mobile/v1/auth/staff/mfa/enroll/confirm
     { "mfa_token": "...", "code": "123456" }
200  <TokenPair, kind "staff"> + "backup_codes": ["xxxx-xxxx", ...]   // prikazani JEDNOM
401  bad_code

POST /api/mobile/v1/auth/customer/login
     { "email": "...", "password": "..." }
200  <TokenPair, kind "customer">
401  bad_login                (isti tekst kao kod osoblja)
403  email_not_verified "Please confirm your email address first. We've sent you a new link."
429  rate_limited
```

### 3.5 M4 — tokeni, refresh, odjava

```
TokenPair
{
  "kind": "staff" | "customer",
  "token_type": "bearer",
  "access_token": "<JWT>",
  "access_expires_in": 900,                          // s
  "refresh_token": "<neprozirni niz, 256 bita>",
  "refresh_expires_at": "2026-10-17T09:05:00Z"       // osoblje: prijava + 12 h (apsolutno)
                                                     // kupac:   izdavanje + 30 d (klizno)
}

Access JWT (informativno; klijent ga ne parsira): sub, kind, scope ("staff"|"customer"),
dev (hash X-Device-Id), iat, exp, jti

POST /api/mobile/v1/auth/refresh
     { "refresh_token": "..." }                     // X-Device-Id mora biti isti kao pri prijavi
200  <TokenPair>                                     // NOVI refresh; stari prestaje vrijediti
401  session_ended "Your session has ended. Please sign in again."
     — za istekao, opozvan, nepoznat, tuđi uređaj ili VEĆ ISKORIŠTEN token.
       Već iskorišten = opoziva se CIJELA obitelj (krađa); razlog ide samo u auth_audit.
429  rate_limited

POST /api/mobile/v1/auth/logout
     { "refresh_token": "..." }                     // Bearer access također obavezan
204  — opozvani su SVI refresh tokeni tog računa, na svim uređajima (odluka vlasnika 1.6)
401  token_invalid
```

Model:

```
refresh_tokens (platforma)
  id, account_kind ('staff'|'customer'), account_id, device_id_hash,
  family_id, token_sha256 UNIQUE, issued_at, expires_at, family_expires_at NULL,
  used_at NULL, revoked_at NULL, revoke_reason NULL, replaced_by NULL
```

Promjena lozinke opoziva sve tokene računa, kao i odjava. Zaključavanje nakon 5 min neaktivnosti
(biometrija ili PIN) radi aplikacija i ne zove server. Nakon 12 h osoblje se prijavljuje ponovno, s
TOTP-om.

---

## 4. Ugovor: kamera (D32, M16) — usklađeno s `erp_spec` v29 §14.8 (`contract: proposed`)

Pravila koja ovaj ugovor nosi, sva odlučena:
- jedna kamera po ormaru, slika pokazuje sve njegove vezove;
- ERP je jedini potrošač slike s ormara i svaki segment povlači jednom;
- HLS, 8–12 s;
- osoblje (Owner, Manager, Glavni mornar, Recepcija) do 10 min; Admin samo s razlogom;
- kupac: važeći ugovor za vez tog ormara, a na njegovu vezu nije tuđe plovilo; 3 min; tek s CRM
  ugovorom i kad marina uključi kameru za kupce;
- dnevnik gledanja 12 mj., bez slike.

### 4.1 Početak gledanja

```
POST /api/mobile/v1/marinas/{marina_id}/camera/sessions
     Authorization: Bearer <access, staff ili customer>
     { "berth_id": 123 }            // kupac: SAMO berth_id (svoj vez)
  ILI{ "cabinet_id": 7 }            // osoblje: berth_id ili cabinet_id, točno jedno
     + "admin_reason": "Storm check, berth row A"   // OBAVEZNO za ulogu admin (≥ 3 znaka)

201
{
  "session_id": "cv_9f3c2a7b",
  "state": "starting" | "live",
  "play_url": "https://api.lika.digital/api/mobile/v1/live/<view_token>/index.m3u8",
  "expires_at": "2026-10-16T21:13:00Z",       // kraj ovog gledanja (3 min kupac, ≤ 10 min osoblje)
  "max_seconds": 180 | 600,
  "cabinet_label": "A-03",
  "berths_shown": ["A-09", "A-10", "A-11", "A-12"],
  "your_berth": "A-11" | null,                // null za osoblje
  "notice": "Camera of pedestal A-03 — you see all its berths (A-09 to A-12), not only yours. Please respect your neighbours' privacy.",
  "delay_note": "Live · about 10 s delay",
  "status_poll_s": 5
}
```

- `play_url` nosi **jednokratni token gledanja u putanji**: vezan uz sesiju, uređaj i kameru,
  vrijedi do `expires_at`.
- Osoblje dobiva `notice` bez rečenice o privatnosti: „Camera of pedestal A-03 — berths A-09 to
  A-12."
- Ako su vezovi ormara razbacani, rečenica ih nabraja.

| Kod | `error.code` | `error.message` |
|---|---|---|
| 400 | `berth_or_cabinet_required` | „Choose a berth or a pedestal." |
| 403 | `role_not_allowed` | „Your role does not include live camera view." |
| 403 | `admin_reason_required` | „Admin mode: give a reason to watch this marina's cameras." |
| 403 | `no_right` | „You can watch this berth while your contract for it is valid." |
| 403 | `customer_not_enabled` | „Live view for guests is not enabled for this pedestal yet." |
| 403 | `other_vessel` | „Another vessel is at your berth — live view is not available." |
| 403 | `feature_off` | „Live camera is not available in this marina." |
| 404 | `camera_not_found` | „This pedestal has no camera." |
| 409 | `restart_not_yet` | „The camera needs a moment before it can start again." + `retry_after_s` *(samo ako ormar uvede pauzu nakon 10 min — R35 pitanje 4)* |
| 429 | `quota` | „This month's live-view limit for the marina has been reached." |
| 503 | `cabinet_unreachable` | „The pedestal is not responding. Try again later." + `retry_after_s` |
| 503 | `camera_unreachable` | „The camera is not responding." + `retry_after_s` |
| 503 | `not_enabled` | „Live view is not enabled on this pedestal." |

### 4.2 Stanje i kraj

```
GET /api/mobile/v1/marinas/{marina_id}/camera/sessions/{session_id}
200
{
  "session_id": "cv_9f3c2a7b",
  "state": "starting" | "live" | "ended",
  "seconds_left": 142 | null,
  "end_reason": null | "viewer_closed" | "limit_customer_3min" | "limit_cabinet_10min"
              | "cabinet_unreachable" | "camera_unreachable" | "cabinet_stopped"
              | "other_vessel" | "right_ended" | "quota",
  "message": "Starting the stream — this takes a few seconds." | null
}
404 not_found                       // nije sesija ovog računa

DELETE /api/mobile/v1/marinas/{marina_id}/camera/sessions/{session_id}
204                                 // idempotentno: 204 i ako je sesija već završila
404 not_found
```

**Pravilo za aplikaciju, da ekran nikad nije prazan bez objašnjenja:**
- dok je `state = "starting"`, prikazuje `message` i pita stanje svakih `status_poll_s`;
- kad player javi grešku ili stoji dulje od 15 s, pita stanje i prikazuje `message`;
- za `ended` uvijek postoji `message`.

| `end_reason` / stanje | `message` |
|---|---|
| `starting` | „Starting the stream — this takes a few seconds." |
| `limit_customer_3min` | „Viewing ends after 3 minutes — tap to watch again." |
| `limit_cabinet_10min` | „The 10-minute limit was reached — tap to watch again." |
| `cabinet_unreachable` | „The pedestal is not responding. Try again later." |
| `camera_unreachable` | „The camera is not responding." |
| `cabinet_stopped` | „The pedestal stopped the stream. Tap to try again." |
| `other_vessel` | „Another vessel is at your berth — live view is not available." |
| `right_ended` | „Your access to this berth has ended." |
| `quota` | „This month's live-view limit for the marina has been reached." |
| `viewer_closed` | „Live view closed." |

**HLS rute** (poziva ih player, ne kod aplikacije):

```
GET /api/mobile/v1/live/{view_token}/index.m3u8    → 200 application/vnd.apple.mpegurl
GET /api/mobile/v1/live/{view_token}/seg/{n}.ts    → 200 video/mp2t
410 (bez tijela)  kad je sesija završila — aplikacija tada zove GET stanja
```

- Bez `Authorization`: token je u putanji. nginx za `/live/` **ne logira putanju**.
- Lista je prepisana: sadrži samo ERP-ove putanje, **nikad adresu ormara**.
- Gledatelj je živ dok player dohvaća listu, pa aplikacija ne šalje zaseban heartbeat.

### 4.3 Snimka zaslona (prijedlog T-20)

```
POST /api/mobile/v1/marinas/{marina_id}/camera/sessions/{session_id}/events
     { "type": "screen_capture_detected" | "screen_recording_started" }
204  — upisano u dnevnik gledanja; gledanje se NE prekida
```

### 4.4 Status kamere u odgovorima overview i berths (M7)

Svaki vez u `overview` i `berths` dobiva polje `camera`. Računa ga server **za tog gledatelja**.

```
"camera": {
  "status": "available" | "unavailable" | "none",
  "can_view": true | false,
  "reason": null | "cabinet_unreachable" | "camera_unreachable" | "not_enabled"
          | "customer_not_enabled" | "no_right" | "other_vessel" | "quota" | "role_not_allowed",
  "message": null | "<rečenica iz tablice 4.1>",
  "cabinet_id": 7,
  "cabinet_label": "A-03",
  "sim": false
}
```

- `none`: ormar tog veza nema kameru, pa aplikacija **ne crta ikonu**.
- `available` + `can_view: true`: zelena ikona.
- Sve ostalo: siva ikona i `message`.
- Svi vezovi istog ormara imaju istu kameru.
- `sim: true` (demo marina, D28): sintetički prijenos, uz oznaku „SIM".

---

## 5. Za chat ormara (polazište §7 ulaza)

Stanje ormara provjereno 2026-10-16 na `Cloud_IOT` `origin/main` `5ec542e`.

1. **`camera.live_*` (R35)** — `live_start`, `live_keepalive`, `live_stop`, `live_status` na
   `/api/ext/*`, token `api_client`; lista i segmenti traže isti token. **Danas ne postoji**, a
   katalog odbija sve kamerne rute (`PHASE1_NO_IMAGES_TO_ERP = True`, `api_catalog.py`). ERP
   treba potvrdu ovih osam stvari:
   1. putanje, metode, tijela; monitor ili bidirectional; traži li išta Smart Mode ON;
   2. `live_start` vraća **relativnu** putanju liste; je li ponovni start idempotentan;
   3. stabilni ključevi stanja u `live_status`;
   4. smije li se nakon 10 min odmah ponovno pokrenuti; koliko kamera istodobno;
   5. trajanje segmenta, dužina liste, kodek, rezolucija, bitrate;
   6. potvrda: jedna kamera po ormaru, slika pokazuje sve njegove vezove;
   7. jesu li maske primijenjene prije nego slika ode ERP-u;
   8. oblik grešaka 409/429/503 kao na ostalim ext rutama.
2. **Maske privatnosti po kameri (R37)**, primijenjene prije slanja, s potvrdom u `live_status`.
   Uvjet za uključenje kupaca.
3. **Stari `GET /api/camera/{id}/stream` i `/snapshot` bez autentikacije** (README: prihvaćeni
   rizik). Kad postoji `camera.live_*`, zatvoriti ih ili staviti iza prijave. Ne smiju biti
   dosežni ni iz tailneta bez tokena.
4. **Rotacija `ERP_API_KEY`** (X-API-Key za `/api/nfc/*`) na svim ormarima: bio je u mobilnom
   bundleu. Novi ključ samo u ERP-u. Potvrda statusa po ormaru.
5. **Gašenje Cloud_IOT customer ruta** (legacy). Mobilna ih ne koristi od F0.
6. **Vrste NFC naljepnica po ormarima:** ISO 15693 ili drugo. U kojem redoslijedu bajtova čitač
   ormara javlja UID (ERP sprema oba, ali treba znati koji je „primarni")?
7. *(niski prioritet, R38)* Zamagljivanje osoba u stvarnom vremenu: izvedivost i CPU NUC-a. Više
   nije uvjet ni za što.

**Povučeno s popisa mobilne** (odlučio vlasnik): izrez po vezu i kamere 1:1 s vezom.
