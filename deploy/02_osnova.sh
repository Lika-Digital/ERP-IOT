#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ERP-IOT · 5b korak 2 — osnova sustava (spec §8.2, §8.4, §10.15)
#
#  Mijenja: vremensku zonu (UTC), NTP, swap 1 GB (swappiness 10),
#  automatska sigurnosna ažuriranja. DNS (runbook 1a) samo provjerava.
#  Svaki dio prvo pogleda stanje i ne radi ništa što je već tako —
#  skripta se smije pokrenuti više puta.
#
#  Pokretanje (kao lika):  bash ~/erp-iot/deploy/02_osnova.sh 2>&1 | tee ~/02_osnova.txt
#  Povratak: naredbe se ispišu na kraju.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

sec() { printf '\n== %s ==\n' "$1"; }
sudo -v

sec "DNS (runbook 1a) — samo provjera"
if [ -f /etc/systemd/resolved.conf.d/dns.conf ]; then
    sed 's/^/  /' /etc/systemd/resolved.conf.d/dns.conf
else
    echo "  NEMA /etc/systemd/resolved.conf.d/dns.conf — stani i javi (runbook 1a)"; exit 1
fi
resolvectl query deb.debian.org >/dev/null && echo "  DNS radi"

sec "Vremenska zona i NTP"
tz_before=$(timedatectl show -p Timezone --value)
echo "  prije: $tz_before"
[ "$tz_before" = "UTC" ] || sudo timedatectl set-timezone UTC
sudo timedatectl set-ntp true
timedatectl | grep -E 'Time zone|synchronized|NTP service' | sed 's/^/  /'

sec "Swap 1 GB, swappiness 10"
if swapon --show --noheadings | grep -q .; then
    echo "  swap već postoji, ne diram:"; swapon --show | sed 's/^/  /'
else
    sudo fallocate -l 1G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile >/dev/null
    sudo swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
    echo "  napravljen /swapfile"
fi
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-erp-swap.conf >/dev/null
sudo sysctl -q -p /etc/sysctl.d/99-erp-swap.conf
echo "  swappiness: $(cat /proc/sys/vm/swappiness)"
free -h | head -3 | sed 's/^/  /'

sec "Automatska sigurnosna ažuriranja"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unattended-upgrades >/dev/null
sudo tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
# samo sigurnosna ažuriranja (Ubuntu zadano), bez automatskog restarta
grep -E '^\s*"\$\{distro_id\}:\$\{distro_codename\}-security"' /etc/apt/apt.conf.d/50unattended-upgrades \
    | sed 's/^/  izvor: /'
grep -E 'Automatic-Reboot "' /etc/apt/apt.conf.d/50unattended-upgrades | sed 's/^/  /' \
    || echo "  Automatic-Reboot: zadano (false)"
sudo unattended-upgrade --dry-run >/dev/null 2>&1 && echo "  probni prolaz: u redu"
systemctl is-enabled unattended-upgrades | sed 's/^/  servis: /'

sec "Povratak (ako zatreba)"
cat <<EOF
  sudo timedatectl set-timezone $tz_before
  sudo swapoff /swapfile && sudo rm /swapfile && sudo sed -i '\#^/swapfile #d' /etc/fstab
  sudo rm /etc/sysctl.d/99-erp-swap.conf && sudo sysctl -w vm.swappiness=60
  sudo rm /etc/apt/apt.conf.d/20auto-upgrades
EOF

sec "Kraj"
echo "Korak 2 gotov."
