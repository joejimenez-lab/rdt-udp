import socket
from packet import Packet, convert_to_bytes, extract_from_bytes
from utils import calculate_checksum

class Receiver:
    def __init__(self, host, port, window_size=1):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.bind((host, port))
        self.window_size = window_size
        self.buffer = {}  # {seq_num => Packet}
        self.expected_seq_num = 0

    def send_ack(self, ack_num, addr):
        p = Packet(0, ack_num, '', 0)
        self.s.sendto(convert_to_bytes(p), addr)
        print(f"sent ACK: {ack_num} to {addr}")

    def start(self):
        print('Receiver started...')
        while True:
            print(f"current window: {self.expected_seq_num} - {self.expected_seq_num + self.window_size}")
            resp_in_bytes, addr = self.s.recvfrom(2048)
            p = extract_from_bytes(resp_in_bytes)
            print(f"printing the extracted packet: {p}")

            # Calculate checksum, ignore packet if invalid checksum
            calculated_checksum = calculate_checksum(p.seq_num, p.ack_num, p.payload)
            if p.checksum != calculated_checksum:
                print(f"ignoring corrupt packet {p.seq_num}")
                continue

            # Handle packets that have been previously ACKed already
            # We're here if the ACK was lost, causing the sender to resend an old packet
              # (We have to resend the ACK, so the sender is not stuck waiting for the ACK)
            if p.seq_num >= self.expected_seq_num - self.window_size and p.seq_num < self.expected_seq_num:
                self.send_ack(p.seq_num, addr)

            # Handle packets that are within the current window
            elif p.seq_num >= self.expected_seq_num and p.seq_num < self.expected_seq_num + self.window_size:
                self.send_ack(p.seq_num, addr)

                if p.seq_num not in self.buffer:
                    self.buffer[p.seq_num] = p

                # Slide the window
                while self.expected_seq_num in self.buffer:
                    self.buffer.pop(self.expected_seq_num)
                    print(f"delivering {self.expected_seq_num} to the upper layer")
                    self.expected_seq_num += 1

            # Ignore packets outside the window
            else:
                continue

recv = Receiver('localhost', 9000)
recv.start()
