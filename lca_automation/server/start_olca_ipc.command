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
note "openLCA headless IPC 服务器启动器（方案 A）"
echo "=============================================================="
echo "  应用    : $OLCA_APP"
echo "  数据目录: $DATA_DIR"
echo "  数据库  : $DB"
echo "  端口    : $PORT"
echo "  内存    : $XMX    线程: $THREADS"
echo "--------------------------------------------------------------"

# ---------------------------------------------------------------------------
# Pre-start checks
# ---------------------------------------------------------------------------
[ -x "$JAVA" ]        || { err "❌ 找不到内置 Java：$JAVA"; exit 1; }
[ -n "$LIBS_DIR" ]    || { err "❌ 找不到 openLCA 插件库目录（plugins/olca-app_*/libs）"; exit 1; }
[ -d "$DATA_DIR/databases/$DB" ] || {
  err "❌ 数据库不存在：$DATA_DIR/databases/$DB"
  echo "   可用数据库："
  ls -1 "$DATA_DIR/databases" 2>/dev/null | sed 's/^/     - /'
  exit 1
}

# Port-in-use check
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  err "❌ 端口 $PORT 已被占用（可能服务器已在运行，或 GUI 的 IPC 已开启）。"
  echo "   先运行 stop_olca_ipc.command 停止，或换一个端口： OLCA_PORT=8090 $0"
  exit 1
fi

# Database lock check
#   The headless server and the openLCA GUI cannot open the same database.
#   - If the openLCA GUI is running: abort (most likely a real lock).
#   - If the GUI is not running but db.lck exists: usually a stale lock from
#     an unclean exit. Leave it to Derby, which can recover a same-host stale lock.
if pgrep -f "openLCA.app/Contents/MacOS" >/dev/null 2>&1; then
  if [ -f "$DATA_DIR/databases/$DB/db.lck" ]; then
    err "❌ openLCA 图形界面正在运行，且该数据库已被打开（存在 db.lck）。"
    err "   headless 服务器无法连接已被 GUI 打开的数据库。"
    err "   请先在 GUI 中关闭该数据库（或退出 openLCA）后重试。"
    exit 1
  fi
  warn "⚠️  检测到 openLCA 图形界面正在运行；请确认它没有打开数据库「$DB」。"
elif [ -f "$DATA_DIR/databases/$DB/db.lck" ]; then
  warn "⚠️  发现残留锁文件 db.lck（GUI 未运行，多为上次异常退出遗留）。将尝试照常启动。"
fi

# Do not start a second server if the recorded PID is still alive
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  warn "⚠️  服务器似乎已在运行（PID $(cat "$PID_FILE")，端口 ${PORT}）。"
  exit 0
fi

# ---------------------------------------------------------------------------
# Start the server
#   - cd to a writable directory so Derby does not try to write derby.log inside the read-only .app
#   - use nohup + setsid (when available) so the process survives closing the terminal
# ---------------------------------------------------------------------------
note "🚀 正在启动服务器…（首次加载数据库需要数秒）"
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
note "⏳ 等待端口 $PORT 就绪…"
for _ in $(seq 1 60); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    err "❌ 服务器进程意外退出，请查看日志：$LOG_FILE"
    tail -n 20 "$LOG_FILE" || true
    rm -f "$PID_FILE"
    exit 1
  fi
  if (echo >/dev/tcp/127.0.0.1/"$PORT") 2>/dev/null; then
    echo
    ok "✅ IPC 服务器已就绪！"
    echo "   地址 : http://localhost:$PORT"
    echo "   PID  : $SERVER_PID"
    echo "   日志 : $LOG_FILE"
    echo "   停止 : 运行 stop_olca_ipc.command  或  kill $SERVER_PID"
    # Performance note: detect whether native libraries were loaded.
    # Even when MKL is loaded, the old NativeLib check still prints
    # "no native libraries" (a false alarm), so prefer "loaded MKL libraries".
    if grep -q "loaded MKL libraries" "$LOG_FILE" 2>/dev/null; then
      echo
      ok "⚡ 已启用 MKL 高性能求解器（计算走原生加速）。"
    elif grep -q "no native libraries could be loaded" "$LOG_FILE" 2>/dev/null; then
      echo
      warn "⚠️  性能提示：未加载原生计算库（MKL），将使用较慢的纯 Java 求解器。"
      warn "   若需启用 MKL 加速，请确认 $SHIM_DIR/OlcaIpcServer.class 与 olca-mkl 目录存在。"
    fi
    exit 0
  fi
  printf '.'
  sleep 1
done

echo
err "❌ 启动超时（60 秒内端口未就绪）。请查看日志：$LOG_FILE"
tail -n 20 "$LOG_FILE" || true
exit 1
