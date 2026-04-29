import socket
from packet import Packet, convert_to_bytes, extract_from_bytes
from utils import calculate_checksum

class Receiver:
    def __init__(self, host, port):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.bind((host, port))

    def send_ack(self, ack_num, addr):
        p = Packet(0, ack_num, '', 0)
        self.s.sendto(convert_to_bytes(p), addr)
        print(f"sent ACK: {ack_num} to {addr}")

    def start(self):
        print('Receiver started...')
        while True:
            resp_in_bytes, addr = self.s.recvfrom(2048)
            p = extract_from_bytes(resp_in_bytes)
            print(f"printing the extracted packet: {p}")

            # Calculate checksum, ignore packet if invalid checksum
            calculated_checksum = calculate_checksum(p.seq_num, p.ack_num, p.payload)
            if p.checksum != calculated_checksum:
                print(f"ignoring corrupt packet {p.seq_num}")
                continue

            self.send_ack(p.seq_num, addr)

recv = Receiver('localhost', 9000)
recv.start()
