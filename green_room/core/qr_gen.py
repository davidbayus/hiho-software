"""Minimal QR code generator — zero external dependencies.

Generates QR codes for short text strings like IP addresses and port numbers.
Supports QR versions 1-4 with error correction level L (7% recovery).

This exists so the Green Room addon can show a scannable QR code without
requiring teachers or students to install any Python packages.
"""


# --- Galois Field GF(256) arithmetic for Reed-Solomon error correction ---
# Primitive polynomial: x^8 + x^4 + x^3 + x^2 + 1

_EXP = [0] * 512
_LOG = [0] * 256

_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x = (_x << 1) ^ (0x11D if _x >= 128 else 0)
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_encode(data, n_ec):
    """Compute Reed-Solomon error correction codewords."""
    # Build generator polynomial: (x - a^0)(x - a^1)...(x - a^(n_ec-1))
    g = [1]
    for i in range(n_ec):
        ng = [0] * (len(g) + 1)
        for j, coef in enumerate(g):
            ng[j] ^= coef
            ng[j + 1] ^= _gf_mul(coef, _EXP[i])
        g = ng

    # Polynomial long division — remainder is the EC codewords
    out = list(data) + [0] * n_ec
    for i in range(len(data)):
        c = out[i]
        if c:
            for j in range(1, len(g)):
                out[i + j] ^= _gf_mul(g[j], c)
    return out[len(data):]


# --- QR version specs (EC level L only) ---
# (matrix_size, data_codewords, ec_codewords, alignment_pattern_centers)

_VERSIONS = {
    1: (21, 19,  7, []),
    2: (25, 34, 10, [6, 18]),
    3: (29, 55, 15, [6, 22]),
    4: (33, 80, 20, [6, 26]),
}

# Pre-computed 15-bit format info for EC level L with each mask pattern (0-7)
_FMT = [0x77C4, 0x72F3, 0x7DAA, 0x789D, 0x662F, 0x6318, 0x6C41, 0x6976]


# --- Data encoding ---

def _encode_data(raw_bytes, n_data):
    """Encode raw bytes into QR data codewords using byte mode."""
    bits = []

    # Mode indicator: 0100 = byte mode
    bits += [0, 1, 0, 0]

    # Character count (8 bits for versions 1-9)
    length = len(raw_bytes)
    bits += [(length >> (7 - i)) & 1 for i in range(8)]

    # Data bits
    for b in raw_bytes:
        bits += [(b >> (7 - i)) & 1 for i in range(8)]

    # Terminator (up to 4 zero bits)
    bits += [0] * min(4, n_data * 8 - len(bits))

    # Pad to byte boundary
    while len(bits) % 8:
        bits.append(0)

    # Convert bits to codewords
    cws = []
    for i in range(0, len(bits), 8):
        cws.append(sum(bits[i + j] << (7 - j) for j in range(8)))

    # Pad with alternating 0xEC, 0x11 to fill capacity
    pad_idx = 0
    while len(cws) < n_data:
        cws.append([0xEC, 0x11][pad_idx % 2])
        pad_idx += 1

    return cws[:n_data]


# --- Matrix construction ---

def _place_patterns(mat, fixed, n, version, aligns):
    """Place finder patterns, separators, timing, alignment, and dark module."""

    def mark(r, c, v):
        if 0 <= r < n and 0 <= c < n:
            mat[r][c] = v
            fixed[r][c] = True

    # Finder patterns (7x7) with white separator borders
    for (tr, tc) in [(0, 0), (0, n - 7), (n - 7, 0)]:
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr, cc = tr + r, tc + c
                if 0 <= rr < n and 0 <= cc < n:
                    if 0 <= r <= 6 and 0 <= c <= 6:
                        v = (r in (0, 6) or c in (0, 6) or
                             (2 <= r <= 4 and 2 <= c <= 4))
                        mark(rr, cc, v)
                    else:
                        mark(rr, cc, False)

    # Timing patterns (alternating dark/light on row 6 and col 6)
    for i in range(8, n - 8):
        mark(6, i, i % 2 == 0)
        mark(i, 6, i % 2 == 0)

    # Alignment patterns (5x5, versions 2+)
    if aligns:
        for ar in aligns:
            for ac in aligns:
                # Skip if overlapping with finder + separator area
                if ar <= 8 and ac <= 8:
                    continue
                if ar <= 8 and ac >= n - 9:
                    continue
                if ar >= n - 9 and ac <= 8:
                    continue
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        v = (abs(dr) == 2 or abs(dc) == 2 or
                             (dr == 0 and dc == 0))
                        mark(ar + dr, ac + dc, v)

    # Dark module (always present)
    mark(4 * version + 9, 8, True)

    # Reserve format info areas (values written later, after masking)
    for i in range(9):
        fixed[8][i] = True
        fixed[i][8] = True
    for i in range(8):
        fixed[8][n - 1 - i] = True
        fixed[n - 1 - i][8] = True


def _place_data(mat, fixed, codewords, n):
    """Place data + EC codewords into the matrix in the zigzag pattern."""
    bits = []
    for cw in codewords:
        for i in range(7, -1, -1):
            bits.append(bool((cw >> i) & 1))

    idx = 0
    col = n - 1
    upward = True

    while col >= 0:
        if col == 6:  # Skip timing column
            col -= 1
            continue

        rows = range(n - 1, -1, -1) if upward else range(n)

        for row in rows:
            for dc in (0, -1):  # Right column first, then left
                c = col + dc
                if c < 0 or fixed[row][c]:
                    continue
                mat[row][c] = bits[idx] if idx < len(bits) else False
                idx += 1

        col -= 2
        upward = not upward


# --- Masking ---

_MASK_FNS = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]


def _apply_mask(mat, fixed, mask_id, n):
    """Apply a mask pattern to data modules. Returns a new matrix."""
    fn = _MASK_FNS[mask_id]
    out = [row[:] for row in mat]
    for r in range(n):
        for c in range(n):
            if not fixed[r][c] and fn(r, c):
                out[r][c] = not out[r][c]
    return out


def _set_format(mat, mask_id, n):
    """Write the 15-bit format info into both copies in the matrix."""
    info = _FMT[mask_id]
    bits = [(info >> (14 - i)) & 1 for i in range(15)]

    # Copy 1: around top-left finder
    for i, c in enumerate([0, 1, 2, 3, 4, 5, 7, 8]):
        mat[8][c] = bool(bits[i])
    for i, r in enumerate([7, 5, 4, 3, 2, 1, 0]):
        mat[r][8] = bool(bits[8 + i])

    # Copy 2: bottom-left (vertical) and top-right (horizontal)
    for i in range(7):
        mat[n - 1 - i][8] = bool(bits[i])
    for i in range(8):
        mat[8][n - 8 + i] = bool(bits[7 + i])


def _penalty(mat, n):
    """Score a masked matrix (lower is better). Rules 1 and 2."""
    score = 0

    # Rule 1: Runs of 5+ same-color modules
    for r in range(n):
        cnt = 1
        for c in range(1, n):
            if mat[r][c] == mat[r][c - 1]:
                cnt += 1
            else:
                if cnt >= 5:
                    score += cnt - 2
                cnt = 1
        if cnt >= 5:
            score += cnt - 2

    for c in range(n):
        cnt = 1
        for r in range(1, n):
            if mat[r][c] == mat[r - 1][c]:
                cnt += 1
            else:
                if cnt >= 5:
                    score += cnt - 2
                cnt = 1
        if cnt >= 5:
            score += cnt - 2

    # Rule 2: 2x2 blocks of same color
    for r in range(n - 1):
        for c in range(n - 1):
            v = mat[r][c]
            if mat[r][c+1] == v and mat[r+1][c] == v and mat[r+1][c+1] == v:
                score += 3

    return score


# --- Public API ---

def make_qr_matrix(text, border=4):
    """Generate a QR code as a 2D boolean matrix.

    Args:
        text: String to encode (max ~78 characters)
        border: Quiet zone width in modules (spec requires 4)

    Returns:
        List of rows, each a list of bools (True = dark/black module).
    """
    raw = text.encode('utf-8')

    # Pick smallest version that fits
    version = None
    for v in range(1, 5):
        needed = (4 + 8 + len(raw) * 8 + 7) // 8
        if needed <= _VERSIONS[v][1]:
            version = v
            break
    if version is None:
        raise ValueError("Text too long for QR versions 1-4")

    n, n_data, n_ec, aligns = _VERSIONS[version]

    # Encode data + compute error correction
    data_cws = _encode_data(raw, n_data)
    ec_cws = _rs_encode(data_cws, n_ec)

    # Build matrix with fixed patterns
    mat = [[False] * n for _ in range(n)]
    fixed = [[False] * n for _ in range(n)]
    _place_patterns(mat, fixed, n, version, aligns)

    # Place data bits in zigzag
    _place_data(mat, fixed, data_cws + ec_cws, n)

    # Find best mask (lowest penalty score)
    best_mask, best_score = 0, float('inf')
    for m in range(8):
        trial = _apply_mask(mat, fixed, m, n)
        _set_format(trial, m, n)
        s = _penalty(trial, n)
        if s < best_score:
            best_mask, best_score = m, s

    # Apply winning mask + format info
    result = _apply_mask(mat, fixed, best_mask, n)
    _set_format(result, best_mask, n)

    # Add quiet zone border
    total = n + 2 * border
    padded = []
    empty = [False] * total
    for _ in range(border):
        padded.append(list(empty))
    for row in result:
        padded.append([False] * border + row + [False] * border)
    for _ in range(border):
        padded.append(list(empty))

    return padded
