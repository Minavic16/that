#!/usr/bin/env bash
# VPS Diagnostic Procedure — Admin Dashboard Engines Page
# Run this on Ubuntu/VPS. Do NOT modify any files.
# Usage: bash scripts/vps_diag.sh

set -euo pipefail

echo "============================================"
echo "  NQTS VPS DIAGNOSTIC — Engines Page"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"
echo ""

# =============================================
# Block 1: Dashboard Process
# =============================================
echo ">>> 1A: Dashboard process"
ps aux | grep -E "next|dashboard" | grep -v grep || echo "(none found)"
echo ""
echo ">>> 1B: Listening ports"
ss -tlnp | grep -E "3000|3001|3002" || echo "(no matching ports)"
echo ""
echo ">>> 1C: systemd services"
systemctl list-units --type=service --state=running 2>/dev/null | grep -iE "nestquant|nqts|dashboard|next" || echo "(no matching systemd services)"
echo ""

# =============================================
# Block 2: Dashboard Logs
# =============================================
echo ">>> 2A: Recent Next.js logs (journalctl)"
journalctl -u nqts-dashboard --no-pager -n 50 2>/dev/null || echo "(no nqts-dashboard journal)"
echo ""
echo ">>> 2B: PM2 logs (if used)"
pm2 logs --nostream --lines 50 2>/dev/null || echo "(no PM2)"
echo ""
echo ">>> 2C: Dashboard stdout/stderr files"
ls -la /root/nestquant/production/dashboard/dashboard/nohup.out 2>/dev/null || echo "(no nohup.out)"
ls -la /root/nestquant/dashboard/nohup.out 2>/dev/null || echo "(no nohup.out at old path)"
echo ""

# =============================================
# Block 3: /api/engines curl
# =============================================
echo ">>> 3A: Unauthenticated /api/engines (expect 401)"
curl -s -o /dev/null -w "HTTP %{http_code}" http://127.0.0.1:3000/api/engines 2>/dev/null || echo "Connection refused"
echo ""
echo ""
echo ">>> 3B: Unauthenticated response body"
curl -s http://127.0.0.1:3000/api/engines 2>/dev/null || echo "Connection refused"
echo ""
echo ""
echo ">>> 3C: Login to obtain session cookie"
LOGIN_RESPONSE=$(curl -s -c /tmp/nqts_cookie.txt -X POST http://127.0.0.1:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"Mindavic","password":"check_below"}' 2>/dev/null)
echo "Login response: $LOGIN_RESPONSE"
echo ""
echo ">>> 3D: Authenticated /api/engines (body)"
curl -s -b /tmp/nqts_cookie.txt http://127.0.0.1:3000/api/engines 2>/dev/null || echo "Connection refused"
echo ""
echo ""
echo ">>> 3E: Authenticated /api/engines (HTTP status)"
curl -s -o /dev/null -w "HTTP %{http_code}" -b /tmp/nqts_cookie.txt http://127.0.0.1:3000/api/engines 2>/dev/null || echo "Connection refused"
echo ""
echo ""
echo ">>> 3F: /api/health (for comparison)"
curl -s -b /tmp/nqts_cookie.txt http://127.0.0.1:3000/api/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('status:', d.get('status')); print('mt5_connected:', d.get('mt5_connected')); print('runner_health:', d.get('runner_health'))" 2>/dev/null || echo "(parse failed or connection refused)"
echo ""
echo ""
echo ">>> 3G: /api/users (calls getDb, tests WASM path)"
curl -s -o /dev/null -w "HTTP %{http_code}" -b /tmp/nqts_cookie.txt http://127.0.0.1:3000/api/users 2>/dev/null || echo "Connection refused"
echo ""
echo ""
echo ">>> 3H: /api/config (calls getDb, tests WASM path)"
curl -s -o /dev/null -w "HTTP %{http_code}" -b /tmp/nqts_cookie.txt http://127.0.0.1:3000/api/config 2>/dev/null || echo "Connection refused"
echo ""

# =============================================
# Block 4: Authentication
# =============================================
echo ">>> 4A: DASHBOARD_SECRET set in current shell?"
if [ -n "${DASHBOARD_SECRET:-}" ]; then echo "DASHBOARD_SECRET: SET"; else echo "DASHBOARD_SECRET: NOT SET (or empty)"; fi
echo ""
echo ">>> 4B: Check systemd unit files"
grep -r "DASHBOARD_SECRET" /etc/systemd/system/nqts* 2>/dev/null || echo "(not in systemd units)"
echo ""
echo ">>> 4C: Check .env files"
cat /root/nestquant/production/dashboard/dashboard/.env 2>/dev/null || echo "(no .env at new path)"
cat /root/nestquant/dashboard/.env 2>/dev/null || echo "(no .env at old path)"
echo ""
echo ">>> 4D: Dashboard process environment"
DASH_PID=$(pgrep -f "next.*start|next-start" | head -1 || true)
if [ -n "$DASH_PID" ]; then
  echo "Dashboard PID: $DASH_PID"
  cat /proc/$DASH_PID/environ 2>/dev/null | tr '\0' '\n' | grep "DASHBOARD_SECRET" | sed 's/=.*/=SET/' || echo "(cannot read process env)"
else
  echo "(no dashboard process found for env check)"
fi
echo ""

# =============================================
# Block 5: NQTS Telemetry Files
# =============================================
echo ">>> 5A: state.json"
ls -la /root/nestquant/logs/shadow_live/state.json 2>/dev/null || echo "MISSING"
echo ""
echo ">>> 5B: metrics.json"
ls -la /root/nestquant/logs/shadow_live/metrics.json 2>/dev/null || echo "MISSING"
echo ""
echo ">>> 5C: infrastructure.jsonl"
ls -la /root/nestquant/logs/shadow_live/infrastructure.jsonl 2>/dev/null || echo "MISSING"
echo ""
echo ">>> 5D: signals.jsonl"
ls -la /root/nestquant/logs/shadow_live/signals.jsonl 2>/dev/null || echo "MISSING"
echo ""
echo ">>> 5E: bars.jsonl"
ls -la /root/nestquant/logs/shadow_live/bars.jsonl 2>/dev/null || echo "MISSING"
echo ""
echo ">>> 5F: state.json age and content"
if [ -f /root/nestquant/logs/shadow_live/state.json ]; then
  echo "Age: $(( ($(date +%s) - $(stat -c %Y /root/nestquant/logs/shadow_live/state.json)) / 60 )) minutes"
  python3 -c "import json; d=json.load(open('/root/nestquant/logs/shadow_live/state.json')); print('updated_at:', d.get('updated_at','?')); print('counters:', d.get('counters',{}))" 2>/dev/null || echo "(parse error)"
else
  echo "(file missing)"
fi
echo ""
echo ">>> 5G: metrics.json age and content"
if [ -f /root/nestquant/logs/shadow_live/metrics.json ]; then
  echo "Age: $(( ($(date +%s) - $(stat -c %Y /root/nestquant/logs/shadow_live/metrics.json)) / 60 )) minutes"
  python3 -c "import json; d=json.load(open('/root/nestquant/logs/shadow_live/metrics.json')); print('execution:', d.get('execution',{})); print('trading:', d.get('trading',{}))" 2>/dev/null || echo "(parse error)"
else
  echo "(file missing)"
fi
echo ""
echo ">>> 5H: bars.jsonl line count and tail"
if [ -f /root/nestquant/logs/shadow_live/bars.jsonl ]; then
  echo "Lines: $(wc -l < /root/nestquant/logs/shadow_live/bars.jsonl)"
  echo "Last entry:"
  tail -1 /root/nestquant/logs/shadow_live/bars.jsonl | python3 -m json.tool 2>/dev/null || tail -1 /root/nestquant/logs/shadow_live/bars.jsonl
else
  echo "(file missing)"
fi
echo ""

# =============================================
# Block 6: MT5 Bridge
# =============================================
echo ">>> 6A: Bridge health"
curl -s http://127.0.0.1:5001/health 2>/dev/null || echo "Connection refused"
echo ""
echo ""
echo ">>> 6B: Bridge account (non-secret fields only)"
curl -s http://127.0.0.1:5001/account 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('login:', d.get('login')); print('balance:', d.get('balance')); print('equity:', d.get('equity')); print('currency:', d.get('currency')); print('server:', d.get('server')); print('leverage:', d.get('leverage'))" 2>/dev/null || echo "Connection refused or parse error"
echo ""
echo ">>> 6C: Bridge process"
ps aux | grep -E "flask|bridge|5001" | grep -v grep || echo "(no bridge process found)"
echo ""

# =============================================
# Block 7: VPS Git State
# =============================================
echo ">>> 7A: Current HEAD (cd /root/nestquant)"
cd /root/nestquant && git log --oneline -3
echo ""
echo ">>> 7B: Working tree"
git status --short
echo ""
echo ">>> 7C: origin/master"
git log --oneline -1 origin/master 2>/dev/null || echo "(no remote tracking)"
echo ""
echo ">>> 7D: HEAD behind origin?"
git log --oneline HEAD..origin/master 2>/dev/null | head -10 || echo "(cannot compare)"
echo ""
echo ">>> 7E: HEAD ahead of origin?"
git log --oneline origin/master..HEAD 2>/dev/null | head -10 || echo "(cannot compare)"
echo ""

# =============================================
# Block 8: Dashboard Build
# =============================================
echo ">>> 8A: Dashboard directory locations"
echo "Old path (pre-migration):"
ls -d /root/nestquant/dashboard 2>/dev/null && echo "  EXISTS" || echo "  MISSING"
echo "New path (post-migration):"
ls -d /root/nestquant/production/dashboard/dashboard 2>/dev/null && echo "  EXISTS" || echo "  MISSING"
echo ""
echo ">>> 8B: .next build directories"
find /root/nestquant -name ".next" -type d -maxdepth 5 2>/dev/null || echo "(none found)"
echo ""
echo ">>> 8C: BUILD_ID"
if [ -f /root/nestquant/production/dashboard/dashboard/.next/BUILD_ID ]; then
  echo "New path BUILD_ID: $(cat /root/nestquant/production/dashboard/dashboard/.next/BUILD_ID)"
else
  echo "No BUILD_ID at new path"
fi
if [ -f /root/nestquant/dashboard/.next/BUILD_ID ]; then
  echo "Old path BUILD_ID: $(cat /root/nestquant/dashboard/.next/BUILD_ID)"
else
  echo "No BUILD_ID at old path"
fi
echo ""
echo ">>> 8D: node_modules locations"
echo "New path node_modules:"
ls -d /root/nestquant/production/dashboard/dashboard/node_modules 2>/dev/null && echo "  EXISTS" || echo "  MISSING"
echo "Old path node_modules:"
ls -d /root/nestquant/dashboard/node_modules 2>/dev/null && echo "  EXISTS" || echo "  MISSING"
echo ""
echo ">>> 8E: package.json locations"
find /root/nestquant -name "package.json" -path "*/dashboard*" -maxdepth 5 2>/dev/null
echo ""

# =============================================
# Block 9: WASM Path Verification
# =============================================
echo ">>> 9A: db.ts referenced WASM path (old path)"
echo "Expected: /root/nestquant/dashboard/node_modules/sql.js/dist/sql-wasm.wasm"
ls -la /root/nestquant/dashboard/node_modules/sql.js/dist/sql-wasm.wasm 2>/dev/null || echo "MISSING"
echo ""
echo ">>> 9B: WASM at /root/that symlink"
echo "Expected: /root/that/dashboard/node_modules/sql.js/dist/sql-wasm.wasm"
ls -la /root/that/dashboard/node_modules/sql.js/dist/sql-wasm.wasm 2>/dev/null || echo "MISSING"
echo ""
echo ">>> 9C: WASM at new path (if rebuilt)"
echo "Expected: /root/nestquant/production/dashboard/dashboard/node_modules/sql.js/dist/sql-wasm.wasm"
ls -la /root/nestquant/production/dashboard/dashboard/node_modules/sql.js/dist/sql-wasm.wasm 2>/dev/null || echo "MISSING"
echo ""
echo ">>> 9D: db.ts DB_PATH"
echo "Expected: /root/nestquant/data/dashboard.db"
ls -la /root/nestquant/data/dashboard.db 2>/dev/null || echo "MISSING"
echo ""

# =============================================
# Cleanup
# =============================================
rm -f /tmp/nqts_cookie.txt 2>/dev/null

echo "============================================"
echo "  DIAGNOSTIC COMPLETE — Paste output back"
echo "============================================"
