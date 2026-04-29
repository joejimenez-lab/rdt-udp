# Sender for the reliable data transfer project.
#
# This file is only responsible for the sender side. The receiver has its own
# file, so this code assumes the receiver follows the packet and ACK behavior
# listed below.
#
# Sender-owned behavior:
# 1. split a message into payload-sized packets
# 2. assign sequence numbers and checksums to outgoing data packets
# 3. send packets over UDP using a configurable window size
# 4. wait for ACKs that match sent sequence numbers
# 5. retransmit unacknowledged packets after a timeout
# 6. validate ACK checksums when the receiver provides them
#
# Receiver contract:
# - data packets use seq_num for ordering
# - ACK packets should set ack_num to the seq_num being acknowledged
# - ACK checksums should be calculated over seq_num, ack_num, and payload
# - checksum=0 ACKs are still accepted by default while the receiver is simple
#
# Notes:
# - window_size=1 gives normal stop-and-wait behavior
# - larger window sizes let us test sender-side sliding window behavior
# - full selective repeat still needs receiver-side buffering/ACK support

import argparse
import socket
import time
from dataclasses import dataclass

from packet import Packet, convert_to_bytes, extract_from_bytes
from utils import calculate_checksum


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000
DEFAULT_TIMEOUT = 1.0
DEFAULT_PAYLOAD_SIZE = 512
DEFAULT_WINDOW_SIZE = 1


@dataclass
class SenderStats:
    # Counters used for debugging runs and report measurements.
    original_packets: int = 0
    packets_sent: int = 0
    retransmissions: int = 0
    timeouts: int = 0
    acks_received: int = 0
    bad_ack_checksums: int = 0
    malformed_acks: int = 0
    unexpected_acks: int = 0


class Sender:
    # Reliable sender built on top of a UDP socket.
    def __init__(
        self,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        timeout=DEFAULT_TIMEOUT,
        payload_size=DEFAULT_PAYLOAD_SIZE,
        window_size=DEFAULT_WINDOW_SIZE,
        max_retries=None,
        allow_legacy_acks=True,
    ):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(timeout)

        self.addr = (host, port)
        self.timeout = timeout
        self.seq_num = 0
        self.payload_size = payload_size
        self.window_size = window_size
        self.max_retries = max_retries
        self.allow_legacy_acks = allow_legacy_acks
        self.stats = SenderStats()

    def close(self):
        # Close the UDP socket owned by the sender.
        self.sock.close()

    def send(self, message):
        # Send a complete message and return the stats for this sender.
        chunks = self._split_message(message)
        packets = self._build_data_packets(chunks)
        print(
            f"[SENDER] sending {len(packets)} packet(s) to {self.addr} "
            f"with window={self.window_size}"
        )

        self._send_packets(packets)
        self.seq_num += len(packets)

        print(f"[SENDER] complete: {self.stats}")
        return self.stats

    def _send_packets(self, packets):
        # Keep track of every packet that has been sent but not ACKed yet.
        # With window_size=1 this works like stop-and-wait. With a larger
        # window, multiple packets can be in flight at once.
        self.stats.original_packets += len(packets)
        states = {
            packet.seq_num: {
                "packet": packet,
                "attempts": 0,
                "last_sent": None,
            }
            for packet in packets
        }
        next_to_send = packets[0].seq_num if packets else self.seq_num
        final_seq = packets[-1].seq_num if packets else self.seq_num - 1

        while states:
            window_base = min(states)
            window_limit = window_base + self.window_size

            while next_to_send <= final_seq and next_to_send < window_limit:
                if next_to_send in states:
                    self._send_packet(states[next_to_send])
                next_to_send += 1

            ack_num = self._receive_ack()
            if ack_num in states:
                print(f"[SENDER] ACK ok for seq={ack_num}")
                del states[ack_num]
            elif ack_num is not None:
                self.stats.unexpected_acks += 1
                print(f"[SENDER] duplicate/out-of-window ACK ignored: {ack_num}")

            self._retransmit_timed_out_packets(states, window_base, window_limit)

    def _send_packet(self, state):
        # Send or resend one packet and update attempt counters.
        if self.max_retries is not None and state["attempts"] > 0:
            retransmissions = state["attempts"] - 1
            if retransmissions >= self.max_retries:
                seq_num = state["packet"].seq_num
                raise TimeoutError(
                    f"no valid ACK for seq={seq_num} "
                    f"after {self.max_retries} retransmission(s)"
                )

        state["attempts"] += 1
        state["last_sent"] = time.monotonic()
        self.stats.packets_sent += 1

        if state["attempts"] > 1:
            self.stats.retransmissions += 1

        packet = state["packet"]
        print(f"[SENDER] sending seq={packet.seq_num}, attempt={state['attempts']}")
        self.sock.sendto(convert_to_bytes(packet), self.addr)

    def _receive_ack(self):
        # Try to read one ACK from the receiver.
        # Return None if the ACK is missing, malformed, or corrupt.
        try:
            ack_bytes, _ = self.sock.recvfrom(2048)
        except socket.timeout:
            print("[SENDER] receive timeout, checking retransmissions")
            return None

        try:
            ack_packet = extract_from_bytes(ack_bytes)
        except (UnicodeDecodeError, ValueError, IndexError) as exc:
            self.stats.malformed_acks += 1
            print(f"[SENDER] malformed ACK ignored: {exc}")
            return None

        self.stats.acks_received += 1
        print(f"[SENDER] received ACK packet: {ack_packet}")

        if not self._ack_checksum_is_valid(ack_packet):
            self.stats.bad_ack_checksums += 1
            print("[SENDER] corrupt ACK ignored")
            return None

        return ack_packet.ack_num

    def _retransmit_timed_out_packets(self, states, window_base, window_limit):
        # Only retransmit packets that are still inside the active window.
        now = time.monotonic()
        for seq_num in sorted(states):
            if seq_num < window_base or seq_num >= window_limit:
                continue

            last_sent = states[seq_num]["last_sent"]
            if last_sent is not None and now - last_sent >= self.timeout:
                self.stats.timeouts += 1
                print(f"[SENDER] timeout on seq={seq_num}, resending")
                self._send_packet(states[seq_num])

    def _build_data_packets(self, chunks):
        # Build data packets with sequence numbers and checksums.
        packets = []
        for offset, payload in enumerate(chunks):
            self._validate_payload(payload)
            seq_num = self.seq_num + offset
            checksum = calculate_checksum(seq_num, 0, payload)
            packets.append(Packet(seq_num, 0, payload, checksum))
        return packets

    def _ack_checksum_is_valid(self, ack_packet):
        # Check ACK integrity. The current receiver still sends ACKs with
        # checksum=0, so we accept those by default while testing.
        expected = calculate_checksum(
            ack_packet.seq_num,
            ack_packet.ack_num,
            ack_packet.payload,
        )

        if ack_packet.checksum == expected:
            return True

        if self.allow_legacy_acks and ack_packet.checksum == 0:
            print("[SENDER] accepting legacy ACK with checksum=0")
            return True

        return False

    def _split_message(self, message):
        # Split text into payload sized chunks for packetization.
        if isinstance(message, bytes):
            message = message.decode()

        if not isinstance(message, str):
            raise TypeError("message must be str or bytes")

        if message == "":
            return [""]

        return [
            message[index : index + self.payload_size]
            for index in range(0, len(message), self.payload_size)
        ]

    def _validate_payload(self, payload):
        # The temporary packet format uses | as a separator.
        if "|" in payload:
            raise ValueError(
                "payload cannot contain '|' while using the temporary "
                "seq|ack|payload|checksum packet format"
            )


def _read_message(args):
    # Read message text from --file or fall back to --message.
    if args.file:
        with open(args.file, "r", encoding="utf-8") as handle:
            return handle.read()

    return args.message


def parse_args():
    # Parse commandline options for local testing.
    parser = argparse.ArgumentParser(
        description="Stop-and-wait reliable sender over UDP."
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--payload-size", type=int, default=DEFAULT_PAYLOAD_SIZE)
    parser.add_argument("--window-size", type=int, default=DEFAULT_WINDOW_SIZE)
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument(
        "--message",
        default="Hello, receiver!",
        help="message text to send when --file is not provided",
    )
    parser.add_argument("--file", help="text file to send instead of --message")
    parser.add_argument(
        "--strict-ack-checksum",
        action="store_true",
        help="reject ACK packets whose checksum is 0 or invalid",
    )
    return parser.parse_args()


def main():
    # Run the sender from the command line.
    args = parse_args()
    if args.payload_size <= 0:
        raise ValueError("--payload-size must be greater than 0")
    if args.window_size <= 0:
        raise ValueError("--window-size must be greater than 0")

    sender = Sender(
        host=args.host,
        port=args.port,
        timeout=args.timeout,
        payload_size=args.payload_size,
        window_size=args.window_size,
        max_retries=args.max_retries,
        allow_legacy_acks=not args.strict_ack_checksum,
    )

    try:
        sender.send(_read_message(args))
    finally:
        sender.close()


if __name__ == "__main__":
    main()
