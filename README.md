# Reliable Data Transfer over UDP

This project implements a small reliable data transfer protocol on top of UDP in
Python. UDP by itself does not guarantee delivery, ordering, duplicate
protection, or corruption detection, so the sender and receiver add those pieces
at the application layer.

The project starts from stop-and-wait behavior and extends it with packet
checksums, ACK validation, timeout-based retransmission, message packetization,
and configurable sender window size. The packet format is intentionally simple
so the protocol state is easy to inspect while testing.

## Protocol

Packets are encoded as text:

```text
seq_num|ack_num|payload|checksum
```

The fields are:

- `seq_num`: sequence number for data ordering.
- `ack_num`: sequence number being acknowledged.
- `payload`: message data carried by the packet.
- `checksum`: checksum over `seq_num`, `ack_num`, and `payload`.

The sender splits a message into payload-sized chunks, assigns sequence numbers,
computes checksums, sends packets over UDP, and waits for matching ACKs. If an
ACK is missing, malformed, corrupt, or outside the active sender state, the
sender ignores it and relies on timeout retransmission.

The receiver validates incoming data checksums before sending an ACK. Valid
packets inside the receiver window are acknowledged and delivered in sequence.
Duplicate packets that were already acknowledged can be ACKed again so the
sender can recover when an earlier ACK was lost.

## Files

```text
.
├── sender.py              # Sender, retransmission logic, CLI options
├── receiver.py            # UDP receiver, checksum checks, ACK generation
├── packet.py              # Packet object and byte conversion helpers
├── utils.py               # Checksum and CRC helper functions
├── scripts/
│   ├── tc_netem.sh        # Linux tc/netem helper for delay/loss/corruption
│   └── sender_linux_trials.sh
├── linux_test_results/    # Saved sender and receiver logs from test runs
└── Docs/                  # Proposal, progress report, and report draft
```

## Running Locally

Start the receiver in one terminal:

```bash
python3 receiver.py
```

Run the sender in another terminal:

```bash
python3 sender.py --message "hello reliable udp" --max-retries 5
```

Run a multi-packet transfer by lowering the payload size:

```bash
python3 sender.py \
  --message "this message is split into several reliable udp packets" \
  --payload-size 8 \
  --max-retries 5
```

Run with a larger sender window:

```bash
python3 sender.py \
  --message "testing a larger sender window" \
  --payload-size 8 \
  --window-size 4 \
  --max-retries 5
```

For separate manual sender runs, restart the receiver between runs. The receiver
keeps its current expected sequence number in memory, while each new sender
process starts sequence numbers from zero.

## Linux Network Testing

The `scripts/tc_netem.sh` helper uses Linux `tc netem` to simulate delay, packet
loss, corruption, duplication, and reordering. It usually needs `sudo`.

Apply 100 ms delay:

```bash
DELAY=100ms LOSS=0% CORRUPT=0% scripts/tc_netem.sh apply
```

Apply 5% packet loss:

```bash
DELAY=0ms LOSS=5% CORRUPT=0% scripts/tc_netem.sh apply
```

Apply 10% corruption:

```bash
DELAY=0ms LOSS=0% CORRUPT=10% scripts/tc_netem.sh apply
```

Check and clear the active rule:

```bash
scripts/tc_netem.sh show
scripts/tc_netem.sh clear
```

The Python preset runner starts a fresh receiver for each trial, applies the
network condition, runs one sender transfer, saves sender and receiver logs, then
clears the network rule:

```bash
scripts/run_preset_tests.py --menu
```

Useful options:

```bash
scripts/run_preset_tests.py --list
scripts/run_preset_tests.py
scripts/run_preset_tests.py --tests baseline loss_5_percent
scripts/run_preset_tests.py --trials 3 --payload-size 8
scripts/run_preset_tests.py --iface eth0 --host 192.168.1.20
```

A Bash runner is also available at `scripts/sender_linux_trials.sh` for the same
basic preset workflow.

## Test Results

Saved logs are included under `linux_test_results/`. Each scenario has a sender
log and a matching receiver log.

| Scenario | Result | Original packets | Packets sent | Retransmissions | Timeouts | ACKs received |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | Pass | 10 | 10 | 0 | 0 | 10 |
| 100 ms delay | Pass | 10 | 10 | 0 | 0 | 10 |
| 5% packet loss | Pass | 10 | 12 | 2 | 2 | 10 |
| 2% corruption | Pass | 11 | 11 | 0 | 0 | 11 |
| 10% corruption | Pass | 11 | 13 | 2 | 2 | 11 |
| Window size 4 | Pass | 11 | 11 | 0 | 0 | 11 |

The loss and corruption runs show the main recovery behavior: packets or ACKs
were dropped/corrupted, the sender timed out, retransmitted the missing packet,
and still completed the transfer.

## Current Limitations

- The packet format is text-based and uses `|` as a separator, so payloads cannot
  contain `|`.
- Receiver runtime options are not yet exposed through command-line arguments.
- Receiver state is per process. Restart the receiver for independent manual test
  runs that start sender sequence numbers at zero.
- The implementation demonstrates reliable transfer behavior for this project,
  but it is not a production transport protocol.

## Authors

Joe Jimenez and Alan Lam  
CS 5470 Computer Networks
