# Reliable Data Transfer over UDP

This project implements a reliable data transfer protocol on top of UDP using
Python. UDP does not guarantee delivery, ordering, duplicate protection, or data
integrity, so this project adds those reliability features at the application
layer.

The long-term goal is to build the protocol in stages:

1. Stop-and-wait reliable transfer
2. Checksums for corruption detection
3. ACK handling and retransmission on timeout
4. Larger message transfer across multiple packets
5. Sliding window support
6. Selective repeat for retransmitting only lost or corrupted packets

## Current Status

The project is currently in the first implementation stage. The sender supports
a basic stop-and-wait flow:

- build a packet with a sequence number, ACK number, payload, and checksum
- send the packet over UDP
- wait for an ACK from the receiver
- retransmit the same packet if the timeout expires
- move to the next sequence number only after receiving the expected ACK

The packet format is temporary and string-based so it is easy to print and debug:

```text
seq_num|ack_num|payload|checksum
```

The current implementation is not the final protocol yet. It is meant to provide
a simple baseline before adding sliding windows and selective repeat.

## Project Structure

```text
.
├── sender.py              # Stop-and-wait sender logic
├── receiver.py            # UDP receiver used for local testing
├── packet.py              # Packet object and byte conversion helpers
├── utils.py               # Shared helper functions, including checksum logic
└── Docs/                  # Proposal and progress report files
```

## Running Locally

Run the receiver in one terminal:

```bash
python3 receiver.py
```

Run the sender in another terminal:

```bash
python3 sender.py
```

The sender currently sends a test message to `localhost` on port `9000`.

## Planned Features

- Validate checksums on incoming ACK packets
- Validate checksums on incoming data packets
- Split larger messages into multiple packets
- Detect and handle duplicate packets
- Track ordering with sequence numbers
- Add packet loss, corruption, and delay testing
- Implement a sliding window
- Implement selective repeat
- Measure throughput, latency, and retransmissions

## Testing Plan

Initial testing is done locally using two terminals on the same machine. The
sender and receiver communicate over `localhost` using UDP sockets.

Later testing will include:

- packet loss simulation
- packet corruption simulation
- artificial network delay
- different timeout values
- different sliding window sizes
- transfer tests across two machines on the same network

## Authors

Joe Jimenez and Alan Lam  
CS 5470 Computer Networks
