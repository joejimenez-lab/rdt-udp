#!/usr/bin/env bash
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TC_SCRIPT="${SCRIPT_DIR}/tc_netem.sh"

IFACE="${IFACE:-lo}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-9000}"
TIMEOUT="${TIMEOUT:-1.0}"
PAYLOAD_SIZE="${PAYLOAD_SIZE:-512}"
WINDOW_SIZE="${WINDOW_SIZE:-1}"
MAX_RETRIES="${MAX_RETRIES:-10}"
TRIALS="${TRIALS:-3}"
MESSAGE="${MESSAGE:-Reliable UDP sender test message from Linux tc netem.}"
RESULTS_DIR="${RESULTS_DIR:-${ROOT_DIR}/results}"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_FILE:-${RESULTS_DIR}/sender_tc_${RUN_ID}.log}"

usage() {
    cat <<'USAGE'
Usage:
  scripts/sender_linux_trials.sh

Run from Linux while receiver.py is already running in another terminal.

Common environment variables:
  IFACE=lo              Interface affected by tc. Use lo for localhost.
  HOST=127.0.0.1        Receiver host.
  PORT=9000             Receiver port.
  TIMEOUT=1.0           Sender timeout in seconds.
  PAYLOAD_SIZE=512      Sender payload size.
  WINDOW_SIZE=1         Sender window size. 1 means stop-and-wait.
  MAX_RETRIES=10        Retransmissions before sender gives up.
  TRIALS=3              Number of sender runs per scenario.
  MESSAGE='text'        Message to send.
  RESULTS_DIR=results   Directory for report logs.

Examples:
  scripts/sender_linux_trials.sh
  LOSS=10% DELAY=200ms scripts/tc_netem.sh apply
  PAYLOAD_SIZE=8 WINDOW_SIZE=4 TRIALS=5 scripts/sender_linux_trials.sh

Notes:
  The current sender accepts legacy checksum=0 ACKs by default.
  For strict ACK checksum testing, add STRICT_ACK_CHECKSUM=1.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 was not found." >&2
    exit 1
fi

if [[ ! -x "$TC_SCRIPT" ]]; then
    echo "Expected executable tc helper at ${TC_SCRIPT}" >&2
    exit 1
fi

mkdir -p "$RESULTS_DIR"

cleanup() {
    IFACE="$IFACE" "$TC_SCRIPT" clear >/dev/null 2>&1 || true
}
trap cleanup EXIT

log() {
    printf '%s\n' "$*" | tee -a "$LOG_FILE"
}

run_sender_once() {
    local label="$1"
    local trial="$2"
    local -a cmd=(
        python3 "${ROOT_DIR}/sender.py"
        --host "$HOST"
        --port "$PORT"
        --timeout "$TIMEOUT"
        --payload-size "$PAYLOAD_SIZE"
        --window-size "$WINDOW_SIZE"
        --max-retries "$MAX_RETRIES"
        --message "$MESSAGE"
    )

    if [[ "${STRICT_ACK_CHECKSUM:-0}" == "1" ]]; then
        cmd+=(--strict-ack-checksum)
    fi

    log ""
    log "=== ${label}, trial ${trial}/${TRIALS} ==="
    log "Command: ${cmd[*]}"

    if "${cmd[@]}" 2>&1 | tee -a "$LOG_FILE"; then
        log "Result: PASS"
    else
        local status=$?
        log "Result: FAIL status=${status}"
        return "$status"
    fi
}

run_scenario() {
    local label="$1"
    local delay="$2"
    local loss="$3"
    local corrupt="$4"

    log ""
    log "############################"
    log "Scenario: ${label}"
    log "IFACE=${IFACE} DELAY=${delay} LOSS=${loss} CORRUPT=${corrupt}"
    log "############################"

    IFACE="$IFACE" DELAY="$delay" LOSS="$loss" CORRUPT="$corrupt" "$TC_SCRIPT" apply 2>&1 | tee -a "$LOG_FILE"
    IFACE="$IFACE" "$TC_SCRIPT" show 2>&1 | tee -a "$LOG_FILE"

    local failures=0
    local trial
    for trial in $(seq 1 "$TRIALS"); do
        if ! run_sender_once "$label" "$trial"; then
            failures=$((failures + 1))
        fi
    done

    IFACE="$IFACE" "$TC_SCRIPT" clear 2>&1 | tee -a "$LOG_FILE"
    log "Scenario summary: ${label}, failures=${failures}/${TRIALS}"
}

log "Sender tc/netem trial log"
log "Started: $(date)"
log "Receiver expected at ${HOST}:${PORT}"
log "Sender settings: TIMEOUT=${TIMEOUT}, PAYLOAD_SIZE=${PAYLOAD_SIZE}, WINDOW_SIZE=${WINDOW_SIZE}, MAX_RETRIES=${MAX_RETRIES}, TRIALS=${TRIALS}"

run_scenario "baseline" "0ms" "0%" "0%"
run_scenario "delay_100ms" "100ms" "0%" "0%"
run_scenario "loss_5_percent" "0ms" "5%" "0%"
run_scenario "delay_100ms_loss_5_percent" "100ms" "5%" "0%"

log ""
log "Completed: $(date)"
log "Log file: ${LOG_FILE}"
