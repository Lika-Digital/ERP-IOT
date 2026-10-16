# Mobilna aplikacija — zahtjevi iz ERP-a (v1)

Status: ULAZ VLASNIKA I ARHITEKTA ERP-a. Obvezujuće za mobilnu specifikaciju
(`docs/mobile_spec.md`) i za ERP spec v3 (mobilni API). Datum: 2026-10-16.
Bez osobnih podataka.

Ovaj dokument odgovara i na otvorena pitanja iz `mobile_spec.md` v0.1 (G.1–G.23)
tamo gdje ERP već ima odluku. Gdje odluke nema, piše **ODLUKA VLASNIKA** i
preporuka.

---

## 0. Neprekršiva načela (iz odluka ERP-a)

1. **Aplikacija razgovara SAMO s ERP-om.** Nikad s ormarom, NUC-om ni Cloud_IOT
   backendom. ERP je jedini backend aplikacije (BFF). (ERP §5.1, D6.2, ormar D6.1)
2. **U aplikaciji nema nijedne tajne:** nema API ključeva, adresa ormara,
   servisnih lozinki ni ičega u `EXPO_PUBLIC_*` što je tajno. Sve što je ikad bilo
   u bundleu smatra se poznatim.
3. **Autorizaciju uvijek radi ERP.** Aplikacija smije sakriti gumb, ali server
   odbija sve što korisnik ne smije. Svaki podatak je vezan na `marina_id`
   (višemarinski model, RLS — spec v3 Faza 0).
4. **Stanje i boje računa server** (`berth_colour`, status sesije, status
   ormara). Aplikacija ih samo prikazuje. `null` nije 0; stari podaci se
   prikazuju kao stari (StaleDataBanner), nikad kao svježi.
5. **Upravljanje (utičnice, ventili, sesije, vrata)** vrijedi samo kad je ormar
   Online i Smart Mode ON (D19); svaka naredba traži razlog i ide u
   `command_audit` — isto kao web.
6. **Kamera (D30 + D32):** analize (referentne slike, match) ostaju na ormaru
   (D30). **Live prikaz veza je dopušten (D32)** — samo preko ERP-a, na zahtjev,
   bez snimanja, s vremenskim ograničenjem i auditom. Lažni "My Ship LIVE" video
   (mp4) zamjenjuje se pravim prijenosom preko ERP-a.
7. **Simulirano je uvijek označeno SIM** i nikad se ne naplaćuje (D28).
8. **Osobni podaci (GDPR, D15):** podaci vlasnika plovila samo na zahtjev uz
   audit; imena kupaca se ne prikazuju na zajedničkim zaslonima; push obavijesti
   ne sadrže osobne podatke ni iznose (samo "Imate novu obavijest").
9. **Spec je izvor istine (§0.0):** pregled → prijedlog izmjene speca → odobrenje
   vlasnika → kod.

---

## 1. Tri profila u jednoj aplikaciji

Profil određuje ERP token (`/api/auth/me` → `kind` + `role`), ne aplikacija.

| Profil | Tko | Što je |
|---|---|---|
| **Korisnik marine** (kupac, nautičar) | vlasnik plovila, član organizacije (obitelj/posada) | NFC punjenje, usluge, ugovori, računi, pristup |
| **Zaposlenik marine** | Marina Owner, Marina Manager, zaposleničke uloge (Recepcija, Glavni mornar, Mornar, Mornar-dizaličar, Vozač, Voditelj servisa, Serviser, Čistač/ica, Računovodstvo) | mobilna preslika ERP-a za njegovu marinu, po pravima uloge |
| **Admin** | Lika Digital (platforma) | mobilna preslika ERP Admina: popis svih marina, ulazak u marinu (admin mode) |

Pravila:
- Zaposlenik vidi samo svoju marinu (ili marine iz `user_marina_access`) i samo
  ono što mu matrica prava dopušta (spec v3 §1.2).
- Admin nakon prijave dobiva popis marina; ulazak u marinu je vidljiv
  ("Admin mode — <marina>") i ide u audit.
- Ista osoba kao zaposlenik i kupac: ODLUKA VLASNIKA. Preporuka: odvojeni
  računi (različiti tokeni i rizici), jer zaposlenik ima MFA i šira prava.

---

## 2. Prijava i sesija

| Tema | Zahtjev |
|---|---|
| Marina ID | QR u marini → https link → app s popunjenim kodom marine; javni ERP endpoint vraća samo naziv, logo, značajke i načine prijave (bez internih polja), uz rate limit |
| Zaposlenik i Admin | lozinka + obavezan TOTP (D20); rezervni kodovi |
| 2FA enrolment na mobitelu | preporuka: dopušteno (otpauth link + tajna za kopiranje), uz isti audit kao na webu |
| Kupac | prijava u ERP-u (kupci žive u ERP-u — CRM modul); MFA nije obavezan u v1 (ODLUKA VLASNIKA: opcionalni TOTP ili email kod kasnije) |
| Račun kupca | preporuka: pozivnica od marine (iz ugovora/ponude u CRM-u) + samoregistracija koju marina odobrava |
| Trajanje | refresh token vezan uz uređaj, rotacija, opoziv, odjava; biometrijsko otključavanje; automatsko zaključavanje staff dijela nakon neaktivnosti |
| Zaboravljena lozinka | kupac: email s jednokratnim linkom; zaposlenik: novi setup link od Ownera/Admina |
| Više marina | zaposlenik: već podržano (M:N); kupac: preporuka jedan račun, više marina (customer_accounts 1:N customers) |
| Pohrana | tokeni samo u SecureStore (Keychain/Keystore); web verzija aplikacije nije za produkciju |
| Audit | svaki zahtjev nosi `X-Client` i `X-Device-Id`; ERP razlikuje web i mobilni kanal |

---

## 3. Profil KORISNIK MARINE (kupac)

### 3.1 v1 (prvi izlazak)
- **Početna:** marina, moje plovilo, moj vez, aktivna sesija (struja/voda),
  obavijesti.
- **NFC punjenje (D6):** telefon pročita UID taga na priključku → `POST` na ERP
  (samo UID, nikad ID kupca s klijenta) → ERP mapira tag → ormar/priključak
  (dva zapisa UID-a, D6.1), provjeri kupca, ugovor i prepaid/postpaid pravila
  (D9, D10), pa sam zove ormar. Aplikacija prikazuje: čekanje (rok), aktivno
  (snaga, kWh, procjena troška), završeno. Zaustavljanje iz aplikacije samo ako
  ERP to dopušta.
- **Povijest:** sesije i potrošnja; računi (pregled, PDF).
- **Profil:** podaci kupca, plovilo, **organizacija** (članovi obitelji i posada —
  dodaje ih vlasnik, uz pristanak i GDPR), odjava.
- **My Ship live (D32):** gumb "Pogledaj moj vez" — kupac vidi SAMO kameru
  svog veza (vez iz važećeg ugovora); prijenos ide preko ERP-a (kratkotrajni
  potpisani URL), ograničeno trajanje, bez snimanja i bez snimki zaslona gdje
  platforma to dopušta; status kamere (zelena/siva) sa servera.
- **Obavijesti (push):** početak/kraj sesije, niska prepaid stanja, potvrde
  narudžbi — bez osobnih podataka u tekstu.

### 3.2 Nakon CRM modula (redom, svaki uz odobrenje)
- Ugovori i ponude: pregled, prihvat ponude, potpis, PDF.
- Plaćanje računa: preko pružatelja plaćanja (PSP); aplikacija nikad ne vidi
  podatke kartice. ODLUKA VLASNIKA: koji PSP.
- Narudžba usluga: servis (paketi Servis 1/2/3, zimovanje), dizalica/spuštanje,
  pranje, parking, ostale usluge iz kataloga; status narudžbe.
- Rezervacije: vez (tranzit), soba, najam plovila, stol u restoranu, narudžba
  hrane i pića.
- Pristup (D25): prava na vrata (WC, gatovi), rampu i parking koja marina dodijeli;
  telefon kao ključ (NFC/QR/BLE) — ODLUKA VLASNIKA kasnije. Aplikacija nikad
  sama ne otključava bez provjere u ERP-u.
- Poruke s marinom.
- Ocjene usluga.

### 3.3 Što kupac NIKAD ne vidi
Tuđe sesije, tuđe plovilo, interne alarme, sigurnosne događaje, podatke drugih
kupaca, kameru tuđeg veza, slike analiza (D30).

---

## 4. Profil ZAPOSLENIK MARINE (preslika ERP-a za Ownera i zaposlenike)

Sadržaj ovisi o ulozi (matrica prava, spec v3 §1.2).

### 4.1 v1 — ono što ERP već ima
- **Pregled:** 2D karta (boje sa servera), 3 KPI kartice, "Needs attention",
  SIM oznake.
- **Alarmi:** aktivni i log; potvrda alarma s razlogom.
- **Ormari / upravljanje:** odabir ormara, sesije na čekanju i aktivne,
  Allow/Deny/Stop, utičnice On/Off — s razlogom; gumbi samo kad je ormar Online i
  Smart Mode ON; demo-marina brava (409) kao rečenica sa servera.
- **Vezovi:** popis i detalj veza (plovilo; vlasnik samo na zahtjev uz audit;
  rezultat analize ormara; funkcije procjene "Not available" dok ormar ne
  isporuči R27–R30).
- **Energija:** sažetak.
- **Live kamera veza (D32):** ikona kamere na karti (zelena = aktivna), klik
  otvara prijenos; prava po ulozi; audit.
- **Push:** novi alarmi (bez osobnih podataka u tekstu).

### 4.2 Nakon Work modula — NAJVAŽNIJA mobilna funkcija za zaposlenike
- **Moji radni nalozi** po ulozi: uplov, isplov, spuštanje/vađenje (dizalica,
  kamion — raspored i rezervacija), čišćenje, servis, računovodstvo.
- Na nalogu: preuzmi, započni, završi; kontrolna lista; fotografije (prijava
  kvara / stanje broda — fotografije koje snima zaposlenik, ne kamera ormara);
  utrošeni materijal (iz zalihe); utrošeno vrijeme; napomena.
- **Rad bez signala** na gatovima: nalozi i promjene se spremaju lokalno i šalju
  kad se veza vrati (red na uređaju, rješavanje sukoba na serveru).
- Glavni mornar / Owner: dodjela naloga ljudima i podugovaračima.

### 4.3 Nakon CRM i Finance
- Owner/Manager: CRM dashboard (ugovori otvoreni/plaćeni), recepcija (uplov,
  dokumenti, uplata), Finance sažetak (samo uloge koje to smiju).

---

## 5. Profil ADMIN

- Popis svih marina; odabir marine → admin mode (vidljivo, audit).
- U marini: sve što vidi Owner + konfiguracija koju ERP Admin smije na mobitelu.
- Preporuka: osjetljive radnje Admina (stvaranje marine, prava, brisanje)
  ostaju samo na webu u v1.

---

## 6. Izgled
- Lika brand iz ERP-a (tokeni iz `frontend/src/theme/tokens.css`): lime
  `#C4FF61`, ink `#2B2A29`, svijetla i tamna tema, statusne boje sa servera,
  status = ikona + riječ + boja, WCAG AA, 360 px.
- Jezik: ERP UI je engleski. ODLUKA VLASNIKA za aplikaciju. Preporuka:
  engleski u v1, ali aplikacija pripremljena za prijevod (kupci su HR, DE, AT,
  SI, IT) — kupčev dio prvi dobiva HR i DE.
- Branding po marini u v1: samo naziv i logo marine unutar Lika teme.

---

## 7. Što ERP mora izgraditi za aplikaciju (ide u ERP spec v3)

| # | Stavka | Kada |
|---|---|---|
| M1 | Javni HTTPS pristup ERP API-ju (5c, Cloudflare); do tada pilot za zaposlenike samo preko Tailscalea | prije kupaca |
| M2 | `marinas.public_code` + javni lookup marine (minimalni podaci, rate limit) | Faza 1 mobilne |
| M3 | Rate limit na auth i javne endpointe | Faza 1 |
| M4 | Refresh token po uređaju, rotacija, opoziv, logout | Faza 1 |
| M5 | `/api/auth/me` s `kind` (staff/customer/admin) i ulogom | Faza 1 |
| M6 | WS bez JWT-a u query stringu (kratkotrajni ticket) | Faza 2 |
| M7 | Stabilni, dokumentirani odgovori za overview, berths, berth detail, control | Faza 2 |
| M8 | Registracija uređaja za push i slanje (alarmi, sesije, nalozi) | Faza 2 |
| M9 | Kupci u ERP-u: `customer_accounts`, prijava, token `scope=customer`; staff ovisnosti izričito odbijaju customer token | Faza 3 |
| M10 | Pozivnica/registracija kupca, zaboravljena lozinka (email — treba SMTP) | Faza 3 |
| M11 | Mobilni NFC: scan po UID-u, sesije kupca, stop (= ERP faza 7) | Faza 3 |
| M12 | Live događaji kupcu (WS ili push) | Faza 3 |
| M13 | API za Work modul (nalozi, fotografije, offline sinkronizacija) | s Work modulom |
| M14 | API za CRM (ugovori, ponude, potpis, računi, narudžbe, rezervacije, pristup) | s CRM modulom |
| M15 | Uključiti `X-Client` / `X-Device-Id` u audit | Faza 1 |
| M16 | D32 live kamera: status kamere, kratkotrajni potpisani URL za gledatelja, media relay na VPS-u, ograničenja, audit gledanja | s D32 u ERP-u |

## 8. Odmah, neovisno o aplikaciji
- **Rotacija ključa** `ERP_API_KEY` (X-API-Key za `/api/nfc/*`) na svim
  ormarima: bio je ugrađen u mobilni bundle i smatra se poznatim. Novi ključ
  samo u ERP-u (`cabinets.erp_api_key_enc`). Ide u chat ormara.
- Customer rute u Cloud_IOT-u (legacy iz testne faze) se gase; kupci, ugovori,
  računi, chat i narudžbe sele se u ERP (CRM). Ide u chat ormara.
- Postojeći testni kupci iz Cloud_IOT-a: preporuka novi početak (testni podaci),
  bez migracije lozinki.

## 9. Odgovori na otvorena pitanja iz mobile_spec v0.1
| G | Odgovor |
|---|---|
| 1 | Aktualan ERP je repo `Lika-Digital/ERP-IOT` (radno `erp-iot-d21`, main/grane faza). Mapa `erp-iot` služi samo kao mjesto ulaznih dokumenata u `docs/inputs`. |
| 2 | ODLUKA VLASNIKA — preporuka §6 |
| 3 | Javno kroz ERP 5c (Cloudflare) nakon testa s pravim ormarom; domena: ODLUKA VLASNIKA. Pilot zaposlenika može ići preko Tailscalea. |
| 4–5 | ODLUKA VLASNIKA (domena); prijedlog bez servisa treće strane je prihvatljiv |
| 6 | Da — kupci žive u ERP-u |
| 7 | Preporuka: pozivnica marine + samoregistracija uz odobrenje marine |
| 8 | Bez MFA u v1, kasnije opcionalno |
| 9 | Dopušteno na mobitelu |
| 10 | Preporuka: odvojeni računi |
| 11 | Da: refresh + biometrija; trajanja predložiti u specu |
| 12 | Jedan račun, više marina |
| 13 | Sele se u ERP (CRM); redoslijed §3.2 |
| 14 | Novi početak |
| 15 | ODLUKA VLASNIKA (SMTP servis) |
| 16 | Da, predložiti ERP-u zajednički `tokens.json` |
| 17 | Samo iOS + Android |
| 18 | Samo logo i naziv marine u v1 |
| 19 | ODLUKA VLASNIKA (računi trgovina, bundle id) |
| 20 | Staff v1 kako je predloženo; Work nalozi čim ERP izgradi Work modul (spec v3); uloga Marina Owner je u spec v3 Faza 0 |
| 21 | Da (Jest, Maestro) |
| 22 | QR na priključku se gasi u korist NFC-a (D6) |
| 23 | Rotacija: vidi §8 — provjeriti na ormarima |
