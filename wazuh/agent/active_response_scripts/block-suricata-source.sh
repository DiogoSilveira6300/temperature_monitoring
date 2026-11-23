#!/bin/bash

read -r INPUT_JSON || exit 1

ACTION=$(jq -er '.command' <<<"$INPUT_JSON") || exit 1
IP=$(jq -er '.parameters.alert.data.src_ip' <<<"$INPUT_JSON") || exit 1

# Accept IPv4 addresses only; this script uses iptables.
python3 -c 'import ipaddress,sys; ipaddress.IPv4Address(sys.argv[1])' "$IP" || exit 1

case "$ACTION" in
  add)
    /usr/sbin/iptables -C INPUT -s "$IP" -j DROP 2>/dev/null ||
      /usr/sbin/iptables -I INPUT -s "$IP" -j DROP || exit 1
    ;;
  delete)
    while /usr/sbin/iptables -C INPUT -s "$IP" -j DROP 2>/dev/null; do
      /usr/sbin/iptables -D INPUT -s "$IP" -j DROP || exit 1
    done
    ;;
  *)
    exit 1
    ;;
esac
