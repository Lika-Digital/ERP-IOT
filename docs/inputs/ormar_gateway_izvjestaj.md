  ---

  IZVJEŠTAJ — ERP ↔ Gateway, stanje koda

  Osnova: 773bca6 (Krk, trenutno) vs main = 282cea5.

  Prvo ono što mijenja opseg cijelog izvještaja: api_catalog.py, external_api_admin.py i sva tri ext_* routera su BITNO NEPROMIJENJENI između 773bca6 i main. Provjereno s git diff --numstat. Zato gotovo svaki
  nalaz niže vrijedi za oboje. Razlike postoje samo u external_api_gateway.py (+15 redaka) i controls.py (+111/−26), i obje su NFC cross-check iz v3.43.

  ---

  1 · USMJERAVANJE PUTANJA

  Mehanizam

  external_api_gateway.py:278:

  internal_path = f"/api/{path}"

  path je sve nakon /api/ext/ (ruta @router.api_route("/api/ext/{path:path}"), linija 203). Dakle gateway ne prosljeđuje „/api/ext/ + interna putanja" — on zamjenjuje /api/ext/ s /api/.

  Match ide na linijama 287–293: iterira ENDPOINT_CATALOG, preskače što nije u allowed_endpoints, i uzima prvi čija putanja odgovara (_path_matches, linija 98 — placeholdere pretvara u [^/]+).

  NALAZ 1.1 — Dvije obitelji endpointa, dva različita pravila (oboje)

  Katalog sadrži 55 unosa i oni se ne poslužuju istim mehanizmom:

  ┌──────────────┬──────┬────────────────────┬────────────────────────────────────────┐
  │              │ broj │ putanja u katalogu │           kako se poslužuje            │
  ├──────────────┼──────┼────────────────────┼────────────────────────────────────────┤
  │ A — proxied  │ 38   │ /api/...           │ kroz gateway (self-proxy na 127.0.0.1) │
  ├──────────────┼──────┼────────────────────┼────────────────────────────────────────┤
  │ B — direktni │ 17   │ /api/ext/...       │ vlastite rute, gateway nije u putu     │
  └──────────────┴──────┴────────────────────┴────────────────────────────────────────┘

  Obitelj B su prave rute registrirane u main.py:904-906, prije catch-alla na 907, s komentarom „must be before gateway catch-all". FastAPI ih rješava prvi, pa gateway nikad ne vidi te pozive.

  Jedno pravilo koje pokriva oboje

  ▎ Vanjska putanja = putanja iz kataloga s /api/ zamijenjenim s /api/ext/ — osim ako putanja u katalogu već počinje s /api/ext/, tada se koristi doslovno.

  NALAZ 1.2 — Putanje koje već počinju s /api/ext/ (oboje)

  Ako ERP pogrešno dvostruko prefiksira, npr. /api/ext/ext/pedestals/1/status:
  - path = ext/pedestals/1/status → internal_path = /api/ext/pedestals/1/status
  - to odgovara katalogu pedestals.status_ext (api_catalog.py:6) → prolazi match
  - gateway proxyja na pravu rutu s internim admin JWT-om (external_api_gateway.py:345, role admin)
  - _check_ext_auth prihvaća samo external_api/api_client (ext_pedestal_endpoints.py:76-80) → 401

  Trostruki prefiks (/api/ext/api/ext/...) → nema match → 403 „Endpoint not allowed". Oba slučaja padaju zatvoreno, ali 401 na dvostrukom prefiksu nije poruka o kredencijalu — to je pogrešna putanja. Ako ERP
  ikad dobije neobjašnjiv 401 na obitelj B, prvo provjeri dvostruki ext.

  NALAZ 1.3 — Gateway match ignorira HTTP metodu (oboje) ⚠

  external_api_gateway.py:287-293 nikad ne usporedi ep["method"]. Tri unosa dijele istu putanju:

  ┌─────────────────────┬────────┬─────────────────────┬────────────────┐
  │        ključ        │ metoda │ allow_bidirectional │ api_catalog.py │
  ├─────────────────────┼────────┼─────────────────────┼────────────────┤
  │ led_schedule.get    │ GET    │ False               │ :33            │
  ├─────────────────────┼────────┼─────────────────────┼────────────────┤
  │ led_schedule.upsert │ PUT    │ True                │ :34            │
  ├─────────────────────┼────────┼─────────────────────┼────────────────┤
  │ led_schedule.delete │ DELETE │ True                │ :35            │
  └─────────────────────┴────────┴─────────────────────┴────────────────┘

  led_schedule.get je prvi u katalogu. Ako je uključen, svaki PUT/DELETE na /api/ext/pedestals/{id}/led-schedule matcha njega, pa korak 5 (linije 308–315) odbija s 403 „Endpoint is read-only" — iako su
  upsert/delete uključeni kao bidirectional.

  Posljedica: LED raspored se preko API-ja ne može mijenjati dok je led_schedule.get uključen. Jedini drugi trostruki/dvostruki sudar u katalogu ne postoji — provjerio sam sve putanje, kolidira samo ovaj
  triplet.

  ---

  2 · KONTROLE

  Tijela zahtjeva

  ┌───────────────────────────┬───────────────────────┬─────────────────────────────────────────────────────────────────┬─────────────────────────────────┐
  │           ključ           │        tijelo         │                      dopuštene vrijednosti                      │            file:line            │
  ├───────────────────────────┼───────────────────────┼─────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ controls.socket_cmd       │ {action, nfc_tag_id?} │ action: activate|stop (regex). nfc_tag_id: str ≤256, opcionalno │ controls.py:558-563             │
  ├───────────────────────────┼───────────────────────┼─────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ controls.water_cmd        │ isti DirectCmdBody    │ activate|stop                                                   │ controls.py:752-756             │
  ├───────────────────────────┼───────────────────────┼─────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ controls.socket_approve   │ nema tijela           │ —                                                               │ controls.py:352                 │
  ├───────────────────────────┼───────────────────────┼─────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ controls.socket_reject    │ {reason?} ≤500        │ slobodan tekst; default "Operator denied"                       │ controls.py:404,423             │
  ├───────────────────────────┼───────────────────────┼─────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ controls.allow            │ nema tijela           │ —                                                               │ controls.py:176                 │
  ├───────────────────────────┼───────────────────────┼─────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ controls.deny             │ {reason?} ≤500        │ slobodan tekst                                                  │ controls.py:159,217             │
  ├───────────────────────────┼───────────────────────┼─────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ controls.stop             │ nema tijela           │ —                                                               │ controls.py:260                 │
  ├───────────────────────────┼───────────────────────┼─────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ sockets.config_patch      │ SocketConfigUpdate    │ pedestal_config.py:482                                          │ :508                            │
  ├───────────────────────────┼───────────────────────┼─────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ valves.config_patch       │ ValveConfigUpdate     │ pedestal_config.py:547                                          │ :575                            │
  ├───────────────────────────┼───────────────────────┼─────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ breakers.socket_reset_ext │ nema tijela           │ —                                                               │ ext_breaker_endpoints.py:172    │
  ├───────────────────────────┼───────────────────────┼─────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ load.auto_stop_ack_ext    │ nema tijela           │ —                                                               │ ext_meter_load_endpoints.py:259 │
  └───────────────────────────┴───────────────────────┴─────────────────────────────────────────────────────────────────┴─────────────────────────────────┘

  NALAZ 2.1 — water_cmd docstring laže o maintenance (oboje)

  controls.py:762 kaže „Valid actions: activate, stop, maintenance", ali koristi isti DirectCmdBody čiji je regex ^(activate|stop)$ (controls.py:560). maintenance vraća 422. Komentar na liniji 559 to i priznaje
  („maintenance is NOT supported by firmware") — dva komentara u istoj datoteci tvrde suprotno. To je peti nalaz „dokumentacija protiv koda".

  Traži li socket_cmd aktivnu sesiju?

  Ne. Docstring (controls.py:659) izrijekom kaže „no session required". Ali activate ima drugi uvjet:

  # controls.py:692-700
  if not sock_state or not sock_state.connected:
      raise HTTPException(409, detail="Socket has no plug inserted")

  Dakle 409 bez utaknutog kabela. stop nema taj uvjet. Pri stop se zatvara aktivna DB sesija ako postoji (controls.py:726-739).

  Odgovori

  - socket_cmd (main): {"status":"sent","socket":…,"action":…,"nfc_cross_check":…} — controls.py:748
  - socket_cmd (773bca6): {"status":"sent","socket":…,"action":…} — bez nfc_cross_check
  - water_cmd: {"status":"sent","valve":…,"action":…} — controls.py:809
  - socket_reject: {"status":"rejected","pedestal_id":…,"socket_id":…} — controls.py:438
  - allow/deny/stop/socket_approve: SessionResponse
  - breakers.socket_reset_ext: {"status":"reset_command_sent","socket_id":…,"initiated_by":"erp-service"} — ext_breaker_endpoints.py:207
  - load.auto_stop_ack_ext: {"status":"acknowledged","socket_id":…} — ext_meter_load_endpoints.py:300

  NALAZ 2.2 — Smart Mode gate nije jednako pokriven (oboje)

  ┌────────────────────────────────┬─────────────────────────────────┬────────────────────────────┬────────────────────────────┐
  │             ključ              │         gate u handleru         │ gate u gatewayu (korak 5b) │ rezultat za ERP kad je OFF │
  ├────────────────────────────────┼─────────────────────────────────┼────────────────────────────┼────────────────────────────┤
  │ controls.socket_cmd            │ da controls.py:673              │ da                         │ 409                        │
  ├────────────────────────────────┼─────────────────────────────────┼────────────────────────────┼────────────────────────────┤
  │ controls.water_cmd             │ da controls.py:769              │ da                         │ 409                        │
  ├────────────────────────────────┼─────────────────────────────────┼────────────────────────────┼────────────────────────────┤
  │ controls.allow/deny/stop       │ ne                              │ da                         │ 409                        │
  ├────────────────────────────────┼─────────────────────────────────┼────────────────────────────┼────────────────────────────┤
  │ controls.socket_approve/reject │ ne                              │ da                         │ 409                        │
  ├────────────────────────────────┼─────────────────────────────────┼────────────────────────────┼────────────────────────────┤
  │ sockets/valves.config_patch    │ ne                              │ da                         │ 409                        │
  ├────────────────────────────────┼─────────────────────────────────┼────────────────────────────┼────────────────────────────┤
  │ breakers.socket_reset_ext      │ da ext_breaker_endpoints.py:189 │ n/p (direktno)             │ 409                        │
  ├────────────────────────────────┼─────────────────────────────────┼────────────────────────────┼────────────────────────────┤
  │ load.auto_stop_ack_ext         │ ne                              │ n/p (direktno)             │ prolazi                    │
  └────────────────────────────────┴─────────────────────────────────┴────────────────────────────┴────────────────────────────┘

  Gateway gate: external_api_gateway.py:321-340, resolver mapa :126-142, 409.

  Za ERP je ishod ispravan svugdje osim load.auto_stop_ack_ext. Ali za dashboard allow/deny/stop/approve/reject nemaju Smart Mode gate — poziv iz UI-a nije blokiran. Tvoja odluka bila je „OFF ⇒ controls 409 +
  grayed"; za te pet akcija 409 postoji samo na ERP putu.

  NALAZ 2.3 — monitor/bidirectional se NE provjerava na direktnim ext write endpointima (oboje) ⚠⚠

  Ovo je nalaz koji dižem odmah jer je granica pristupa.

  Gateway ima fail-closed provjeru moda (external_api_gateway.py:304-315): write prolazi samo ako je mod bidirectional i allow_bidirectional=True. Ta provjera štiti isključivo obitelj A.

  Obitelj B ne prolazi kroz gateway. Njihov jedini filter je _endpoint_enabled, a on čita samo id, nikad mode:

  # ext_breaker_endpoints.py:91-101  (identično u ostala dva routera)
  allowed = json.loads(cfg.allowed_endpoints or "[]")
  return any(e.get("id") == endpoint_id for e in allowed)

  Grep za mode/bidirectional u sva tri ext_* routera vraća samo import redove — nijedne provjere.

  Posljedica: ova tri write endpointa su izvršna čim su uključena, bez obzira što je operater odabrao u UI-u:

  ┌───────────────────────────┬─────────────────┬───────────────────────┐
  │           ključ           │ mod se poštuje? │     druga zaštita     │
  ├───────────────────────────┼─────────────────┼───────────────────────┤
  │ breakers.socket_reset_ext │ ne              │ Smart Mode 409 (:189) │
  ├───────────────────────────┼─────────────────┼───────────────────────┤
  │ load.auto_stop_ack_ext    │ ne              │ nikakva               │
  ├───────────────────────────┼─────────────────┼───────────────────────┤
  │ berths.push_image_ext     │ ne              │ nikakva (upis slike)  │
  └───────────────────────────┴─────────────────┴───────────────────────┘

  Postavljanje na „monitor" u UI-u za ta tri ne čini ništa. To je točno oblik koji si zabranio: kontrola koja izgleda kao da je isključena, a poznati URL je i dalje doseže.

  Nije nužno aktivno — ovisi isključivo o tome je li ikoji od tri u allowed_endpoints. To možeš provjeriti GET-om (dolje).

  Postoji li GET koji vraća Smart Mode?

  Da — pedestals.health. pedestal_config.py:397 → /api/pedestals/health, vanjski poziv GET /api/ext/pedestals/health. Bez parametra, pa je i jedini od ovih koji verifikacija uspješno testira.

  # pedestal_config.py:413-422 — po pedestal_id (numerički PK)
  "opta_connected": bool(cfg.opta_connected),
  "opta_client_id": cfg.opta_client_id,
  "smart_mode":     bool(cfg.smart_mode),
  "last_heartbeat": iso_z(cfg.last_heartbeat),
  "camera_reachable": …, "temp_sensor_reachable": …

  pedestals.status_ext ne vraća smart_mode (ext_pedestal_endpoints.py:300-318) — vraća opta_connected, status, last_heartbeat, door_state, temp/moisture. Ako ERP želi znati smije li uopće slati kontrolu, mora
  na pedestals.health.

  ---

  3 · AUTENTIFIKACIJA

  NALAZ 3.1 — I 422 i 401 su artefakt verifikacije, ne stanje autentifikacije (oboje)

  Korijen je jedan redak:

  # external_api_admin.py:241
  has_param = "{id}" in ep["path"]

  Podstring test na doslovno {id}. {pedestal_id} ne sadrži {id} (sadrži _id}). Pa se preskaču samo putanje s točno {id}, a sve s {pedestal_id}, {marina_id}, {socket_id}, {valve_id}, {cabinet_id}, {session_id},
  {month} se pozivaju doslovno, s vitičastim zagradama u URL-u.

  Odatle i podjela koju si vidio — ona je točno tipska:

  ┌────────────────────────────┬───────────────────────────┬───────┬─────────────────────────────────────────────────────────────────────────────┐
  │           ključ            │    tip path parametra     │ ishod │                                    zašto                                    │
  ├────────────────────────────┼───────────────────────────┼───────┼─────────────────────────────────────────────────────────────────────────────┤
  │ pedestals.status_ext       │ pedestal_id: **str** :262 │ 401   │ {pedestal_id} je valjan string → handler se izvrši → _check_ext_auth odbije │
  ├────────────────────────────┼───────────────────────────┼───────┼─────────────────────────────────────────────────────────────────────────────┤
  │ water.status_ext           │ pedestal_id: **str** :326 │ 401   │ isto                                                                        │
  ├────────────────────────────┼───────────────────────────┼───────┼─────────────────────────────────────────────────────────────────────────────┤
  │ load.marina_alarms_ext     │ marina_id: **str** :153   │ 401   │ isto                                                                        │
  ├────────────────────────────┼───────────────────────────┼───────┼─────────────────────────────────────────────────────────────────────────────┤
  │ breakers.marina_alarms_ext │ marina_id: **str** :242   │ 401   │ isto                                                                        │
  ├────────────────────────────┼───────────────────────────┼───────┼─────────────────────────────────────────────────────────────────────────────┤
  │ load.pedestal_alarms_ext   │ pedestal_id: **int** :195 │ 422   │ FastAPI ne može {pedestal_id} → int, prije handlera                         │
  └────────────────────────────┴───────────────────────────┴───────┴─────────────────────────────────────────────────────────────────────────────┘

  Pet od pet se poklapa. Da — 422 su posljedica doslovnog {pedestal_id}. I 401 su, samo jedan korak dalje: to su endpointi koji su stigli do provjere ovlasti. 422 do nje nikad nisu došli.

  Kojim kredencijalom verifikacija zove?

  external_api_admin.py:227 → _make_internal_admin_jwt() → external_api_gateway.py:86-93, payload "role": "admin", 5 min.

  Ali _check_ext_auth prihvaća samo {"external_api","api_client"} (ext_pedestal_endpoints.py:76-80). Admin JWT je za ext rute neispravan kredencijal po dizajnu. Verifikacija testira obitelj B kredencijalom koji
  ta obitelj ne priznaje — pa 401 nije ni mogao ne nastati.

  Prolaze li s api_client JWT-om?

  Da, obje obitelji.

  - Obitelj A: _GATEWAY_ROLES = {"external_api", "api_client"} — external_api_gateway.py:53, dekodiranje :56-71. Za api_client se ne uspoređuje cfg.api_key (linija 267 važi samo za external_api).
  - Obitelj B: isti set rola — ext_pedestal_endpoints.py:76-80.

  POST /api/auth/service-token postoji na oba commita (auth.py:30; odbija sve osim role == "api_client", auth.py:59).

  Uvjeti koji moraju vrijediti za oboje: ExternalApiConfig.active = 1 (gateway :256; _check_ext_auth → 503) i ključ u allowed_endpoints.

  NALAZ 3.2 — verifikacija nikad ne može pozeleniti, ali ni ne blokira (oboje)

  external_api_admin.py:291: verified = any_pass and not any_fail. Svaki 401/422 postavlja any_fail=True, pa je verified trajno False ako je ijedan parametrizirani-ne-{id} endpoint uključen.

  Ali to ništa ne blokira. Ispravljam vlastitu bilješku iz ranije: activate_config (external_api_admin.py:304-317) ne provjerava verified, a ni gumb nije onemogućen — ApiGateway.tsx:627 nema disabled, linija
  620 samo ispiše tekst „Some endpoints failed — fix before activating." Verifikacija je čisto savjetodavna. Crveni badge te ne sprječava da aktiviraš i koristiš Gateway.

  ---

  4 · OCCUPANCY

  GET /api/ext/pedestals/{id}/berths/occupancy → ext_pedestal_endpoints.py:149-207. Direktna ruta (obitelj B), pedestal_id: str → prima i numerički PK i MAR_KRK_ORM_01 (_resolve_pedestal, :117-147).

  NALAZ 4.1 — tri različita oblika odgovora (oboje)

  // A) nema definiranih vezova — :184-188
  { "pedestal_id": "MAR_KRK_ORM_01", "berths": [],
    "message": "No berth definitions found for this pedestal" }

  // B) vez bez analize — :193-198   (NEMA ključa last_analyzed!)
  { "pedestal_id": "MAR_KRK_ORM_01",
    "berths": [ { "berth_id": 3, "berth_name": "A-12",
                  "occupied": null, "note": "No analysis performed yet" } ] }

  // C) analiziran vez — :200-205    (NEMA ključa note)
  { "pedestal_id": "MAR_KRK_ORM_01",
    "berths": [ { "berth_id": 3, "berth_name": "A-12",
                  "occupied": true, "last_analyzed": "2026-10-10T07:14:22Z" } ] }

  Set ključeva se mijenja po grani — last_analyzed i note se isključuju. ERP parser mora oba tretirati kao opcionalna. pedestal_id je display_id (opta_client_id), ne numerički PK (:207).

  Gdje su traženi podaci

  ┌───────────────────────────┬──────────────┬─────────────────────────────────────────────────────────────────────────────┐
  │           polje           │ u occupancy? │                                gdje postoji                                 │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ state_code                │ ne           │ berth_models.py:43 (0=FREE 1=OK 2=WRONG) → izloženo u BerthOut berths.py:50 │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ match_ok_bit              │ ne           │ berth_models.py:42 → berths.py:49                                           │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ match_score               │ ne           │ berth_models.py:45 → berths.py:52                                           │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ vrijeme zadnjeg ML izlaza │ djelomično   │ last_analyzed (grana C) → berths.py:46                                      │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ is_stale                  │ NE POSTOJI   │ grep po cijelom backend/app/ — nema ga za vezove nigdje                     │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ vez → utičnice            │ ne           │ models/berth_assignment.py, čitaju ga samo marina.py i marina_service.py    │
  └───────────────────────────┴──────────────┴─────────────────────────────────────────────────────────────────────────────┘

  Puni ML izlaz je u berths.list — GET /api/ext/berths, BerthOut (berths.py:39-65): occupied_bit, match_ok_bit, state_code, alarm, match_score, analysis_error, confidence, last_analyzed. To je obitelj A
  (proxied), bez parametra.

  NALAZ 4.2 — veza vez→utičnica nije dostupna preko ext API-ja (main; na 773bca6 model ne postoji)

  berth_assignment čita isključivo marina CORE (marina.py), a nijedna /api/marina/* ruta nije u ENDPOINT_CATALOG. Dakle ERP tu vezu ne može dobiti ni proxyjem ni direktno. BerthOut nosi pedestal_id, ali ne
  socket_id.

  Na 773bca6 models/berth_assignment.py uopće ne postoji (+63 u diffu), pa ni pitanje nema predmet.

  ---

  5 · POVEZANOST UREĐAJA

  NALAZ 5.1 — generičko polje ne postoji; last_heartbeat JE last_seen po dizajnu (oboje)

  Grep za device_connected po cijelom backend/ → nula pogodaka. last_seen postoji samo kao lokalna varijabla u erp_reconciliation.py:153 i parametar u marina_status.py:170, nikad kao stupac.

  Model to izrijekom kaže:

  # models/pedestal_config.py:43-58
  opta_connected = Column(Integer, default=0)
  last_heartbeat = Column(DateTime, nullable=True)  # also serves as "last_seen_at" — see v3.7
  ...
  # `last_seen_at` column — `last_heartbeat` above plays that role.
  status = Column(String, nullable=True, default="online")

  Dakle ime je vendor-specifično, semantika nije. Preslikavanje za ERP:

  ┌──────────────────┬───────────────────────────┬────────────────────────────────────────┐
  │   ERP očekuje    │           čitaj           │                 izvor                  │
  ├──────────────────┼───────────────────────────┼────────────────────────────────────────┤
  │ device_connected │ opta_connected (0/1)      │ pedestals.health, pedestals.status_ext │
  ├──────────────────┼───────────────────────────┼────────────────────────────────────────┤
  │ last_seen        │ last_heartbeat (ISO Z)    │ isto                                   │
  ├──────────────────┼───────────────────────────┼────────────────────────────────────────┤
  │ grubo stanje     │ status ("online" default) │ pedestals.status_ext                   │
  └──────────────────┴───────────────────────────┴────────────────────────────────────────┘

  Jedno upozorenje koje si sam već utvrdio u v3.40: opta_connected i last_heartbeat su se u prošlosti punili iz retained MQTT poruka. ERP ne smije opta_connected == 1 tretirati kao dokaz da je ormar živ — za to
  služi starost last_heartbeat, koju ERP mora sam računati jer heartbeat_age nije izložen (marina_status.py:170, samo CORE).

  ---

  6 · WEBHOOK

  services/webhook_service.py — nepromijenjen između 773bca6 i main. Registracija hooka: main.py:758-759, ws_manager.add_broadcast_hook(dispatch_webhook).

  Okidač

  Svaki ws_manager.broadcast() poziv. Filtar su tri uvjeta, redom (:76-85): active → webhook_url postavljen → event in allowed_events.

  Payload

  // webhook_service.py:94-98
  { "event": "<id iz EVENT_CATALOG>",
    "data":  { … },
    "timestamp": "2026-10-10T07:14:22.123456+00:00" }

  timestamp je vrijeme otpreme, ne nastanka događaja (datetime.now(timezone.utc) u trenutku POST-a). Zaglavlja: X-API-Key, Content-Type (:103-106).

  Jedna iznimka u obliku: berth_occupancy_updated se reže na {pedestal_id, berths:[{berth_id, occupied}]} (_project_berth_occupancy, :50-60) da zone, URL kamere, match_score i putanje embeddinga ne izađu. Ta
  projekcija izostavlja last_analyzed, pa primatelj webhooka ne može ocijeniti svježinu.

  NALAZ 6.1 — potpisivanja nema (oboje) ⚠

  X-API-Key: <cfg.api_key> je statični zajednički ključ u zaglavlju, ne potpis. Nema HMAC-a nad tijelom, nema potpisanog timestampa, nema noncea. ERP ne može utvrditi da payload nije mijenjan, a svaki uhvaćeni
  zahtjev je ponovljiv. Dodatno, :93 — api_key = cfg.get("api_key") or "" → ako ključ nije postavljen, šalje se prazan X-API-Key, a ne nijedan.

  NALAZ 6.2 — retry-a nema (oboje) ⚠

  # webhook_service.py:99-109
  async with httpx.AsyncClient(timeout=5.0) as client:
      await client.post(webhook_url, json=payload, headers={…})
  except Exception as e:
      logger.warning(f"Webhook dispatch failed: {e}")

  Jedan POST, timeout 5 s, iznimka se samo zapiše u log. Nema ponovnog pokušaja, nema backoffa, nema dead-letter reda, nema zapisa o dostavi. Propušten događaj je trajno izgubljen i ERP ne može znati da je
  postojao. Ako ERP na bilo čemu računa kao na potpun tok događaja — naplata, zatvaranje sesija — ovo je tiha rupa. Jedini način da ERP uhvati propušteno je pull.

  NALAZ 6.3 — 11 događaja se emitira, ali ERP ih ne može pretplatiti (oboje)

  Sva 38 EVENT_CATALOG ID-a se stvarno emitiraju kao {"event": …} — katalog je u tom smjeru iskren. Obrnuto ne vrijedi; 49 različitih imena se emitira, 11 ih nema u katalogu:

  meter_telemetry_received      ← per-socket telemetrija brojila
  direct_cmd_sent               ← potvrda da je kontrola poslana
  socket_auto_activate_changed
  guard_alarm, guard_health, guard_state_changed,
  guard_recording_ready, guard_retention_state_changed
  chat_message, error_logged, training_storage_alarm

  meter_telemetry_received i direct_cmd_sent su jedini vrijedni spomena za ERP: prvi je mjerna telemetrija, drugi je jedina push-potvrda da je naredba otišla.

  Stanje na ormaru sada

  Rekao si da external_api_config ima webhook_url = None. Po :80-81 to znači da dispatch_webhook izlazi prije ikakvog POST-a — trenutno se ne šalje nijedan webhook, bez obzira na active=1. Kad URL postaviš,
  allowed_events = ["heartbeat","temperature_reading"] pa idu samo ta dva.

  ---

  PRVO ŠTO BIH PROVJERIO (GET, bez izmjena)

  Većina nalaza ovisi o jednoj vrijednosti koju nemam — allowed_endpoints. S admin JWT-om na ormaru:

  curl -s -H "Authorization: Bearer $ADMIN_JWT" \
    http://127.0.0.1:8000/api/admin/ext-api/config | python3 -m json.tool

  Gledaj tri stvari:
  1. je li allowed_endpoints prazan — ako jest, cijeli ERP put vraća 403/503 i ništa od ovoga nije aktivno;
  2. sadrži li breakers.socket_reset_ext, load.auto_stop_ack_ext ili berths.push_image_ext — ako da, NALAZ 2.3 je aktivan i mod koji je uz njih zapisan se ne primjenjuje;
  3. je li led_schedule.get uključen zajedno s upsert/delete — ako da, NALAZ 1.3 je aktivan.

  ---

  TABLICA — svi 55 endpointa

  bidir? = mora li operater postaviti mod bidirectional da write prođe.
  773bca6? = radi li jednako na ormaru danas.

  Obitelj A — proxied kroz gateway (38)

  ┌─────────────────────────┬────────┬────────────────────────────────────────────────────────────────────────┬────────┬───────────────────────────────┐
  │          ključ          │ metoda │                   putanja koju zove vanjski klijent                    │ bidir? │           773bca6?            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ pedestals.list          │ GET    │ /api/ext/pedestals                                                     │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ pedestals.health        │ GET    │ /api/ext/pedestals/health                                              │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ sessions.active         │ GET    │ /api/ext/sessions/active                                               │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ sessions.pending        │ GET    │ /api/ext/sessions/pending                                              │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ controls.allow          │ POST   │ /api/ext/controls/{session_id}/allow                                   │ da     │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ controls.deny           │ POST   │ /api/ext/controls/{session_id}/deny                                    │ da     │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ controls.stop           │ POST   │ /api/ext/controls/{session_id}/stop                                    │ da     │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ controls.socket_approve │ POST   │ /api/ext/controls/sockets/{pedestal_id}/{socket_id}/approve            │ da     │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ controls.socket_reject  │ POST   │ /api/ext/controls/sockets/{pedestal_id}/{socket_id}/reject             │ da     │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ controls.socket_cmd     │ POST   │ /api/ext/controls/pedestal/{pedestal_id}/socket/{socket_name}/cmd      │ da     │ da, bez NFC cross-checka      │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ controls.water_cmd      │ POST   │ /api/ext/controls/pedestal/{pedestal_id}/water/{valve_name}/cmd        │ da     │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ controls.reset          │ POST   │ /api/ext/controls/pedestal/{id}/reset                                  │ da     │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ controls.led            │ POST   │ /api/ext/controls/pedestal/{id}/led                                    │ da     │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ analytics.daily         │ GET    │ /api/ext/analytics/consumption/daily                                   │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ analytics.summary       │ GET    │ /api/ext/analytics/sessions/summary                                    │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ alarms.active           │ GET    │ /api/ext/alarms/active                                                 │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ alarms.acknowledge      │ POST   │ /api/ext/alarms/{id}/acknowledge                                       │ da     │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ berths.list             │ GET    │ /api/ext/berths                                                        │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ diagnostics.run         │ POST   │ /api/ext/pedestals/{id}/diagnostics/run                                │ da     │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ camera.snapshot         │ GET    │ /api/ext/camera/{pedestal_id}/snapshot                                 │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ camera.stream           │ GET    │ /api/ext/camera/{pedestal_id}/stream                                   │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ sockets.config_list     │ GET    │ /api/ext/pedestals/{pedestal_id}/sockets/config                        │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ sockets.config_patch    │ PATCH  │ /api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/config            │ da     │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ sockets.auto_log        │ GET    │ /api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/auto-activate-log │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ valves.config_list      │ GET    │ /api/ext/pedestals/{pedestal_id}/valves/config                         │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ valves.config_patch     │ PATCH  │ /api/ext/pedestals/{pedestal_id}/valves/{valve_id}/config              │ da     │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ led_schedule.get        │ GET    │ /api/ext/pedestals/{pedestal_id}/led-schedule                          │ —      │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ led_schedule.upsert     │ PUT    │ /api/ext/pedestals/{pedestal_id}/led-schedule                          │ da     │ blokiran ako je .get uključen │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ led_schedule.delete     │ DELETE │ /api/ext/pedestals/{pedestal_id}/led-schedule                          │ da     │ blokiran ako je .get uključen │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ led_schedule.test       │ POST   │ /api/ext/pedestals/{pedestal_id}/led-schedule/test                     │ da     │ da                            │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ usage.history           │ GET    │ /api/ext/pedestals/{pedestal_id}/usage/history                         │ —      │ da¹                           │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ usage.reports_list      │ GET    │ /api/ext/pedestals/{pedestal_id}/usage/reports                         │ —      │ da¹                           │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ usage.report_download   │ GET    │ /api/ext/pedestals/{pedestal_id}/usage/reports/{month}                 │ —      │ da¹                           │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ mobile.qr_claim         │ POST   │ /api/ext/mobile/qr/claim                                               │ da     │ da¹                           │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ mobile.session_live     │ GET    │ /api/ext/mobile/sessions/{session_id}/live                             │ —      │ da¹                           │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ mobile.socket_qr        │ GET    │ /api/ext/mobile/socket/{pedestal_id}/{socket_id}/qr                    │ —      │ da¹                           │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ qr.pedestal_all         │ GET    │ /api/ext/pedestals/{cabinet_id}/qr/all                                 │ —      │ da¹                           │
  ├─────────────────────────┼────────┼────────────────────────────────────────────────────────────────────────┼────────┼───────────────────────────────┤
  │ qr.pedestal_regenerate  │ POST   │ /api/ext/pedestals/{cabinet_id}/qr/regenerate                          │ da     │ da¹                           │
  └─────────────────────────┴────────┴────────────────────────────────────────────────────────────────────────┴────────┴───────────────────────────────┘

  ¹ ruta postoji i usmjeravanje je identično, ali usage_history.py (+30/−7), mobile.py (+168/−28) i qr.py (+7/−2) su mijenjani — oblik odgovora može se razlikovati. Nisam provjeravao polje po polje; nije bilo u
  opsegu.

  Obitelj B — direktne rute, gateway nije u putu (17)

  ┌───────────────────────────────┬────────┬─────────────────────────────────────────────────────────────────────────────────┬──────────────────┬──────────┐
  │             ključ             │ metoda │                        putanja koju zove vanjski klijent                        │      bidir?      │ 773bca6? │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ pedestals.status_ext          │ GET    │ /api/ext/pedestals/{pedestal_id}/status                                         │ —                │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ water.status_ext              │ GET    │ /api/ext/pedestals/{pedestal_id}/water                                          │ —                │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ berths.occupancy_ext          │ GET    │ /api/ext/pedestals/{id}/berths/occupancy                                        │ —                │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ berths.push_image_ext         │ POST   │ /api/ext/pedestals/{pedestal_id}/berths/{berth_id}/reference-image              │ ne — ignorira se │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ camera.frame_ext              │ GET    │ /api/ext/pedestals/{id}/camera/frame                                            │ —                │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ camera.stream_ext             │ GET    │ /api/ext/pedestals/{id}/camera/stream                                           │ —                │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ load.pedestal_get_ext         │ GET    │ /api/ext/pedestals/{pedestal_id}/load                                           │ —                │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ load.socket_get_ext           │ GET    │ /api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/load                       │ —                │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ load.pedestal_alarms_ext      │ GET    │ /api/ext/pedestals/{pedestal_id}/load/alarms                                    │ —                │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ load.marina_alarms_ext        │ GET    │ /api/ext/marinas/{marina_id}/load/alarms                                        │ —                │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ load.socket_history_ext       │ GET    │ /api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/load/history               │ —                │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ load.auto_stop_ack_ext        │ POST   │ /api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/load/auto-stop/acknowledge │ ne — ignorira se │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ breakers.pedestal_list_ext    │ GET    │ /api/ext/pedestals/{pedestal_id}/breakers                                       │ —                │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ breakers.socket_get_ext       │ GET    │ /api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/breaker                    │ —                │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ breakers.socket_reset_ext     │ POST   │ /api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/breaker/reset              │ ne — ignorira se │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ breakers.pedestal_history_ext │ GET    │ /api/ext/pedestals/{pedestal_id}/breaker/history                                │ —                │ da       │
  ├───────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┼──────────────────┼──────────┤
  │ breakers.marina_alarms_ext    │ GET    │ /api/ext/marinas/{marina_id}/breaker/alarms                                     │ —                │ da       │
  └───────────────────────────────┴────────┴─────────────────────────────────────────────────────────────────────────────────┴──────────────────┴──────────┘

  Napomena o tipu pedestal_id: obitelj B u ext_pedestal_endpoints.py prima i MAR_KRK_ORM_01 (str + _resolve_pedestal), a ext_breaker_* i ext_meter_load_* primaju samo numerički PK (int). Isti ERP mora za
  load/breaker koristiti broj, a za status/water/berths/camera smije oboje.

  ---

  Jedna stvar s datumom

  config.py:194 — nfc_cross_check_required: bool = False, s komentarom „REQUIRED FROM: 2026-11-30." Danas je opcionalno, pa nadogradnja Krka na main ne mijenja ništa za ERP osim što socket_cmd počne vraćati
  nfc_cross_check u odgovoru, a nfc_tag_id prestaje biti tiho odbacivan.

  Kad se ta zastavica prebaci na True, svaki activate iz ERP-a bez nfc_tag_id dobiva 400 (controls.py:600-606) — a to je poziv koji uključuje struju kupcu. Na 773bca6 polje se tiho ignorira (Pydantic default
  extra='ignore'), pa ERP koji ga već šalje ne dobiva nikakvu potvrdu da ga netko čita. Ako ERP tim misli da cross-check radi jer ne dobiva grešku — ne radi, i neće do nadogradnje.

✻ Baked for 11m 40s