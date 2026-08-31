#!/usr/bin/env bash
#
# stop_olca_ipc.command —— 停止 openLCA headless IPC 服务器（方案 A）
#
# 用法：
#   双击本文件；或终端执行： ./stop_olca_ipc.command
#
# 可选环境变量：
#   OLCA_PORT  端口（默认 8080）—— 用于定位对应的 PID 文件

set -euo pipefail

PORT="${OLCA_PORT:-8080}"
RUN_DIR="$HOME/.olca-ipc"
PID_FILE="$RUN_DIR/ipc-$PORT.pid"

ok()   { printf '\033[0;32m%s\033[0m\n' "$*"; }
warn() { printf '\033[0;33m%s\033[0m\n' "$*"; }
err()  { printf '\033[0;31m%s\033[0m\n' "$*"; }

echo "停止 openLCA IPC 服务器（端口 ${PORT}）…"

# 收集所有可能的目标 PID（RPC 关库后端口会释放，故须在此之前抓取）：
#   - PID 文件中记录的进程
#   - 当前正监听该端口的进程
PIDS=""
[ -f "$PID_FILE" ] && PIDS="$(cat "$PID_FILE" 2>/dev/null || true)"
PORT_PID="$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
PIDS="$(printf '%s\n%s\n' "$PIDS" "$PORT_PID" | sort -u | grep -E '^[0-9]+$' || true)"

# 1) 优先用 JSON-RPC 优雅关闭（让数据库正常落盘、释放锁）
if (echo >/dev/tcp/127.0.0.1/"$PORT") 2>/dev/null; then
  curl -s -m 5 -X POST "http://localhost:$PORT" \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"runtime/shutdown"}' >/dev/null 2>&1 || true
  sleep 2
fi

# 2) 确保上述 JVM 进程真正退出（runtime/shutdown 会关库释放锁，但不退出 JVM）
for PID in $PIDS; do
  kill -0 "$PID" 2>/dev/null || continue
  kill "$PID" 2>/dev/null || true
  for _ in $(seq 1 10); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$PID" 2>/dev/null; then
    warn "进程未响应，强制结束 PID $PID"
    kill -9 "$PID" 2>/dev/null || true
  fi
done
rm -f "$PID_FILE"

# 3) 兜底：再查一次端口残留监听进程
LEFT="$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$LEFT" ]; then
  warn "清理端口 $PORT 上的残留进程：$LEFT"
  kill $LEFT 2>/dev/null || true
  sleep 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  err "❌ 端口 $PORT 仍被占用，请手动检查。"
  exit 1
fi

ok "✅ 服务器已停止，数据库已释放。现在可在 openLCA 图形界面中打开该数据库查看结果。"
