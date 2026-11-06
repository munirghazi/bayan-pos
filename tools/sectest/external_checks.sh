#!/usr/bin/env bash
# External checks of the LIVE server — run from your laptop (outside the server).
# ONLY after the Oracle notification period (5 business days). Light, non-load checks.
#
#   bash external_checks.sh                       # defaults below
#   bash external_checks.sh 158.101.250.177 sahlpos.roaa.sa admin.sahlpos.roaa.sa
#
# Needs: nmap, curl, openssl   (sudo apt install nmap curl openssl)

IP="${1:-158.101.250.177}"
APP="${2:-sahlpos.roaa.sa}"
ADMIN="${3:-admin.sahlpos.roaa.sa}"
OUT="external-report-$(date +%Y%m%d-%H%M).txt"
PASS=0; FAIL=0; WARN=0

ok()   { echo "PASS  $*" | tee -a "$OUT"; PASS=$((PASS+1)); }
bad()  { echo "FAIL  $*" | tee -a "$OUT"; FAIL=$((FAIL+1)); }
warn() { echo "WARN  $*" | tee -a "$OUT"; WARN=$((WARN+1)); }

echo "External checks — $IP / $APP / $ADMIN — $(date)" | tee "$OUT"
for t in nmap curl openssl; do command -v $t >/dev/null || { echo "missing tool: $t (sudo apt install $t)"; exit 1; }; done

echo; echo "— Open ports (top 1000 TCP + common DB/app ports)" | tee -a "$OUT"
nmap -Pn -sT --top-ports 1000 -p 22,80,443,5432,6379,8000,8001,3000,5173 "$IP" -oG - 2>/dev/null | tee -a "$OUT.nmap" >/dev/null
OPEN=$(grep -oE '[0-9]+/open' "$OUT.nmap" | cut -d/ -f1 | sort -n | tr '\n' ' ')
echo "open: $OPEN" | tee -a "$OUT"
for p in $OPEN; do
  case $p in 22|80|443) ;; *) bad "port $p is reachable from the internet (should be closed)";; esac
done
for p in 5432 8000 8001; do echo " $OPEN " | grep -q " $p " || ok "port $p not reachable from outside"; done

echo; echo "— TLS" | tee -a "$OUT"
for host in "$APP" "$ADMIN"; do
  for proto in tls1 tls1_1; do
    if echo | timeout 10 openssl s_client -connect "$host:443" -servername "$host" -$proto >/dev/null 2>&1; then
      bad "$host accepts old $proto"; else ok "$host refuses old $proto"; fi
  done
  if echo | timeout 10 openssl s_client -connect "$host:443" -servername "$host" -tls1_2 >/dev/null 2>&1; then ok "$host speaks TLS 1.2+"; else bad "$host: TLS 1.2 handshake failed"; fi
  exp=$(echo | openssl s_client -connect "$host:443" -servername "$host" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
  [ -n "$exp" ] && ok "$host certificate valid until $exp" || bad "$host: cannot read certificate"
done
code=$(curl -s -o /dev/null -w '%{http_code}' "http://$APP/")
[[ "$code" =~ ^30[178]$ ]] && ok "http:// redirects to https ($code)" || bad "http:// does not redirect ($code)"

echo; echo "— Security headers" | tee -a "$OUT"
for url in "https://$APP/" "https://$ADMIN/"; do
  H=$(curl -s -D - -o /dev/null "$url" | tr -d '\r' | tr 'A-Z' 'a-z')
  for h in strict-transport-security x-content-type-options x-frame-options; do
    echo "$H" | grep -q "^$h:" && ok "$url has $h" || bad "$url missing $h"
  done
  echo "$H" | grep -q "^server: .*[0-9]" && warn "$url reveals server version" || true
done
curl -s -D - -o /dev/null "https://$ADMIN/" | tr 'A-Z' 'a-z' | grep -q "content-security-policy" && ok "console has a CSP" || bad "console has no CSP"

echo; echo "— Exposed endpoints" | tee -a "$OUT"
for path in /docs /openapi.json /redoc /metrics /.env /.git/config /backend/.env /api/platform/tenants; do
  body=$(curl -s "https://$APP$path" | head -c 400)
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://$APP$path")
  if echo "$body" | grep -qiE '"openapi"|swagger|requests_total|SECRET_KEY|DATABASE_URL|\[core\]|"tenants"'; then
    bad "https://$APP$path exposes data ($code)"
  else
    ok "https://$APP$path not exposed ($code)"
  fi
done
for path in /docs /openapi.json /metrics; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://$ADMIN$path")
  [ "$code" = "404" ] || [ "$code" = "401" ] && ok "https://$ADMIN$path not exposed ($code)" || \
    { curl -s "https://$ADMIN$path" | grep -qiE '"openapi"|swagger|requests_total' && bad "https://$ADMIN$path exposed" || ok "https://$ADMIN$path not exposed ($code)"; }
done
code=$(curl -s -o /dev/null -w '%{http_code}' "https://$ADMIN/api/platform/tenants")
[ "$code" = "401" ] && ok "console API needs a session (401)" || bad "console API answered $code without a session"

echo; echo "PASS $PASS  FAIL $FAIL  WARN $WARN   →  $OUT" | tee -a "$OUT"
rm -f "$OUT.nmap"
