#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ERP-IOT · 5b blok A = koraci 8, 9, 10 (spec §8.4, §10.15, §13.1)
#
#   8  baza na head (015) kao erp (erp-run); alembic check; probe sheme (59);
#      AGT-01/02 (prava uloge erp_agent, kao postgres jer AGT-02 radi SET ROLE)
#   9  erp-iot.service na 127.0.0.1:8000; P3 namjerno (downgrade -1 → start
#      mora pasti s porukom → upgrade head → start); /api/health s 127.0.0.1;
#      SystemCallFilter ~@resources ne smije ubiti uvicorn/psycopg2
#  10  erp-agent.service: bez mreže (systemctl show + mrežni namespace procesa),
#      jedan prolaz u journalu
#
#  Staje na PRVOJ grešci (STANI + što javiti). Ponovljiva: što je gotovo, samo
#  se provjeri. P3 (downgrade) ide SAMO dok u bazi nema korisnika — poslije bi
#  downgrade brisao podatke migracije 015.
#
#  Pokretanje (kao lika):  bash ~/erp-iot/deploy/08_blok_a.sh 2>&1 | tee ~/08_blok_a.txt
# ─────────────────────────────────────────────────────────────────────────────
set -Eeuo pipefail

sec() { printf '\n== %s ==\n' "$1"; }
NA_014=0
stani() {
    echo "  STANI: $* — javi"
    if [ "$NA_014" = 1 ]; then
        echo "  Baza je ostala na 014. Vrati je:  sudo ~/erp-iot/deploy/erp-run alembic upgrade head"
    fi
    exit 1
}
# i greška izvan pokreni/stani (set -e) javi se istim putem, s uputom za vraćanje
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
APP=/opt/erp-iot
PY=$APP/backend/.venv/bin/python
RUN=(sudo "$HERE/erp-run")
HEAD_REV=015                       # spec §10.15 korak 8
HEALTH=http://127.0.0.1:8000/api/health
P3_MSG='run `alembic upgrade head`'  # app/database.py, SchemaNotAtHead
sudo -v

sec "Preduvjeti (koraci 5–7)"
for f in jwt_secret.cred erp_encryption_key.cred erp-iot.env; do
    sudo test -s "/etc/erp-iot/$f" || stani "nema /etc/erp-iot/$f (korak 7)"
done
systemctl is-active -q postgresql || stani "postgresql ne radi"
echo "  tajne i erp-iot.env postoje; postgresql radi"
echo "  $APP: $(sudo git -C "$APP" rev-parse --short HEAD)  $(sudo git -C "$APP" log -1 --format=%s | cut -c1-60 || true)"
code_head=$("${RUN[@]}" alembic heads 2>/dev/null | awk '{print $1}' || true)
echo "  head migracija u kodu: $code_head"
[ "$code_head" = "$HEAD_REV" ] || stani "kod traži $code_head, runbook $HEAD_REV"

# ── 8 ──────────────────────────────────────────────────────────────────────
sec "8 · alembic upgrade head (kao erp)"
pokreni "alembic upgrade head" "${RUN[@]}" alembic upgrade head
cur=$("${RUN[@]}" alembic current 2>/dev/null | tail -1 || true)
echo "  alembic current: $cur"
[ "$cur" = "$HEAD_REV (head)" ] || stani "baza nije na $HEAD_REV (head)"

sec "8 · alembic check (modeli = migracije, O17)"
pokreni "alembic check" "${RUN[@]}" alembic check

sec "8 · probe sheme (baza sama drži pravila §4; svaka u transakciji koja se poništi)"
pokreni "probe sheme" "${RUN[@]}" python -c '
import os, sys
sys.path.insert(0, "/opt/erp-iot/scripts")
import schema_probes
from sqlalchemy import create_engine
eng = create_engine(os.environ["DATABASE_URL"])
try:
    res = schema_probes.run(eng)
finally:
    eng.dispose()
bad = [r for r in res if not r[1]]
for name, _, detail in bad:
    print(f"[FAIL] {name} - {detail}")
print(f"probe: {len(res) - len(bad)}/{len(res)} drže")
sys.exit(0 if res and not bad else 1)
'

sec "8 · AGT-01/02 (uloga erp_agent: čita izvore, piše samo alarm)"
# kao postgres: AGT-02 postaje erp_agent (SET ROLE), što erp ne smije; sve se poništi
pokreni "AGT-01/02" sudo -u postgres env PYTHONDONTWRITEBYTECODE=1 "$PY" "$APP/scripts/agent_db_check.py" \
    "postgresql+psycopg2://postgres@/erp_iot?host=/var/run/postgresql"

# ── 9 ──────────────────────────────────────────────────────────────────────
ugradi() {   # ugradi <unit> — kopira iz repoa ako se razlikuje; vraća 0 ako je promijenjen
    local u=$1
    if sudo cmp -s "$HERE/$u" "/etc/systemd/system/$u"; then
        echo "  $u: već ugrađen, isti kao u repou"; return 1
    fi
    sudo install -m 0644 -o root -g root "$HERE/$u" /etc/systemd/system/
    sudo systemctl daemon-reload
    echo "  $u: ugrađen"
}
ceka_health() {   # ceka_health <sekundi>
    local i
    for i in $(seq "$1"); do
        curl -fsS --max-time 2 "$HEALTH" 2>/dev/null && return 0
        sleep 1
    done
    return 1
}

sec "9 · erp-iot.service"
api_novi=0
ugradi erp-iot.service && api_novi=1
pokreni "systemd-analyze verify erp-iot" sudo systemd-analyze verify /etc/systemd/system/erp-iot.service

sec "9 · P3 namjerno: baza na 014 → start mora pasti s porukom"
users=$(sudo -u erp psql -X -d erp_iot -Atc 'SELECT count(*) FROM users') || stani "ne mogu prebrojati korisnike"
if [ "$users" != 0 ]; then
    echo "  preskačem: u bazi ima korisnika ($users) — downgrade bi brisao podatke"
else
    sudo systemctl stop erp-iot 2>/dev/null || true
    NA_014=1
    pokreni "alembic downgrade -1" "${RUN[@]}" alembic downgrade -1
    echo "  baza: $("${RUN[@]}" alembic current 2>/dev/null | tail -1 || true)"
    t0=$(date +%s)
    sudo systemctl start erp-iot || true
    nadjeno=""
    for _ in $(seq 30); do
        nadjeno=$(sudo journalctl -u erp-iot --since "@$t0" -o cat --no-pager | grep -F "$P3_MSG" | head -1 || true)
        [ -n "$nadjeno" ] && break
        sleep 1
    done
    if curl -fsS --max-time 2 "$HEALTH" >/dev/null 2>&1; then
        sudo systemctl stop erp-iot; stani "na 014 aplikacija ODGOVARA na /api/health (P3 ne drži)"
    fi
    sudo systemctl stop erp-iot
    [ -n "$nadjeno" ] || stani "start na 014 nije pao s porukom P3 u 30 s"
    echo "  start odbijen: $nadjeno"
    pokreni "alembic upgrade head" "${RUN[@]}" alembic upgrade head
    NA_014=0
    cur=$("${RUN[@]}" alembic current 2>/dev/null | tail -1 || true)
    echo "  baza vraćena: $cur"
    [ "$cur" = "$HEAD_REV (head)" ] || stani "baza nije na $HEAD_REV (head) nakon P3"
    api_novi=1
fi

sec "9 · start na head i /api/health s 127.0.0.1"
sudo systemctl enable -q erp-iot
# P3 je namjerno rušio servis; bez ovoga ga start-limit može blokirati
sudo systemctl reset-failed erp-iot 2>/dev/null || true
if [ "$api_novi" = 1 ] || ! systemctl is-active -q erp-iot; then
    sudo systemctl restart erp-iot
fi
pid0=$(systemctl show -p MainPID --value erp-iot)
if ! h=$(ceka_health 40); then
    sudo journalctl -u erp-iot -n 40 -o cat --no-pager | uvuci
    stani "/api/health ne odgovara u 40 s"
fi
echo "  $h"
printf '%s' "$h" | grep -q '"status":"ok"' || stani "health nije status ok"

sec "9 · SystemCallFilter ~@resources (uvicorn, psycopg2, kolektor)"
# zabranjeni poziv ubija proces signalom SYS; 20 s rada (kolektor, baza) pa provjera
t1=$(date +%s)
sleep 20
curl -fsS --max-time 2 "$HEALTH" >/dev/null 2>&1 || true
sudo -u erp psql -X -d erp_iot -Atc 'SELECT 1' >/dev/null
pid1=$(systemctl show -p MainPID --value erp-iot)
restarts=$(systemctl show -p NRestarts --value erp-iot)
sys_kill=$(sudo journalctl -u erp-iot --since "@$t1" -o cat --no-pager | grep -E 'status=31/SYS|Bad system call' || true)
sys_kern=$(sudo journalctl -k --since "@$t1" -o cat --no-pager | grep -iE 'seccomp|type=1326' | grep -F 'comm="python' || true)
echo "  MainPID $pid0 → $pid1, NRestarts=$restarts, stanje $(systemctl is-active erp-iot || true)"
if [ "$pid0" != "$pid1" ] || ! systemctl is-active -q erp-iot || [ -n "$sys_kill$sys_kern" ]; then
    printf '%s\n%s\n' "$sys_kill" "$sys_kern" | uvuci
    sudo journalctl -u erp-iot -n 30 -o cat --no-pager | uvuci
    echo "  Prijedlog (ne primjenjujem): u erp-iot.service dodati SystemCallErrorNumber=EPERM"
    echo "  (zabranjeni poziv vraća grešku umjesto da ubije proces) ili maknuti @resources;"
    echo "  odluka je tvoja nakon što vidimo koji poziv."
    stani "proces je pao ili zamijenjen dok radi pod ~@resources"
fi
echo "  nijedan zabranjeni poziv; proces isti, radi; baza dostupna"
echo "  $(sudo systemd-analyze security erp-iot --no-pager 2>&1 | tail -1 || true)"

# ── 10 ─────────────────────────────────────────────────────────────────────
sec "10 · erp-agent.service (D21: samo čita, piše samo alarm, bez mreže)"
ag_novi=0
ugradi erp-agent.service && ag_novi=1
pokreni "systemd-analyze verify erp-agent" sudo systemd-analyze verify /etc/systemd/system/erp-agent.service
sudo systemctl enable -q erp-agent
t2=$(date +%s)
if [ "$ag_novi" = 1 ] || ! systemctl is-active -q erp-agent; then
    sudo systemctl restart erp-agent
    prolaz=""
    for _ in $(seq 60); do
        prolaz=$(sudo journalctl -u erp-agent --since "@$t2" -o cat --no-pager | grep -F 'erp-agent: pass ' | tail -1 || true)
        [ -n "$prolaz" ] && break
        sleep 1
    done
else
    prolaz=$(sudo journalctl -u erp-agent -o cat --no-pager | grep -F 'erp-agent: pass ' | tail -1 || true)
fi
if [ -z "$prolaz" ]; then
    sudo journalctl -u erp-agent -n 30 -o cat --no-pager | uvuci
    stani "agent nije napravio prolaz u 60 s"
fi
echo "  prolaz: $(printf '%s' "$prolaz" | cut -c1-200)"
systemctl is-active -q erp-agent || stani "erp-agent ne radi nakon prolaza"

sec "10 · agent bez mreže"
systemctl show erp-agent -p User -p PrivateNetwork -p IPAddressDeny -p RestrictAddressFamilies -p NRestarts | uvuci
[ "$(systemctl show -p User --value erp-agent)" = erp-agent ] || stani "agent ne radi kao erp-agent"
[ "$(systemctl show -p PrivateNetwork --value erp-agent)" = yes ] || stani "PrivateNetwork nije yes"
[ "$(systemctl show -p RestrictAddressFamilies --value erp-agent)" = AF_UNIX ] || stani "RestrictAddressFamilies nije samo AF_UNIX"
[ -n "$(systemctl show -p IPAddressDeny --value erp-agent)" ] || stani "IPAddressDeny je prazan"
# što proces stvarno vidi: u svom mrežnom namespaceu samo lo, bez adrese prema van
apid=$(systemctl show -p MainPID --value erp-agent)
veze=$(sudo nsenter -t "$apid" -n ip -br link)
printf '%s\n' "$veze" | sed 's/^/  namespace agenta: /'
[ "$(printf '%s\n' "$veze" | awk '{print $1}')" = lo ] || stani "agent vidi mrežno sučelje osim lo"

sec "Slušači"
bash "$HERE/slusaci.sh"

sec "Povratak (ako zatreba)"
cat <<EOF
  sudo systemctl disable --now erp-agent erp-iot
  sudo rm /etc/systemd/system/erp-agent.service /etc/systemd/system/erp-iot.service
  sudo systemctl daemon-reload
  Baza ostaje na $HEAD_REV. SAMO dok nema podataka (prije koraka 14): sudo -u postgres dropdb erp_iot
  pa ponovno 05_postgres.sh i ovaj blok.
EOF

sec "Kraj"
echo "Blok A (koraci 8, 9, 10) gotov."
