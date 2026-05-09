# Proxy Impairment Tests

- Sent messages: proxy preset messages from `scripts/run_proxy_tests.py`.
- Network conditions: proxy-injected delay, jitter, packet loss, corruption, duplication, and reordering.
- Result: both proxy runs passed. `all_tests` delivered 17 original packets after 42 retransmissions; `rigorous_test` delivered 46 original packets and ignored 3 bad ACK checksums.

