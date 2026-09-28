#!/usr/bin/env bash
#
# start_olca_ipc.command — start the openLCA headless IPC server (option A)
#
# Purpose:
#   Connect to a chosen database as a headless server, without opening the
#   openLCA GUI, and expose a JSON-RPC API on port 8080 (olca-ipc / Python).
#
# Usage:
#   1) Double-click this file in Finder; or
#   2) From a terminal: ./start_olca_ipc.command ["database name"]
#
# Optional environment variables (override the defaults):
#   OLCA_APP       path to openLCA.app          default /Applications/openLCA.app
#   OLCA_DATA_DIR  workspace data directory     default ~/openLCA-data-1.4
#   OLCA_DB        database name (folder under databases)
#   OLCA_PORT      port                         default 8080
#   OLCA_XMX       JVM max heap                 default 16G
#   OLCA_THREADS   calculation threads          default 4
#
# Note: the headless server and the openLCA GUI cannot open the same database
#       at the same time. Close it in the GUI first (this script also checks
#       the database lock).

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OLCA_APP="${OLCA_APP:-/Applications/openLCA.app}"
DATA_DIR="${OLCA_DATA_DIR:-$HOME/openLCA-data-1.4}"
DEFAULT_DB="ecoinvent 3.12 Cutoff Unit 2025-12-19"
PORT="${OLCA_PORT:-8080}"
XMX="${OLCA_XMX:-16G}"
THREADS="${OLCA_THREADS:-4}"

# Database name priority: CLI argument > OLCA_DB > default
DB="${1:-${OLCA_DB:-$DEFAULT_DB}}"

# ---------------------------------------------------------------------------
# Derived paths
# ---------------------------------------------------------------------------
ECLIPSE="$OLCA_APP/Contents/Eclipse"
JAVA="$ECLIPSE/jre/Contents/Home/bin/java"
LIBS_DIR="$(ls -d "$ECLIPSE"/plugins/olca-app_*/libs 2>/dev/null | head -1 || true)"
MKL_DIR="$(ls -d "$ECLIPSE"/olca-mkl-* 2>/dev/null | head -1 || true)"

# Launcher shim directory (loads native MKL libraries in headless mode)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHIM_DIR="$SCRIPT_DIR/lib"

RUN_DIR="$HOME/.olca-ipc"
PID_FILE="$RUN_DIR/ipc-$PORT.pid"
LOG_FILE="$RUN_DIR/ipc-$PORT.log"
mkdir -p "$RUN_DIR"

note()  { printf '\033[0;36m%s\033[0m\n' "$*"; }   # cyan
ok()    { printf '\033[0;32m%s\033[0m\n' "$*"; }   # green
warn()  { printf '\033[0;33m%s\033[0m\n' "$*"; }   # yellow
err()   { printf '\033[0;31m%s\033[0m\n' "$*"; }   # red

echo "=============================================================="
note "openLCA headless IPC server launcher (option A)"
echo "=============================================================="
echo "  App     : $OLCA_APP"
echo "  Data dir: $DATA_DIR"
echo "  Database: $DB"
echo "  Port    : $PORT"
echo "  Memory  : $XMX    Threads: $THREADS"
echo "--------------------------------------------------------------"

# ---------------------------------------------------------------------------
# Pre-start checks
# ---------------------------------------------------------------------------
[ -x "$JAVA" ]        || { err "❌ Built-in Java not found: $JAVA"; exit 1; }
[ -n "$LIBS_DIR" ]    || { err "❌ openLCA plugin libs directory not found (plugins/olca-app_*/libs)"; exit 1; }
[ -d "$DATA_DIR/databases/$DB" ] || {
  err "❌ Database does not exist: $DATA_DIR/databases/$DB"
  echo "   Available databases:"
  ls -1 "$DATA_DIR/databases" 2>/dev/null | sed 's/^/     - /'
  exit 1
}

# Port-in-use check
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  err "❌ Port $PORT is already in use (server may already be running, or GUI IPC is enabled)."
  echo "   Run stop_olca_ipc.command first, or use another port: OLCA_PORT=8090 $0"
  exit 1
fi

# Database lock check
#   The headless server and the openLCA GUI cannot open the same database.
#   - If the openLCA GUI is running: abort (most likely a real lock).
#   - If the GUI is not running but db.lck exists: usually a stale lock from
#     an unclean exit. Leave it to Derby, which can recover a same-host stale lock.
if pgrep -f "openLCA.app/Contents/MacOS" >/dev/null 2>&1; then
  if [ -f "$DATA_DIR/databases/$DB/db.lck" ]; then
    err "❌ openLCA GUI is running and this database is already open (db.lck exists)."
    err "   The headless server cannot connect to a database already opened by the GUI."
    err "   Close the database in the GUI (or quit openLCA) and try again."
    exit 1
  fi
  warn "⚠️  openLCA GUI is running; make sure it has not opened database \"$DB\"."
elif [ -f "$DATA_DIR/databases/$DB/db.lck" ]; then
  warn "⚠️  Stale lock file db.lck found (GUI is not running; likely left from an unclean exit). Will try to start anyway."
fi

# Do not start a second server if the recorded PID is still alive
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  warn "⚠️  Server appears to be already running (PID $(cat "$PID_FILE"), port ${PORT})."
  exit 0
fi

# ---------------------------------------------------------------------------
# Start the server
#   - cd to a writable directory so Derby does not try to write derby.log inside the read-only .app
#   - use nohup + setsid (when available) so the process survives closing the terminal
# ---------------------------------------------------------------------------
note "🚀 Starting server… (first database load may take a few seconds)"
cd "$RUN_DIR"

# Prefer the launcher shim (loads the MKL solver); fall back to the stock entry if the .class or MKL directory is missing
if [ -f "$SHIM_DIR/OlcaIpcServer.class" ] && [ -n "$MKL_DIR" ]; then
  ENTRY_ARGS=( -Dolca.mkl.dir="$MKL_DIR" -cp "$SHIM_DIR:$LIBS_DIR/*" OlcaIpcServer )
else
  ENTRY_ARGS=( -cp "$LIBS_DIR/*" org.openlca.ipc.Server )
fi

JAVA_ARGS=(
  -Xmx"$XMX"
  -Dderby.system.home="$RUN_DIR"
  "${ENTRY_ARGS[@]}"
  -data "$DATA_DIR"
  -db "$DB"
  -port "$PORT"
  -threads "$THREADS"
)

if command -v setsid >/dev/null 2>&1; then
  setsid nohup "$JAVA" "${JAVA_ARGS[@]}" >"$LOG_FILE" 2>&1 &
else
  nohup "$JAVA" "${JAVA_ARGS[@]}" >"$LOG_FILE" 2>&1 &
fi
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

# ---------------------------------------------------------------------------
# Wait until the port is ready
# ---------------------------------------------------------------------------
note "⏳ Waiting for port $PORT to become ready…"
for _ in $(seq 1 60); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    err "❌ Server process exited unexpectedly; check the log: $LOG_FILE"
    tail -n 20 "$LOG_FILE" || true
    rm -f "$PID_FILE"
    exit 1
  fi
  if (echo >/dev/tcp/127.0.0.1/"$PORT") 2>/dev/null; then
    echo
    ok "✅ IPC server is ready!"
    echo "   Address: http://localhost:$PORT"
    echo "   PID  : $SERVER_PID"
    echo "   Log    : $LOG_FILE"
    echo "   Stop   : run stop_olca_ipc.command  or  kill $SERVER_PID"
    # Performance note: detect whether native libraries were loaded.
    # Even when MKL is loaded, the old NativeLib check still prints
    # "no native libraries" (a false alarm), so prefer "loaded MKL libraries".
    if grep -q "loaded MKL libraries" "$LOG_FILE" 2>/dev/null; then
      echo
      ok "⚡ MKL high-performance solver enabled (native acceleration)."
    elif grep -q "no native libraries could be loaded" "$LOG_FILE" 2>/dev/null; then
      echo
      warn "⚠️  Performance note: native compute libraries (MKL) were not loaded; using the slower pure-Java solver."
      warn "   To enable MKL acceleration, confirm $SHIM_DIR/OlcaIpcServer.class and the olca-mkl directory exist."
    fi
    exit 0
  fi
  printf '.'
  sleep 1
done

echo
err "❌ Startup timed out (port not ready within 60 seconds). Check the log: $LOG_FILE"
tail -n 20 "$LOG_FILE" || true
exit 1
