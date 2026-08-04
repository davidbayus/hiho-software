"""Phone connection utilities — IP detection for PPParty.

Detects the local network IP so students can configure
Live Link Face to send data to this computer.
"""

import socket


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
