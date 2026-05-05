#!/usr/bin/env python3
"""Run reproducible UDP impairment tests without Linux tc.

This helper is useful on macOS or CI environments where Linux tc/netem is not
available. It starts the normal receiver on port 9000, starts a UDP proxy on a
separate port, then points the sender at the proxy. The proxy applies
deterministic delay, jitter, loss, corruption, duplication, and reordering.
"""

import argparse
import heapq
import random
import select
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent


@dataclass(frozen=True)
class ProxyPreset:
    name: str
    delay_ms: float
    jitter_ms: float
    loss_percent: float
    corrupt_percent: float
    duplicate_percent: float
    reorder_percent: float
    window_size: int
    timeout: float
    payload_size: int
    max_retries: int
    message: str
    seed: int


PRESETS = [
    ProxyPreset(
        name="all_tests",
        delay_ms=100,
        jitter_ms=20,
        loss_percent=5,
        corrupt_percent=2,
        duplicate_percent=1,
        reorder_percent=2,
        window_size=4,
        timeout=0.75,
        payload_size=8,
        max_retries=40,
        message=(
            "Reliable UDP all-tests proxy run with delay, jitter, packet loss, "
            "corruption, duplication, reordering, and a sliding sender window."
        ),
        seed=547001,
    ),
    ProxyPreset(
        name="rigorous_test",
        delay_ms=100,
        jitter_ms=30,
        loss_percent=10,
        corrupt_percent=5,
        duplicate_percent=2,
        reorder_percent=5,
        window_size=1,
        timeout=1.0,
        payload_size=16,
        max_retries=80,
        message=(
            "Rigorous reliable UDP proxy stress test. This longer payload is "
            "split across many packets while bidirectional delay, jitter, loss, "
            "corruption, duplication, and reordering are applied. "
        )
        * 4,
        seed=547002,
    ),
]


class ImpairmentProxy:
    def __init__(self, preset, listen_host, listen_port, receiver_host, receiver_port):
        self.preset = preset
        self.listen = (listen_host, listen_port)
        self.receiver = (receiver_host, receiver_port)
        self.sender = None
        self.rng = random.Random(preset.seed)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.listen)
        self.sock.setblocking(False)
        self.stop_event = threading.Event()
        self.queue = []
        self.counter = 0

    def close(self):
        self.stop_event.set()
        self.sock.close()

    def run(self):
        while not self.stop_event.is_set():
            timeout = self._next_timeout()
            try:
                readable, _, _ = select.select([self.sock], [], [], timeout)
            except (OSError, ValueError):
                return

            if readable:
                try:
                    data, addr = self.sock.recvfrom(4096)
                except BlockingIOError:
                    data = None
                except OSError:
                    return

                if data is not None:
                    if addr == self.receiver:
                        if self.sender is not None:
                            self._enqueue(data, self.sender)
                    else:
                        self.sender = addr
                        self._enqueue(data, self.receiver)

            self._flush_ready()

    def _next_timeout(self):
        if not self.queue:
            return 0.05
        return max(0.0, min(0.05, self.queue[0][0] - time.monotonic()))

    def _enqueue(self, data, dest):
        if self._chance(self.preset.loss_percent):
            return

        packet = self._maybe_corrupt(data)
        self._schedule(packet, dest, duplicate=False)

        if self._chance(self.preset.duplicate_percent):
            self._schedule(packet, dest, duplicate=True)

    def _schedule(self, data, dest, duplicate):
        delay = self.preset.delay_ms / 1000.0
        if self.preset.jitter_ms:
            jitter = self.rng.uniform(-self.preset.jitter_ms, self.preset.jitter_ms)
            delay += jitter / 1000.0
        if self._chance(self.preset.reorder_percent):
            delay += self.rng.uniform(0.05, 0.2)
        if duplicate:
            delay += self.rng.uniform(0.01, 0.08)

        self.counter += 1
        heapq.heappush(self.queue, (time.monotonic() + max(0.0, delay), self.counter, data, dest))

    def _flush_ready(self):
        now = time.monotonic()
        while self.queue and self.queue[0][0] <= now:
            _, _, data, dest = heapq.heappop(self.queue)
            try:
                self.sock.sendto(data, dest)
            except OSError:
                return

    def _chance(self, percent):
        return self.rng.random() < percent / 100.0

    def _maybe_corrupt(self, data):
        if not self._chance(self.preset.corrupt_percent):
            return data
        if not data:
            return data

        # Keep the packet parseable and corrupt only the checksum field. The
        # receiver and sender both validate checksums after parsing, while this
        # avoids crashing the current receiver on malformed text packets.
        try:
            text = data.decode()
            prefix, checksum = text.rsplit("|", 1)
            return f"{prefix}|{int(checksum) + 1}".encode()
        except (UnicodeDecodeError, ValueError):
            return data[:-1] + bytes([data[-1] ^ 0x01])


def parse_args():
    parser = argparse.ArgumentParser(description="Run deterministic UDP proxy impairment tests.")
    parser.add_argument("--results-dir", default=str(ROOT_DIR / "linux_test_results"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--receiver-port", type=int, default=9000)
    parser.add_argument("--proxy-port", type=int, default=9100)
    parser.add_argument(
        "--tests",
        nargs="+",
        choices=[preset.name for preset in PRESETS],
        default=[preset.name for preset in PRESETS],
    )
    return parser.parse_args()


def selected_presets(names):
    by_name = {preset.name: preset for preset in PRESETS}
    return [by_name[name] for name in names]


def start_receiver(log_path):
    handle = log_path.open("w", encoding="utf-8")
    handle.write("Receiver started through scripts/run_proxy_tests.py\n")
    handle.flush()
    proc = subprocess.Popen(
        [sys.executable, "-u", str(ROOT_DIR / "receiver.py")],
        cwd=ROOT_DIR,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, handle


def stop_process(proc):
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def run_preset(args, preset):
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    sender_log = results_dir / f"{preset.name}_sender.log"
    receiver_log = results_dir / f"{preset.name}_receiver.log"

    receiver_proc, receiver_handle = start_receiver(receiver_log)
    proxy = ImpairmentProxy(preset, args.host, args.proxy_port, args.host, args.receiver_port)
    proxy_thread = threading.Thread(target=proxy.run, daemon=True)
    proxy_thread.start()
    time.sleep(1.0)

    sender_cmd = [
        sys.executable,
        str(ROOT_DIR / "sender.py"),
        "--host",
        args.host,
        "--port",
        str(args.proxy_port),
        "--timeout",
        str(preset.timeout),
        "--payload-size",
        str(preset.payload_size),
        "--window-size",
        str(preset.window_size),
        "--max-retries",
        str(preset.max_retries),
        "--message",
        preset.message,
    ]

    with sender_log.open("w", encoding="utf-8") as handle:
        handle.write(f"=== {preset.name} ===\n")
        handle.write(
            "Proxy impairment: "
            f"delay={preset.delay_ms}ms jitter={preset.jitter_ms}ms "
            f"loss={preset.loss_percent}% corrupt={preset.corrupt_percent}% "
            f"duplicate={preset.duplicate_percent}% reorder={preset.reorder_percent}% "
            f"seed={preset.seed}\n"
        )
        handle.write(f"Command: {' '.join(str(part) for part in sender_cmd)}\n")
        handle.flush()
        proc = subprocess.Popen(
            sender_cmd,
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            handle.write(line)
        status = proc.wait()
        handle.write(f"RESULT_STATUS={status}\n")

    proxy.close()
    proxy_thread.join(timeout=1)
    stop_process(receiver_proc)
    receiver_handle.close()
    return status


def main():
    args = parse_args()
    failures = 0

    def handle_signal(signum, _frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    for preset in selected_presets(args.tests):
        status = run_preset(args, preset)
        failures += 1 if status else 0
        print(f"{preset.name}: {'PASS' if status == 0 else f'FAIL status={status}'}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
