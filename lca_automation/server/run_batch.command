#!/usr/bin/env bash
#
# run_batch.command —— 串行批处理多个 LCA 案例（方案 A：串行，最省内存）
#
# 作用：
#   1) 启动 openLCA headless IPC 服务器（默认端口 8080，复用 start_olca_ipc.command）
#   2) 依次（串行）运行多个 Excel 案例 —— 单个失败不中断，继续下一个
#   3) 全部跑完后停止服务器（仅当服务器是本脚本启动的）
#   4) 打印成功/失败汇总表，每个案例独立日志存到 batch_results/<时间戳>/
#
# 用法：
#   1) 在「访达 Finder」中双击本文件 —— 跑 LCA_case/ 下全部 *.xlsx
#   2) 终端指定若干案例（绝对或相对路径均可）：
#        ./run_batch.command "../../LCA_case/smartphone.xlsx" "../../LCA_case/battery production.xlsx"
#
# 可选环境变量（覆盖默认值）：
#   LCA_PYTHON   含 olca_ipc 的 Python 解释器
#                默认 /Users/haizhou/opt/anaconda3/envs/olca_py311/bin/python
#   OLCA_DB      headless 服务器加载的数据库名（databases 目录下文件夹名）
#                默认 "ecoinvent 3.12 Cutoff Unit 2025-12-19"
#   OLCA_PORT    IPC 端口（默认 8080）。注意：lca_automation.main 端口写死 8080，
#                若改端口则 main.py 连不上，仅在你自定义入口时才改。
#   OLCA_XMX     单服务器 JVM 最大堆内存（默认沿用 start 脚本的 16G）。
#                ⚠️ 本机物理内存有限时，完整 ecoinvent + 蒙特卡洛可能吃满内存导致变慢/OOM。
#   CASES_DIR    无参数时扫描的案例目录（默认 仓库根/LCA_case）
#
# 注意：headless 服务器与 openLCA 图形界面【不能同时打开同一个数据库】。

# 不使用 -e：单个案例失败时要继续后续案例
set -uo pipefail

# ---------------------------------------------------------------------------
# 路径与配置
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
# 前置检查
# ---------------------------------------------------------------------------
[ -x "$PY" ] || { err "❌ 找不到 Python 解释器：$PY"; echo "   用 LCA_PYTHON 环境变量指定含 olca_ipc 的解释器。"; exit 1; }
"$PY" -c "import olca_ipc" 2>/dev/null || { err "❌ 该 Python 缺少 olca_ipc 模块：$PY"; exit 1; }
[ -f "$START_SH" ] || { err "❌ 找不到启动脚本：$START_SH"; exit 1; }

# ---------------------------------------------------------------------------
# 收集案例列表（参数优先；否则扫描 CASES_DIR）
# ---------------------------------------------------------------------------
CASES=()
if [ "$#" -gt 0 ]; then
  for f in "$@"; do
    [[ "$f" = /* ]] || f="$(cd "$(pwd)" && pwd)/$f"   # 相对路径转绝对
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
# 启动服务器（若端口已被占用则认为已在运行，复用且结束时不关闭）
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

# 结束时清理（仅关闭本脚本启动的服务器）
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
# 串行运行案例
# ---------------------------------------------------------------------------
PASS=0; FAIL=0
printf '%-4s %-9s %-9s %s\n' "#" "状态" "耗时(s)" "案例" > "$SUMMARY"

cd "$REPO_ROOT"   # 必须在仓库根执行 python -m lca_automation.main
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
  # PYTHONUNBUFFERED 实时输出；同时写入日志和终端
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
# 汇总
# ---------------------------------------------------------------------------
echo
echo "=============================================================="
note "批处理完成：成功 $PASS / 失败 $FAIL / 共 ${#CASES[@]}"
echo "=============================================================="
cat "$SUMMARY"
echo "--------------------------------------------------------------"
echo "汇总文件：$SUMMARY"

exit 0
