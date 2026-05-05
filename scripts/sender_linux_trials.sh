#!/usr/bin/env bash
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TC_SCRIPT="${SCRIPT_DIR}/tc_netem.sh"

IFACE="${IFACE:-lo}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-9000}"
TIMEOUT="${TIMEOUT:-0.5}"
PAYLOAD_SIZE="${PAYLOAD_SIZE:-8}"
WINDOW_SIZE="${WINDOW_SIZE:-1}"
WINDOW_TEST_SIZE="${WINDOW_TEST_SIZE:-4}"
MAX_RETRIES="${MAX_RETRIES:-10}"
TRIALS="${TRIALS:-1}"
RECEIVER_STARTUP_DELAY="${RECEIVER_STARTUP_DELAY:-1}"
MESSAGE="${MESSAGE:-Reliable UDP network test message split into several chunks.}"
RESULTS_DIR="${RESULTS_DIR:-${ROOT_DIR}/results}"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
SUMMARY_LOG="${SUMMARY_LOG:-${RESULTS_DIR}/sender_tc_${RUN_ID}.log}"

receiver_pid=""

usage() {
    cat <<'USAGE'
Usage:
  scripts/sender_linux_trials.sh

Run from Linux. The script starts a fresh receiver for each trial, applies the
requested tc/netem condition, runs one sender transfer, saves sender and receiver
logs, then clears the network rule.

Common environment variables:
  IFACE=lo                 Interface affected by tc.
  HOST=127.0.0.1           Receiver host used by sender.
  PORT=9000                Receiver port.
  TIMEOUT=0.5              Sender timeout in seconds.
  PAYLOAD_SIZE=8           Sender payload size.
  WINDOW_SIZE=1            Sender window size for normal scenarios.
  WINDOW_TEST_SIZE=4       Sender window size for the window test scenario.
  MAX_RETRIES=10           Retransmissions before sender gives up.
  TRIALS=1                 Number of sender runs per scenario.
  MESSAGE='text'           Message to send.
  RESULTS_DIR=results      Directory for logs.

Examples:
  scripts/sender_linux_trials.sh
  TRIALS=3 scripts/sender_linux_trials.sh
  PAYLOAD_SIZE=8 WINDOW_TEST_SIZE=4 scripts/sender_linux_trials.sh

Notes:
  This script uses scripts/tc_netem.sh, which calls Linux tc netem and usually
  needs sudo.
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

log() {
    printf '%s\n' "$*" | tee -a "$SUMMARY_LOG"
}

stop_receiver() {
    if [[ -n "$receiver_pid" ]]; then
        kill "$receiver_pid" >/dev/null 2>&1 || true
        wait "$receiver_pid" >/dev/null 2>&1 || true
        receiver_pid=""
    fi
}

cleanup() {
    stop_receiver
    IFACE="$IFACE" "$TC_SCRIPT" clear >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

start_receiver() {
    local receiver_log="$1"

    python3 -u "${ROOT_DIR}/receiver.py" > "$receiver_log" 2>&1 &
    receiver_pid=$!
    sleep "$RECEIVER_STARTUP_DELAY"

    if ! kill -0 "$receiver_pid" >/dev/null 2>&1; then
        log "Receiver failed to start. See ${receiver_log}"
        return 1
    fi
}

run_sender_once() {
    local label="$1"
    local trial="$2"
    local window_size="$3"
    local sender_log="${RESULTS_DIR}/${RUN_ID}_${label}_trial_${trial}_sender.log"
    local receiver_log="${RESULTS_DIR}/${RUN_ID}_${label}_trial_${trial}_receiver.log"
    local -a cmd=(
        python3 "${ROOT_DIR}/sender.py"
        --host "$HOST"
        --port "$PORT"
        --timeout "$TIMEOUT"
        --payload-size "$PAYLOAD_SIZE"
        --window-size "$window_size"
        --max-retries "$MAX_RETRIES"
        --message "$MESSAGE"
    )

    log ""
    log "=== ${label}, trial ${trial}/${TRIALS} ==="
    log "Sender log: ${sender_log}"
    log "Receiver log: ${receiver_log}"
    log "Command: ${cmd[*]}"

    if ! start_receiver "$receiver_log"; then
        log "Result: FAIL receiver_start"
        return 1
    fi

    "${cmd[@]}" 2>&1 | tee "$sender_log" | tee -a "$SUMMARY_LOG"
    local status=${PIPESTATUS[0]}

    stop_receiver

    if [[ "$status" -eq 0 ]]; then
        log "Result: PASS"
    else
        log "Result: FAIL status=${status}"
    fi

    return "$status"
}

run_scenario() {
    local label="$1"
    local delay="$2"
    local loss="$3"
    local corrupt="$4"
    local window_size="$5"

    log ""
    log "############################"
    log "Scenario: ${label}"
    log "IFACE=${IFACE} DELAY=${delay} LOSS=${loss} CORRUPT=${corrupt} WINDOW_SIZE=${window_size}"
    log "############################"

    IFACE="$IFACE" DELAY="$delay" LOSS="$loss" CORRUPT="$corrupt" "$TC_SCRIPT" apply 2>&1 | tee -a "$SUMMARY_LOG"
    IFACE="$IFACE" "$TC_SCRIPT" show 2>&1 | tee -a "$SUMMARY_LOG"

    local failures=0
    local trial
    for trial in $(seq 1 "$TRIALS"); do
        if ! run_sender_once "$label" "$trial" "$window_size"; then
            failures=$((failures + 1))
        fi
    done

    IFACE="$IFACE" "$TC_SCRIPT" clear 2>&1 | tee -a "$SUMMARY_LOG"
    log "Scenario summary: ${label}, failures=${failures}/${TRIALS}"
}

log "Sender tc/netem trial log"
log "Started: $(date)"
log "Results directory: ${RESULTS_DIR}"
log "Sender settings: HOST=${HOST}, PORT=${PORT}, TIMEOUT=${TIMEOUT}, PAYLOAD_SIZE=${PAYLOAD_SIZE}, WINDOW_SIZE=${WINDOW_SIZE}, WINDOW_TEST_SIZE=${WINDOW_TEST_SIZE}, MAX_RETRIES=${MAX_RETRIES}, TRIALS=${TRIALS}"

run_scenario "baseline" "0ms" "0%" "0%" "$WINDOW_SIZE"
run_scenario "delay_100ms" "100ms" "0%" "0%" "$WINDOW_SIZE"
run_scenario "loss_5_percent" "0ms" "5%" "0%" "$WINDOW_SIZE"
run_scenario "corrupt_10_percent" "0ms" "0%" "10%" "$WINDOW_SIZE"
run_scenario "window_${WINDOW_TEST_SIZE}_baseline" "0ms" "0%" "0%" "$WINDOW_TEST_SIZE"

log ""
log "Completed: $(date)"
log "Summary log: ${SUMMARY_LOG}"
