#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ERP-IOT · 5b — provjera slušača nakon svakog koraka (spec §10.15, v25.1)
#
#  Pravilo: na 0.0.0.0 / [::] smije slušati samo SSH :22. Postgres samo socket
#  (nijedan :5432), uvicorn samo 127.0.0.1, nginx samo na Tailscale IP.
#  Dopušteno je dakle: *:22, loopback (127.0.0.0/8, ::1) i Tailscale adrese.
#  Sve drugo je greška koraka. Samo čita.
#
#  Pokretanje:  bash ~/erp-iot/deploy/slusaci.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ts4=$(tailscale ip -4 2>/dev/null || true)
ts6=$(tailscale ip -6 2>/dev/null || true)
bad=0

echo "  ss -ltn:"
while read -r addr; do
    port=${addr##*:}
    # prvo oznaka zone (%tailscale0, %lo), pa zagrade IPv6: [fd7a::1]%tailscale0 → fd7a::1
    host=${addr%:*}; host=${host%%\%*}; host=${host#[}; host=${host%]}
    verdict=GREŠKA
    if [ "$port" = "5432" ]; then
        verdict="GREŠKA (Postgres mora biti samo socket)"
    elif [ "$port" = "22" ]; then
        verdict=ok
    else
        case "$host" in
            127.*|::1) verdict=ok ;;
            *) { [ "$host" = "$ts4" ] || [ "$host" = "$ts6" ]; } && [ -n "$host" ] && verdict=ok ;;
        esac
    fi
    printf '    %-28s %s\n' "$addr" "$verdict"
    [ "$verdict" = ok ] || bad=1
done < <(ss -ltnH | awk '{print $4}' | sort -u)

if [ "$bad" = 1 ]; then
    echo "  SLUŠAČI: GREŠKA — stani i javi"; exit 1
fi
echo "  SLUŠAČI: u redu"
