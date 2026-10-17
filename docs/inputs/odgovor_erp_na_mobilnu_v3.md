# Odgovor ERP-a na odgovor mobilne v3 i v4

| | |
|---|---|
| Od | ERP (`Lika-Digital/ERP-IOT`, `docs/erp_spec.md` **v31**, grana `spec/v3-moduli`) |
| Za | Marina Mobile (`docs/mobile_spec.md` v0.5, kod F1–F3 na `develop`) |
| Na | `odgovor_mobilne_v3.md` (H-16…H-22) i `odgovor_mobilne_v4.md` (H-23…H-30), oba 2026-10-17 |
| Datum | 2026-10-17 |
| Status | **Prijedlog ERP-a.** Predodluke vlasnika (H-16…H-26) su ugrađene i ne otvaraju se. Za H-27…H-30 vlasnik nije dao predodluku: to je prijedlog ERP-a. Sve postaje obvezujuće kad vlasnik odobri trojke iz §3 (§0.0). Oblici ruta ostaju `contract: proposed` dok se ne upišu u §14.9 (T-22) |

Oznake kao u v1 i v2: **PRIHVAĆAM**, **NE PRIHVAĆAM** (uz zamjenu), **ODLUKA VLASNIKA**.
Sve iz ERP odgovora v1 i v2 što ovdje nije spomenuto ostaje kako je napisano.

---

## 0. Što se promijenilo na ERP-u od v30 (mobilna je čitala v30)

**D32.1 (vlasnik, 2026-10-17; spec v31):** live prikaz je **bez maski i bez zamagljivanja**. Maske
i DPIA više nisu uvjet. Osoblje gleda čim ormar uključi bidirectional za live rute, a kupci s M2.
Za mobilnu to znači tri stvari:

- **`customer_not_enabled` je povučen.** Kupcima se kamera više ne uključuje po kameri, pa taj
  ključ ne postoji. Iz tablice odbijenica (v1 §4.1, §4.4) i iz mocka ga treba maknuti.
- **`privacy_mask` iz `live_status` je samo informacija**, nikad razlog odbijanja. Aplikacija ga
  ne prikazuje.
- Rečenica da kamera pokazuje sve vezove ormara ostaje (§1.25).

---

## 1. Odgovor mobilnoj v3 (H-16…H-22)

### 1.1 H-16 · MOB-0a preko Tailscalea prije 5c — PRIHVAĆAM (odluka vlasnika)

- `/api/mobile/v1` je, dok nema 5c, dostupan **samo preko Tailscalea**. Ide kroz isti nginx na
  Tailscale adresi VPS-a (`:80`) kao web UI (5b korak 12); preko Cloudflarea ne ide ništa.
- U koraku 4 (Tailscale ACL) vlasnikov telefon dobiva pristup **samo ERP-u na `:80`**: ništa
  drugo na VPS-u i nijedan ormar.
- **MOB-0a se gradi nakon testa čitanja s ormarom** (5d), kako je odlučeno u v25.1. Uvjet „javno
  tek s 5c" (T-25) ostaje. Tailscale nije javno izlaganje.
- **Napomena za mobilnu:** Tailscale nosi WireGuard, ali URL je `http://100.x.y.z`. Android
  (network security config) i iOS (ATS) promet bez TLS-a dopuštaju samo izuzetkom. Izuzetak smije
  biti **samo u dev buildu i samo za tu adresu**, nikad u release buildu. Release ide na `https://`
  s 5c.
- **Mijenja:** T-25 (§10.16, MOB-0a). Trojka **T-31**.

### 1.2 H-17 · Rana tablica zahtjeva — PRIHVAĆAM (odluka vlasnika)

- `staff_requests` dolazi uz **MOB-1**, a `customer_requests` uz **MOB-0b**. CRM (M2) i Work
  (M4) ih kasnije preuzmu **bez promjene ugovora**: `request_id`, stanja i oblik iz §1.7 ostaju.
- Model (po marini, RLS kao ostale tablice v3 §14.1):

```
customer_requests   id (UUID), marina_id, customer_account_id, customer_id, type, category,
                    text, berth_id NULL, vessel_id NULL, status ('open'|'in_progress'|'resolved'),
                    client_op_id, client_created_at NULL, created_at, updated_at, resolved_at NULL
                    UNIQUE (customer_account_id, marina_id, client_op_id)
customer_request_replies  id, request_id, text, created_by (osoblje), created_at
staff_requests      id (UUID), marina_id, user_id, type, urgency, text,
                    berth_id NULL, cabinet_id NULL, location_text NULL,
                    status ('proposed'|'accepted'|'rejected'|'withdrawn'),
                    reject_reason NULL, work_order_id NULL, reviewed_by NULL, reviewed_at NULL,
                    client_op_id, client_created_at NULL, created_at, updated_at
                    UNIQUE (user_id, marina_id, client_op_id)
                    CHECK  berth_id, cabinet_id ili location_text — barem jedno
                    CHECK  status = 'rejected' ⇒ length(trim(reject_reason)) >= 3
request_photos      id (UUID), marina_id, request_kind ('customer'|'staff'), request_id,
                    jpeg BYTEA, size_bytes, sha256, client_op_id, created_at, delete_after NULL
```

- **Imena nisu slučajna.** CRM već ima „upit" (ulaz prodaje: upit → ponuda → ugovor, §14.3).
  Zahtjev kupca (prigovor, pitanje, povratna informacija) je druga stvar i ne smije se zvati
  „upit" ni „inquiry". U ERP webu se zove **„Customer requests"**, a zaposlenikov prijedlog
  **„Fault reports"**.
- **Mijenja:** §10.16 (MOB-0b, MOB-1), §14.3 i §14.4 (preuzimanje), §14.1 (tablice). Trojka **T-32**.

### 1.3 H-18 · Popis zasad fiksan, šalje ga server — PRIHVAĆAM (odluka vlasnika)

- Popis je u v1 **fiksan u kodu ERP-a**, ali aplikacija ga uvijek čita s `GET …/requests/options`.
  Popis po marini dolazi kasnije bez promjene ugovora.
- Server provjerava `type`, `category` i `urgency` prema **istom** popisu koji šalje. Nepoznat
  ključ vraća `422 invalid_request`.
- Kategorije kupca i hitnosti zaposlenika su prihvaćene kako je predloženo. Labele su na
  engleskom (MD-2).
- Ključevi `customer_requests` i `staff_requests` u `features[]` su prihvaćeni (T-14 ostaje jedini
  prekidač).
- **Mijenja:** T-14 (popis ključeva), §14.9. Trojka **T-33**.

### 1.4 H-19 · Tko vidi i obrađuje — PRIHVAĆAM (odluka vlasnika)

- **Obradu u ERP webu radi `marina_manager`** svoje marine. Admin to smije samo u admin modu s
  razlogom. Od v3 obradu nose prava `requests.customer.handle` (Recepcija) i
  `requests.staff.review` (Glavni mornar), kako je predložila mobilna.
- **Član organizacije** smije slati zahtjeve i vidi samo svoje. **Nositelj ne vidi zahtjeve
  članova.**
- **U v1 nema obrade iz mobilne.**
- **Push `staff_request.created`** ide onima koji smiju potvrditi u toj marini: u v1 to su
  `marina_manager`, od v3 nositelji prava `requests.staff.review`. Admin ga ne dobiva, jer
  admin nije vezan uz marinu.
- **Mijenja:** §14.9, §14.2 (zaslon „Customer requests" i „Fault reports"). Trojka **T-34**.

### 1.5 H-20 · Fotografije — PRIHVAĆAM (odluka vlasnika), uz razradu

- **Rok:** fotografija se briše **180 dana nakon zatvaranja**, a tekst ostaje koliko i ostali
  CRM zapisi. Zatvaranje se računa ovako:
  - kupac: `resolved`;
  - zaposlenik: `rejected` ili `withdrawn`; za `accepted` prije M4 vrijedi `reviewed_at`, a od M4
    zatvaranje radnog naloga, jer je fotografija tada dokaz popravka.

  Brisanje radi noćna retencija (§4.7, `delete_after`).
- **Svako gledanje fotografije od strane osoblja** ide u `audit_log`: tko, kada, koja fotografija,
  bez sadržaja. Podnositelj koji gleda svoju fotografiju se ne bilježi.
- **Evidencija obrada (čl. 30 GDPR): da**, upis „zahtjevi i prijave s fotografijama". **DPIA nije
  preduvjet**, u istom duhu kao D32.1.
- **Server sam čisti sliku**, kao drugi zid uz aplikaciju (MD-26):
  - dekodira JPEG i ponovno ga kodira bez metapodataka;
  - ograničava stranicu na 2048 px;
  - original se nikad ne sprema ni ne vraća.

  Pillow je već u locku (P5).
- **Gdje stoji:** `request_photos.jpeg` u PostgreSQL-u (`BYTEA`, nakon ponovnog kodiranja obično
  ispod 1 MB). Ide istim backupom (`pg_dump | age`, 7 dana), pod istim RLS-om i bez ičega na
  disku izvan baze. Zbog backupa obrisana fotografija nestaje i iz zadnje kopije najkasnije za 7
  dana, što se upisuje u evidenciju obrada.
- **Ista pravila vrijede i za fotografije zaposlenika**, jer i one mogu uhvatiti ljude.
- **Mijenja:** §4.7 (retencija), §14.9, §14.3 (GDPR). Trojka **T-35**.

### 1.6 H-21 · Odbijanje, spajanje, povlačenje — PRIHVAĆAM (odluka vlasnika)

- **Odbijanje traži razlog** od najmanje 3 znaka; baza to drži CHECK-om. Zaposlenik vidi
  `reject_reason` doslovno i dobiva push `staff_request.reviewed`.
- **Spajanje s postojećim nalogom** je dopušteno od M4: stanje `accepted`, `work_order_id`
  postojećeg naloga, `status_text` „Added to an existing work order". Prije M4 `accepted` vrijedi
  bez naloga (`work_order_id: null`).
- **Zaposlenik smije povući prijedlog** dok je `proposed`:
  - ruta `POST /marinas/{marina_id}/work/requests/{request_id}/withdraw` s tijelom
    `{client_op_id}` vraća 200 `Request` u stanju `withdrawn`, `status_text` „Withdrawn";
  - povlačenje već povučenog vraća opet 200;
  - nakon pregleda vraća `409 request_closed`.
- **Kupac ne povlači zahtjev** u v1; marina ga zatvara kao `resolved`. Ako mobilna to želi, to je
  nova točka.
- **Mijenja:** §14.9, §14.4. Trojka **T-36**.

### 1.7 H-22 · Rute — PRIHVAĆAM u načelu, usklađeno s prefiksom

| | Kupac → CRM | Zaposlenik → Work |
|---|---|---|
| Baza | `/api/mobile/v1/marinas/{marina_id}/me/requests` | `/api/mobile/v1/marinas/{marina_id}/work/requests` |
| Pravilo | T-29: kupčeva ruta marine je pod `/me/` ✔ | osoblje je pod `/marinas/{marina_id}/…` (kao `camera/sessions`); `/me/` je samo za kupca ✔ |
| Druga vrsta računa | `403 wrong_account_kind` | `403 wrong_account_kind` |

Usklađenja:
1. **`request_id` je UUID** koji daje server (neprozirni string), ne broj. Tako se zahtjevi ne
   mogu prebrojavati, a literal `options` ne može se sudariti s `{request_id}`. Ruta
   `…/requests/options` registrira se prije `…/requests/{request_id}`.
2. **`url` fotografije je relativna putanja pod prefiksom**:
   `/api/mobile/v1/marinas/{marina_id}/me/requests/{request_id}/photos/{photo_id}` (zaposlenik
   pod `/work/…`). Traži Bearer **i** zaglavlja `X-Client`/`X-Device-Id`. Izuzeće od zaglavlja
   ima samo `/live/` (T-30); slike nisu izuzete.
3. **Idempotentnost:** isti `client_op_id` vraća isti zahtjev s **200**, a prvi put **201**.
   `client_op_id` je jedinstven po (račun, marina), što drži baza. Za fotografije je jedinstven
   po zahtjevu.
4. **429 `rate_limited`** s `Retry-After`: 20 novih zahtjeva na sat po računu i marini, i 30
   fotografija na sat po računu i marini.
5. **413 `photo_too_large`** dolazi iz aplikacije ERP-a, ne iz nginxa: nginx propušta do 26 MB,
   a ERP odbija sve iznad `photo_max_bytes` (8 MB) s tijelom u M19 obliku.
6. **`replies[]` bez imena zaposlenika:** prihvaćam. Polje `created_by` ostaje u ERP-u za audit.
7. **Push tablica (§3.5):** prihvaćam kako je. Kada se push uključi, odlučuje MA-8 (I.6.5);
   tijelo nikad ne nosi tekst, kategoriju, vez, ime ni fotografiju.
- **Mijenja:** §14.9 (rute I.6). Trojka **T-37**.

---

## 2. Odgovor mobilnoj v4 (H-23…H-30)

### 2.1 H-23 · `public_code` u `/me` → `memberships[]` — PRIHVAĆAM (odluka vlasnika)

`memberships[]` dobiva `public_code` uz `marina_id`. Polje se dodaje, pa `v1` ostaje (I.1).
**Mijenja:** v1 §3.3 (M5), §14.9. Trojka **T-38**.

### 2.2 H-24 · MA-7 oblici — PRIHVAĆAM načela (odluka vlasnika), konačni oblik u §14.9

Načela su prihvaćena bez rezerve:
- `tone` i `state_text` računa server;
- `actions` se šalju po utičnici;
- `control_message` objašnjava zašto upravljanje nije moguće;
- aplikacija ne crta akciju koju ne poznaje.

Oblik ulazi u §14.9 uz ove ispravke, a ostalo je kako je predloženo:

1. **Upravljanje na ormaru ide po sesiji, ne po utičnici.** `allow`, `deny` i `stop` su naredbe
   nad **sesijom** (ugovor ormara: `controls.allow|deny|stop` sa `session_id`), a `enable` i
   `disable` nad utičnicom (`controls.socket_cmd`). Zato:
   - `POST …/control` za `allow`, `deny` i `stop` nosi i `session_id` iz `Socket.session`;
   - ako sesija na utičnici više nije ta, ERP vraća **`409 session_changed`** („The socket's
     state changed. Please check it again.");
   - bez toga bi pritisak na „Allow" mogao pustiti sesiju koja se pojavila nakon što je
     zaposlenik pogledao ekran.
2. **`Socket.kind` je `power | water`.** Voda (`V1`) ima vlastitu naredbu
   (`controls.water_cmd`). U v1 se crta samo `power`, a `water` se dodaje bez nove verzije.
3. **Potvrda alarma je naredba ormaru** (`alarms.acknowledge`, bidirectional). Zato je
   `can_acknowledge` `false`, a `POST …/ack` vraća `403 feature_off`, sve dok marina nema
   `pedestal_control` (2.3). Isti uvjet vrijedi kao za upravljanje.
4. **`sim` (D28)** se prikazuje na pločici i na ormaru. Simulirani podaci se nikad ne miješaju sa
   stvarnima bez oznake: na pločici je vidljiva oznaka „Simulated", ne samo boja.
5. **Kodovi odbijanja:**
   - 409 `cabinet_offline`, `smart_mode_off`, `action_not_available`, `session_changed`;
   - 403 `role_not_allowed`, `feature_off`;
   - 422 za razlog kraći od 3 znaka.

   Svi imaju `message`.
- **Mijenja:** §14.9 (MA-7). Trojka **T-39**.

### 2.3 H-25 · Ključ `pedestal_control` — PRIHVAĆAM (odluka vlasnika)

- Ključ ulazi u `features[]` marine **tek nakon prvog upravljačkog testa** (§10.15 korak 7) i
  samo uz bidirectional na ormaru.
- Uključenje bilježi tko, kada i koji test. Bez ključa:
  - aplikacija nema tab Control;
  - ERP svejedno odbija `POST …/control` i `…/ack` s `403 feature_off`.
- **Važno i za kupca:** NFC punjenje (T-9) ERP izvodi naredbom `controls.allow` ormaru. Zato
  `nfc_charging` u `features[]` također ide tek uz `pedestal_control`. Bez njega `nfc/scan` vraća
  `403 feature_off`.
- **Mijenja:** T-14, §14.9, §10.16. Trojka **T-40**.

### 2.4 H-26 · Razlog admin moda za čitanje: zaglavlje `X-Admin-Reason` — PRIHVAĆAM (odluka vlasnika)

- U admin modu **svaki** zahtjev pod `/marinas/{marina_id}/…` nosi `X-Admin-Reason`
  (URL-encoded UTF-8, 3–200 znakova). Admin bez zaglavlja dobiva **`403 admin_reason_required`**
  („Enter a reason to open this marina in admin mode.").
- **Zaglavlje je jedini mehanizam.** Polje `admin_reason` u tijelu `camera/sessions` otpada, jer
  je oblik još `proposed`, pa ga sad nije skupo maknuti.
- **Audit bez buke:** `audit_log` dobiva zapis pri prvom zahtjevu s novim razlogom za (admin,
  marina, uređaj), a ne na svakom GET-u. Svaki upis i svaka naredba i dalje imaju vlastiti zapis s
  razlogom.
- nginx ne logira zaglavlja, pa razlog ne završava u access logu.
- **Mijenja:** §14.9, v1 §4 (kamera). Trojka **T-41**.

### 2.5 H-27 · `nfc/scan` → 202 `Session` u `pending` — PRIHVAĆAM (prijedlog ERP-a)

- **202** vraća `Session` u stanju `pending` s `message`. **`client_op_id` je prihvaćen:**
  dvostruki dodir daje jednu sesiju, isti `client_op_id` vraća **200** istu sesiju, a
  jedinstvenost drži baza.
- Prijelaz `pending` → `active` | `denied` | `failed` ERP zna iz ormara (kolektor ili webhook kad
  bude uključen).
- **Polling:** svake 2 s, najviše 30 s, pa poruka da ormar još nije potvrdio. Kad dođe MA-6 (WS
  ticket), polling otpada.
- Odbijenice su kao u v4 §3.2, uz `403 feature_off` kad marina nema `nfc_charging` (2.3).
- **Mijenja:** T-9 (tekst koraka 2), §14.9. Trojka **T-42**.

### 2.6 H-28 · Sesije članova — PRIHVAĆAM (prijedlog ERP-a)

- **Nositelj vidi i zaustavlja sve sesije računa**, jer plaća. **Član vidi i zaustavlja samo
  svoje.** Tuđa sesija vraća `404 not_found`, ne 403, da se ne otkriva postoji li.
- **`started_by`:** nositelj vidi ime člana kako ga je sam upisao pri pozivu (`full_name` člana).
  Nositelj je člana pozvao i za njega plaća, pa je to razmjerno. Član u svojim sesijama vidi „You"
  i nikad ne vidi tuđa imena.
- **Mijenja:** T-12, §14.9. Trojka **T-43**.

### 2.7 H-29 · Kredit za člana — NE PRIHVAĆAM prikaz stanja članu; zamjena

- Stanje kredita je novac nositelja, pa ga član ne vidi: `GET …/me/credit` za člana vraća
  **`403 holder_only`**, a aplikacija ne crta karticu.
- Član ipak treba znati može li puniti. Zato:
  - `nfc/scan` odbija s `409 no_credit` i rečenicom „There isn't enough credit on the account.
    Please contact the account holder.";
  - ako je postavljen `spend_limit`, odbija s `409 member_limit_reached` („You have reached the
    limit the account holder set for you.").
- **Mijenja:** T-12, §14.9. Trojka **T-44**.

### 2.8 H-30 · Nositelj mijenja prava člana iz aplikacije — PRIHVAĆAM (prijedlog ERP-a)

- `PATCH …/me/members/{member_id}` s `{rights: {...}}` je dopušten **samo nositelju**. Pravo
  člana nikad ne prelazi pravo nositelja (T-24). Prava nositelja se ne mijenjaju
  (`409 holder_rights_fixed`).
- Svaka promjena ide u `audit_log` (tko, kome, staro → novo). Član dobiva push bez detalja:
  „Your permissions for this marina changed."
- Recepcija u ERP webu to i dalje može (T-24).
- **Mijenja:** T-24, §14.9. Trojka **T-45**.

---

## 3. Izmjene `erp_spec.md` — trojke (gdje / staro / novo)

Sve na `spec/v3-moduli`. Ništa se ne upisuje dok vlasnik ne odobri (§0.0). „§14.9" je poglavlje
ruta mobilne koje se piše kad se odobri T-22. Do tada su oblici u odgovorima v1–v3.

| # | Gdje | Staro | Novo |
|---|---|---|---|
| **T-31** | §10.16 (T-25, MOB-0a) | „MOB-0a … javno tek s 5c" | + „do 5c dostupan **samo preko Tailscalea** (nginx na Tailscale IP-u, `:80`); u koraku 4 vlasnikov telefon → samo ERP `:80`; gradi se nakon 5d; dev build smije `http://` samo za tu adresu" |
| **T-32** | §10.16 (MOB-0b, MOB-1); §14.1 (tablice); §14.3, §14.4 (preuzimanje) | nema zahtjeva iz aplikacije prije M2/M4 | `customer_requests` (+ `customer_request_replies`) uz MOB-0b, `staff_requests` uz MOB-1, `request_photos` zajednička; CRM (M2) i Work (M4) ih preuzimaju bez promjene ugovora; imena „Customer requests" i „Fault reports", nikad „upit" |
| **T-33** | T-14 (`features[]`); §14.9 | popis ključeva bez zahtjeva | + `customer_requests`, `staff_requests`; popisi tipova, kategorija i hitnosti fiksni u kodu, isporučeni kroz `…/requests/options`; server provjerava prema istom popisu |
| **T-34** | §14.9; §14.2 (zasloni) | — | obrada: `marina_manager` (admin samo u admin modu s razlogom), od v3 `requests.customer.handle` / `requests.staff.review`; član šalje i vidi svoje, nositelj ne vidi članove; v1 bez obrade iz mobilne; push `staff_request.created` onima koji smiju potvrditi |
| **T-35** | §4.7 (retencija); §14.9; §14.3 (GDPR) | — | fotografije zahtjeva: 180 dana nakon zatvaranja (kupac `resolved`; zaposlenik `rejected`/`withdrawn`, `accepted` = `reviewed_at` do M4, poslije zatvaranje naloga); u bazi (`BYTEA`), server ponovno kodira bez metapodataka, ≤ 2048 px; gledanje osoblja u `audit_log`; upis u evidenciju obrada; DPIA nije uvjet |
| **T-36** | §14.9; §14.4 | `proposed` → `accepted` \| `rejected` | + `withdrawn` (zaposlenik, samo dok je `proposed`, ruta `…/withdraw`); odbijanje s razlogom ≥ 3 znaka (CHECK); spajanje s postojećim nalogom od M4 |
| **T-37** | §14.9 (I.6, rute zahtjeva) | prijedlog mobilne v3 §3 | prihvaćen uz: `request_id` UUID; `options` prije `{request_id}`; URL fotografije pod prefiksom, traži Bearer i zaglavlja; 201/200 po `client_op_id`; 20 zahtjeva/h i 30 fotografija/h; `413` iz ERP-a u M19 obliku |
| **T-38** | v1 §3.3 (M5, `/me`); §14.9 | `memberships[]`: `marina_id`, `marina_name`, … | + `public_code` |
| **T-39** | §14.9 (MA-7) | „oblici overview/berths dolaze u §14.9" | oblik iz mobilne v4 §2 uz: `session_id` za `allow`/`deny`/`stop` i `409 session_changed`; `Socket.kind: power\|water`; `can_acknowledge` i `…/ack` uz `pedestal_control`; vidljiva oznaka „Simulated" (D28) |
| **T-40** | T-14; §14.9; §10.16 | „upravljanje u MA-7 tek nakon prvog upravljačkog testa" | ključ `pedestal_control`, uključuje se po marini nakon prvog upravljačkog testa i uz bidirectional (tko, kada, koji test); `nfc_charging` samo uz njega; bez ključa `403 feature_off` |
| **T-41** | §14.9; v1 §4 (kamera) | razlog admin moda samo uz kameru (`admin_reason` u tijelu) | zaglavlje `X-Admin-Reason` na svakom zahtjevu pod `/marinas/{id}/…` u admin modu; `403 admin_reason_required`; polje u tijelu otpada; audit pri novom razlogu, ne na svakom GET-u |
| **T-42** | T-9 (§5.1 korak 2); §14.9 | `POST …/nfc/scan {tag_uid}` | + `client_op_id`; 202 `Session` (`pending`) / 200 isti; polling 2 s do 30 s dok nema MA-6 |
| **T-43** | T-12; §14.9 | — | nositelj vidi i zaustavlja sve sesije računa, član samo svoje (tuđa → 404); `started_by` = „You" ili ime člana samo nositelju |
| **T-44** | T-12; §14.9 | — | `…/me/credit` samo nositelju (`403 holder_only` članu); član saznaje kroz `409 no_credit` i `409 member_limit_reached` na `nfc/scan` |
| **T-45** | T-24; §14.9 | „promjenu zastavice radi samo nositelj (ili osoblje marine)" | + kroz aplikaciju: `PATCH …/me/members/{member_id}` samo nositelju; `409 holder_rights_fixed`; `audit_log`; push članu bez detalja |

**Zašto, ukratko, za ono što nije predodluka vlasnika:**
- **`session_id` (T-39):** pritisak mora djelovati na sesiju koju je zaposlenik vidio. Ako
  griješim, polje je višak koji aplikacija ionako ima.
- **Kredit članu (T-44):** novac nositelja nije podatak člana. Ako vlasnik želi da član vidi
  stanje, mijenja se jedan uvjet u jednoj ruti.
- **Ime člana nositelju (T-43):** nositelj je člana pozvao i plaća ga. Ako griješim, `started_by`
  postaje „A member".
- **Fotografije u bazi (T-35):** jedan backup, isti RLS i ništa na disku izvan baze. Ako baza
  naraste više od očekivanog, sadržaj se može preseliti u datoteke bez promjene ugovora.

---

## 4. Sažetak

| # | Odgovor |
|---|---|
| H-16 | PRIHVAĆAM (vlasnik): samo Tailscale do 5c; dev build `http://` samo za tu adresu |
| H-17 | PRIHVAĆAM (vlasnik): rane tablice uz MOB-1 / MOB-0b |
| H-18 | PRIHVAĆAM (vlasnik): fiksno, kroz `…/requests/options` |
| H-19 | PRIHVAĆAM (vlasnik) |
| H-20 | PRIHVAĆAM (vlasnik), uz razradu zatvaranja i spremanja |
| H-21 | PRIHVAĆAM (vlasnik); `withdrawn` + ruta |
| H-22 | PRIHVAĆAM u načelu; sedam usklađenja |
| H-23 | PRIHVAĆAM (vlasnik) |
| H-24 | PRIHVAĆAM načela (vlasnik); `session_id`, `power\|water`, ack uz `pedestal_control`, oznaka „Simulated" |
| H-25 | PRIHVAĆAM (vlasnik); `nfc_charging` također tek uz njega |
| H-26 | PRIHVAĆAM (vlasnik): `X-Admin-Reason`, `admin_reason` u tijelu otpada |
| H-27 | PRIHVAĆAM: 202 `pending`, `client_op_id`, polling 2 s / 30 s |
| H-28 | PRIHVAĆAM: nositelj sve, član svoje; ime člana samo nositelju |
| H-29 | **NE PRIHVAĆAM** prikaz stanja članu; `403 holder_only` + jasne odbijenice na `nfc/scan` |
| H-30 | PRIHVAĆAM: samo nositelj, uz audit i push |
| D32.1 | `customer_not_enabled` povučen; `privacy_mask` samo informacija |
