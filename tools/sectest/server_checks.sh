#!/usr/bin/env bash
# Configuration review ON the server (read-only; changes nothing). No Oracle notice needed.
#   sudo bash /srv/bayan-pos/tools/sectest/server_checks.sh
PASS=0; FAIL=0; WARN=0
ok()   { echo "PASS  $*"; PASS=$((PASS+1)); }
bad()  { echo "FAIL  $*"; FAIL=$((FAIL+1)); }
warn() { echo "WARN  $*"; WARN=$((WARN+1)); }
[ "$(id -u)" = "0" ] || { echo "run with sudo"; exit 1; }
APPDIR=/srv/bayan-pos

echo "— Listening services"
command -v ss >/dev/null || { echo "install iproute2 (ss) first"; exit 1; }
for a in $(ss -tlnH | awk '{print $4}' | sort -u); do
  case "$a" in
    127.0.0.*|\[::1\]:*|::1:*) ;;          # localhost only (incl. 127.0.0.53%lo = local DNS)
    *:22|*:80|*:443) ;;
    *) bad "service listening on all interfaces: $a (ufw blocks it, but better switch it off)";;
  esac
done
ss -tlnH | grep -qE '(0\.0\.0\.0|\*|\[::\]):5432\b' && bad "PostgreSQL listens publicly" || ok "PostgreSQL only on localhost"
ss -tlnH | grep -qE '127\.0\.0\.1:8000\b' && ok "app on 127.0.0.1:8000" || warn "app not seen on 127.0.0.1:8000"
ss -tlnH | grep -qE '127\.0\.0\.1:8001\b' && ok "console on 127.0.0.1:8001" || warn "console not seen on 127.0.0.1:8001"

echo; echo "— SSH"
S=$(sshd -T 2>/dev/null)
if [ -z "$S" ]; then warn "cannot read the SSH server settings (sshd -T)"; else
echo "$S" | grep -q '^passwordauthentication no' && ok "SSH passwords disabled (keys only)" || bad "SSH password login is enabled"
echo "$S" | grep -qE '^permitrootlogin (no|prohibit-password|without-password)' && ok "root cannot log in with a password" || bad "root password login allowed"
echo "$S" | grep -q '^maxauthtries [1-4]$' && ok "SSH MaxAuthTries ≤ 4" || warn "SSH MaxAuthTries is high (set 3)"
fi
systemctl is-active --quiet fail2ban && ok "fail2ban running" || warn "fail2ban not installed/running (brute-force protection for SSH)"

echo; echo "— Firewall"
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then ok "ufw active"; ufw status | sed 's/^/      /'
else
  n=$(iptables -S INPUT 2>/dev/null | grep -c -- '-j ACCEPT')
  iptables -S INPUT 2>/dev/null | grep -q -- '-P INPUT DROP\|REJECT' && ok "iptables INPUT restricted ($n accept rules)" || warn "host firewall: check iptables/ufw (OCI security list is the outer layer)"
fi

echo; echo "— Updates"
if [ -f /etc/apt/apt.conf.d/20auto-upgrades ] && grep -q '"1"' /etc/apt/apt.conf.d/20auto-upgrades; then ok "automatic security updates on"; else warn "automatic security updates off (apt install unattended-upgrades)"; fi
up=$(apt list --upgradable 2>/dev/null | grep -c security)
[ "$up" -eq 0 ] && ok "no pending security updates" || warn "$up security updates pending (apt upgrade)"
[ -f /var/run/reboot-required ] && warn "reboot required for updates" || ok "no reboot pending"

echo; echo "— Secrets and files"
ENV=$APPDIR/backend/.env
if [ -f "$ENV" ]; then
  perm=$(stat -c %a "$ENV"); own=$(stat -c %U "$ENV")
  [ "$perm" -le 640 ] && ok ".env permissions $perm ($own)" || bad ".env is readable by others ($perm) — chmod 600"
  grep -q '^ENVIRONMENT=production' "$ENV" && ok "ENVIRONMENT=production" || bad "ENVIRONMENT is not production (docs would be public)"
  k=$(grep '^SECRET_KEY=' "$ENV" | cut -d= -f2-); [ ${#k} -ge 32 ] && ok "SECRET_KEY length ${#k}" || bad "SECRET_KEY missing or short"
  grep -qi '^COOKIE_SECURE=false' "$ENV" && bad "COOKIE_SECURE=false in production" || ok "secure cookies"
  grep -q '^BOOTSTRAP_ADMIN_PASSWORD=.\+' "$ENV" && warn "BOOTSTRAP_ADMIN_PASSWORD still set (remove after first setup)" || ok "no bootstrap password in .env"
else bad "$ENV not found"; fi
p=$(stat -c %a $APPDIR/backend/storage/proofs 2>/dev/null); [ -n "$p" ] && { [ "$p" -le 750 ] && ok "proofs folder $p" || bad "proofs folder too open ($p)"; }
[ -d $APPDIR/.git ] && sudo -u "$(stat -c %U $APPDIR)" git -C $APPDIR ls-files | grep -qE '(^|/)\.env$|\.dev_secret|\.pem$|id_rsa' && bad "a secret file is tracked in git" || ok "no secret files tracked in git"

echo; echo "— Database"
pg_ver=$(sudo -u postgres psql -Atc "show server_version" 2>/dev/null); ok "PostgreSQL $pg_ver"
la=$(sudo -u postgres psql -Atc "show listen_addresses" 2>/dev/null); [ "$la" = "localhost" ] || [ "$la" = "127.0.0.1" ] && ok "listen_addresses=$la" || bad "listen_addresses=$la"
mc=$(sudo -u postgres psql -Atc "show max_connections" 2>/dev/null); ok "max_connections=$mc (app needs ≤ 60)"
su=$(sudo -u postgres psql -d pos -Atc "select rolsuper or rolbypassrls from pg_roles where rolname='pos_app'" 2>/dev/null)
[ "$su" = "f" ] && ok "pos_app is not superuser and cannot bypass RLS" || bad "pos_app can bypass RLS!"
nf=$(sudo -u postgres psql -d pos -Atc "select count(*) from information_schema.columns c join pg_class t on t.relname=c.table_name where c.table_schema='public' and c.column_name='tenant_id' and not (t.relrowsecurity and t.relforcerowsecurity)" 2>/dev/null)
[ "$nf" = "0" ] && ok "every tenant table has forced RLS" || bad "$nf tenant tables without forced RLS"

echo; echo "— Backups"
last=$(ls -t /var/backups/bayan-pos/*.dump 2>/dev/null | head -1)
if [ -n "$last" ]; then
  age=$(( ( $(date +%s) - $(stat -c %Y "$last") ) / 86400 ))
  [ $age -le 1 ] && ok "latest backup $age day(s) old: $last" || warn "latest backup is $age days old (no nightly backup?)"
else bad "no database backup found in /var/backups/bayan-pos"; fi
crontab -l -u postgres 2>/dev/null | grep -q pg_dump || ls /etc/cron.d 2>/dev/null | grep -qi backup || warn "no scheduled backup found"

echo; echo "PASS $PASS  FAIL $FAIL  WARN $WARN"
