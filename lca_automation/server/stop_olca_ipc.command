#!/usr/bin/env bash
#
# stop_olca_ipc.command — stop the openLCA headless IPC server (option A)
#
# Usage:
#   Double-click this file, or run: ./stop_olca_ipc.command
#
# Optional environment variable:
#   OLCA_PORT  port (default 8080) — selects the matching PID file

set -euo pipefail

PORT="${OLCA_PORT:-8080}"
RUN_DIR="$HOME/.olca-ipc"
PID_FILE="$RUN_DIR/ipc-$PORT.pid"

ok()   { printf '\033[0;32m%s\033[0m\n' "$*"; }
warn() { printf '\033[0;33m%s\033[0m\n' "$*"; }
err()  { printf '\033[0;31m%s\033[0m\n' "$*"; }

echo "Stopping openLCA IPC server (port ${PORT})…"

# Collect every candidate PID before shutdown (closing the DB via RPC frees the port):
#   - the process recorded in the PID file
#   - the process currently listening on this port
PIDS=""
[ -f "$PID_FILE" ] && PIDS="$(cat "$PID_FILE" 2>/dev/null || true)"
PORT_PID="$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
PIDS="$(printf '%s\n%s\n' "$PIDS" "$PORT_PID" | sort -u | grep -E '^[0-9]+$' || true)"

# 1) Prefer a graceful JSON-RPC shutdown so the database flushes and releases its lock
if (echo >/dev/tcp/127.0.0.1/"$PORT") 2>/dev/null; then
  curl -s -m 5 -X POST "http://localhost:$PORT" \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"runtime/shutdown"}' >/dev/null 2>&1 || true
  sleep 2
fi

# 2) Make sure that JVM actually exits (runtime/shutdown closes the DB but does not exit the JVM)
for PID in $PIDS; do
  kill -0 "$PID" 2>/dev/null || continue
  kill "$PID" 2>/dev/null || true
  for _ in $(seq 1 10); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$PID" 2>/dev/null; then
    warn "Process did not respond; force-killing PID $PID"
    kill -9 "$PID" 2>/dev/null || true
  fi
done
rm -f "$PID_FILE"

# 3) Fallback: check once more for a process still listening on the port
LEFT="$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$LEFT" ]; then
  warn "Cleaning residual process(es) on port $PORT: $LEFT"
  kill $LEFT 2>/dev/null || true
  sleep 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  err "❌ Port $PORT is still in use; please check manually."
  exit 1
fi

ok "✅ Server stopped and database released. You can now open this database in the openLCA GUI to view results."
