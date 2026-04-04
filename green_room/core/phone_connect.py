"""Phone connection utilities — IP detection and QR code generation.

The QR code shows the computer's IP address and port so students
can quickly set up Live Link Face on their phones.
"""

import os
import socket
import struct
import tempfile
import zlib

from .qr_gen import make_qr_matrix


def get_local_ip():
    """Get this computer's local network IP address.

    Returns the IP as a string, or None if detection fails.
    """
    # Method 1: Connect to a non-routable address to find our LAN IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass

    # Method 2: Hostname lookup fallback
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return None


def generate_qr_png(text, scale=8):
    """Generate a QR code PNG file for the given text.

    Returns the filepath to the PNG.
    """
    matrix = make_qr_matrix(text)
    filepath = os.path.join(tempfile.gettempdir(), "greenroom_qr.png")
    _write_png(matrix, filepath, scale)
    return filepath


def _write_png(matrix, filepath, scale):
    """Write a QR matrix as a grayscale PNG. Pure Python, no PIL needed."""
    size = len(matrix) * scale

    # Build raw image data: each row starts with a filter byte (0),
    # followed by one byte per pixel (0=black, 255=white)
    raw = bytearray()
    for row in matrix:
        for _ in range(scale):
            raw.append(0)  # PNG row filter: None
            for cell in row:
                raw.extend([0 if cell else 255] * scale)

    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        c = tag + data
        crc = struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack('>I', len(data)) + c + crc

    with open(filepath, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')  # PNG signature
        # IHDR: width, height, bit depth 8, grayscale
        f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 0, 0, 0, 0)))
        f.write(chunk(b'IDAT', compressed))
        f.write(chunk(b'IEND', b''))
