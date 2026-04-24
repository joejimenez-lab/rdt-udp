# Sender (Phase 1: stop-and-wait)
#
# Flow:
# 1. build packet with current seq_num
# 2. send packet
# 3. wait for ACK
# 4. if timeout -> resend
# 5. if correct ACK -> move to next seq
#
# NOTES:
# - receiver should send ACK packets where ack_num == seq_num being acknowledged
# - we only advance seq_num after correct ACK
# - checksum is calculated for outgoing data packets
# - this is baseline before adding sliding window / selective repeat

import socket
from packet import Packet, from_bytes, to_bytes
from utils import calculate_checksum


class Sender:
    def __init__(self, host, port):
        # UDP socket for sending packets
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # timeout used to trigger retransmission
        self.sock.settimeout(1.0)

        # receiver address
        self.addr = (host, port)

        # current sequence number
        self.seq_num = 0

    def send(self, message):
        # build packet for current sequence number
        checksum = calculate_checksum(self.seq_num, 0, message)
        packet = Packet(self.seq_num, 0, message, checksum)

        while True:
            print(f"[SENDER] sending seq={self.seq_num}")
            self.sock.sendto(to_bytes(packet), self.addr)

            try:
                # wait for ACK from receiver
                ack_bytes, _ = self.sock.recvfrom(2048)
                ack_packet = from_bytes(ack_bytes)

                print(f"[SENDER] received: {ack_packet}")

                # expect ACK where ack_num matches current seq
                if ack_packet.ack_num == self.seq_num:
                    print(f"[SENDER] ACK ok for seq={self.seq_num}")

                    # move forward only after correct ACK
                    self.seq_num += 1
                    break
                else:
                    # could be duplicate or out-of-order ACK
                    print("[SENDER] unexpected ACK, ignoring")

            except socket.timeout:
                # assume packet or ACK was lost → resend
                print(f"[SENDER] timeout on seq={self.seq_num}, resending")


# simple test entry point (will expand to file transfer later)
if __name__ == "__main__":
    sender = Sender("127.0.0.1", 9000)
    sender.send("Hello, receiver!")
