def calculate_checksum(seq_num, ack_num, payload):
    data = f"{seq_num}|{ack_num}|{payload}".encode()
    return sum(data) & 0xffff
