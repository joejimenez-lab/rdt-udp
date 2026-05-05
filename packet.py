# Packet format (string based for easy debugging):
# seq_num|ack_num|payload|checksum
#
# NOTES:
# - checksum is calculated over the packet fields to detect corruption
# - ack_num is the sequence number being acknowledged
# - this format is intentionally simple and readable during testing

class Packet:
    def __init__(self, seq_num, ack_num, payload, checksum):
        self.seq_num = seq_num
        self.ack_num = ack_num
        self.payload = payload
        self.checksum = checksum

    def __repr__(self):
        return (
            f"Packet(seq_num={self.seq_num}, "
            f"ack_num={self.ack_num}, "
            f"payload={self.payload}, "
            f"checksum={self.checksum})"
        )


def convert_to_bytes(packet):
    # encode packet into bytes for UDP transmission
    return f"{packet.seq_num}|{packet.ack_num}|{packet.payload}|{packet.checksum}".encode()


def extract_from_bytes(data):
    # parse incoming packet bytes back into a Packet object
    parts = data.decode().split("|", 3)

    seq_num = int(parts[0])
    ack_num = int(parts[1])
    payload = parts[2]
    checksum = int(parts[3])

    return Packet(seq_num, ack_num, payload, checksum)
