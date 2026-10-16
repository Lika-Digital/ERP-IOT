# Odgovor ERP-a na odgovor mobilne v2

| | |
|---|---|
| Od | ERP (`Lika-Digital/ERP-IOT`, `docs/erp_spec.md` **v30**, grana `spec/v3-moduli`) |
| Za | Marina Mobile (`docs/mobile_spec.md` v0.4.1, poglavlja H i I) |
| Na | `odgovor_mobilne_v2.md` (Marina-Mobile `develop`; pročitano na `ad48ade`, vlasnik naveo `fa5c455`) |
| Datum | 2026-10-16 |
| Status | **Prijedlog ERP-a.** Odluke vlasnika (H-3, H-9, H-11) su ugrađene i ne otvaraju se. Ostalo postaje obvezujuće tek kad vlasnik odobri trojke iz §2 (§0.0). Oblici ruta su `contract: proposed` dok vlasnik ne odobri §14.9 (T-22) |

Oznake kao u v1: **PRIHVAĆAM**, **NE PRIHVAĆAM** (uz zamjenu), **ODLUKA VLASNIKA**.
Sve iz ERP odgovora v1 što ovdje nije spomenuto ostaje kako je napisano.

---

## 1. Odgovor po točkama

### 1.1 H-1 · Oznake MA-n — PRIHVAĆAM

- Stavke za mobilnu su od sada **MA-1…MA-23** (isti brojevi kao M1–M23). **M0–M6** su samo ERP
  v3 faze.
- U ERP odgovoru v1 stavka „M5 — `/me`" je **MA-5**, „M2 — javni lookup" je **MA-2**, M16 je
  **MA-16**, M17 je **MA-17** (T-13: MA-17-K1/K2/K3), M19 je **MA-19**. Faze „s M2 (CRM)" i „s M5
  (eRačun)" ostaju faze.
- **Mijenja u `erp_spec.md`:** dvije reference na „`mobilna_zahtjevi_iz_ERP.md` M16" (v28 tablica
  i §14.8) postaju MA-16. Trojka T-23.

### 1.2 H-5 · Tri prava člana — PRIHVAĆAM

Jedno `can_access` miješa tri stvari s različitim rizikom: novac (punjenje), privatnost (kamera) i
fizički pristup (vrata). Skiper koji puni i otvara vrata, a ne gleda kameru, je normalan slučaj.

```
customer_members   … can_charge        bool NOT NULL DEFAULT false   -- NFC punjenje na ugovor nositelja
                     can_view_camera   bool NOT NULL DEFAULT false   -- D32
                     can_access_doors  bool NOT NULL DEFAULT false   -- D25
```

Pravila:
- **Nositelj** (`member_role = 'holder'`) ima sva tri prava po ugovoru; zastavice se za njega ne
  čitaju i u `/me` su sve `true`.
- **Član** ima pravo samo kad je zastavica `true` **i** pravo postoji kod nositelja (važeći
  ugovor; za kameru još i §1.25: vez NIJE KRIVO). Zastavica nikad ne daje više nego što nositelj ima.
- `can_charge` ide uz `spend_limit` iz v1 (T-12): `spend_limit` vrijedi samo kad je `can_charge`.
- Promjenu zastavice radi samo nositelj (ili osoblje marine), upisuje se u `audit_log`.
- `/me` → `memberships[]` za svakog člana vraća:

```
"rights": { "can_charge": true, "can_view_camera": false, "can_access_doors": true }
```

  Aplikacija skriva ono što član ne smije. Server svejedno provjerava svaki zahtjev; sakrivanje u
  aplikaciji nije provjera.
- Odbijenica kamere zbog zastavice: **403** `member_not_allowed` — „The account holder hasn't
  allowed live view for you." (novi ključ u tablici v1 §4.1, `contract: proposed`).
- **Mijenja:** v3 §14.3.1 (`customer_members`), §14.8 (red „član organizacije kupca"), T-12 iz v1.
  Trojka T-24.

### 1.3 H-6 · Mobilne stavke u ERP rasporedu — PRIHVAĆAM DJELOMIČNO

Prihvaćam MOB-0 i MOB-1 kao imenovane faze u §10.16. Ne prihvaćam „MOB-0 uz 5c ili odmah nakon"
u cijelosti, iz dva razloga:

1. **Vlasnik je 2026-10-16 promijenio redoslijed 5b (v25.1):** vatrozid (korak 3) i Tailscale ACL
   (korak 4) idu nakon testa čitanja s pravim ormarom, a **prije svakog javnog izlaganja**. Javni
   prefiks `/api/mobile/v1` je javno izlaganje, pa MOB-0 ne smije biti javan prije 3, 4 i 5c.
2. **Pola MOB-0 treba v3 model.** `public_code` (MA-2), `customer_accounts` (kupčeva prijava,
   MA-4 i MA-5 za kupca) i Owner koji šalje setup link (MA-23) ne postoje bez v3 faze **M0**
   (višemarinski model), koja čeka odobrenje.

Zamjena — MOB-0 se dijeli na dva dijela:

| Faza | Sadržaj | Uvjet |
|---|---|---|
| **MOB-0a** · osoblje | MA-19 (prefiks, greške), MA-15 (zaglavlja, audit), MA-3 (rate limit), MA-4 i MA-5 **za osoblje**, `GET /marinas` (H-12) | gradi se nakon 5d; **javno tek s 5c**, a 5c tek nakon koraka 3 i 4 (v25.1). MA-3 mora biti gotov prije prvog javnog zahtjeva |
| **MOB-0b** · kupac | MA-2 (lookup, `public_code`, QR H-11), MA-4 i MA-5 **za kupca**, provjera uređaja (H-3), MA-23 (setup link) | nakon v3 **M0**; kupac se u pravoj marini ne upisuje dok P-5/O67 vrijede |
| **MOB-1** · osoblje v1 | MA-7 (overview, berths s poljem `camera`, alarmi), MA-6 (WS ticket), MA-8 (push) | čitanje odmah nakon MOB-0a; **upravljanje u MA-7 tek nakon prvog upravljačkog testa** (§10.15 korak 7) |
| s fazom 7 | MA-9, MA-11, MA-12, MA-17-K1, MA-18, MA-20 | kupac K1 |
| s L1 / L2, M2, M5 | MA-16, MA-17-K2, MA-17-K3 | prema T-13 |

Mobilna F1 i dalje radi protiv mocka po ugovoru; na pravi ERP prelazi kad je MOB-0a javan.
**Mijenja:** §10.16 (nove faze MOB-0a, MOB-0b, MOB-1 i njihovi uvjeti). Trojka T-25.

### 1.4 H-9 · Kamera kad je signal plovila NEPOZNATO — ODLUKA VLASNIKA, ugrađena (v30)

- **NEPOZNATO je dopušteno.** Pravilo je NIJE KRIVO, a nepoznato nije krivo (nema reference,
  ormar offline, analiza starija od 30 min).
- Upisano u `erp_spec.md` v30: §1.25 dopuna (3) i red „Kupac" u §14.8.
- Kupcu se o plovilu tada ne govori ništa: nema rečenice, nema `reason`. `other_vessel` ostaje
  isključivo za KRIVO.
- Prijedlog uz odluku (T-26): `camera_views` bilježi signal plovila u trenutku početka
  (`vessel_signal`: `none` | `right` | `unknown`), da se kasnije može vidjeti koliko je gledanja
  prošlo uz NEPOZNATO. Kupcu se to ne prikazuje.

### 1.5 H-3 · Email kod s novog uređaja — ODLUKA VLASNIKA, oblik PRIHVAĆAM uz dopune

Oblik iz H-3 prihvaćam. Dopune:

```
POST /api/mobile/v1/auth/customer/login            { "email", "password" }
200  <TokenPair, kind "customer">                   // poznat uređaj
202  { "challenge_token": "<10 min>", "sent_to": "g•••@example.test", "code_length": 6 }
401  bad_login                                      // isti odgovor kao do sada (O14)
403  email_not_verified                             // provjerava se PRIJE uređaja
429  rate_limited

POST /api/mobile/v1/auth/customer/device/verify    { "challenge_token", "code" }
200  <TokenPair, kind "customer">                   // uređaj postaje poznat
401  bad_code             "That code didn't work. Check the latest email from us."
401  challenge_expired    "Sign-in took too long. Please start again."
401  challenge_locked     "Too many wrong codes. Please start again."

POST /api/mobile/v1/auth/customer/device/resend    { "challenge_token" }
204                                                 // novi kod poništava stari
429  rate_limited                                   // 5/h po primatelju (MA-20)
401  challenge_expired | challenge_locked
```

- **`X-Device-Id` na `verify` mora biti isti kao na `login`** koji je izdao `challenge_token`;
  inače `401 challenge_expired` (isti odgovor, bez objašnjenja).
- Kod: 6 znamenki, 10 min, 5 pokušaja po izazovu; nakon petog krivog izazov je zaključan
  (`challenge_locked`). Kod se sprema **samo kao hash**, nikad u log.
- Kod se šalje **tek nakon točne lozinke**; za krivu lozinku i dalje isti `401 bad_login`.
- Poznati uređaji su platformska tablica (kao `customer_accounts`):

```
customer_devices  (platforma)  account_id, device_hash (sha256 X-Device-Id), first_verified_at,
                               last_seen_at, forgotten_at NULL
                               UNIQUE (account_id, device_hash)
```

- Odjava uređaj ne zaboravlja. Promjena lozinke i reset lozinke zaboravljaju **sve** uređaje i
  opozivaju sve refresh tokene računa. Uređaj nekorišten **180 dana** postaje nov (prihvaćam).
- Svaki izdani kod, uspjeh, neuspjeh i zaključavanje idu u `auth_audit` (s `X-Client`, bez koda).
- Osoblje se ovo ne tiče: osoblje ima TOTP (D20).
- **Mijenja:** v3 §14.1.2 (`customer_devices`), §14.9 (rute). Trojka T-27.

### 1.6 H-11 · QR putanja — ODLUKA VLASNIKA, ispravljeno

- QR marine je **`https://lika.digital/marina/<public_code>`**.
- Ispravljeno u ERP odgovoru v1 (točka 4.1 i §3.2; oznaka „ispravljeno u v2, H-11") i upisano u
  `erp_spec.md` v30 (tablica promjena). `erp_spec.md` dosad nije imao QR putanju, pa nema drugog
  mjesta za ispravak.
- Lookup ruta se ne mijenja: `GET /api/mobile/v1/public/marinas/{public_code}`.

### 1.7 H-12 · Popis marina za osoblje — PRIHVAĆAM, uz dopune

```
GET /api/mobile/v1/marinas?limit=&cursor=          Authorization: Bearer <staff>
200 { "items": [ { "marina_id": 1, "name": "Marina Primjer", "public_code": "K7RM2Q",
                   "timezone": "Europe/Zagreb", "features": ["nfc_charging", "camera_live"],
                   "access": "member" | "admin_mode" } ],
      "next_cursor": null }
403 wrong_account_kind                              // kupčev token
```

- `marina_manager` (i ostale uloge osoblja iz v3): **samo marine u kojima ima članstvo**,
  `access: "member"`.
- `admin`: sve aktivne marine, `access: "admin_mode"`. Popis je samo izbornik: ulazak u marinu je
  admin mode s razlogom (v3 §14.1.4) i svaka ruta marine to provjerava. Popis sam po sebi ne daje
  pristup.
- `features` je isti popis kao u T-14 (v1).
- Redoslijed: po `name`, pa `marina_id`. Ugašene marine se ne vraćaju.
- Pripada **MOB-0a**. Trojka T-28 (dio §14.9).

### 1.8 H-13 · Prefiks kupčevih ruta — PRIHVAĆAM, izričito

**Pravilo:** svaka kupčeva ruta koja se odnosi na marinu počinje s

```
/api/mobile/v1/marinas/{marina_id}/me/…
```

- K1–K3: `…/me/credit`, `…/me/sessions`, `…/me/consumption`, `…/me/vessel`, `…/me/berth`,
  `…/me/contract`, `…/me/invoices`; organizacija (MA-18): `…/me/members`.
- `tenant()` prvo provjerava aktivno članstvo računa u toj marini (v1 1.4), inače **403**
  `marina_forbidden`. Pod istim prefiksom osoblje dobiva **403** `wrong_account_kind`.
- **Bez marine** su samo rute računa: `/api/mobile/v1/auth/*` (prijava, uređaj, refresh, odjava,
  `/auth/me`) i javni lookup `/api/mobile/v1/public/*`. Druge iznimke nema; nova kupčeva ruta bez
  `{marina_id}` je greška, a test je traži po listi ruta (kao TC-ERP-AUTH-01).
- Kamera ostaje kako je u v1: `/api/mobile/v1/marinas/{marina_id}/camera/sessions` za osoblje i
  kupca (nije pod `/me/`, jer je ista ruta za obje vrste računa).
- Trojka T-29.

### 1.9 H-14 · Zaglavlja na HLS rutama — PRIHVAĆAM

- Rute `/api/mobile/v1/live/{view_token}/…` su **izuzete** od pravila `X-Client`/`X-Device-Id` i
  od `Authorization`. Token u putanji je dovoljan.
- Vezanje tokena uz uređaj radi se **pri izdavanju**: `POST …/camera/sessions` traži zaglavlja i
  token zapisuje uz `X-Device-Id`. Na HLS rutama se uređaj ne provjerava, jer ga player ne šalje.
- Zato token mora sam nositi zaštitu: najmanje 128 bita slučajnosti, vrijedi do `expires_at`,
  samo za jednu sesiju i jednu kameru, poništava se `DELETE`-om ili krajem sesije. nginx za `/live/`
  ne logira putanju (v1).
- Izuzeće je **samo** za `/live/`. Sve ostalo pod prefiksom i dalje vraća `400
  client_headers_missing`.
- Trojka T-30 (dio §14.9 i v1 §3.1).

### 1.10 H-15 · `index.m3u8` dok je `starting` — PRIHVAĆAM, uz cijelu tablicu

Da mobilna, mock i ERP rade isto, HLS rute vraćaju **samo statusne kodove bez tijela** (player
JSON ionako ne čita):

| Stanje | `index.m3u8` | `seg/{n}.ts` |
|---|---|---|
| `starting` | **503**, bez tijela, `Retry-After: 2` | **404** |
| `live` | **200**, prepisana lista | **200**; segment kojeg nema u međuspremniku → **404** |
| `ended` (bilo koji `end_reason`) | **410**, bez tijela | **410** |
| token nepoznat ili istekao | **404**, bez tijela | **404** |

- Aplikacija i dalje pokreće player tek kad je `state = "live"` (pravilo mobilne). 503 je samo
  zaštita za slučaj da player krene ranije.
- Nakon 410 ili 404 aplikacija zove `GET …/camera/sessions/{session_id}` i prikazuje `message`.
- Trojka T-30 (zajedno s H-14).

---

## 2. Izmjene `erp_spec.md`

Upisano u **v30** (odluke vlasnika, bez trojke): H-9 (§1.25 dopuna 3, §14.8 red „Kupac") i H-11
(tablica promjena v30).

Trojke koje čekaju odobrenje (nastavak T-1…T-22 iz v1):

**T-23 · Oznake MA-n**
- *Odlučeno (prijedlog):* mobilne stavke su MA-1…MA-23; M0–M6 su samo ERP faze. Dvije reference
  na „M16" u `erp_spec.md` postaju „MA-16".
- *Zašto:* iste oznake za dvije različite stvari već su pomiješane u ERP odgovoru v1.
- *Ako griješim:* preimenovanje je pretraga i zamjena u dva dokumenta.

**T-24 · Tri prava člana**
- *Odlučeno (prijedlog):* `customer_members.can_charge`, `can_view_camera`, `can_access_doors`,
  zadano `false`; nositelj ima sve po ugovoru; zastavica nikad ne daje više od nositelja;
  `403 member_not_allowed`; `rights` u `/me`. Zamjenjuje `can_access` u v3 §14.3.1, §14.8 i T-12.
- *Zašto:* novac, privatnost i fizički pristup imaju različit rizik; posada realno dobiva jedno
  bez drugog. Preporuka vlasnika.
- *Ako griješim:* četvrta zastavica je jedan stupac i jedan ključ u `rights`.

**T-25 · MOB-0a, MOB-0b, MOB-1 u §10.16**
- *Odlučeno (prijedlog):* raspored iz 1.3; MOB-0a javan tek s 5c (nakon koraka 3 i 4, v25.1);
  MOB-0b nakon v3 M0; upravljanje u MA-7 tek nakon prvog upravljačkog testa.
- *Zašto:* javni prefiks je javno izlaganje; kupčeve rute trebaju v3 model koji još nije odobren.
- *Ako griješim:* ako vlasnik želi kupca ranije, MOB-0b ide uz M0 kao njegov dio, ne prije.

**T-26 · `camera_views.vessel_signal`**
- *Odlučeno (prijedlog):* dnevnik gledanja bilježi signal plovila u trenutku početka.
- *Zašto:* NEPOZNATO je dopušteno (v30); bez zapisa se ne može vidjeti koliko se gleda bez
  potvrde da je vez kupčev.
- *Ako griješim:* stupac se ne koristi; ništa ne ovisi o njemu.

**T-27 · Provjera uređaja kupca (H-3)**
- *Odlučeno (prijedlog):* rute i pravila iz 1.5; `customer_devices` kao platformska tablica;
  promjena i reset lozinke zaboravljaju sve uređaje; 180 dana.
- *Zašto:* odluka vlasnika (H-3); kupac nema TOTP, a e-mail kod pokriva krađu lozinke s novog
  uređaja.
- *Ako griješim:* rok 180 dana je jedna konstanta.

**T-28 · `GET /marinas`**
- *Odlučeno (prijedlog):* ruta iz 1.7, u MOB-0a; popis ne daje pristup, admin ulazi u marinu kroz
  admin mode.
- *Zašto:* `/me` adminu vraća prazan popis, a izbornik marina treba nazive.
- *Ako griješim:* ako se pokaže da admin ne treba popis u mobilnoj, ruta se svodi na članstva.

**T-29 · Prefiks `/marinas/{marina_id}/me/…`**
- *Odlučeno (prijedlog):* pravilo iz 1.8, s jedinim iznimkama `/auth/*` i `/public/*`; test po
  listi ruta.
- *Zašto:* jedan račun, više marina (odluka 1.4); RLS treba marinu iz putanje.
- *Ako griješim:* nema verzije u kojoj kupčeva ruta marine smije biti bez marine.

**T-30 · HLS: zaglavlja i stanja**
- *Odlučeno (prijedlog):* izuzeće iz 1.9 samo za `/live/`; tablica kodova iz 1.10, bez tijela.
- *Zašto:* player ne šalje zaglavlja ni ne čita JSON; vezanje uz uređaj radi se pri izdavanju
  tokena.
- *Ako griješim:* ako se pokaže da neki player ne podnosi 503 na listi, `starting` vraća 200 s
  praznom listom i `#EXT-X-PLAYLIST-TYPE:EVENT`; to je promjena samo na jednom mjestu.

---

## 3. Za chat ormara

Ništa novo iz ovog kruga. Osam pitanja za `camera.live_*` (R35) poslana su zasebno.
