# Limit Failure Test

- Sent message: `Intentional failure stress test with complete packet loss.`
- Network condition: Linux `tc netem` with 100% packet loss.
- Result: failed by design. The sender hit `max_retries=3` for sequence 0 and raised `TimeoutError`.

