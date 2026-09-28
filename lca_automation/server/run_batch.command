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
[ -x "$PY" ] || { err "❌ Python interpreter not found: $PY"; echo "   Set LCA_PYTHON to an interpreter that has olca_ipc."; exit 1; }
"$PY" -c "import olca_ipc" 2>/dev/null || { err "❌ This Python is missing the olca_ipc module: $PY"; exit 1; }
[ -f "$START_SH" ] || { err "❌ Start script not found: $START_SH"; exit 1; }

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

[ "${#CASES[@]}" -gt 0 ] || { err "❌ No runnable cases found. Check directory: $CASES_DIR"; exit 1; }

echo "=============================================================="
note "LCA serial batch processing (option A)"
echo "=============================================================="
echo "  Python   : $PY"
echo "  Database   : $OLCA_DB"
echo "  Port       : $PORT"
echo "  Case count : ${#CASES[@]}"
echo "  Results dir: $RESULTS_DIR"
echo "--------------------------------------------------------------"

# ---------------------------------------------------------------------------
# Start the server (if the port is already listening, reuse it and do not stop it at the end)
# ---------------------------------------------------------------------------
STARTED_BY_US=0
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  warn "⚠️  Port $PORT is already listening; reusing the existing server (will not stop it at the end)."
else
  note "🚀 Starting IPC server…"
  if ! OLCA_PORT="$PORT" OLCA_DB="$OLCA_DB" ${OLCA_XMX:+OLCA_XMX="$OLCA_XMX"} "$START_SH" "$OLCA_DB"; then
    err "❌ Server failed to start; aborting batch."
    exit 1
  fi
  STARTED_BY_US=1
fi

# Cleanup on exit (stop the server only if this script started it)
cleanup() {
  if [ "$STARTED_BY_US" -eq 1 ]; then
    echo
    note "🧹 Stopping the IPC server started by this script…"
    OLCA_PORT="$PORT" "$STOP_SH" || true
  else
    note "ℹ️  Reused existing server left running; not stopped."
  fi
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Run cases serially
# ---------------------------------------------------------------------------
PASS=0; FAIL=0
printf '%-4s %-9s %-9s %s\n' "#" "Status" "Time(s)" "Case" > "$SUMMARY"

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
    err "  Skipping: file does not exist -> $case"
    printf '%-4s %-9s %-9s %s\n' "$idx" "MISSING" "-" "$base" >> "$SUMMARY"
    FAIL=$((FAIL+1))
    continue
  fi

  t0=$(date +%s)
  # PYTHONUNBUFFERED streams output live to both the log and the terminal
  PYTHONUNBUFFERED=1 "$PY" -m lca_automation.main "$case" 2>&1 | tee "$logf"
  rc=${PIPESTATUS[0]}
  t1=$(date +%s); dt=$((t1-t0))

  if [ "$rc" -eq 0 ] && grep -q "completed successfully" "$logf" 2>/dev/null; then
    ok "  ✅ Completed (${dt}s) log: $logf"
    printf '%-4s %-9s %-9s %s\n' "$idx" "OK" "$dt" "$base" >> "$SUMMARY"
    PASS=$((PASS+1))
  else
    err "  ❌ Failed (exit code ${rc}, ${dt}s) log: $logf"
    printf '%-4s %-9s %-9s %s\n' "$idx" "FAIL($rc)" "$dt" "$base" >> "$SUMMARY"
    FAIL=$((FAIL+1))
  fi
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "=============================================================="
note "Batch finished: passed $PASS / failed $FAIL / total ${#CASES[@]}"
echo "=============================================================="
cat "$SUMMARY"
echo "--------------------------------------------------------------"
echo "Summary file: $SUMMARY"

exit 0
