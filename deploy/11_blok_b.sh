#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ERP-IOT · 5b blok B = koraci 11 i 12 (spec §7.0, §8.1, §8.2, O43)
#
#  11  frontend/dist koji je CI izgradio i provjerio (gate, browser check) s grane
#      `dist` — preko deploy ključa lika, bez tokena. Uzima se build čije je stablo
#      frontend/ JEDNAKO kodu u /opt/erp-iot (git rev-parse HEAD:frontend);
#      sha256 se provjeri prije raspakiravanja, sadržaj tara prije nego dotakne disk.
#      /var/www/erp-iot/releases/<sha256>, `current` se prebaci atomarno.
#  12  nginx SAMO na <Tailscale IP>:80: statika + /api + /ws prema 127.0.0.1:8000,
#      /api/webhooks/ 404, ograničenje prijave po IP-u (O43). Zadani site na
#      0.0.0.0:80 se nikad ne pokrene (apt ne smije startati nginx).
#
#  Preduvjeti: blok A (erp-iot radi) i kljucevi_repo.sh prebaci (~/erp-iot preko ssh).
#  Staje na prvoj grešci; ponovljiva. Na kraju slusaci.sh i povratak.
#
#  Pokretanje (kao lika):  bash ~/erp-iot/deploy/11_blok_b.sh 2>&1 | tee ~/11_blok_b.txt
# ─────────────────────────────────────────────────────────────────────────────
set -Eeuo pipefail

sec() { printf '\n== %s ==\n' "$1"; }
stani() { echo "  STANI: $* — javi"; exit 1; }
trap 'stani "neočekivana greška (redak $LINENO)"' ERR
uvuci() { sed 's/^/    /'; }
pokreni() {   # pokreni <opis> <naredba...> — ispis uvučen; greška = STANI
    local opis=$1 out; shift
    if ! out=$("$@" 2>&1); then
        printf '%s\n' "$out" | tail -40 | uvuci
        stani "$opis nije prošlo"
    fi
    [ -z "$out" ] || printf '%s\n' "$out" | uvuci
}
HERE=$(cd "$(dirname "$0")" && pwd)
cd /
REPO=$HOME/erp-iot
APP=/opt/erp-iot
WEB=/var/www/erp-iot
SSH_URL=git@github.com:Lika-Digital/ERP-IOT.git
TMP=$(mktemp -d)
NAS_POLICY=0
pocisti() {
    rm -rf "$TMP"
    if [ "$NAS_POLICY" = 1 ]; then sudo rm -f /usr/sbin/policy-rc.d; fi
}
trap pocisti EXIT
sudo -v

sec "Preduvjeti (blok A, privatni repo)"
TS_IP=$(tailscale ip -4)
echo "  Tailscale IP: $TS_IP"
want_url=$(sudo sed -n 's/^PUBLIC_BASE_URL=//p' /etc/erp-iot/erp-iot.env)
[ "$want_url" = "http://$TS_IP" ] || stani "erp-iot.env kaže $want_url, Tailscale je $TS_IP"
systemctl is-active -q erp-iot || stani "erp-iot ne radi (blok A)"
curl -fsS --max-time 3 http://127.0.0.1:8000/api/health | grep -q '"status":"ok"' || stani "/api/health na 127.0.0.1 ne odgovara"
[ "$(git -C "$REPO" remote get-url origin)" = "$SSH_URL" ] || stani "~/erp-iot nije na ssh (kljucevi_repo.sh prebaci)"
echo "  erp-iot radi; ~/erp-iot čita preko deploy ključa"

# ── 11 ─────────────────────────────────────────────────────────────────────
sec "11 · dist s grane dist (build koji je prošao gate)"
pokreni "git fetch origin dist" git -C "$REPO" fetch -q origin dist
tree=$(sudo git -C "$APP" rev-parse HEAD:frontend)
echo "  $APP: $(sudo git -C "$APP" rev-parse --short HEAD), stablo frontend/ $tree"
git -C "$REPO" cat-file -e "FETCH_HEAD:$tree/erp-iot-dist.tar.gz" 2>/dev/null \
    || stani "na grani dist nema builda za stablo $tree (je li CI objavio dist?)"
for f in erp-iot-dist.tar.gz erp-iot-dist.tar.gz.sha256 SOURCE; do
    git -C "$REPO" show "FETCH_HEAD:$tree/$f" > "$TMP/$f"
done
sed 's/^/  SOURCE: /' "$TMP/SOURCE"
grep -qx "frontend_tree=$tree" "$TMP/SOURCE" || stani "SOURCE ne pripada stablu $tree"
chk=$(cd "$TMP" && sha256sum -c erp-iot-dist.tar.gz.sha256 2>&1) || stani "sha256 se NE slaže: $chk"
echo "  sha256: $chk"
sha=$(cut -d' ' -f1 "$TMP/erp-iot-dist.tar.gz.sha256")

# sadržaj prije raspakiravanja: samo dist/…, bez apsolutnih putanja, bez .., samo
# obične datoteke i mape (bez linkova i uređaja)
popis=$(tar -tzf "$TMP/erp-iot-dist.tar.gz")
if printf '%s\n' "$popis" | grep -vE '^dist(/|$)' | grep -q .; then stani "u taru je nešto izvan dist/"; fi
if printf '%s\n' "$popis" | grep -qE '(^|/)\.\.(/|$)'; then stani "u taru je putanja s .."; fi
if tar -tvzf "$TMP/erp-iot-dist.tar.gz" | cut -c1 | grep -qv '[-d]'; then stani "u taru je link ili uređaj"; fi
printf '%s\n' "$popis" | grep -qx 'dist/index.html' || stani "u taru nema dist/index.html"
echo "  tar: $(printf '%s\n' "$popis" | grep -vc '/$') datoteka, sve pod dist/, bez linkova"

REL=$WEB/releases/$sha
if sudo test -f "$REL/index.html"; then
    echo "  $REL već postoji"
else
    sudo install -d -m 0755 -o root -g root "$WEB" "$WEB/releases" "$REL.tmp"
    sudo tar -xzf "$TMP/erp-iot-dist.tar.gz" -C "$REL.tmp" --strip-components=1 \
        --no-same-owner --no-same-permissions
    sudo chown -R root:root "$REL.tmp"
    sudo find "$REL.tmp" -type d -exec chmod 0755 {} +
    sudo find "$REL.tmp" -type f -exec chmod 0644 {} +
    sudo mv -T "$REL.tmp" "$REL"
    echo "  raspakirano u $REL"
fi
sudo ln -sfn "$REL" "$WEB/current.novi"
sudo mv -T "$WEB/current.novi" "$WEB/current"
echo "  current → $(readlink "$WEB/current")"

# ── 12 ─────────────────────────────────────────────────────────────────────
sec "12 · nginx (bez zadanog sitea na 0.0.0.0:80)"
if dpkg -s nginx >/dev/null 2>&1; then
    echo "  nginx već instaliran: $(dpkg-query -W -f='${Version}' nginx)"
else
    # apt bi nginx odmah pokrenuo sa zadanim siteom na 0.0.0.0:80 — a vatrozida još
    # nema (korak 3 je na kraju). policy-rc.d to zabrani dok ne postavimo svoje.
    [ -e /usr/sbin/policy-rc.d ] && stani "/usr/sbin/policy-rc.d već postoji — ne diram ga"
    printf '#!/bin/sh\nexit 101\n' | sudo tee /usr/sbin/policy-rc.d >/dev/null
    sudo chmod 0755 /usr/sbin/policy-rc.d
    NAS_POLICY=1
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx >/dev/null
    sudo rm -f /usr/sbin/policy-rc.d
    NAS_POLICY=0
    echo "  nginx instaliran (nije pokrenut): $(dpkg-query -W -f='${Version}' nginx)"
fi
sudo rm -f /etc/nginx/sites-enabled/default
sed "s/@TS_IP@/$TS_IP/g" "$HERE/nginx-erp-iot.conf" | sudo tee /etc/nginx/sites-available/erp-iot >/dev/null
sudo ln -sfn /etc/nginx/sites-available/erp-iot /etc/nginx/sites-enabled/erp-iot
sudo install -d -m 0755 /etc/systemd/system/nginx.service.d
sed "s/@TS_IP@/$TS_IP/g" "$HERE/nginx-tailscale.conf" | sudo tee /etc/systemd/system/nginx.service.d/erp-tailscale.conf >/dev/null
sudo systemctl daemon-reload
echo "  site erp-iot ugrađen; zadani site maknut; drop-in čeka tailscale0"

sec "12 · nginx -t i svi listen u konfiguraciji"
pokreni "nginx -t" sudo nginx -t
listens=$(sudo nginx -T 2>/dev/null | grep -E '^[[:space:]]*listen[[:space:]]' | sed 's/^[[:space:]]*//')
printf '%s\n' "$listens" | sed 's/^/  /'
if printf '%s\n' "$listens" | grep -vqx "listen $TS_IP:80;"; then
    stani "u konfiguraciji je listen osim $TS_IP:80"
fi

sudo systemctl enable -q nginx
if systemctl is-active -q nginx; then sudo systemctl reload nginx; else sudo systemctl start nginx; fi
systemctl is-active -q nginx || stani "nginx ne radi"

sec "12 · provjere preko Tailscale adrese"
B=http://$TS_IP
kod() { curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$@" || true; }
[ "$(kod "$B/")" = 200 ] || stani "$B/ nije 200"
curl -fsS --max-time 5 "$B/" | grep -q 'id="root"' || stani "$B/ nije index.html aplikacije"
echo "  $B/            200, index.html aplikacije"
[ "$(kod "$B/login")" = 200 ] || stani "$B/login nije 200 (SPA fallback)"
echo "  $B/login       200 (rute preglednika → index.html)"
asset=$(printf '%s\n' "$popis" | grep -E '^dist/assets/.+\.js$' | head -1 | sed 's#^dist##')
[ -n "$asset" ] && [ "$(kod "$B$asset")" = 200 ] || stani "asset $asset nije 200"
echo "  $B$asset  200"
h=$(curl -fsS --max-time 5 "$B/api/health") || stani "$B/api/health ne odgovara"
printf '%s' "$h" | grep -q '"status":"ok"' || stani "health preko nginxa nije ok"
echo "  $B/api/health  ok"
# /ws: bez tokena backend odbija rukovanje (403) — znači da je Upgrade stigao do uvicorna
ws=$(kod -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' \
        -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' "$B/ws")
[ "$ws" = 403 ] || stani "$B/ws vraća $ws, očekujem 403 od backenda (Upgrade ne prolazi?)"
echo "  $B/ws          403 bez tokena (Upgrade stiže do backenda)"
[ "$(kod -X POST "$B/api/webhooks/cabinet/1")" = 404 ] || stani "webhook kroz UI blok nije 404"
echo "  $B/api/webhooks/…  404 (webhook nije u ovom bloku)"
curl -fsSI --max-time 5 "$B/" | grep -qi '^x-content-type-options: nosniff' || stani "nema sigurnosnih zaglavlja"
echo "  sigurnosna zaglavlja: da"

sec "12 · O43: prijava po IP-u (10/min, burst 5)"
# prazno tijelo → 422 u aplikaciji, ništa u bazi; nginx broji svaki pokušaj
kodovi=""
for _ in $(seq 12); do
    kodovi="$kodovi $(kod -X POST -H 'Content-Type: application/json' -d '{}' "$B/api/auth/login")"
done
echo "  12 pokušaja:$kodovi"
case "$kodovi" in *429*) ;; *) stani "nijedan 429 — ograničenje ne radi" ;; esac
first=$(echo "$kodovi" | awk '{print $1}')
[ "$first" != 429 ] || stani "već prvi pokušaj je 429"

sec "12 · javno zatvoreno"
pub=$(ip -4 route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')
if curl -sS -o /dev/null --max-time 3 "http://$pub/" 2>/dev/null; then
    stani "http://$pub/ (javna adresa) odgovara"
fi
echo "  http://$pub/ (javna adresa): nema odgovora"

sec "Slušači"
bash "$HERE/slusaci.sh"

sec "Povratak (ako zatreba)"
cat <<EOF
  sudo systemctl disable --now nginx
  sudo rm /etc/nginx/sites-enabled/erp-iot /etc/nginx/sites-available/erp-iot
  sudo rm -r /etc/systemd/system/nginx.service.d && sudo systemctl daemon-reload
  sudo rm -r $WEB          # statika; aplikacija i baza ostaju
  (apt-get purge nginx samo ako ga više ne želiš; zadani site bi se vratio na 0.0.0.0:80)
EOF

sec "Kraj"
echo "Blok B (koraci 11, 12) gotov. S PC-a otvori: http://$TS_IP"
