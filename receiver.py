import socket
from packet import Packet, to_bytes, from_bytes

class Receiver:
    def __init__(self, host, port):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.bind((host, port))

    def send_ack(self, ack_num, addr):
        p = Packet(0, ack_num, '', 0)
        self.s.sendto(to_bytes(p), addr)
        print(f"sent ACK: {ack_num} to {addr}")

    def start(self):
        print('Receiver started...')
        while True:
            resp_in_bytes, addr = self.s.recvfrom(2048)
            p = from_bytes(resp_in_bytes)
            print(f"printing the extracted packet: {p}")
            self.send_ack(p.ack_num, addr)

recv = Receiver('localhost', 9000)
recv.start()
