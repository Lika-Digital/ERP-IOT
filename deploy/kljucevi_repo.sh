#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ERP-IOT · 5b, između bloka A i bloka B — privatni repo, deploy ključevi
#  samo za čitanje (tvoja odluka 2026-10-17)
#
#  Ista skripta, dva poziva:
#
#   1) bash ~/erp-iot/deploy/kljucevi_repo.sh
#      Dva ed25519 ključa: lika (~/erp-iot, deploy skripte) i root (/opt/erp-iot,
#      aplikacija) — svaki se na GitHubu povlači zasebno. GitHubov ključ
#      poslužitelja prikuca se na objavljeni otisak. Ispisuje SAMO javne ključeve.
#
#   → ti na GitHubu: Settings → Deploy keys → Add deploy key, za oba ključa,
#     „Allow write access" NE uključuješ. Zatim Settings → General → Danger
#     Zone → Change visibility → Private.
#
#   2) bash ~/erp-iot/deploy/kljucevi_repo.sh prebaci
#      Oba klona na ssh, svaki preko svog ključa. Provjerava: anonimni https više
#      ne radi (repo je privatan), fetch radi, push je odbijen (ključ samo čita).
#      /opt/erp-iot ostaje na istom commitu — samo se dohvati, ništa ne mijenja.
#
#  Ponovljiva; postojeći ključ se ne prepisuje. Staje na prvoj grešci.
#  Pokretanje (kao lika):  bash ~/erp-iot/deploy/kljucevi_repo.sh [prebaci] 2>&1 | tee ~/kljucevi.txt
# ─────────────────────────────────────────────────────────────────────────────
set -Eeuo pipefail

sec() { printf '\n== %s ==\n' "$1"; }
stani() { echo "  STANI: $* — javi"; exit 1; }
trap 'stani "neočekivana greška (redak $LINENO)"' ERR
HERE=$(cd "$(dirname "$0")" && pwd)
cd /
MOD=${1:-pripremi}

# docs.github.com → „GitHub's SSH key fingerprints", ed25519
GH_FP='SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU'
SSH_URL=git@github.com:Lika-Digital/ERP-IOT.git
HTTPS_URL=https://github.com/Lika-Digital/ERP-IOT.git
APP=/opt/erp-iot
L_REPO=$HOME/erp-iot
L_KEY=$HOME/.ssh/erp_iot_deploy   L_KH=$HOME/.ssh/known_hosts_github
R_KEY=/root/.ssh/erp_iot_deploy   R_KH=/root/.ssh/known_hosts_github
ssh_cmd() { echo "ssh -i $1 -o IdentitiesOnly=yes -o UserKnownHostsFile=$2 -o StrictHostKeyChecking=yes"; }
sudo -v

pripremi() {
    sec "GitHubov ključ poslužitelja (prikucan na objavljeni otisak)"
    local line fp
    line=$(ssh-keyscan -t ed25519 github.com 2>/dev/null | grep -E '^github\.com ssh-ed25519 ' | head -1 || true)
    [ -n "$line" ] || stani "ssh-keyscan github.com nije vratio ed25519 ključ"
    fp=$(printf '%s\n' "$line" | ssh-keygen -lf - | awk '{print $2}')
    echo "  dobiven: $fp"
    echo "  očekuje: $GH_FP"
    [ "$fp" = "$GH_FP" ] || stani "otisak GitHubova ključa NIJE objavljeni — ne nastavljam"
    install -d -m 0700 "$HOME/.ssh"
    printf '%s\n' "$line" > "$L_KH"; chmod 0644 "$L_KH"
    sudo install -d -m 0700 -o root -g root /root/.ssh
    printf '%s\n' "$line" | sudo tee "$R_KH" >/dev/null; sudo chmod 0644 "$R_KH"
    echo "  upisan u $L_KH i $R_KH"

    sec "Deploy ključevi (privatni ostaju na stroju, nikad se ne ispisuju)"
    if [ -e "$L_KEY" ]; then
        echo "  lika: već postoji — ne diram"
    else
        ssh-keygen -q -t ed25519 -N '' -C "erp-iot VPS lika ~/erp-iot (read-only)" -f "$L_KEY"
        echo "  lika: napravljen"
    fi
    chmod 0600 "$L_KEY"
    if sudo test -e "$R_KEY"; then
        echo "  root: već postoji — ne diram"
    else
        sudo ssh-keygen -q -t ed25519 -N '' -C "erp-iot VPS root /opt/erp-iot (read-only)" -f "$R_KEY"
        echo "  root: napravljen"
    fi
    sudo chmod 0600 "$R_KEY"
    stat -c '  %A %U %n' "$L_KEY"
    sudo stat -c '  %A %U %n' "$R_KEY"

    sec "JAVNI ključevi — za GitHub → Settings → Deploy keys (bez write access)"
    echo "  Naslov: VPS lika (~/erp-iot)"
    sed 's/^/    /' "$L_KEY.pub"
    echo "  Naslov: VPS root (/opt/erp-iot)"
    sudo sed 's/^/    /' "$R_KEY.pub"
    echo
    echo "  Nakon toga: Settings → General → Change visibility → Private,"
    echo "  pa:  bash ~/erp-iot/deploy/kljucevi_repo.sh prebaci 2>&1 | tee ~/kljucevi_prebaci.txt"
}

prebaci() {
    for f in "$L_KEY" "$L_KH"; do [ -s "$f" ] || stani "nema $f — prvo bez argumenta"; done
    for f in "$R_KEY" "$R_KH"; do sudo test -s "$f" || stani "nema $f — prvo bez argumenta"; done

    sec "Repo je privatan (anonimni https odbijen)"
    if GIT_TERMINAL_PROMPT=0 git -c credential.helper= ls-remote "$HTTPS_URL" >/dev/null 2>&1; then
        stani "repo je još javan — prvo Settings → Change visibility → Private"
    fi
    echo "  anonimni https: odbijen"

    sec "~/erp-iot (lika) → ssh, svoj ključ"
    local L_SSH R_SSH old
    L_SSH=$(ssh_cmd "$L_KEY" "$L_KH")
    git -C "$L_REPO" remote set-url origin "$SSH_URL"
    git -C "$L_REPO" config core.sshCommand "$L_SSH"
    git -C "$L_REPO" fetch -q origin || stani "fetch u ~/erp-iot ne radi (je li ključ lika dodan?)"
    echo "  origin: $(git -C "$L_REPO" remote get-url origin)"
    echo "  main na GitHubu: $(git -C "$L_REPO" ls-remote -q origin refs/heads/main | cut -f1)"

    sec "$APP (root) → ssh, svoj ključ; commit se ne mijenja"
    R_SSH=$(ssh_cmd "$R_KEY" "$R_KH")
    old=$(sudo git -C "$APP" rev-parse HEAD)
    sudo git -C "$APP" remote set-url origin "$SSH_URL"
    sudo git -C "$APP" config core.sshCommand "$R_SSH"
    sudo git -C "$APP" fetch -q origin main || stani "fetch u $APP ne radi (je li ključ root dodan?)"
    [ "$(sudo git -C "$APP" rev-parse HEAD)" = "$old" ] || stani "$APP se pomaknuo"
    echo "  origin: $(sudo git -C "$APP" remote get-url origin)"
    echo "  HEAD ostaje: $old"

    sec "Ključevi samo čitaju (push --dry-run mora biti odbijen; ništa se ne šalje)"
    local out
    for who in lika root; do
        if [ "$who" = lika ]; then
            out=$(git -C "$L_REPO" push --dry-run origin HEAD:refs/heads/zz-provjera-deploy-kljuca 2>&1) && ok=1 || ok=0
        else
            out=$(sudo git -C "$APP" push --dry-run origin HEAD:refs/heads/zz-provjera-deploy-kljuca 2>&1) && ok=1 || ok=0
        fi
        if [ "$ok" = 1 ]; then
            stani "ključ $who SMIJE pisati — na GitHubu isključi „Allow write access“"
        fi
        echo "  $who: odbijen — $(printf '%s\n' "$out" | grep -iE 'read.only|denied|permission' | head -1 | cut -c1-120)"
    done

    sec "Slušači"
    bash "$HERE/slusaci.sh"

    sec "Povratak (ako zatreba)"
    cat <<EOF
  Na GitHubu obriši deploy ključ (svaki zasebno). Na VPS-u:
    git -C ~/erp-iot remote set-url origin $HTTPS_URL && git -C ~/erp-iot config --unset core.sshCommand
    sudo git -C $APP remote set-url origin $HTTPS_URL && sudo git -C $APP config --unset core.sshCommand
  (https radi samo dok je repo javan)
EOF
}

case "$MOD" in
    pripremi) pripremi ;;
    prebaci)  prebaci ;;
    *) echo "uporaba: kljucevi_repo.sh [prebaci]" >&2; exit 2 ;;
esac

sec "Kraj"
echo "kljucevi_repo.sh ($MOD) gotov."
