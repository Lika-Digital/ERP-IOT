#!/usr/bin/env bash
# 5 · Restore both databases from a krk_backup.py copy.
#
#   sudo bash /tmp/krk/krk_restore.sh /var/backups/cloud-iot-erp <stamp>           # plan only
#   sudo bash /tmp/krk/krk_restore.sh /var/backups/cloud-iot-erp <stamp> --apply   # restore
#
# <stamp> is the one in the copy names, e.g. 20261012T143000Z.
# Order: stop the backend -> nothing may hold the files -> delete -wal and -shm
# -> put the copy in place (owner and mode as the live file had) -> integrity
# check -> start -> is it running. An old -wal over a restored database
# replays old pages into it and corrupts it, so -wal/-shm are deleted, always.
set -euo pipefail

DIR="${1:?backup directory}"; STAMP="${2:?stamp}"; APPLY="${3:-}"
UNIT=cloud-iot-backend
PY=/opt/cloud-iot/backend/.venv/bin/python
declare -A MAP=(
  [/opt/cloud-iot/backend/pedestal.db]="$DIR/pedestal-$STAMP.db"
  [/opt/cloud-iot/backend/data/users.db]="$DIR/users-$STAMP.db"
)

[ "$(id -u)" -eq 0 ] || { echo "STOP: pokreni sa sudo"; exit 2; }
for live in "${!MAP[@]}"; do
  [ -f "${MAP[$live]}" ] || { echo "STOP: nema kopije ${MAP[$live]}"; exit 2; }
done

echo "PLAN:"
echo "  systemctl stop $UNIT"
for live in "${!MAP[@]}"; do
  echo "  rm -f $live-wal $live-shm"
  echo "  $live  <-  ${MAP[$live]}   (vlasnik/prava: $(stat -c '%U:%G %a' "$live"))"
done
echo "  integrity_check obje, pa systemctl start $UNIT"
[ "$APPLY" = "--apply" ] || { echo "Bez --apply: ništa nije učinjeno."; exit 0; }

systemctl stop "$UNIT"
systemctl is-active --quiet "$UNIT" && { echo "STOP: $UNIT još radi"; exit 3; }
for live in "${!MAP[@]}"; do
  holders=$(find /proc/[0-9]*/fd -lname "$live*" 2>/dev/null || true)
  [ -z "$holders" ] || { echo "STOP: datoteku još drži proces:"; echo "$holders"; exit 3; }
done

for live in "${!MAP[@]}"; do
  read -r own mode < <(stat -c '%U:%G %a' "$live")
  rm -f "$live-wal" "$live-shm"
  install -o "${own%%:*}" -g "${own##*:}" -m "$mode" "${MAP[$live]}" "$live"
  ok=$(sudo -u cloud-iot "$PY" -c \
       "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0])" \
       "$live")
  echo "  vraćeno $live  integrity=$ok"
  [ "$ok" = "ok" ] || { echo "STOP: integrity nije ok — backend NE pokrećem"; exit 4; }
done

systemctl start "$UNIT"
sleep 5
systemctl is-active "$UNIT"
journalctl -u "$UNIT" -n 20 --no-pager
