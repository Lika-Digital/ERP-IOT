#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ERP-IOT · 5b korak 1 — snimka stanja VPS-a
#
#  SAMO ČITA. Ne mijenja ništa na sustavu; može se vrtjeti koliko god puta.
#  Ispis je polazna točka za sve sljedeće korake (runbook spec §8.4).
#
#  Pokretanje (kao lika):  bash ~/erp-iot/deploy/01_stanje.sh 2>&1 | tee ~/01_stanje.txt
#  sudo će jednom tražiti lozinku (sshd -T, ss -p i nft trebaju root za čitanje).
# ─────────────────────────────────────────────────────────────────────────────
set -u

sec() { printf '\n== %s ==\n' "$1"; }

sec "OS"
. /etc/os-release && echo "$PRETTY_NAME"
uname -r
hostnamectl --static

sec "Vrijeme"
timedatectl | grep -E 'Time zone|synchronized|NTP service'

sec "Resursi"
echo "CPU: $(nproc)"
free -h | head -2
df -h / | tail -1
swapon --show --noheadings | grep -q . && swapon --show || echo "swap: nema"

sec "Korisnici s ljuskom"
awk -F: '$7 ~ /(bash|sh)$/ {print $1, "uid=" $3, $7}' /etc/passwd
getent group sudo

sec "SSH (efektivna konfiguracija)"
sudo sshd -T | grep -Ei '^(port|listenaddress|permitrootlogin|passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication|authenticationmethods) '
ls -l /etc/ssh/sshd_config.d/
echo "ključevi za lika: $(grep -c . ~/.ssh/authorized_keys 2>/dev/null || echo 0)"

sec "Slušatelji (TCP/UDP)"
sudo ss -tulpn

sec "Vatrozid"
sudo nft list ruleset | head -80
sudo ufw status 2>/dev/null || echo "ufw: nije instaliran"

sec "Tailscale"
tailscale ip -4
tailscale status --peers=false

sec "DNS (runbook korak 1a)"
ls -l /etc/systemd/resolved.conf.d/ 2>/dev/null
resolvectl status | grep -E 'DNSSEC|DNS Servers|Current DNS' | sort -u
resolvectl query deb.debian.org | head -2

sec "Paketi"
python3 --version
for p in git nftables unattended-upgrades postgresql nginx crowdsec age; do
    v=$(dpkg-query -W -f='${Version} ${db:Status-Abbrev}' "$p" 2>/dev/null)
    case "$v" in *ii*) echo "$p: $v" ;; *) echo "$p: nije instaliran" ;; esac
done

sec "Paketi za korake 5-6 (v25): dostupne verzije, ništa se ne instalira"
apt-cache policy postgresql-16 python3.12-venv 2>/dev/null | grep -E '^[a-z]|Installed|Candidate'
python3 -c 'import ensurepip' 2>/dev/null && echo "ensurepip: da" || echo "ensurepip: nema (treba python3.12-venv)"

sec "Ostaci prijašnjih pokušaja (5b)"
for d in /opt/erp-iot /etc/erp-iot /var/backups/erp; do [ -e "$d" ] && echo "$d: POSTOJI" || echo "$d: nema"; done
id erp 2>/dev/null || echo "korisnik erp: nema"
id erp-agent 2>/dev/null || echo "korisnik erp-agent: nema"

sec "Servisi"
for s in ssh tailscaled unattended-upgrades nftables systemd-resolved; do
    printf '%-22s enabled=%-10s active=%s\n' "$s" \
        "$(systemctl is-enabled "$s" 2>/dev/null)" "$(systemctl is-active "$s" 2>/dev/null)"
done

sec "Ažuriranja"
echo "paketa za nadogradnju: $(apt list --upgradable 2>/dev/null | tail -n +2 | grep -c .)"
[ -f /var/run/reboot-required ] && echo "TREBA RESTART" || echo "restart ne treba"

sec "Kraj"
echo "Gotovo, ništa nije mijenjano."
