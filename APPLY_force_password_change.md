# Feature: forced password change on first login + self-service change

## Files (5) — copy over your local repo, same paths
- backend/routers/auth.py                     ← new POST /auth/change-password endpoint
- frontend/src/services/api.js                ← authAPI.changePassword()
- frontend/src/pages/ChangePassword.jsx       ← NEW change-password screen
- frontend/src/App.jsx                         ← route + guard (forces change when flagged)
- frontend/src/components/Sidebar.jsx          ← "تغيير كلمة المرور" link (voluntary change)

## What it does
- On login, if the account has must_change_password set (new tenants/admins,
  password resets), the user is sent to a change-password screen and cannot use
  the app until they set a new password.
- Any user can change their own password anytime via the sidebar link.
- No database/schema change → no migration needed.

## PART A — push to GitHub (on your laptop)
```
cd ~/"Development/POS for charity"
# copy the 5 files from this zip into place (same paths), then:
git checkout -b feat/force-password-change
git add -A
git commit -m "auth: force password change on first login + self-service change"
git push origin feat/force-password-change
```
Open a Pull Request on GitHub, review the diff, and merge into main.
(If you prefer to skip the PR for now: commit on main and push directly.)

## PART B — deploy to the server (SSH to the VM)
```
ssh ubuntu@158.101.250.177
cd /srv/bayan-pos && sudo -u bayan git pull
cd backend && sudo -u bayan .venv/bin/pip install -r requirements.txt   # (no new deps; safe)
cd ../frontend && sudo -u bayan npm ci && sudo -u bayan npm run build
sudo systemctl restart bayan-pos
```
No migration is needed for this change. After the restart, hard-refresh the
browser (Ctrl+F5).

## Test it
1. Create a fresh tenant/admin (or reset a user's password in Settings → Users).
2. Log in as that user → you're forced to the change-password screen.
3. Set a new password (min 8 chars) → you land in the app.
4. Click "تغيير كلمة المرور" in the sidebar → change it again voluntarily.
