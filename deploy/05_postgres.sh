#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ERP-IOT · 5b korak 5 — PostgreSQL 16 (spec §8.3, §8.4, §10.15, O47, D20, D21)
#
#  Mijenja: instalira postgresql-16; samo Unix socket (listen_addresses = '');
#  pg_hba samo peer, bez ijednog host retka; pg_ident erp-agent → erp_agent;
#  uloge erp (vlasnik baze) i erp_agent (D21, PRIJE migracija); baza erp_iot;
#  bez TEMPORARY za PUBLIC (O47). Lozinke ne postoje (D20).
#  Sistemske korisnike erp i erp-agent stvara korak 6 — tek tada se peer
#  prijava može probati.
#  Svaki dio prvo pogleda stanje — skripta se smije pokrenuti više puta.
#
#  Pokretanje (kao lika):  bash ~/erp-iot/deploy/05_postgres.sh 2>&1 | tee ~/05_postgres.txt
#  Povratak: naredbe se ispišu na kraju.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

sec() { printf '\n== %s ==\n' "$1"; }
HERE=$(cd "$(dirname "$0")" && pwd)
cd /   # sudo -u postgres ne može u ~lika
CONF=/etc/postgresql/16/main
psql_pg() { sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 "$@"; }
sudo -v

sec "Paket"
if dpkg -s postgresql-16 >/dev/null 2>&1; then
    echo "  postgresql-16 već instaliran"
else
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql-16 >/dev/null
    echo "  postgresql-16 instaliran"
fi
pg_lsclusters | sed 's/^/  /'
[ -d "$CONF" ] || { echo "  NEMA $CONF — stani i javi"; exit 1; }

sec "Samo Unix socket, samo peer"
echo "listen_addresses = ''" | sudo tee "$CONF/conf.d/10-erp.conf" >/dev/null
for f in pg_hba.conf pg_ident.conf; do
    [ -f "$CONF/$f.orig-erp" ] || sudo cp -p "$CONF/$f" "$CONF/$f.orig-erp"
done
sudo tee "$CONF/pg_hba.conf" >/dev/null <<'EOF'
# ERP-IOT (deploy/05_postgres.sh) — samo Unix socket, samo peer, nijedan host redak.
# Izvornik: pg_hba.conf.orig-erp
# TYPE  DATABASE  USER       METHOD
local   all       postgres   peer
local   erp_iot   erp        peer
local   erp_iot   erp_agent  peer map=erpagent
EOF
sudo tee "$CONF/pg_ident.conf" >/dev/null <<'EOF'
# ERP-IOT (deploy/05_postgres.sh) — sistemski korisnik erp-agent je uloga erp_agent (D21).
# Izvornik: pg_ident.conf.orig-erp
# MAPNAME   SYSTEM-USERNAME   PG-USERNAME
erpagent    erp-agent         erp_agent
EOF
sudo chown postgres:postgres "$CONF/pg_hba.conf" "$CONF/pg_ident.conf"
sudo chmod 640 "$CONF/pg_hba.conf" "$CONF/pg_ident.conf"
sudo systemctl restart postgresql@16-main
for _ in $(seq 1 20); do pg_isready -q && break; sleep 0.5; done
pg_isready | sed 's/^/  /'
echo "  listen_addresses: '$(psql_pg -Atc 'SHOW listen_addresses')'"
echo "  greške u pg_hba:   $(psql_pg -Atc 'SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL')"
echo "  greške u pg_ident: $(psql_pg -Atc 'SELECT count(*) FROM pg_ident_file_mappings WHERE error IS NOT NULL')"
psql_pg -Atc "SELECT '  pg_hba: ' || type || ' ' || array_to_string(database, ',') || ' ' || array_to_string(user_name, ',') || ' ' || auth_method || coalesce(' ' || array_to_string(options, ','), '') FROM pg_hba_file_rules ORDER BY line_number"

sec "Uloge (bez lozinke, D20)"
psql_pg <<'EOF'
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'erp') THEN
        CREATE ROLE erp LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
    -- D21 / runbook 5a: prije migracija, jer erp nema CREATEROLE (migracija 011 je samo provjeri)
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'erp_agent') THEN
        CREATE ROLE erp_agent LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                              NOREPLICATION NOBYPASSRLS NOINHERIT;
    END IF;
END $$;
EOF
psql_pg -Atc "SELECT '  ' || rolname || ': login=' || rolcanlogin || ' super=' || rolsuper || ' createrole=' || rolcreaterole || ' createdb=' || rolcreatedb || ' replication=' || rolreplication || ' bypassrls=' || rolbypassrls || ' inherit=' || rolinherit || ' lozinka=' || (rolpassword IS NOT NULL) FROM pg_authid WHERE rolname IN ('erp','erp_agent') ORDER BY rolname"
too_much=$(psql_pg -Atc "SELECT count(*) FROM pg_authid WHERE rolname IN ('erp','erp_agent') AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls OR rolpassword IS NOT NULL)")
[ "$too_much" = 0 ] || { echo "  STANI: uloga ima više prava nego smije (ili lozinku) — javi"; exit 1; }

sec "Baza erp_iot"
if [ "$(psql_pg -Atc "SELECT count(*) FROM pg_database WHERE datname = 'erp_iot'")" = 1 ]; then
    echo "  baza već postoji"
else
    sudo -u postgres createdb --owner=erp --encoding=UTF8 --template=template0 erp_iot
    echo "  baza napravljena"
fi
# O47: privremene tablice samo vlasniku aplikacije, ne PUBLIC-u (pa ni erp_agent)
psql_pg -c "REVOKE TEMPORARY ON DATABASE erp_iot FROM PUBLIC" -c "GRANT TEMPORARY ON DATABASE erp_iot TO erp"
psql_pg -Atc "SELECT '  vlasnik=' || pg_get_userbyid(datdba) || ' encoding=' || pg_encoding_to_char(encoding) || ' collate=' || datcollate || ' ctype=' || datctype FROM pg_database WHERE datname = 'erp_iot'"
psql_pg -Atc "SELECT '  TEMPORARY: erp=' || has_database_privilege('erp', 'erp_iot', 'TEMPORARY') || ' erp_agent=' || has_database_privilege('erp_agent', 'erp_iot', 'TEMPORARY')"
[ "$(psql_pg -Atc "SELECT has_database_privilege('erp_agent', 'erp_iot', 'TEMPORARY')")" = f ] \
    || { echo "  STANI: erp_agent ima TEMPORARY (O47) — javi"; exit 1; }
psql_pg -Atc "SELECT '  verzija: ' || version()"

sec "Slušači"
bash "$HERE/slusaci.sh"

sec "Povratak (ako zatreba)"
cat <<EOF
  samo baza i uloge:
    sudo -u postgres dropdb erp_iot && sudo -u postgres dropuser erp_agent && sudo -u postgres dropuser erp
  izvorne postavke:
    sudo cp -p $CONF/pg_hba.conf.orig-erp $CONF/pg_hba.conf
    sudo cp -p $CONF/pg_ident.conf.orig-erp $CONF/pg_ident.conf
    sudo rm $CONF/conf.d/10-erp.conf && sudo systemctl restart postgresql@16-main
  sve:
    sudo apt-get purge -y postgresql-16 && sudo rm -rf /etc/postgresql/16 /var/lib/postgresql/16
EOF

sec "Kraj"
echo "Korak 5 gotov."
