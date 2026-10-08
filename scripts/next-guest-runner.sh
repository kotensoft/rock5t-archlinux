#!/bin/bash
set -u
grep -qw rock5t.builder=1 /proc/cmdline || exit 1
J=/mnt/host/vm/next
printf 'ready\n' > "$J/runner.status"
while :; do
 if [[ -f $J/shutdown.request ]]; then sync; mount -o remount,ro /; poweroff -f; exit; fi
 if [[ -f $J/job.request ]]; then
  mapfile -t request < "$J/job.request"
  id=${request[0]:-}; script=${request[1]:-}
  if [[ $id =~ ^[a-z0-9-]+$ && $script == /mnt/host/scripts/*.sh && -f $script ]]; then
   mv "$J/job.request" "$J/$id.running"
   bash "$script" > "$J/$id.log" 2>&1
   result=$?
   printf '%s\n' "$result" > "$J/$id.exit"
   rm -f "$J/$id.running"
  else
   mv "$J/job.request" "$J/job.rejected"
  fi
 fi
 sleep 1
done
