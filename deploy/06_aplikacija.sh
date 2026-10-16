#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ERP-IOT · 5b korak 6 — korisnici, kod s main-a, venv iz locka (spec §8.4, §10.15)
#
#  Mijenja: sistemski korisnici erp i erp-agent (bez prijave, bez doma);
#  python3.12-venv; /opt/erp-iot = klon grane main (vlasnik root — aplikacija
#  svoj kod ne može mijenjati); /opt/erp-iot/backend/.venv iz requirements.lock.
#  Ne dira bazu, tajne ni systemd (koraci 7–10).
#  Svaki dio prvo pogleda stanje — skripta se smije pokrenuti više puta.
#
#  Pokretanje (kao lika):  bash ~/erp-iot/deploy/06_aplikacija.sh 2>&1 | tee ~/06_aplikacija.txt
#  Povratak: naredbe se ispišu na kraju.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

sec() { printf '\n== %s ==\n' "$1"; }
HERE=$(cd "$(dirname "$0")" && pwd)
cd /   # sudo -u erp / erp-agent ne mogu u ~lika
REPO=https://github.com/Lika-Digital/ERP-IOT.git
APP=/opt/erp-iot
VENV=$APP/backend/.venv
sudo -v

sec "Sistemski korisnici"
for u in erp erp-agent; do
    if id "$u" >/dev/null 2>&1; then
        echo "  $u već postoji"
    else
        sudo useradd --system --user-group --no-create-home --home-dir /nonexistent \
            --shell /usr/sbin/nologin "$u"
        echo "  $u napravljen"
    fi
    echo "  $(id "$u")  shell=$(getent passwd "$u" | cut -d: -f7)"
done

sec "Peer prijava u bazu (korak 5)"
echo "  erp       → $(sudo -u erp psql -X -d erp_iot -Atc 'SELECT current_user')"
echo "  erp-agent → $(sudo -u erp-agent psql -X -U erp_agent -d erp_iot -Atc 'SELECT current_user')"
# i obrnuto: nitko ne smije u tuđu ulogu
if sudo -u erp psql -X -U erp_agent -d erp_iot -Atc 'SELECT 1' >/dev/null 2>&1; then
    echo "  STANI: erp ulazi kao erp_agent — javi"; exit 1
fi
if sudo -u erp-agent psql -X -U erp -d erp_iot -Atc 'SELECT 1' >/dev/null 2>&1; then
    echo "  STANI: erp-agent ulazi kao erp — javi"; exit 1
fi
if psql -X -U erp -d erp_iot -Atc 'SELECT 1' >/dev/null 2>&1; then
    echo "  STANI: lika ulazi kao erp — javi"; exit 1
fi
echo "  tuđe uloge odbijene: erp↛erp_agent, erp-agent↛erp, lika↛erp"

sec "Kod s main-a u $APP"
if [ -d "$APP/.git" ]; then
    sudo git -C "$APP" fetch -q origin main
    sudo git -C "$APP" checkout -q --detach origin/main
    echo "  osvježeno"
else
    sudo git clone -q --branch main "$REPO" "$APP"
    echo "  klonirano"
fi
sudo chown -R root:root "$APP"
sudo chmod -R go-w "$APP"
want=$(git -C ~/erp-iot ls-remote -q "$REPO" refs/heads/main | cut -f1)
have=$(sudo git -C "$APP" rev-parse HEAD)
echo "  main na GitHubu: $want"
echo "  u $APP:          $have  $(sudo git -C "$APP" log -1 --format='%s' | cut -c1-70)"
[ "$want" = "$have" ] || { echo "  STANI: $APP nije na main-u — javi"; exit 1; }
[ -z "$(sudo git -C "$APP" status --porcelain)" ] || { echo "  STANI: izmjene u $APP — javi"; exit 1; }

sec "Python i venv iz locka"
if ! dpkg -s python3.12-venv >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.12-venv >/dev/null
    echo "  python3.12-venv instaliran"
fi
lock_sha=$(sha256sum "$APP/backend/requirements.lock" | cut -d' ' -f1)
if [ -x "$VENV/bin/python" ] && [ "$(sudo cat "$VENV/.lock.sha256" 2>/dev/null)" = "$lock_sha" ]; then
    echo "  venv već odgovara locku"
else
    sudo rm -rf "$VENV"
    sudo python3.12 -m venv "$VENV"
    sudo "$VENV/bin/python" -m pip install -q --upgrade pip
    # --no-deps: lock je PUN tranzitivni popis; ništa izvan njega ne ulazi (kao CI)
    sudo "$VENV/bin/pip" install -q --no-deps --prefer-binary -r "$APP/backend/requirements.lock"
    echo "$lock_sha" | sudo tee "$VENV/.lock.sha256" >/dev/null
    echo "  venv napravljen iz locka"
fi
sudo chown -R root:root "$VENV"
echo "  python: $("$VENV/bin/python" --version)"
echo "  lock sha256: $lock_sha"
echo "  paketa u locku: $(grep -c '==' "$APP/backend/requirements.lock"), u venvu: $("$VENV/bin/pip" list --format=freeze 2>/dev/null | grep -vc '^pip==')"
"$VENV/bin/pip" check | sed 's/^/  pip check: /'

sec "Uvoz kao korisnik erp"
sudo -u erp "$VENV/bin/python" -c "import PIL, psycopg2, fastapi, sqlalchemy, alembic; print('  PIL', PIL.__version__, '· psycopg2', psycopg2.__version__.split()[0], '· fastapi', fastapi.__version__, '· sqlalchemy', sqlalchemy.__version__)"
if sudo -u erp touch "$APP/backend/.pisanje" 2>/dev/null; then
    sudo rm -f "$APP/backend/.pisanje"; echo "  STANI: erp smije pisati u $APP — javi"; exit 1
fi
echo "  erp ne može pisati u $APP"

sec "Slušači"
bash "$HERE/slusaci.sh"

sec "Povratak (ako zatreba)"
cat <<EOF
  sudo rm -rf $APP
  sudo userdel erp-agent && sudo userdel erp
EOF

sec "Kraj"
echo "Korak 6 gotov."
