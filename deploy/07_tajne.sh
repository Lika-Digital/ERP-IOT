#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ERP-IOT · 5b korak 7 — tajne generirane na stroju (spec §8.3, D20, §10.15)
#
#  Mijenja: /etc/erp-iot (root, 0700) s dvije šifrirane vjerodajnice
#    jwt_secret.cred          — 32 slučajna bajta, heks (64 znaka)
#    erp_encryption_key.cred  — Fernet ključ (32 slučajna bajta, base64url)
#  šifrirane sa `systemd-creds encrypt` (ključ stroja; uz TPM2 i TPM2), i
#  erp-iot.env (nije tajna): PUBLIC_BASE_URL i ALLOWED_ORIGINS = Tailscale IP.
#
#  Vrijednost tajne NITKO ne vidi: nastaje u cjevovodu i ide ravno u
#  systemd-creds; ne ispisuje se, nije u argumentima procesa, nije na disku
#  nešifrirana. Ispisuju se samo duljine i provjera da je aplikacija može čitati.
#
#  Postojeća tajna se NIKAD ne prepisuje: novi ERP_ENCRYPTION_KEY bi učinio
#  nečitljivim sve šifrirano u bazi. Zamjena je zaseban, izričit postupak.
#
#  Pokretanje (kao lika):  bash ~/erp-iot/deploy/07_tajne.sh 2>&1 | tee ~/07_tajne.txt
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

sec() { printf '\n== %s ==\n' "$1"; }
HERE=$(cd "$(dirname "$0")" && pwd)
cd /
DIR=/etc/erp-iot
PY=/opt/erp-iot/backend/.venv/bin/python
sudo -v

sec "systemd-creds"
systemctl --version | head -1 | sed 's/^/  /'
if sudo systemd-creds has-tpm2 >/dev/null 2>&1; then
    echo "  TPM2: da — vjerodajnice vezane uz ključ stroja i TPM"
else
    echo "  TPM2: ne — vjerodajnice vezane uz ključ stroja (/var/lib/systemd/credential.secret, samo root)"
fi

sec "Mapa $DIR"
sudo install -d -m 0700 -o root -g root "$DIR"
sudo stat -c '  %A %U:%G %n' "$DIR"

gen() {   # gen <ime> <python izraz koji vraća vrijednost>
    local name=$1 expr=$2 file="$DIR/$1.cred"
    if sudo test -e "$file"; then
        echo "  $name: već postoji — ne diram"
        return
    fi
    python3 -c "import base64, os, secrets, sys; sys.stdout.write($expr)" \
        | sudo systemd-creds encrypt --name="$name" - "$file"
    sudo chmod 0600 "$file"
    echo "  $name: generiran i šifriran"
}

sec "Tajne"
gen jwt_secret         "secrets.token_hex(32)"
gen erp_encryption_key "base64.urlsafe_b64encode(os.urandom(32)).decode()"
sudo find "$DIR" -name '*.cred' -exec stat -c '  %A %U:%G %s B %n' {} \;

sec "erp-iot.env (nije tajna)"
ts_ip=$(tailscale ip -4)
sudo tee "$DIR/erp-iot.env" >/dev/null <<EOF
# ERP-IOT (deploy/07_tajne.sh) — gdje se UI otvara; ide u jednokratne linkove i CORS.
# 5b: Tailscale adresa VPS-a, nginx :80 (korak 12). U 5c se mijenja na javnu adresu.
PUBLIC_BASE_URL=http://$ts_ip
ALLOWED_ORIGINS=http://$ts_ip
EOF
sudo chmod 0600 "$DIR/erp-iot.env"
sudo sed 's/^/  /' "$DIR/erp-iot.env"
if sudo grep -v '^#' "$DIR/erp-iot.env" | grep -Eiq 'SECRET|KEY|PASSWORD'; then
    echo "  STANI: u erp-iot.env je nešto što liči na tajnu — javi"; exit 1
fi

sec "Provjera: aplikacija (korisnik erp) ih dobiva kao u erp-iot.service"
# isti put kao unit i erp-run: systemd dešifrira za jedan proces korisnika erp
sudo systemd-run --quiet --pipe --wait --collect --service-type=exec \
    -p User=erp -p Group=erp \
    -p LoadCredentialEncrypted=jwt_secret:$DIR/jwt_secret.cred \
    -p LoadCredentialEncrypted=erp_encryption_key:$DIR/erp_encryption_key.cred \
    "$PY" -c '
import os, sys
from cryptography.fernet import Fernet
d = os.environ["CREDENTIALS_DIRECTORY"]
jwt = open(os.path.join(d, "jwt_secret")).read()
key = open(os.path.join(d, "erp_encryption_key")).read()
ok_jwt = len(jwt) == 64 and all(c in "0123456789abcdef" for c in jwt)
f = Fernet(key.encode())
ok_key = f.decrypt(f.encrypt(b"probe")) == b"probe"
print(f"  JWT_SECRET: {len(jwt)} znakova, heks: {ok_jwt}")
print(f"  ERP_ENCRYPTION_KEY: {len(key)} znakova, ispravan Fernet: {ok_key}")
sys.exit(0 if ok_jwt and ok_key else 1)
'
if sudo -u erp test -r "$DIR/jwt_secret.cred" 2>/dev/null; then
    echo "  STANI: korisnik erp može čitati $DIR izravno — javi"; exit 1
fi
echo "  korisnik erp ne može čitati $DIR izravno (samo preko systemd-a)"
if env | grep -Eq '^(JWT_SECRET|ERP_ENCRYPTION_KEY|DEFAULT_ADMIN_PASSWORD)='; then
    echo "  STANI: tajna je u okruženju ove ljuske — javi"; exit 1
fi
echo "  nijedna tajna nije u okruženju ove ljuske"

sec "Slušači"
bash "$HERE/slusaci.sh"

sec "Povratak (ako zatreba)"
cat <<EOF
  SAMO dok u bazi nema šifriranih podataka (prije koraka 14 i upisa ormara):
    sudo rm -rf $DIR
  Poslije toga gubitak erp_encryption_key znači ponovni upis lozinki ormara (§8.3).
EOF

sec "Kraj"
echo "Korak 7 gotov."
