# Ulaz za specifikaciju v3: četiri modula ERP-a i višemarinski model

Status: ULAZ VLASNIKA ZA SPECIFIKACIJU. Ovo nije odluka o kodu. Code iz ovoga piše
prijedlog izmjene speca (trojke), §1 pitanja i plan faza, pa staje.
Datum: 2026-10-16. Izvor: vlasnik (Lika Digital) i analiza primjera iz prave marine.

> **Bez osobnih podataka:** ovaj dokument opisuje samo FUNKCIONALNOST i STRUKTURU
> (polja, veze, formule). U njemu nema nijednog stvarnog imena, adrese, e-maila,
> OIB-a ni iznosa po kupcu. Isto pravilo vrijedi za spec i testove: testni podaci
> su izmišljeni.

---

## 0. Cilj i položaj

ERP-IOT (dosadašnji rad: ormari, karta, sigurnost) postaje **prvi od četiri modula**.
Ostala tri modula daju ERP-u poslovni smisao:

| # | Modul (izbornik lijevo) | Bit |
|---|---|---|
| 1 | **ERP-IOT** (postoji) | ormari, struja/voda, karta, sigurnost, agent |
| 2 | **CRM** | ugovori (kupci i podugovarači), ponude, plovila, organizacija, dodatne usluge, servisna zona |
| 3 | **Work** (poslovanje) | radni nalozi po zaposlenicima: uplov, isplov, dizalica/transport, čišćenje, servis, računovodstvo |
| 4 | **Finance** | glavna knjiga (ledger), mjesečni računi, plaće, izvješća, performanse po mjesecu i YTD, projekcija do kraja godine prema poslovnom planu |

Svi moduli dijele iste matične podatke: marina, vezovi, plovila, kupci, artikli i
usluge (katalog), zaposlenici i resursi (dizalice, kamion, sobe, parkirna mjesta).

---

## 1. Višemarinski model i uloge (temelj — prije svih modula)

### 1.1 Zahtjev vlasnika
- Krovni ključ cijele baze je **marina_id**. Sve što pripada marini (korisnici,
  zaposlenici, kupci, plovila, ugovori, imovina: ormari, dizalice…) nosi marina_id.
- **Marina Owner** (nova uloga) pripremi svoju marinu i prijavom dobiva "instancu"
  koja vidi SAMO podatke svoje marine, u sva 4 modula.
- **Admin** (platforma, Lika Digital) nakon prijave dobiva izbornik svih marina, na
  glavnom dashboardu odabire marinu i ulazi u "admin mode" te marine (pregled i
  konfiguracija).

### 1.2 Preporuka arhitekta (za trojku)
- "Instanca" = **logička izolacija u jednoj bazi**: marina_id na svakoj tablici +
  PostgreSQL Row-Level Security (RLS) kao drugi zid uz provjeru u aplikaciji.
  Baza po marini se ne preporučuje sada (cijena: migracije i backup × N).
- Test koji pokušava pročitati/izmijeniti tuđu marinu kroz svaku rutu mora pasti
  (cross-tenant test), i na razini baze (RLS) i na razini API-ja.
- Admin "ulazak u marinu" je vidljiv (traka "Admin mode — <marina>") i ide u audit.
- Uloge (prijedlog, Code predlaže matricu prava):
  - Admin (platforma), Marina Owner, Marina Manager (postoji, D20)
  - zaposleničke uloge za Work modul: Recepcija, Glavni mornar (head of deckhands),
    Mornar, Mornar-dizaličar, Vozač kamiona, Voditelj servisa, Serviser,
    Čistač/ica, Računovodstvo
  - podugovarač kao vanjski izvršitelj naloga (bez prijave ili s ograničenom)
- 2FA i pravila D20 vrijede za sve uloge.
- Marina Owner stvara svoje korisnike; Admin stvara marinu i prvog Ownera
  (jednokratni link, D20).

---

## 2. Modul CRM

### 2.1 Dvije velike grupe ugovora
1. **Troškovni ugovori (supply)** — podugovarači i dobavljači: servis i radovi,
   nabava struje, nabava vode, materijal, internet i telekom, sve što marina
   podugovara unutar svojih troškovnih segmenata.
2. **Prihodovni ugovori (top line, kupci)**, po tipovima.

### 2.2 Tipovi ugovora s kupcima (izmjereno na primjeru marine)
Iz primjera Umsatzübersicht i popisa ugovora:
- godišnji (vez u moru), godišnji — hala, godišnji — suhi vez na otvorenom
- 6+6 (6 mj. more + 6 mj. hala), 6+6 na otvorenom, 6+6 PREMIUM (vez + hala)
- višegodišnji (npr. 3-godišnji)
- mjesečni
- dnevni / tranzit (po noćenju)
- dodatno: najam plovila (dnevno/tjedno, sezonske cijene, polog), smještaj (sobe)

Svaki ugovor: broj, kupac, plovilo, vez (ili mjesto u hali / suhi vez), razdoblje
od–do, cjenovna stavka (cjenik), **cjenik vs dogovorena cijena (popust)**,
plan plaćanja (rate po mjesecima), uplate, ostatak duga, napomena, status.

> Nalaz: u primjeru se ugovor NE veže na broj veza (stupac prazan). ERP mora
> vezati ugovor → vez/mjesto, jer iz toga se puni 2D karta.

### 2.3 Tok ugovora (vlasnik)
upit → ponuda → potvrda ili plaćanje → **rezervacija veza** → ugovor aktivan →
računi i uplate → istek ili produljenje.
- Postojeći sustav već ima "povezivanje upitnika s ponudom" (upit → ponuda jednim
  klikom); to je obavezan dio toka.
- Dinamika 2D karte se puni iz ugovora (Reserved, Occupied — correct vessel…).
  Veza na D2 (četiri signala) i D27 (plovilo veza) mora biti izričita.

### 2.4 Plovilo i organizacija
- Plovilo: ime, registracijska oznaka, zastava, vrsta, duljina (i širina),
  motor (vrsta, snaga), dokumenti.
- Vlasnik (ime i prezime ili tvrtka) + **Organizacija**: članovi obitelji i posada.
- Osobni podaci: GDPR (D15), O67 (90 dana nakon uklanjanja), audit čitanja.

### 2.5 Dodatne usluge (CRM vodi prodaju i statistiku)
- Hotelski segment: sobe (kalendar po sobi, sezonski cjenik A/B/C, boravišna
  pristojba po osobi i danu, prijava gostiju).
- Ugostiteljstvo: narudžba hrane i pića, rezervacija stola.
- Kontrola pristupa: prava kupca na vrata (WC, gatovi), rampe, parkiralište
  (dodjela parkirnog mjesta). Veza s D25: CRM DODJELJUJE prava, Safety & Security
  ih PROVODI i nadzire — jedan registar prava, ne dva.
- Ostale usluge (iz primjera): dizalica, žetoni za pranje, tegljenje, parking,
  pranje trupa, gorivo/transport, punjenje baterija, ostalo.
- Najam plovila (vlastita flota marine).

### 2.6 Servisna zona
- Rezervacija servisa, ponuda servisa, servisni nalog, vrste servisa.
- Tri osnovna paketa, po uzoru na autoindustriju (vlasnik); predložak, ne
  tvrdo kodirano:
  - **Servis 1 — redovni pregled:** pregled broda po kritičnim točkama (trup,
    motor, akumulatori, kaljužne pumpe, elektrika, ventili, anode vizualno,
    sigurnosna oprema) + prijava kvarova s fotografijama.
  - **Servis 2:** Servis 1 + vađenje, pranje pod tlakom, antifouling, anode,
    zaštita trupa.
  - **Servis 3:** Servis 1 + Servis 2 + servis motora (ulje, filteri, impeler,
    remen, separator goriva — stavke iz stvarnog računa).
  - Sezonski: konzervacija / dekonzervacija (zimovanje) kao zaseban paket
    (u primjeru: "konzervacija motora, ispiranje motora").
  - Industrija paketima obično nudi: dizanje-pranje-spuštanje, zaštitu trupa
    (antifouling) i zimovanje, a servis motora i anode vodi kao zasebne stavke.
- Registar ponuda servisa (iz primjera): datum, kupac, brod, iznos, status
  (odbijena / radovi gotovi), datum završetka, broj naloga, utrošeni materijal,
  **vanjski dobavljač i iznos vanjske usluge**, račun, plaćeno, način plaćanja,
  avans, provizije. Iz toga KPI: omjer vlastiti / vanjski rad (cilj 50:50),
  prihod servisa, broj naloga godišnje.

### 2.7 CRM dashboard
- Broj otvorenih (neplaćenih) ugovora, plaćenih u tekućem mjesecu, ugovora u
  tekućoj godini.
- Razdvojeno: troškovni (podugovarači) vs prihodovni (kupci), i po tipu ugovora.
- Statistika po razredu duljine broda (1 m razredi): broj, %, prihod, prosječna
  duljina, prosječna cijena — kao list STATISTIK u primjeru.
- Svrha: odnos potražnja–ponuda (vezovi po duljini, lista čekanja, stopa
  produljenja) → financijske projekcije za poslovni plan.

---

## 3. Modul Work (radni nalozi)

- Radni nalog (RN) po zaposlenicima marine; osnovni procesi:
  - **Uplov:** recepcija (dokumenti, prijava), glavni mornar (dodjela veza),
    mornar (vez i privez).
  - **Isplov.**
  - **Spuštanje u more / vađenje:** dizalica + **rezervacija kamiona/prikolice**
    za prijevoz do glavne dizalice; noćni transporti. (U primjeru se to danas
    vodi u Google kalendaru "TRANSPORTI": "u more", "u halu", "noć u more".)
  - **Čišćenje marine** (služba čišćenja; sobe i sanitarije).
  - **Servis** (izvršenje servisnog naloga iz CRM-a).
  - **Računovodstvo** (nalozi na kojima radi financijska služba).
- RN ima: vrstu, status, prioritet, rok, plovilo/vez/ugovor, odgovornog,
  izvršitelje (ljudi), **materijale** (iz kataloga i zalihe), **podugovarače** (iz
  liste podugovarača iz CRM-a), utrošeno vrijeme, kontrolnu listu, fotografije.
- Resursi s kalendarom i rezervacijom: dizalica, kamion/prikolica, travel lift,
  sobe, parkirna mjesta.
- Zaliha: utrošak materijala na RN smanjuje zalihu (u primjeru: zaliha s
  nabavnom i prodajnom cijenom).
- KPI po radnom mjestu (primjer): vrijeme odziva, % izvršenih zadataka, % izvršenja
  plana dizanja/spuštanja, broj transporta (~170 god., ~60 noćnih), incidenti,
  ocjene gostiju. Računaju se iz RN-ova.
  > Pazi: praćenje rada zaposlenika — radno pravo i GDPR (transparentnost,
  > svrha). Za §1.

---

## 4. Modul Finance

### 4.1 Zahtjev vlasnika
Ledger (obrada mjesečnih računa), obrada plaća, financijsko izvješće, performanse
po mjesecu i YTD, projekcija rezultata do kraja godine na osnovi poslovnog plana;
sve na glavnom dashboardu modula. **Umsatzübersicht je osnova obračuna.**

### 4.2 Mapiranje Umsatzübersicht → struktura ERP-a

| List u Excelu | Što sadrži | U ERP-u |
|---|---|---|
| WASSERLIEGEPLATZ-VERTRÄGE 20xx | ugovori za vez u moru sklopljeni te godine: br., kupac, zastava, duljina, brod, vrsta, trajanje, cjenik, dogovoreno, plaćeno, ostatak, dospijeća po mjesecima | `contracts` (kategorija vez u moru) + `payment_schedule` + `payments`; prikaz = filtar po godini sklapanja |
| HALLENSTELLPLATZ-VERTRÄGE 20xx | isto za halu i suhi vez | `contracts` (kategorija hala / otvoreno) |
| JAHRESVERTRÄGE | tekući godišnji ugovori na dan, grupe: vez / 6+6 / hala; godišnja cijena, kontakt, broj veza (prazan!), očekivano produljenje po mjesecu | upit "aktivni ugovori na datum" + **prognoza produljenja** |
| ABRECHNUNGSPLAN | dospijeća iz postojećih ugovora po mjesecu + plan novih / produljenih ugovora po mjesecu | **novčani tijek i plan prihoda** = rate + pipeline produljenja |
| TRANSITLIEGEPLÄTZE | tranzit: kupac, datumi, noćenja, iznos, plaćeno, ostatak, datum plaćanja | `contracts` tip tranzit (ili `stays`) + račun + uplata |
| ZAR 65, ZAR 85 | najam plovila: kupac, država, datum, dani, plovilo, iznos, plaćeno | najam (resurs + rezervacija + račun) |
| NEFAKTURIRANO | plovila u marini bez dokumenata i bez računa | **automatska iznimka**: plovilo prisutno (IoT/kamera/vez zauzet) bez važećeg ugovora → lista "nefakturirano" |
| WEITERE DIENSTLEISTUNGEN | dodatne usluge po kategoriji (dizalica, žetoni, tegljenje, parking, pranje, gorivo, baterije, servis, ostalo) | stavke računa po artiklu iz kataloga, kategorija = grupa artikla |
| UNTERKUNFT | smještaj: gost, razdoblje, noćenja, cijena po noći | sobe: rezervacija + račun (+ boravišna pristojba) |
| REKAPITULATION | po izvoru prihoda: ugovoreno / plaćeno / za naplatu, bez PDV-a | izvješće "prihod po izvoru" na datum |
| STATISTIK | godišnji ugovori po razredu duljine: broj, %, prihod, prosjek duljine i cijene; po tipu (vez, 6+6 hala/otvoreno/premium, hala/otvoreno) | CRM/Finance statistika (§2.7) |

Pravila iz Excela koja ERP mora ispraviti, a ne preslikati:
- PDV se u Excelu računa kao bruto / 1,25 → ERP čuva **neto, stopu i bruto po
  stavci** (stopa iz kataloga artikla), nikad pretpostavljenu stopu.
- Ugovor nema broj veza → ERP veže ugovor na vez/mjesto.
- Ručni "plaćeno / ostatak" → ERP to računa iz uplata.
- Datumi kao tekst ("01.06.-30.09.2026") → pravi datumi od–do.

### 4.3 KPI za Finance dashboard (primjer marine)
Popunjenost veza u moru i suhog veza (%), prihod po raspoloživom vezu (RevPAB),
prihod po metru, EBITDA marža, omjer OPEX/prihod, udio dodatnih prihoda (gorivo,
struja i voda, trgovina, parking), ARPU, stopa produljenja godišnjih ugovora,
lista čekanja po duljini, YoY rast. EBITDA traži troškove → troškovni ugovori iz
CRM-a, ulazni računi i plaće.

### 4.4 Fiskalizacija i plaće — ODLUČENO (vlasnik, 2026-10-16)
- **ERP NIJE informacijski posrednik.** ERP priprema kompletan eRačun i šalje ga
  informacijskom posredniku po izboru marine; ulazne eRačune ERP prima od
  posrednika. (Okvir: od 1.1.2026. obveznici PDV-a u B2B izdaju, primaju i
  fiskaliziraju eRačune — Fiskalizacija 2.0, Zakon o fiskalizaciji NN 89/25.)
- Spec mora opisati: format eRačuna koji posrednik prima, sučelje prema
  posredniku (slanje, status, odbijanje, primanje ulaznih), arhiviranje, i
  povezivanje statusa računa s ugovorom i uplatom.
- Otvoreno za §1: računi za gotovinu/karticu (B2C, fiskalizacija računa 1.0) —
  tko ih fiskalizira; numeracija računa "broj/poslovni prostor/naplatni uređaj".
- Smještaj: boravišna pristojba i prijava gostiju (eVisitor) — za §1.
- **Plaće: ERP ne radi obračun plaća.** Plaće se uvoze (iz obračuna plaća ili od
  knjigovođe) kao trošak u Finance.

---

## 5. Predlošci dokumenata

- Predlošci: ponuda, ugovor, račun, nalog za servis, cjenici (smještaj, najam,
  usluge), popis roba i usluga.
- Svaka marina bira osnovni predložak (baseline) i dodaje svoj brand: logo, podaci
  tvrtke (OIB, IBAN, adresa, sud, temeljni kapital), podnožje.
- Višejezičnost dokumenata (kupci su HR, DE, AT, SI, IT…): za §1, sučelje ostaje
  engleski (ranija odluka).
- Numeracija dokumenata po marini, godini i vrsti.

## 6. Matični podaci koji nedostaju danas
- Katalog artikala i usluga (grupe, šifra, J.mj., cijena, PDV %, KPD šifra,
  dodatna šifra, komisijska roba), zaliha, nabavna cijena.
- Kupci (fizička osoba / tvrtka, država, kontakt, tip kupca), plovila,
  organizacija.
- Zaposlenici i resursi.
- Uvoz iz postojećeg sustava (kupci, plovila, ugovori, katalog, zaliha):
  uvoz s provjerom, probni uvoz, izvještaj razlika. Paralelni rad dok se ne
  potvrdi ispravnost.

## 7. Prijedlog redoslijeda faza (arhitekt) — Code predlaže svoj s razlogom
0. Višemarinski temelj: marina_id svugdje, RLS, Marina Owner, matrica prava,
   cross-tenant testovi, admin mode. **Prije prvog stvarnog kupca u bazi.**
1. Matični podaci + uvoz iz postojećeg sustava + predlošci s brandom.
2. CRM jezgra: upit → ponuda → ugovor → plan plaćanja → uplata → stanje veza na
   karti; dashboard CRM-a.
3. Work: radni nalozi (uplov, isplov, dizalica/transport s rezervacijom resursa,
   čišćenje, servis), materijal i zaliha, podugovarači.
4. Finance I: izvješća iz §4.2 (zamjena za Umsatzübersicht), KPI §4.3.
5. Finance II: ledger, ulazni računi, plaće (uvoz), poslovni plan i projekcija.
6. Dodatne usluge: sobe, najam, ugostiteljstvo, pristup i parking (uz D25).
7. Fiskalni računi u ERP-u — tek nakon odluke §4.4.

## 8. Otvorena pitanja za vlasnika (Code ih stavlja u §1 s trojkom)
1. ~~Fiskalizacija~~ — odlučeno (§4.4): ERP šalje eRačune posredniku i prima
   ulazne od posrednika; otvoreno samo B2C gotovina/kartica.
2. Izolacija: RLS u jednoj bazi (preporuka) ili baza po marini?
3. Rezervacija veza: u trenutku plaćanja (zahtjev vlasnika) — vrijedi li i
   "privremena opcija" s istekom dok ponuda čeka, da se vez ne proda dvaput?
4. ~~Plaće~~ — odlučeno (§4.4): uvoz, bez vlastitog obračuna.
5. Sadržaj paketa Servis 1/2/3 i zimovanja — potvrda.
6. Jezici dokumenata.
7. Prava Marina Owner vs Marina Manager (tko vidi financije, plaće).
8. Prijelaz s postojećeg sustava: paralelni rad koliko dugo, što je izvor istine.

---

## 9. Arhitektura — prijedlog D31 (za trojku i odobrenje)

### 9.1 Situacija
- ERP je na VPS-u; svaka marina ga koristi preko weba i mobitela.
- Ormari danas: ERP ih proziva preko REST-a (pull je istina, D7) + webhook kao
  okidač. Ubuduće: i MQTT (ormar sam šalje).
- Rizik nije količina (gruba procjena: 10 marina × 75 ormara ≈ desetak poruka u
  sekundi), nego: skokovi (mnogo ormara se vrati odjednom, zaostali podaci),
  promet ormara ne smije usporiti korisničko sučelje, duplikati i redoslijed
  poruka, prelazak na MQTT.

### 9.2 Načelo
**Prijem poruka odvojen je od upisa u bazu; između njih je red čekanja.**

```
Ormari --REST pull--+
Ormari --MQTT-------+--> PRIJEM --> RED CEKANJA --> RADNICI --> PostgreSQL
Webhookovi ---------+    (brzo, ne      (upis u paketima,
                          dira bazu)      bez duplikata)
Web + mobitel --> API -----------------------------------> PostgreSQL
                  (zaseban proces, ne ceka ormare)
```

### 9.3 Uvođenje u koracima (tek kad zatreba)
| Korak | Kada | Red čekanja | Razlog |
|---|---|---|---|
| 1 | spec v3 | tablica u PostgreSQL-u + radnici (FOR UPDATE SKIP LOCKED), upis u paketima, idempotentno po event_id | nema novog sustava; dovoljno za stotine poruka u sekundi |
| 2 | kad ormari dobiju MQTT | MQTT broker (npr. Mosquitto ili EMQX) samo na Tailscaleu, korisnik i ACL po ormaru, most u isti red | MQTT je standard za IoT; ormari ga već koriste interno |
| 3 | po mjerenju (deseci marina) | NATS JetStream ili Redpanda | lakši od Kafke; NATS ima ugrađen MQTT |

Kafka se ne predlaže za ovu veličinu: traži 2–4 GB RAM-a sama za sebe (VPS ima
3,8 GB), još jedan sustav za održavanje i zaštitu, i ne govori MQTT.
Ako griješim: zamjena reda u PostgreSQL-u za NATS mijenja samo sloj između
prijema i radnika.

### 9.4 Zaštita baze (odmah, bez novih sustava)
- Odvojeni procesi: API (web i mobitel) / prijem i radnici / agent.
- Ograničen broj veza prema bazi (pool) i statement_timeout.
- Jedinstveni ID svake poruke (event_id, R22) — duplikat se preskače.
- Ograničenje broja poruka po ormaru (jedan pokvareni ormar ne zatrpava sustav).
- Telemetrija u tablicama po mjesecima (particioniranje) s automatskim brisanjem.
- Dashboardi čitaju unaprijed izračunate brojke (karta to već radi).
- Zahtjev prema ormaru (§7.2): store-and-forward — kod prekida veze ormar čuva
  podatke i šalje ih kad se veza vrati.

### 9.5 Ostalo
- Web i mobitel koriste isti API; push obavijesti za mobitel.
- Izmjeriti i zapisati opterećenje: poruka/s danas (74 simulirana ormara) i
  procjena za 10, 50 i 100 marina po 75 ormara; RAM i CPU VPS-a.
- Jedna točka kvara (jedan VPS): što i kada se odvaja (baza na zaseban stroj,
  drugi API čvor).

---

## 10. D32 — Live prikaz veza (kamera), izmjena D30 — ODLUKA VLASNIKA 2026-10-16

### 10.1 Odluka vlasnika
- U ERP-u na 2D karti uz vez/ormar postoji **ikona kamere**: zelena = kamera
  aktivna i dostupna za prijenos; siva = nedostupna; bez ikone = nema kamere.
  Status računa server.
- Klik na ikonu otvara **live prijenos veza** u ERP-u.
- Ista funkcija postoji u mobilnoj aplikaciji ("My Ship live") — kupac gleda
  SVOJ vez; zaposlenik po pravima uloge.

### 10.2 Odnos prema D30
- D30 ostaje za **analizu**: referentne slike, match, zauzeće — procjena na
  ormaru, prema ERP-u samo rezultat.
- D32 dodaje **živi prijenos na zahtjev** kao zasebnu funkciju s vlastitim
  pravilima (ispod). Ništa se ne snima ni ne sprema na ERP-u.

### 10.3 Pravila (prijedlog arhitekta — Code ih piše kao trojke u §1)
- **Put prijenosa (D12):** kamera → ormar (nginx :80, ext ključ za stream) →
  ERP → preglednik/aplikacija. Aplikacija i preglednik nikad ne idu na ormar ni
  na kameru. ERP pokreće povlačenje s ormara SAMO dok netko gleda.
- **Medijski sloj:** prijedlog lagani media relay na VPS-u (npr. MediaMTX) koji
  na zahtjev povlači stream s ormara i daje ga gledateljima (HLS ili WebRTC);
  jedan dolazni stream po kameri bez obzira na broj gledatelja.
- **Ograničenja:** najviše N istovremenih gledatelja po kameri, najdulje
  trajanje gledanja (npr. 2–5 min, pa ponovni klik), niža rezolucija/bitrate
  (veza ormara je često LTE), bez snimanja.
- **Prava:** kupac samo kamera svog veza (vez iz važećeg ugovora); zaposlenik
  po matrici prava; Admin u admin modu. Svako gledanje ide u audit (tko, kada,
  koja kamera, koliko dugo).
- **GDPR (D15):** živi video ljudi u marini je videonadzor. Obavezno: oznaka
  videonadzora u marini; maske privatnosti (privacy mask) na kameri tako da se
  vidi samo vez; zamagljivanje osoba na ormaru prije slanja ako je izvedivo u
  stvarnom vremenu — ako nije, za §1 s prijedlogom; nema snimanja; svrha i
  pravna osnova zapisani.
- **Sigurnost:** stream s ormara samo preko Tailscalea; kratkotrajni potpisani
  URL za gledatelja (vezan uz korisnika i kameru, istječe); nikakve trajne
  adrese kamera u klijentu.
- **Zahtjevi prema ormaru (§7.2):** uključiti `camera.stream_ext` (i status
  kamere) u gateway za ERP; maske privatnosti; zamagljivanje osoba (izvedivost i
  cijena CPU-a na ormaru); stream samo dok ERP traži.
