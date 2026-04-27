# Packet format (temporary, string based for easy debugging):
# seq_num|ack_num|payload|checksum
#
# NOTES:
# - checksum is a placeholder for now (we’ll replace with a real one later)
# - ack_num is the sequence number being acknowledged
# - this format is intentionally simple so sender/receiver stay in sync early
# - once everything works, we can switch to a structured/byte-based format

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
