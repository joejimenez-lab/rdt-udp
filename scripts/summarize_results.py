#!/usr/bin/env python3
"""Summarize logs from a run_preset_tests.py results folder."""

import argparse
import re
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS_DIR = ROOT_DIR / "results"
GREP_PATTERNS = ("complete: SenderStats", "Result:", "Scenario summary")
STATS_RE = re.compile(r"SenderStats\((?P<body>[^)]*)\)")
SENDER_LOG_RE = re.compile(
    r"(?P<run_id>\d{8}_\d{6})_(?P<scenario>.+)_trial_(?P<trial>\d+)_sender\.log$"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Print a grep-style summary and table for preset test logs."
    )
    parser.add_argument(
        "run",
        nargs="?",
        help="Run id, results subfolder name, or full path. Prompts when omitted.",
    )
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    return parser.parse_args()


def list_run_dirs(results_dir):
    if not results_dir.exists():
        return []
    return sorted(
        [path for path in results_dir.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def prompt_for_run(results_dir):
    run_dirs = list_run_dirs(results_dir)
    if not run_dirs:
        raise FileNotFoundError(f"No run folders found under {results_dir}")

    print("Available result runs:")
    for index, path in enumerate(run_dirs[:10], start=1):
        print(f"{index}. {path.name}")
    print()
    print("Enter a run id/folder name, number from the list, or press Enter for latest.")

    choice = input("Run: ").strip()
    if not choice:
        return run_dirs[0]
    if choice.isdigit():
        index = int(choice)
        if 1 <= index <= len(run_dirs[:10]):
            return run_dirs[index - 1]
    return resolve_run_path(choice, results_dir)


def resolve_run_path(run, results_dir):
    path = Path(run)
    if path.exists():
        return path

    direct = results_dir / run
    if direct.exists():
        return direct

    matches = sorted(results_dir.glob(f"*{run}*"))
    matches = [match for match in matches if match.is_dir()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(match.name for match in matches)
        raise ValueError(f"Run id matched multiple folders: {names}")

    raise FileNotFoundError(f"Could not find results folder for {run}")


def grep_style_lines(run_dir):
    for path in sorted(run_dir.glob("*.log")):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if any(pattern in line for pattern in GREP_PATTERNS):
                    yield f"{path}:{line.rstrip()}"


def parse_stats(line):
    match = STATS_RE.search(line)
    if not match:
        return None

    stats = {}
    for part in match.group("body").split(", "):
        key, value = part.split("=", 1)
        stats[key] = int(value)
    return stats


def scenario_from_sender_log(path):
    match = SENDER_LOG_RE.match(path.name)
    if not match:
        return path.stem, ""
    return match.group("scenario"), match.group("trial")


def sender_rows(run_dir):
    rows = []
    for path in sorted(run_dir.glob("*_sender.log")):
        stats = None
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parsed = parse_stats(line)
                if parsed is not None:
                    stats = parsed

        scenario, trial = scenario_from_sender_log(path)
        if stats is None:
            rows.append([scenario, trial, "FAIL", "-", "-", "-", "-", "-"])
            continue

        rows.append(
            [
                scenario,
                trial,
                "PASS",
                stats["original_packets"],
                stats["packets_sent"],
                stats["retransmissions"],
                stats["timeouts"],
                stats["acks_received"],
            ]
        )
    return rows


def print_table(rows):
    headers = [
        "Scenario",
        "Trial",
        "Result",
        "Original",
        "Sent",
        "Retrans",
        "Timeouts",
        "ACKs",
    ]
    table = [headers] + [[str(item) for item in row] for row in rows]
    widths = [max(len(row[index]) for row in table) for index in range(len(headers))]

    def format_row(row):
        return " | ".join(str(value).ljust(widths[index]) for index, value in enumerate(row))

    print(format_row(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(format_row(row))


def main():
    args = parse_args()
    results_dir = Path(args.results_dir)
    run_dir = resolve_run_path(args.run, results_dir) if args.run else prompt_for_run(results_dir)

    print(f"\nResults folder: {run_dir}")
    print("\nGrep-style summary:")
    for line in grep_style_lines(run_dir):
        print(line)

    print("\nResult table:")
    rows = sender_rows(run_dir)
    if rows:
        print_table(rows)
    else:
        print("No sender logs found.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
