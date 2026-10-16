# Odgovor mobilne na ERP ulaz v1

| | |
|---|---|
| Od | Marina Mobile (`Lika-Digital/Marina-Mobile`, `docs/mobile_spec.md` v0.3) |
| Za | ERP chat (`Lika-Digital/ERP-IOT`) |
| Na | `mobilna_zahtjevi_iz_ERP.md` v1 (2026-10-16) |
| Datum | 2026-10-16 |
| Status | Komentari i prijedlozi mobilne + odluke vlasnika koje utječu na ERP. **Ništa od prijedloga nije odluka ERP-a** — tražimo: prihvaćaš / ne prihvaćaš / treba ormar, s razlogom. |

Oznake:
- **ODLUKA VLASNIKA** — vlasnik je odlučio 2026-10-16. ERP je ugrađuje ili predlaže izmjenu vlasniku.
- **PRIJEDLOG** — prijedlog mobilne. ERP ga prihvaća, mijenja ili odbija.
- **TREBA ORMAR** — ERP to ne može sam; ide u chat ormara (Cloud_IOT).
- `ERP §x` — `erp-iot-d21/docs/erp_spec.md` v25; `ulaz §x` — `mobilna_zahtjevi_iz_ERP.md`; `v3 §x` — `erp-iot/docs/inputs/moduli_v3_ulaz.md`.

Format svake točke: **Ulaz kaže → Problem → Prijedlog → Što mobilna treba.**

---

## 1. Pristup, identitet i prijava

### 1.1 Javni pristup samo za mobilni prefiks (M1, M19) — ODLUKA VLASNIKA
- **Ulaz kaže:** M1 "Javni HTTPS pristup ERP API-ju (5c, Cloudflare)"; §1 i M5 navode `/api/auth/me`.
- **Problem:** "ERP API" je preširoko. Vlasnik je odlučio da kroz Cloudflare tunel ide **samo `/api/mobile/v1/*`**; admin UI i ostali `/api` ostaju na Tailscaleu. Danas taj prefiks ne postoji.
- **Prijedlog:**
  - **M19** — zaseban, verzioniran router `/api/mobile/v1` (public, auth, staff, customer, nfc, camera, devices) koji poziva iste servise kao web rute, s istim pravilima i auditom;
  - tunel/nginx odbija sve izvan prefiksa (test);
  - M1 i M5 preformulirati na taj prefiks.
- **Mobilna treba:** stabilan, verzioniran ugovor pod `/api/mobile/v1`. Do M19 mobilna u razvoju koristi lokalni ERP i proxy na postojeće `/api/marinas/{id}/…` rute (dev, nikad u bundleu).

### 1.2 `kind` = `staff | customer`; admin je uloga (M5, ulaz §1) — ODLUKA VLASNIKA, ispravak ulaza
- **Ulaz kaže:** M5 "`/api/auth/me` s `kind` (staff/customer/admin)"; §1 tri profila.
- **Problem:** Admin je u ERP-u `users.role = 'admin'` (DB CHECK `admin`/`marina_manager`), ne zaseban tip računa. Treći `kind` bi dupliciralo ulogu.
- **Prijedlog:** `kind ∈ {staff, customer}`; za staff `role ∈ {admin, marina_manager}` (+ buduće uloge iz v3); admin mode je ponašanje uloge `admin`.
- **Mobilna treba:**
  - staff: `GET /api/mobile/v1/auth/me` → `{kind:"staff", role, marina_ids[]}`;
  - customer: `{kind:"customer", account_id, memberships[]}` (vidi 1.4).

### 1.3 `permissions[]` u `/me` (M21) — PRIJEDLOG
- **Ulaz kaže:** zaposlenik vidi "samo ono što mu matrica prava dopušta (spec v3 §1.2)".
- **Problem:** matrica prava i nove uloge (Marina Owner, 9 zaposleničkih) postoje samo u v3 ulazu. Ako mobilna veže ekrane na nazive uloga, svaka nova uloga traži novu verziju aplikacije.
- **Prijedlog:** `/me` vraća `permissions[]` (npr. `overview.read`, `alarms.ack`, `control.command`, `berths.read`, `vessel.owner.read`, `camera.view`, `energy.read`). Mobilna prikazuje ekrane po dozvolama, a server i dalje odbija sve nedopušteno.
- **Mobilna treba:** ništa odmah. **Odluka vlasnika: mobilna v1 radi s ulogama `admin` i `marina_manager`**; `permissions[]` je prijedlog za v3.

### 1.4 Kupac: jedan račun, više marina (M9) — ODLUKA VLASNIKA (= preporuka ERP-a)
- **Ulaz kaže:** §2 preporuka "jedan račun, više marina (`customer_accounts 1:N customers`)".
- **Problem:** treba odrediti kako token nosi marinu.
- **Prijedlog:**
  - token kupca nosi `account_id` i `scope=customer`, **bez fiksne marine**;
  - svaki kupčev endpoint ima `marina_id` u putanji (`/api/mobile/v1/marinas/{id}/me/...`), a server provjerava članstvo računa u toj marini;
  - staff ovisnosti (`get_current_user`, `require_admin`, WS) izričito odbijaju `scope=customer`.
- **Mobilna treba:** `/me.memberships = [{marina_id, customer_id, member_role, status}]`; prebacivanje marine bez nove prijave.

### 1.5 Ista osoba kao zaposlenik i kupac — ODLUKA VLASNIKA
- **Ulaz kaže:** §1 "ODLUKA VLASNIKA. Preporuka: odvojeni računi".
- **Odluka:** dvije prijave, dva profila, odvojeni računi i tokeni.
- **Prijedlog:**
  - odvojeni endpointi `POST /api/mobile/v1/auth/staff/login` (→ MFA) i `POST /api/mobile/v1/auth/customer/login`;
  - isti email smije postojati u obje tablice;
  - refresh tokeni odvojeni po (račun, uređaj).
- **Mobilna treba:** to; app drži do dva profila i prebacuje se između njih.

### 1.6 Trajanja i refresh (M4) — ODLUKA VLASNIKA
- **Ulaz kaže:** "refresh token vezan uz uređaj, rotacija, opoziv, odjava … trajanja predložiti u specu".
- **Odluka:**
  - kupac: access 15 min, rotirajući refresh 30 d;
  - zaposlenik: access 15 min, refresh 12 h; mobilna zaključava nakon 5 min neaktivnosti (biometrija/PIN uređaja); nakon 12 h puna prijava s TOTP-om;
  - odjava i promjena lozinke opozivaju **sve** refresh tokene korisnika.
- **Prijedlog:**
  - tablica `refresh_tokens(id, account_kind, account_id, device_id, family_id, expires_at, revoked_at, replaced_by)`;
  - ponovna uporaba već iskorištenog refresh tokena opoziva cijelu obitelj (detekcija krađe);
  - `POST /auth/refresh {refresh_token, device_id}`, `POST /auth/logout`;
  - zapis u `auth_audit`.
- **Mobilna treba:** to; postojeći `/api/auth/refresh` (samo dok je token valjan) nije dovoljan.

### 1.7 2FA enrolment na mobitelu — ODLUKA VLASNIKA (= preporuka ERP-a)
- **Ulaz kaže:** §2 "preporuka: dopušteno (otpauth link + tajna za kopiranje), uz isti audit kao na webu".
- **Odluka:** dozvoljeno.
- **Prijedlog:**
  - postojeći `mfa/enroll/start` i `enroll/confirm` izložiti pod `/api/mobile/v1/auth/staff/…`;
  - `enroll/start` za mobilni ne mora vraćati `qr_svg` (skeniranje istim telefonom nije moguće); dovoljni su `otpauth_uri` i `secret`;
  - audit bilježi kanal (`X-Client`).
- **Mobilna treba:** to + rezervni kodovi u odgovoru `confirm` (već postoji).

### 1.8 Setup link i zaboravljena lozinka zaposlenika (M23) — PRIJEDLOG
- **Ulaz kaže:** §2 "zaposlenik: novi setup link od Ownera/Admina".
- **Problem:** danas su svi `users.py` endpointi `require_admin`; uloga Owner ne postoji.
- **Prijedlog:** M23 uz uvođenje uloge Owner (v3). Do tada setup link izdaje samo Admin. Setup link na domeni koja podržava universal link (vidi 4.1), da ga mobilna može otvoriti.
- **Mobilna treba:** ekran "Ask your marina administrator for a new setup link"; deep link `…/setup#token=` → ekran postavljanja lozinke.

---

## 2. NFC

### 2.1 Identitet kupca kroz token, ne kroz tijelo (ERP §5.1 korak 2, M11) — ODLUKA VLASNIKA
- **Ulaz kaže:** §3.1 "`POST` na ERP (samo UID, nikad ID kupca s klijenta)". ERP §5.1 korak 2: `app → ERP {nfc_tag_id, user_id}`.
- **Problem:** §5.1 korak 2 i dalje ima `user_id` u tijelu, što se može podmetnuti. Upravo zbog toga je stari Cloud_IOT tok bio ranjiv (`/api/nfc/scan` s klijentskim `user_id`).
- **Odluka:** app šalje **UID taga**; identitet prijavljenog kupca ide **kroz token prijave** (potpisan od ERP-a). ERP iz kombinacije tag (ormar/priključak) + kupac (iz tokena) + ugovor provjerava kredit.
- **Prijedlog izmjene ERP §5.1, korak 2:**
  ```
  2  app → ERP  POST /api/mobile/v1/marinas/{marina_id}/nfc/scan {tag_uid}
                Authorization: Bearer <customer access token>
                identitet = račun iz tokena (scope=customer); tijelo NE nosi ID kupca.
                ERP odbija ako marina taga ≠ {marina_id} ili račun nije član te marine.
  ```
  - Korak 4 (§5.4) dodaje: račun → `customers` (vlastiti ugovor ili ugovor nositelja organizacije, vidi 2.3) → ugovor → prepaid/postpaid.
  - `erp_ref` prema ormaru ostaje kako je.
- **Mobilna treba:**
  - odgovor `{session_id, status:"pending", expires_at, outlet_label, cabinet_label, can_stop}`;
  - rečenica za čovjeka na molu kod odbijanja;
  - `GET …/sessions/active`, `GET …/sessions/{id}` (snaga, kWh, procjena troška), `POST …/sessions/{id}/stop` (ako `can_stop`).

### 2.2 Pravilo zaustavljanja iz aplikacije (K-14) — PRIJEDLOG
- **Ulaz kaže:** "Zaustavljanje iz aplikacije samo ako ERP to dopušta."
- **Problem:** pravilo nije zapisano. Cloud_IOT danas vraća 403 za stop kupca; ERP kanal B ima `/api/nfc/session/{id}/stop`.
- **Prijedlog:** ERP upisuje pravilo u §5 (npr. vlastita aktivna sesija, nositelj i za članove) i vraća `can_stop` po sesiji.
- **Mobilna treba:** `can_stop` u odgovoru sesije.

### 2.3 Članovi organizacije pune istim tokom (M18) — ODLUKA VLASNIKA
- vidi 3.1.

### 2.4 UID na iOS-u i format UID-a (K-22, K-23) — PRIJEDLOG
- **Ulaz kaže:** "telefon pročita UID taga"; ERP §4.4: `uid_primary` i `uid_reversed` s dvotočkama, `tag_standard` zadano `ISO15693`.
- **Problem:**
  1. Na iOS-u UID ISO 15693 naljepnice daje tag-reader tehnologija (Core NFC `NFCISO15693Tag`), ne NDEF sesija; postojeći mobilni kod čita NDEF. Mobilna to provjerava na uređaju (F0).
  2. Telefoni vraćaju UID s različitim separatorima i velikim/malim slovima.
- **Prijedlog:**
  - ERP normalizira na serveru (makni separatore i razmake, velika slova) prije traženja po oba stupca;
  - mobilna šalje sirovi hex;
  - ERP potvrđuje da su sve naljepnice u marinama ISO 15693 (ako postoje druge, trebamo popis tipova).
- **Mobilna treba:** potvrdu formata i tipova naljepnica.

---

## 3. Kupac v1

### 3.1 Organizacija kupca (M18) — ODLUKA VLASNIKA + PRIJEDLOG modela
- **Ulaz kaže:** §3.1 Profil "organizacija (članovi obitelji i posada — dodaje ih vlasnik, uz pristanak i GDPR)"; v3 §2.4 "Vlasnik + Organizacija".
- **Odluka:** članovi imaju **vlastitu prijavu** i pune preko NFC-a **istim tokom** kao kupac (ista osnova — ugovor nositelja — drugo mjesto u UI-ju).
- **Što postoji danas:**
  - ERP kod: ništa (`customers` je ravan; `vessels.owner_name/owner_contact` je tekst).
  - ERP spec v25: ništa (samo skica `access_group_members` za vrata).
  - v3 ulaz: plan u CRM-u.
  - Cloud_IOT: ništa.
- **Prijedlog modela:**
  ```
  customer_accounts (id, email, password_hash, status, email_verified_at, failed_count, locked_until, created_at)
  customers         (postoji: id, marina_id, … — nositelj ugovora po marini)
  customer_members  (customer_id, account_id, member_role holder|member,
                     invited_by, invited_at, consent_at, active, removed_at)
  ```
  Isti model pokriva i 1.4 (jedan račun, više marina).
- **Otvorena pravila (ERP i vlasnik):**
  - vidi li nositelj sesije članova (prijedlog: da) i vidi li član tuđe sesije u organizaciji (prijedlog: ne);
  - ograničenje potrošnje po članu;
  - maloljetni članovi i pristanak;
  - vidi li član kameru veza (prijedlog: da, isti vez);
  - što se događa s članstvom kad ugovor istekne;
  - GDPR rok brisanja (O67).
- **Mobilna treba:**
  - pozivnica člana: `POST …/organization/invites {email}` → email → `accept`;
  - popis i uklanjanje članova; napuštanje organizacije.

### 3.2 Kupčevo čitanje prije CRM-a (M17, K-10) — PRIJEDLOG
- **Ulaz kaže:** §3.1 v1: plovilo, vez, aktivna sesija, povijest, računi (pregled, PDF), procjena troška. M14 (CRM) dolazi "s CRM modulom".
- **Problem:** v1 to traži, a ne postoji M-stavka prije CRM-a. Tablice `contracts`, `credit_ledger`, `tariffs`, `billing_records` postoje bez endpointa.
- **Prijedlog M17:** `GET …/me/vessel`, `…/me/berth` (vez/priključci iz važećeg ugovora), `…/me/credit`, `…/me/contract` (+PDF), `…/me/invoices` (+PDF, kad ERP izdaje), `…/me/sessions?from&to`. Procjenu troška računa ERP iz tarife.
- **Mobilna treba:** to za F3.

### 3.3 Feature flagovi (K-15) — PRIJEDLOG
- **Ulaz kaže:** §2 javni lookup vraća "naziv, logo, značajke i načine prijave".
- **Prijedlog:** `features[]` je **jedini** mehanizam za uključivanje modula po marini (npr. `camera_live`, `chat`, `services`, `bookings`, `access`, `payments`). Ključevi se zapisuju u spec.
- **Mobilna treba:** popis ključeva.

### 3.4 Plaćanje — ODLUKA VLASNIKA
- **Ulaz kaže:** §3.2 "ODLUKA VLASNIKA: koji PSP".
- **Odluka:** **Stripe**, implementacija u F6 (s M14). App nikad ne vidi podatke kartice (Stripe hosted/PaymentSheet, PaymentIntent na ERP-u).

---

## 4. Domena, email, build

### 4.1 Domena `lika.digital` — ODLUKA VLASNIKA
- **Ulaz kaže:** §9/3–5 "domena: ODLUKA VLASNIKA".
- **Odluka:**
  - postojeća web stranica `lika.digital` dobiva zaseban korisnički dio s linkovima za download i datotekama `/.well-known/apple-app-site-association` i `/.well-known/assetlinks.json`;
  - API na poddomeni, prijedlog **`api.lika.digital`** (Cloudflare tunel prema ERP-u, samo `/api/mobile/v1/*`).
- **Prijedlog:**
  - linkovi koje ERP generira (pozivnice, reset, verifikacija, setup) idu na `https://lika.digital/<putanja>` (putanje usklađujemo; prijedlog `/m/<code>`, `/invite`, `/reset`, `/verify`, `/setup`), da ih app hvata universal linkom;
  - bez instalirane aplikacije ista stranica nudi download ili web nastavak (setup zaposlenika može ostati na ERP webu preko Tailscalea).
- **Mobilna treba:** da ERP u emailovima koristi te putanje (konfigurabilan `PUBLIC_APP_BASE_URL`).

### 4.2 Email preko Google Workspace SMTP relaya (M10, M20, K-12) — ODLUKA VLASNIKA
- **Ulaz kaže:** M10 "zaboravljena lozinka (email — treba SMTP)"; §9/15 ODLUKA VLASNIKA.
- **Problem:** ERP danas nema nikakvo slanje emaila (`smtplib` je u `erp_spec.md` samo na popisu zabranjenih importa za D21 agenta, TC-ERP-AGT-03).
- **Odluka:** ERP šalje preko **Google Workspace SMTP relaya** (`smtp-relay.gmail.com`), pošiljatelj **`noreply@lika.digital`**. Bez vlastitog mail servera na VPS-u (isporučivost, port 25, održavanje, VPS bez javnih ulaznih portova).
- **Prijedlog M20:**
  - servis za slanje u ERP-u, odvojen od D21 agenta (ne krši TC-ERP-AGT-03);
  - izlaz na 587 sa STARTTLS;
  - autentifikacija relaya: SMTP AUTH s lozinkom aplikacije, ili dopuštena izlazna IP adresa VPS-a u Workspace adminu;
  - tajne u systemd credentials;
  - za `lika.digital`: SPF, DKIM i DMARC;
  - predlošci na engleskom: pozivnica (kupac, član), verifikacija, reset;
  - ograničenje slanja po primatelju; audit (bez sadržaja).
- **Mobilna treba:** ništa izravno; o tome ovise tokovi pozivnice, registracije i reseta (F3).

### 4.3 Zajednički `tokens.json` (M22) — PRIJEDLOG (prihvaćen u ulazu §9/16)
- **Prijedlog:** `frontend/src/theme/tokens.json` je izvor (boje kao RGB trojke, radijusi, sjena); ERP generira `tokens.css`, mobilna `theme.ts`. Do tada mobilna drži kopiju `tokens.css` i provjerava razliku.
- **Mobilna treba:** stabilnu putanju datoteke.

---

## 5. Live kamera (D32, M16)
**ODLUKA VLASNIKA:** D32 je odlučen i mobilna ga MORA imati. Ne otvara se ponovo. Ispod su tehnička pitanja koja ERP treba uskladiti, dijelom s ormarom.

### 5.1 D32 nije u ERP specu, a test D30 ga zabranjuje (K-1)
- **Ulaz kaže:** načelo 6 "Live prikaz veza je dopušten (D32)".
- **Problem:**
  - `erp_spec.md` v25 §6.12 (D30): "ERP ne zove nijedan kamerni endpoint (test)";
  - `camera.frame_ext` i `camera.stream_ext` su uklonjeni iz ugovora (v21);
  - D32 postoji samo u v3 ulazu §10.
- **Prijedlog:** ERP unosi D32 u spec kao izmjenu D30. D30 ostaje za analizu, a test D30 se sužava na analizu i slike (ne na live relay). Dodaje se M16 kao faza.
- **Mobilna treba:** to prije F2c.

### 5.2 Jedna kamera po ormaru, ne po vezu (K-2) — TREBA ORMAR
- **Ulaz kaže:** "kupac vidi SAMO kameru svog veza".
- **Problem:**
  - Cloud_IOT `docs/ui_v2_spec.md` §5.3: "one camera per pedestal"; ormar pokriva više vezova.
  - Kupac bi vidio susjedne vezove, brodove i ljude.
  - Maska privatnosti na kameri je jedna za sve gledatelje.
- **Prijedlog (za ERP i ormar):**
  - **(a)** kupcu live samo gdje je kamera 1:1 s vezom; ili
  - **(b)** relay radi **izrez po vezu** (zaseban izlaz po vezu, koordinate izreza u ERP-u); ili
  - **(c)** maska na ormaru ili kameri koja ostavlja samo zajedničko područje.
  
  Vlasnik je opseg za kupca ostavio otvorenim dok ERP i ormar ne kažu što je izvedivo.
- **Mobilna treba:** iz `/camera/sessions` odgovora zna samo smije li i što pušta; logika ostaje na serveru.

### 5.3 Stream na ormaru je danas bez autentifikacije (K-3) — TREBA ORMAR
- **Ulaz kaže:** v3 §10.3 "kamera → ormar (nginx :80, ext ključ za stream) → ERP".
- **Problem:** Cloud_IOT README navodi `GET /api/camera/{id}/stream` bez autentifikacije kao prihvaćeni rizik.
- **Prijedlog:** ormar izlaže `camera.stream_ext` (i status kamere) iza ext autentifikacije, dostupno samo preko Tailscalea, i šalje stream samo dok ERP traži.
- **Mobilna treba:** ništa izravno; preduvjet za M16.

### 5.4 Zaštita od snimke zaslona (K-4) — PRIJEDLOG teksta
- **Ulaz kaže:** "bez snimki zaslona gdje platforma to dopušta".
- **Problem:** Android `FLAG_SECURE` blokira snimku i snimanje zaslona. iOS **ne može** blokirati snimku zaslona; može prikriti sadržaj tijekom snimanja ekrana i detektirati snimku.
- **Prijedlog:** upisati točno to u ERP spec. Detektirana snimka na iOS-u može se upisati u audit gledanja (ako ERP to želi).
- **Mobilna treba:** odluku o auditu iOS snimke.

### 5.5 Format prijenosa i API (K-5, M16) — PRIJEDLOG
- **Ulaz kaže:** v3 §10.3 "HLS ili WebRTC", media relay (npr. MediaMTX), N gledatelja, 2–5 min, niža rezolucija.
- **Prijedlog:**
  - **HLS** (LL-HLS ako relay podržava) za v1; mobilna ga pušta s `expo-video` bez novog nativnog modula. WebRTC nije potreban za "pogledaj vez".
  - API:
    ```
    POST   /api/mobile/v1/marinas/{id}/camera/sessions {berth_id | camera_id}
           → {session_id, play_url (potpisan, vezan uz korisnika i kameru), expires_at, max_seconds}
           → 403 not allowed · 409 viewer limit · 503 camera unavailable (rečenica sa servera)
    DELETE /api/mobile/v1/marinas/{id}/camera/sessions/{session_id}
    ```
  - Status kamere (`available | unavailable | none`) dolazi u overview/berths odgovorima (M7) za ikonu na karti.
- **Mobilna treba:** to za F2c.

---

## 6. Ostalo

### 6.1 ERP ulazni dokumenti nisu u gitu (K-20) — PRIJEDLOG
- **Problem:** `erp-iot/docs/inputs` (bare repo) sadrži `moduli_v3_ulaz.md`, `ERP_v3_specifikacija_ulaz.docx` i mobilni ulaz, ali nisu ni u jednom gitu. `erp-iot-d21/docs/inputs` ima stariji skup.
- **Prijedlog:** ERP ih commita u `docs/inputs` ERP repoa. Mobilni ulaz je verzioniran u mobilnom repou: `docs/erp_zahtjevi/`.

### 6.2 Ugovor za mock — PRIJEDLOG
- **Problem:** vlasnik je odlučio da mobilna za endpointe koje ERP još nema (M2, M4, M5, M9…) koristi `dev/mock-erp` **strogo po ugovoru iz ERP speca**. Taj ugovor danas ne postoji.
- **Prijedlog:** ERP što ranije upiše u spec shapeove za M2, M4, M5 i M19 (request, response, kodovi), makar prije implementacije. Mobilna do tada mockira prema ovom dokumentu i označava mock "contract: proposed".
- **Mobilna treba:** shapeove M2, M4, M5 za F1.

### 6.3 Rotacija `ERP_API_KEY` i gašenje customer ruta (ulaz §8) — TREBA ORMAR
- Mobilna je uklanja iz aplikacije.
- Status rotacije na ormarima nije potvrđen; vlasnik ga vodi kao visoki prioritet.
- Gašenje Cloud_IOT customer ruta: mobilna ih više ne koristi od F0.

### 6.4 Radni nalozi (M13) — informacija
- Zahtjevi mobilne opisani su u `mobile_spec.md` C.4: ekrani, polja, statusi, dodjela, offline red s `client_op_id` i `version`.
- **Odluka vlasnika:** GPS se briše iz EXIF-a fotografija na uređaju.
- Mobilna gradi offline podatkovni sloj od početka.

### 6.5 Prihvaćeno bez komentara
M2, M3, M6, M7 (uz 1.1), M8, M12, M14 (uz 3.4), M15. Ulaz §0 načela 1–9; §3.3; §4.1; §4.2; §5; §6.

---

## 7. Sažetak: TREBA ORMAR (za chat ormara)
1. **Kamera — stream iza autentifikacije:** `camera.stream_ext` + status kamere u gatewayu za ERP, samo preko Tailscalea, stream samo dok ERP traži (5.3).
2. **Kamera — privatnost po vezu:** što je izvedivo — maske privatnosti, izrez po vezu, zamagljivanje osoba (CPU na ormaru); koje kamere su 1:1 s vezom (5.2).
3. **Rotacija `ERP_API_KEY`** na svim ormarima i potvrda statusa (6.3).
4. **Gašenje Cloud_IOT customer ruta** (legacy) prema ERP ulazu §8 (6.3).
5. **Tipovi NFC naljepnica** po ormarima (ISO 15693 ili drugo) — potvrda za iOS čitanje (2.4).

## 8. Sažetak: prijedlozi ERP spec izmjena
| # | Izmjena | Točka |
|---|---|---|
| 1 | M1 i M5 na prefiks `/api/mobile/v1`; nova M19 (mobilna fasada) | 1.1 |
| 2 | `kind = staff \| customer`; admin je uloga | 1.2 |
| 3 | M21 `permissions[]` (v3) | 1.3 |
| 4 | Model kupca: `customer_accounts`, `customer_members`; token bez fiksne marine | 1.4, 3.1 |
| 5 | Odvojeni staff i customer login endpointi | 1.5 |
| 6 | `refresh_tokens`, trajanja, opoziv, detekcija ponovne uporabe | 1.6 |
| 7 | Mobilni 2FA enrolment (bez `qr_svg`) | 1.7 |
| 8 | M23 setup link od Ownera | 1.8 |
| 9 | §5.1 korak 2: UID + token, bez ID-a kupca u tijelu | 2.1 |
| 10 | Pravilo stopa i `can_stop` | 2.2 |
| 11 | Normalizacija UID-a na serveru | 2.4 |
| 12 | M18 organizacija | 3.1 |
| 13 | M17 kupčevo čitanje prije CRM-a | 3.2 |
| 14 | `features[]` kao feature flagovi | 3.3 |
| 15 | Stripe za M14 | 3.4 |
| 16 | `lika.digital` putanje, `api.lika.digital`, `PUBLIC_APP_BASE_URL` | 4.1 |
| 17 | M20 email preko Google Workspace SMTP relaya | 4.2 |
| 18 | M22 `tokens.json` | 4.3 |
| 19 | D32 u spec; sužavanje testa D30; M16 API i HLS | 5.1, 5.5 |
| 20 | Tekst o snimci zaslona (Android/iOS) | 5.4 |
| 21 | Ulazni dokumenti u git | 6.1 |
| 22 | Rani shapeovi M2, M4, M5, M19 | 6.2 |
