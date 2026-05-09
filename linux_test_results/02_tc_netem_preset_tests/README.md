# Linux tc netem Preset Tests

- Sent messages: preset test messages from `scripts/run_preset_tests.py`; `extreme_test` used `extreme_test.txt`.
- Network conditions: baseline, 100 ms delay, 5% loss, 2%/10% corruption, window size 4 baseline, 100 ms delay plus 5% loss, and the extreme mixed-impairment preset.
- Result: all listed preset runs passed. The strongest passing run was `extreme_test`, which sent 46 packets to deliver 29 original packets.

