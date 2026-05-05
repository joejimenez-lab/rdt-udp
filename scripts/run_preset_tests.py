#!/usr/bin/env python3
"""Run preset reliable-UDP tests and save sender/receiver logs."""

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
TC_SCRIPT = SCRIPT_DIR / "tc_netem.sh"


@dataclass(frozen=True)
class Preset:
    name: str
    delay: str = "0ms"
    loss: str = "0%"
    corrupt: str = "0%"
    window_size: int = 1


PRESETS = [
    Preset("baseline"),
    Preset("delay_100ms", delay="100ms"),
    Preset("loss_5_percent", loss="5%"),
    Preset("corrupt_10_percent", corrupt="10%"),
    Preset("window_4_baseline", window_size=4),
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run preset UDP reliability tests with fresh receiver processes."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--iface", default="lo")
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--payload-size", type=int, default=8)
    parser.add_argument("--max-retries", type=int, default=10)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--receiver-startup-delay", type=float, default=1.0)
    parser.add_argument(
        "--message",
        default="Reliable UDP network test message split into several chunks.",
    )
    parser.add_argument("--results-dir", default=str(ROOT_DIR / "results"))
    parser.add_argument(
        "--tests",
        nargs="+",
        choices=[preset.name for preset in PRESETS],
        default=None,
        help="Preset tests to run. Default: all presets unless --menu is used.",
    )
    parser.add_argument(
        "--menu",
        action="store_true",
        help="Open an interactive numbered preset menu.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available preset tests and exit.",
    )
    return parser.parse_args()


def run_command(cmd, *, env=None, log_file=None, check=False):
    print(f"$ {' '.join(str(part) for part in cmd)}")
    with subprocess.Popen(
        cmd,
        cwd=ROOT_DIR,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="")
            if log_file is not None:
                log_file.write(line)
        status = proc.wait()

    if check and status != 0:
        raise subprocess.CalledProcessError(status, cmd)

    return status


def apply_netem(preset, iface, summary):
    env = os.environ.copy()
    env.update(
        {
            "IFACE": iface,
            "DELAY": preset.delay,
            "LOSS": preset.loss,
            "CORRUPT": preset.corrupt,
        }
    )
    run_command([str(TC_SCRIPT), "apply"], env=env, log_file=summary, check=True)
    run_command([str(TC_SCRIPT), "show"], env=env, log_file=summary, check=True)


def clear_netem(iface, summary=None):
    env = os.environ.copy()
    env["IFACE"] = iface
    run_command([str(TC_SCRIPT), "clear"], env=env, log_file=summary, check=False)


def start_receiver(receiver_log):
    handle = receiver_log.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-u", str(ROOT_DIR / "receiver.py")],
        cwd=ROOT_DIR,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, handle


def stop_receiver(proc, handle):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    handle.close()


def port_is_available(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((host, port))
    except OSError:
        return False
    finally:
        sock.close()
    return True


def require_receiver_port_available(host, port):
    if port_is_available(host, port):
        return

    raise RuntimeError(
        f"UDP port {host}:{port} is already in use. Stop the existing receiver "
        "before running preset tests. Try: ps -ef | grep '[r]eceiver.py'"
    )


def run_trial(args, preset, trial, run_id, summary):
    sender_log = Path(args.results_dir) / f"{run_id}_{preset.name}_trial_{trial}_sender.log"
    receiver_log = Path(args.results_dir) / f"{run_id}_{preset.name}_trial_{trial}_receiver.log"
    sender_cmd = [
        sys.executable,
        str(ROOT_DIR / "sender.py"),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--timeout",
        str(args.timeout),
        "--payload-size",
        str(args.payload_size),
        "--window-size",
        str(preset.window_size),
        "--max-retries",
        str(args.max_retries),
        "--message",
        args.message,
    ]

    print(f"\n=== {preset.name}, trial {trial}/{args.trials} ===")
    print(f"Sender log: {sender_log}")
    print(f"Receiver log: {receiver_log}")
    summary.write(f"\n=== {preset.name}, trial {trial}/{args.trials} ===\n")
    summary.write(f"Sender log: {sender_log}\n")
    summary.write(f"Receiver log: {receiver_log}\n")

    receiver_proc, receiver_handle = start_receiver(receiver_log)
    time.sleep(args.receiver_startup_delay)
    if receiver_proc.poll() is not None:
        receiver_handle.close()
        summary.write("Result: FAIL receiver_start\n")
        return 1

    try:
        with sender_log.open("w", encoding="utf-8") as sender_handle:
            status = run_command(sender_cmd, log_file=sender_handle, check=False)
    finally:
        stop_receiver(receiver_proc, receiver_handle)

    result = "PASS" if status == 0 else f"FAIL status={status}"
    print(f"Result: {result}")
    summary.write(f"Result: {result}\n")
    summary.flush()
    return status


def selected_presets(names):
    by_name = {preset.name: preset for preset in PRESETS}
    return [by_name[name] for name in names]


def print_preset_list():
    for index, preset in enumerate(PRESETS, start=1):
        print(
            f"{index}. {preset.name} "
            f"(delay={preset.delay}, loss={preset.loss}, "
            f"corrupt={preset.corrupt}, window_size={preset.window_size})"
        )


def prompt_for_presets():
    print("Available preset tests:")
    print_preset_list()
    print(f"{len(PRESETS) + 1}. all")
    print("q. quit")
    print()
    print("Choose one or more presets by number, separated by spaces or commas.")
    print("Example: 1 3 5")

    while True:
        choice = input("Selection: ").strip().lower()
        if choice in {"q", "quit", "exit"}:
            raise SystemExit(0)

        if choice in {"all", "a", str(len(PRESETS) + 1)}:
            return list(PRESETS)

        tokens = [token for token in choice.replace(",", " ").split() if token]
        selected = []
        seen = set()
        invalid = []

        for token in tokens:
            if not token.isdigit():
                invalid.append(token)
                continue

            index = int(token)
            if index < 1 or index > len(PRESETS):
                invalid.append(token)
                continue

            preset = PRESETS[index - 1]
            if preset.name not in seen:
                selected.append(preset)
                seen.add(preset.name)

        if selected and not invalid:
            return selected

        print("Invalid selection. Use preset numbers from the list, or choose all.")


def main():
    args = parse_args()

    if args.list:
        print_preset_list()
        return 0

    if args.payload_size <= 0:
        raise ValueError("--payload-size must be greater than 0")
    if args.trials <= 0:
        raise ValueError("--trials must be greater than 0")
    if not TC_SCRIPT.exists():
        raise FileNotFoundError(f"Expected tc helper at {TC_SCRIPT}")
    require_receiver_port_available(args.host, args.port)

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    summary_log = results_dir / f"preset_tests_{run_id}.log"
    failures = 0

    def handle_signal(signum, _frame):
        print(f"\nReceived signal {signum}; clearing netem before exit.")
        clear_netem(args.iface)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    with summary_log.open("w", encoding="utf-8") as summary:
        summary.write("Preset reliable-UDP test log\n")
        summary.write(f"Started: {time.ctime()}\n")
        summary.write(f"Results directory: {results_dir}\n")

        presets_to_run = (
            prompt_for_presets()
            if args.menu
            else selected_presets(args.tests or [preset.name for preset in PRESETS])
        )

        for preset in presets_to_run:
            print(f"\n############################")
            print(f"Scenario: {preset.name}")
            print(
                f"DELAY={preset.delay} LOSS={preset.loss} "
                f"CORRUPT={preset.corrupt} WINDOW_SIZE={preset.window_size}"
            )
            print("############################")
            summary.write(f"\nScenario: {preset.name}\n")
            summary.flush()

            apply_netem(preset, args.iface, summary)
            scenario_failures = 0
            try:
                for trial in range(1, args.trials + 1):
                    if run_trial(args, preset, trial, run_id, summary) != 0:
                        scenario_failures += 1
            finally:
                clear_netem(args.iface, summary)

            failures += scenario_failures
            line = f"Scenario summary: {preset.name}, failures={scenario_failures}/{args.trials}"
            print(line)
            summary.write(line + "\n")

        summary.write(f"\nCompleted: {time.ctime()}\n")
        summary.write(f"Total failures: {failures}\n")

    print(f"\nSummary log: {summary_log}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
