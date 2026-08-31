#!/usr/bin/env bash
#
# start_olca_ipc.command —— 一键启动 openLCA headless IPC 服务器（方案 A）
#
# 作用：
#   不打开 openLCA 图形界面，直接以「无界面服务器」方式连接指定数据库，
#   在 8080 端口对外提供 JSON-RPC 接口（olca-ipc / Python 可直接连接）。
#
# 用法：
#   1) 在「访达 Finder」中双击本文件；或
#   2) 终端执行： ./start_olca_ipc.command ["数据库名"]
#
# 可选环境变量（覆盖默认值）：
#   OLCA_APP       openLCA.app 路径        默认 /Applications/openLCA.app
#   OLCA_DATA_DIR  工作区数据目录          默认 ~/openLCA-data-1.4
#   OLCA_DB        数据库名（databases 下的文件夹名）
#   OLCA_PORT      端口                    默认 8080
#   OLCA_XMX       JVM 最大堆内存          默认 16G
#   OLCA_THREADS   计算线程数              默认 4
#
# 注意：headless 服务器与 openLCA 图形界面【不能同时打开同一个数据库】。
#       启动前请确认 GUI 没有打开该数据库（脚本会自动检测数据库锁）。

set -euo pipefail

# ---------------------------------------------------------------------------
# 配置项
# ---------------------------------------------------------------------------
OLCA_APP="${OLCA_APP:-/Applications/openLCA.app}"
DATA_DIR="${OLCA_DATA_DIR:-$HOME/openLCA-data-1.4}"
DEFAULT_DB="ecoinvent 3.12 Cutoff Unit 2025-12-19"
PORT="${OLCA_PORT:-8080}"
XMX="${OLCA_XMX:-16G}"
THREADS="${OLCA_THREADS:-4}"

# 数据库名优先级：命令行参数 > OLCA_DB 环境变量 > 默认值
DB="${1:-${OLCA_DB:-$DEFAULT_DB}}"

# ---------------------------------------------------------------------------
# 路径推导
# ---------------------------------------------------------------------------
ECLIPSE="$OLCA_APP/Contents/Eclipse"
JAVA="$ECLIPSE/jre/Contents/Home/bin/java"
LIBS_DIR="$(ls -d "$ECLIPSE"/plugins/olca-app_*/libs 2>/dev/null | head -1 || true)"
MKL_DIR="$(ls -d "$ECLIPSE"/olca-mkl-* 2>/dev/null | head -1 || true)"

# 启动壳目录（用于在 headless 模式加载 MKL 原生计算库）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHIM_DIR="$SCRIPT_DIR/lib"

RUN_DIR="$HOME/.olca-ipc"
PID_FILE="$RUN_DIR/ipc-$PORT.pid"
LOG_FILE="$RUN_DIR/ipc-$PORT.log"
mkdir -p "$RUN_DIR"

note()  { printf '\033[0;36m%s\033[0m\n' "$*"; }   # 青色
ok()    { printf '\033[0;32m%s\033[0m\n' "$*"; }   # 绿色
warn()  { printf '\033[0;33m%s\033[0m\n' "$*"; }   # 黄色
err()   { printf '\033[0;31m%s\033[0m\n' "$*"; }   # 红色

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
# 启动前检查
# ---------------------------------------------------------------------------
[ -x "$JAVA" ]        || { err "❌ 找不到内置 Java：$JAVA"; exit 1; }
[ -n "$LIBS_DIR" ]    || { err "❌ 找不到 openLCA 插件库目录（plugins/olca-app_*/libs）"; exit 1; }
[ -d "$DATA_DIR/databases/$DB" ] || {
  err "❌ 数据库不存在：$DATA_DIR/databases/$DB"
  echo "   可用数据库："
  ls -1 "$DATA_DIR/databases" 2>/dev/null | sed 's/^/     - /'
  exit 1
}

# 端口占用检查
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  err "❌ 端口 $PORT 已被占用（可能服务器已在运行，或 GUI 的 IPC 已开启）。"
  echo "   先运行 stop_olca_ipc.command 停止，或换一个端口： OLCA_PORT=8090 $0"
  exit 1
fi

# 数据库占用检查
#   headless 服务器与 openLCA 图形界面不能同时打开同一个数据库。
#   - 若 openLCA GUI 正在运行：直接阻止（最可能是真实占用）。
#   - 若 GUI 未运行但存在 db.lck：多为上次非正常退出残留的「陈旧锁」，
#     交给 Derby 处理（Derby 能识别同机陈旧锁并重新启动）。
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

# 已有 PID 仍存活则不重复启动
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  warn "⚠️  服务器似乎已在运行（PID $(cat "$PID_FILE")，端口 ${PORT}）。"
  exit 0
fi

# ---------------------------------------------------------------------------
# 启动服务器
#   - cd 到可写目录，避免 Derby 在只读的 .app 内写 derby.log 报错
#   - 使用 nohup + setsid（若可用）让进程脱离终端，关闭窗口也不退出
# ---------------------------------------------------------------------------
note "🚀 正在启动服务器…（首次加载数据库需要数秒）"
cd "$RUN_DIR"

# 优先走启动壳（加载 MKL 高性能求解器）；缺少 .class 或 MKL 目录时回退到原生入口
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
# 等待端口就绪
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
    # 性能提示：检测原生计算库是否加载
    # 注意：即便 MKL 已加载，旧的 NativeLib 检查仍会打印 "no native libraries"
    # 警告（误报），因此必须优先判断 "loaded MKL libraries"。
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
