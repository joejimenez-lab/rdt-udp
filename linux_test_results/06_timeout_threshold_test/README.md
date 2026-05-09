# Timeout Threshold Test

- Sent message: `Intentional timeout threshold test with latency higher than sender timeout.`
- Network condition: Linux `tc netem` with 500 ms delay and no packet loss; sender timeout was 100 ms.
- Result: failed by design. The receiver received and ACKed sequence 0, but the sender timed out too quickly and hit `max_retries=3`.

