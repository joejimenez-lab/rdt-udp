#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage:
  scripts/tc_netem.sh apply
  scripts/tc_netem.sh show
  scripts/tc_netem.sh clear

Environment variables:
  IFACE      Network interface to affect. Default: lo
  DELAY      Delay value for netem. Default: 100ms
  JITTER     Optional delay jitter. Default: empty
  LOSS       Packet loss percentage. Default: 0%
  CORRUPT    Packet corruption percentage. Default: 0%
  DUPLICATE  Packet duplication percentage. Default: 0%
  REORDER    Packet reordering percentage. Default: 0%

Examples:
  DELAY=100ms LOSS=5% scripts/tc_netem.sh apply
  scripts/tc_netem.sh show
  scripts/tc_netem.sh clear

Notes:
  This script is for Linux. It uses tc netem and usually needs sudo.
  Use IFACE=lo for localhost testing or IFACE=eth0/wlan0 for LAN testing.
USAGE
}

need_tc() {
    if ! command -v tc >/dev/null 2>&1; then
        echo "tc was not found. Install iproute2 first." >&2
        exit 1
    fi
}

apply_netem() {
    local iface="${IFACE:-lo}"
    local delay="${DELAY:-100ms}"
    local jitter="${JITTER:-}"
    local loss="${LOSS:-0%}"
    local corrupt="${CORRUPT:-0%}"
    local duplicate="${DUPLICATE:-0%}"
    local reorder="${REORDER:-0%}"

    local args=(delay "$delay")
    if [[ -n "$jitter" ]]; then
        args+=("$jitter")
    fi

    args+=(loss "$loss" corrupt "$corrupt" duplicate "$duplicate")

    if [[ "$reorder" != "0" && "$reorder" != "0%" ]]; then
        args+=(reorder "$reorder")
    fi

    echo "Applying netem on ${iface}: ${args[*]}"
    sudo tc qdisc replace dev "$iface" root netem "${args[@]}"
}

clear_netem() {
    local iface="${IFACE:-lo}"
    echo "Clearing netem on ${iface}"
    sudo tc qdisc del dev "$iface" root 2>/dev/null || true
}

show_netem() {
    local iface="${IFACE:-lo}"
    tc qdisc show dev "$iface"
}

main() {
    if [[ $# -ne 1 ]]; then
        usage
        exit 1
    fi

    need_tc

    case "$1" in
        apply)
            apply_netem
            ;;
        clear)
            clear_netem
            ;;
        show)
            show_netem
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"
