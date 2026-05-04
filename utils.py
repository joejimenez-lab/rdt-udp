def calculate_checksum(seq_num, ack_num, payload, use_crc=False):
    if use_crc:
        # Following 6.2.3 of the textbook
        generator = '1001'
        data_str = f"{seq_num}|{ack_num}|{payload}"
        data_as_binary_str = string_to_binary(data_str)
        data_as_binary_str = data_as_binary_str + ('0' * (len(generator)-1))
        remainder = divide_modulo_2(data_as_binary_str, generator)
        return int(remainder, 2)
    else:
        data = f"{seq_num}|{ack_num}|{payload}".encode()
        return sum(data) & 0xffff

def string_to_binary(s):
    return ''.join(format(ord(char), '08b') for char in s)

# Based on https://www.geeksforgeeks.org/python/cyclic-redundancy-check-python/
# but with variable names that make more sense to me

def xor(a, b):
    result = []

    # Skipping the leftmost bit because a[0] and b[0] will always be the same (because of the divide algorithm)
    for i in range(1, len(a)):
        if a[i] == b[i]:
            result.append('0')
        else:
            result.append('1')

    return ''.join(result)

def divide_modulo_2(dividend, divisor):
    dividend_index = len(divisor)
    dividend_substr = dividend[0 : dividend_index]

    while dividend_index < len(dividend):
        # Divisor "divides" into the dividend substring
        # If dividend substring starts with a 1, divisor and dividend are the same length
        if dividend_substr[0] == '1':
            dividend_substr = xor(dividend_substr, divisor) + dividend[dividend_index]

        # Divisor "doesn't divide" into the dividend substring
        # If dividend substring starts with a 0, divisor > dividend_substr
        else:
            dividend_substr  = xor(dividend_substr, '0' * dividend_index) + dividend[dividend_index]

        dividend_index += 1

    if dividend_substr[0] == '1':
        dividend_substr = xor(dividend_substr, divisor)
    else:
        dividend_substr  = xor(dividend_substr, '0' * dividend_index)

    remainder = ''.join(dividend_substr)
    return remainder