# Loss Threshold Test

- Sent message: `Intentional threshold stress test with seventy percent packet loss.`
- Network condition: Linux `tc netem` with 70% packet loss.
- Result: failed by design. The receiver saw sequence 0 and sent ACKs, but the sender still hit the retry limit before receiving a valid ACK.

