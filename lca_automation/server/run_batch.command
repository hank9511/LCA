#!/usr/bin/env bash
#
# run_batch.command — run LCA cases one after another (option A: serial, lowest memory)
#
# Purpose:
#   1) Start the openLCA headless IPC server (port 8080 by default, via start_olca_ipc.command)
#   2) Run Excel cases serially — one failure does not stop the rest
#   3) Stop the server when finished (only if this script started it)
#   4) Print a pass/fail summary; each case log goes to batch_results/<timestamp>/
#
# Usage:
#   1) Double-click this file in Finder — runs every *.xlsx under LCA_case/
#   2) Or pass case paths (absolute or relative):
#        ./run_batch.command "../../LCA_case/smartphone.xlsx" "../../LCA_case/battery production.xlsx"
#
# Optional environment variables (override the defaults):
#   LCA_PYTHON   Python interpreter that has olca_ipc
#                default /Users/haizhou/opt/anaconda3/envs/olca_py311/bin/python
#   OLCA_DB      database folder name loaded by the headless server
#                default "ecoinvent 3.12 Cutoff Unit 2025-12-19"
#   OLCA_PORT    IPC port (default 8080). lca_automation.main hard-codes 8080,
#                so changing the port breaks main.py unless you use a custom entry point.
#   OLCA_XMX     JVM max heap for the single server (default 16G from the start script).
#                With limited RAM, full ecoinvent plus Monte Carlo can exhaust memory and slow down or OOM.
#   CASES_DIR    case directory scanned when no arguments are given (default <repo>/LCA_case)
#
# Note: the headless server and the openLCA GUI cannot open the same database
#       at the same time.

# Do not use -e: a failed case must not abort the remaining cases
set -uo pipefail

# ---------------------------------------------------------------------------
# Paths and configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"          # .../lca_automation/server
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"                         # .../OpenLCA_1017_0610
START_SH="$SCRIPT_DIR/start_olca_ipc.command"
STOP_SH="$SCRIPT_DIR/stop_olca_ipc.command"

PY="${LCA_PYTHON:-/Users/haizhou/opt/anaconda3/envs/olca_py311/bin/python}"
OLCA_DB="${OLCA_DB:-ecoinvent 3.12 Cutoff Unit 2025-12-19}"
PORT="${OLCA_PORT:-8080}"
CASES_DIR="${CASES_DIR:-$REPO_ROOT/LCA_case}"

STAMP="$(date +%Y%m%d_%H%M%S)"
RESULTS_DIR="$REPO_ROOT/batch_results/$STAMP"
SUMMARY="$RESULTS_DIR/_summary.txt"
mkdir -p "$RESULTS_DIR"

note() { printf '\033[0;36m%s\033[0m\n' "$*"; }
ok()   { printf '\033[0;32m%s\033[0m\n' "$*"; }
warn() { printf '\033[0;33m%s\033[0m\n' "$*"; }
err()  { printf '\033[0;31m%s\033[0m\n' "$*"; }

# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------
[ -x "$PY" ] || { err "❌ 找不到 Python 解释器：$PY"; echo "   用 LCA_PYTHON 环境变量指定含 olca_ipc 的解释器。"; exit 1; }
"$PY" -c "import olca_ipc" 2>/dev/null || { err "❌ 该 Python 缺少 olca_ipc 模块：$PY"; exit 1; }
[ -f "$START_SH" ] || { err "❌ 找不到启动脚本：$START_SH"; exit 1; }

# ---------------------------------------------------------------------------
# Collect cases (arguments first; otherwise scan CASES_DIR)
# ---------------------------------------------------------------------------
CASES=()
if [ "$#" -gt 0 ]; then
  for f in "$@"; do
    [[ "$f" = /* ]] || f="$(cd "$(pwd)" && pwd)/$f"   # relative path to absolute
    CASES+=("$f")
  done
else
  while IFS= read -r f; do CASES+=("$f"); done \
    < <(find "$CASES_DIR" -maxdepth 1 -type f -iname "*.xlsx" 2>/dev/null | sort)
fi

[ "${#CASES[@]}" -gt 0 ] || { err "❌ 没有可运行的案例。检查目录：$CASES_DIR"; exit 1; }

echo "=============================================================="
note "LCA 串行批处理（方案 A）"
echo "=============================================================="
echo "  Python   : $PY"
echo "  数据库   : $OLCA_DB"
echo "  端口     : $PORT"
echo "  案例数   : ${#CASES[@]}"
echo "  结果目录 : $RESULTS_DIR"
echo "--------------------------------------------------------------"

# ---------------------------------------------------------------------------
# Start the server (if the port is already listening, reuse it and do not stop it at the end)
# ---------------------------------------------------------------------------
STARTED_BY_US=0
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  warn "⚠️  端口 $PORT 已在监听，复用现有服务器（结束时不会关闭它）。"
else
  note "🚀 启动 IPC 服务器…"
  if ! OLCA_PORT="$PORT" OLCA_DB="$OLCA_DB" ${OLCA_XMX:+OLCA_XMX="$OLCA_XMX"} "$START_SH" "$OLCA_DB"; then
    err "❌ 服务器启动失败，终止批处理。"
    exit 1
  fi
  STARTED_BY_US=1
fi

# Cleanup on exit (stop the server only if this script started it)
cleanup() {
  if [ "$STARTED_BY_US" -eq 1 ]; then
    echo
    note "🧹 停止本脚本启动的 IPC 服务器…"
    OLCA_PORT="$PORT" "$STOP_SH" || true
  else
    note "ℹ️  复用的现有服务器保持运行，未关闭。"
  fi
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Run cases serially
# ---------------------------------------------------------------------------
PASS=0; FAIL=0
printf '%-4s %-9s %-9s %s\n' "#" "状态" "耗时(s)" "案例" > "$SUMMARY"

cd "$REPO_ROOT"   # python -m lca_automation.main must run from the repository root
idx=0
for case in "${CASES[@]}"; do
  idx=$((idx+1))
  base="$(basename "$case")"
  safe="$(echo "$base" | tr ' /' '__')"
  logf="$RESULTS_DIR/${idx}_${safe}.log"

  echo
  echo "=============================================================="
  note "[$idx/${#CASES[@]}] ▶ $base"
  echo "=============================================================="

  if [ ! -f "$case" ]; then
    err "  跳过：文件不存在 -> $case"
    printf '%-4s %-9s %-9s %s\n' "$idx" "MISSING" "-" "$base" >> "$SUMMARY"
    FAIL=$((FAIL+1))
    continue
  fi

  t0=$(date +%s)
  # PYTHONUNBUFFERED streams output live to both the log and the terminal
  PYTHONUNBUFFERED=1 "$PY" -m lca_automation.main "$case" 2>&1 | tee "$logf"
  rc=${PIPESTATUS[0]}
  t1=$(date +%s); dt=$((t1-t0))

  if [ "$rc" -eq 0 ] && grep -q "LCA分析成功完成" "$logf" 2>/dev/null; then
    ok "  ✅ 完成（${dt}s）日志：$logf"
    printf '%-4s %-9s %-9s %s\n' "$idx" "OK" "$dt" "$base" >> "$SUMMARY"
    PASS=$((PASS+1))
  else
    err "  ❌ 失败（退出码 ${rc}，${dt}s）日志：$logf"
    printf '%-4s %-9s %-9s %s\n' "$idx" "FAIL($rc)" "$dt" "$base" >> "$SUMMARY"
    FAIL=$((FAIL+1))
  fi
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "=============================================================="
note "批处理完成：成功 $PASS / 失败 $FAIL / 共 ${#CASES[@]}"
echo "=============================================================="
cat "$SUMMARY"
echo "--------------------------------------------------------------"
echo "汇总文件：$SUMMARY"

exit 0
