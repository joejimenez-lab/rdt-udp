# Reliable Data Transfer over UDP

This project implements reliable data transfer on top of UDP in Python for
CS 5470 Computer Networks. UDP does not guarantee delivery, ordering, duplicate
protection, or corruption detection, so this project adds those mechanisms at
the application layer.

The protocol supports stop-and-wait and a configurable sender window. It uses
sequence numbers, ACKs, CRC checksums, receiver buffering, timeout-based
retransmission, and retry limits.

## Protocol Summary

Packets use a readable text format for debugging:

```text
seq_num|ack_num|payload|checksum
```

- `seq_num`: data packet sequence number
- `ack_num`: sequence number being acknowledged
- `payload`: message data, empty for ACKs
- `checksum`: CRC over `seq_num`, `ack_num`, and `payload`

The sender splits a message into payload-sized chunks, sends packets inside the
current sender window, tracks unacknowledged packets, and retransmits timed-out
packets. The receiver validates CRCs, sends ACKs, buffers valid in-window
packets, and delivers data upward only in sequence order.

## Repository Layout

```text
.
├── sender.py                  # Sender, window logic, ACK handling, retries
├── receiver.py                # UDP receiver, CRC validation, ACK generation
├── packet.py                  # Packet object and byte conversion helpers
├── utils.py                   # CRC/checksum helpers
├── scripts/
│   ├── run_preset_tests.py    # Linux tc netem preset runner
│   ├── run_proxy_tests.py     # Deterministic UDP impairment proxy tests
│   ├── summarize_results.py   # Log summary helper
│   ├── tc_netem.sh            # Linux tc netem wrapper
│   └── sender_linux_trials.sh # Older Linux trial runner
├── linux_test_results/        # Raw experimental results and brief READMEs
└── Docs/
    ├── Papers/                # Proposal, progress report, final report tex
    └── Slides/                # Final presentation PDF
```

## Running Manually

Start the receiver in one terminal:

```bash
python3 receiver.py
```

Run the sender in another terminal:

```bash
python3 sender.py --message "hello reliable udp" --max-retries 5
```

Send a multi-packet message:

```bash
python3 sender.py \
  --message "testing a larger sender window" \
  --payload-size 4 \
  --window-size 10 \
  --max-retries 5
```

For independent manual runs, restart the receiver. The receiver keeps
`expected_seq_num` in memory, while a new sender process starts at sequence 0.

## Test Scripts

Linux `tc netem` preset tests:

```bash
python3 scripts/run_preset_tests.py --menu
python3 scripts/run_preset_tests.py --list
python3 scripts/run_preset_tests.py --tests baseline loss_5_percent
python3 scripts/run_preset_tests.py --tests extreme_test
```

The `tc_netem.sh` helper can also be used directly on Linux:

```bash
DELAY=100ms LOSS=0% CORRUPT=0% scripts/tc_netem.sh apply
scripts/tc_netem.sh show
scripts/tc_netem.sh clear
```

Proxy-based impairment tests, useful when Linux `tc netem` is not available:

```bash
python3 scripts/run_proxy_tests.py
python3 scripts/run_proxy_tests.py --tests all_tests
python3 scripts/run_proxy_tests.py --tests rigorous_test
```

## Raw Experimental Results

Raw logs are organized under `linux_test_results/`. Each subfolder has its own
short `README.md`.

```text
linux_test_results/
├── 01_two_terminal_manual_demo/
├── 02_tc_netem_preset_tests/
├── 03_proxy_impairment_tests/
├── 04_limit_failure_test/
├── 05_loss_threshold_test/
└── 06_timeout_threshold_test/
```

Summary of final runs:

| Scenario | Result | Original packets | Packets sent | Retransmissions | Timeouts | ACKs received |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Manual two-terminal demo | Pass | 8 | 8 | 0 | 0 | 8 |
| Baseline | Pass | 10 | 10 | 0 | 0 | 10 |
| 100 ms delay | Pass | 10 | 10 | 0 | 0 | 10 |
| 5% packet loss | Pass | 10 | 12 | 2 | 2 | 10 |
| 2% corruption | Pass | 11 | 11 | 0 | 0 | 11 |
| 10% corruption | Pass | 11 | 13 | 2 | 2 | 11 |
| Window size 4 baseline | Pass | 11 | 11 | 0 | 0 | 11 |
| 100 ms delay + 5% loss | Pass | 8 | 9 | 1 | 1 | 8 |
| Extreme tc netem test | Pass | 29 | 46 | 17 | 17 | 29 |
| Proxy all_tests | Pass | 17 | 59 | 42 | 42 | 17 |
| Proxy rigorous_test | Pass | 46 | 62 | 16 | 16 | 49 |
| 100% loss stress | Fail by design | 8 | - | - | - | 0 |
| 70% loss stress | Fail by design | 9 | - | - | - | 0 |
| 500 ms delay / 100 ms timeout | Fail by design | 10 | - | - | - | 0 |

The stress failures are intentional limitation tests. They show that when loss
or delay exceeds the configured retry/timeout budget, the sender raises
`TimeoutError` instead of hanging forever.

## Reports and Presentation

- Final report source: `Docs/Papers/finaReport.tex`
- Progress report source: `Docs/Papers/ProgressReport.tex`
- Proposal PDF: `Docs/Papers/CS5470_Proposal.pdf`
- Final presentation PDF: `Docs/Slides/Final Presentatiomn - CS5470 (2).pdf`

## Current Limitations

- Packet encoding is text-based and uses `|` as a separator, so payloads cannot
  contain `|`.
- The receiver does not expose host, port, or window size through CLI arguments.
- Timeout and retry values are fixed by configuration; adaptive RTT-based
  timeout estimation is future work.
- This is a project implementation for inspecting reliable transport behavior,
  not a production transport protocol.

## Authors

Joe Jimenez and Alan Lam  
CS 5470 Computer Networks
