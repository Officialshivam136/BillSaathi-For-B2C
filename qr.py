"""QR code encoder: byte mode, error correction level M, versions 1-10 (up to 213 bytes). Standard library only.

    matrix = make_qr("upi://pay?pa=shop@upi&am=100")      # list of rows of bools, True = dark module
    svg = to_svg(matrix)                                  # inline SVG string
"""

# version -> (EC codewords per block, [(block count, data codewords per block), ...]) for level M
EC_M = {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]),
        6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]),
        10: (26, [(4, 43), (1, 44)])}
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
         9: [6, 26, 46], 10: [6, 28, 50]}
REMAINDER_BITS = {1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7, 7: 0, 8: 0, 9: 0, 10: 0}
MAX_BYTES = 213

# ---- Reed-Solomon over GF(256), polynomial 0x11D ----
_EXP, _LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _generator(n):
    g = [1]
    for i in range(n):
        nxt = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            nxt[j] ^= c
            nxt[j + 1] ^= _mul(c, _EXP[i])
        g = nxt
    return g  # highest degree first


def rs_remainder(data, n):
    """The n error-correction codewords for data."""
    gen = _generator(n)
    rem = list(data) + [0] * n
    for i in range(len(data)):
        c = rem[i]
        if c:
            for j in range(1, len(gen)):
                rem[i + j] ^= _mul(gen[j], c)
    return rem[len(data):]


# ---- bit stream ----
def _data_codewords(payload, version):
    ec, groups = EC_M[version]
    total = sum(n * d for n, d in groups)
    bits = [0, 1, 0, 0]  # byte mode
    count_len = 8 if version <= 9 else 16
    bits += [(len(payload) >> i) & 1 for i in range(count_len - 1, -1, -1)]
    for byte in payload:
        bits += [(byte >> i) & 1 for i in range(7, -1, -1)]
    bits += [0] * min(4, total * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = (0xEC, 0x11)
    while len(words) < total:
        words.append(pad[(len(words) - len(bits) // 8) % 2])
    return words


def _interleave(words, version):
    ec_len, groups = EC_M[version]
    blocks, pos = [], 0
    for n, d in groups:
        for _ in range(n):
            blocks.append(words[pos:pos + d])
            pos += d
    ecs = [rs_remainder(b, ec_len) for b in blocks]
    out = []
    for i in range(max(len(b) for b in blocks)):
        out += [b[i] for b in blocks if i < len(b)]
    for i in range(ec_len):
        out += [e[i] for e in ecs]
    return out


# ---- matrix ----
def format_bits(mask):
    """15 format bits for level M and the given mask (BCH(15,5) then xor 0x5412)."""
    data = (0 << 3) | mask  # level M = 00
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return ((data << 10) | rem) ^ 0x5412


def _version_bits(version):
    rem = version
    for _ in range(12):
        rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
    return (version << 12) | rem


def _mask_fn(mask):
    return (lambda r, c: (r + c) % 2 == 0, lambda r, c: r % 2 == 0, lambda r, c: c % 3 == 0, lambda r, c: (r + c) % 3 == 0,
            lambda r, c: (r // 2 + c // 3) % 2 == 0, lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
            lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0, lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0)[mask]


class _Grid:
    def __init__(self, version):
        self.v, self.n = version, 17 + 4 * version
        self.m = [[False] * self.n for _ in range(self.n)]
        self.fn = [[False] * self.n for _ in range(self.n)]
        self._patterns()

    def set(self, r, c, dark):
        self.m[r][c] = bool(dark)
        self.fn[r][c] = True

    def _patterns(self):
        n = self.n
        for i in range(8, n - 8):  # timing
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):  # finders with separators
            for dr in range(-1, 8):
                for dc in range(-1, 8):
                    r, c = r0 + dr, c0 + dc
                    if 0 <= r < n and 0 <= c < n:
                        self.set(r, c, 0 <= dr <= 6 and 0 <= dc <= 6 and (dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4)))
        pos = ALIGN[self.v]
        for r in pos:
            for c in pos:
                if (r, c) in ((pos[0], pos[0]), (pos[0], pos[-1]), (pos[-1], pos[0])):
                    continue
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        self.set(r + dr, c + dc, max(abs(dr), abs(dc)) != 1)
        self.draw_format(0)  # reserve the format areas
        if self.v >= 7:
            bits = _version_bits(self.v)
            for i in range(18):
                a, b = n - 11 + i % 3, i // 3
                self.set(b, a, (bits >> i) & 1)
                self.set(a, b, (bits >> i) & 1)

    def draw_format(self, mask):
        n, bits = self.n, format_bits(mask)
        bit = lambda i: (bits >> i) & 1
        for i in range(6):
            self.set(i, 8, bit(i))
        self.set(7, 8, bit(6))
        self.set(8, 8, bit(7))
        self.set(8, 7, bit(8))
        for i in range(9, 15):
            self.set(8, 14 - i, bit(i))
        for i in range(8):
            self.set(8, n - 1 - i, bit(i))
        for i in range(8, 15):
            self.set(n - 15 + i, 8, bit(i))
        self.set(n - 8, 8, True)  # the always-dark module

    def place(self, codewords):
        bits = [(w >> i) & 1 for w in codewords for i in range(7, -1, -1)] + [0] * REMAINDER_BITS[self.v]
        n, k, col, up = self.n, 0, self.n - 1, True
        while col > 0:
            if col == 6:
                col -= 1
            for r in (range(n - 1, -1, -1) if up else range(n)):
                for c in (col, col - 1):
                    if not self.fn[r][c]:
                        self.m[r][c] = bool(bits[k]) if k < len(bits) else False
                        k += 1
            up, col = not up, col - 2

    def apply_mask(self, mask):
        f = _mask_fn(mask)
        for r in range(self.n):
            for c in range(self.n):
                if not self.fn[r][c] and f(r, c):
                    self.m[r][c] = not self.m[r][c]


def _penalty(m):
    n = len(m)
    score = 0
    rows = ["".join("1" if x else "0" for x in row) for row in m]
    cols = ["".join("1" if m[r][c] else "0" for r in range(n)) for c in range(n)]
    for line in rows + cols:
        run = 1
        for i in range(1, n):
            if line[i] == line[i - 1]:
                run += 1
            else:
                score += 3 + (run - 5) if run >= 5 else 0
                run = 1
        score += 3 + (run - 5) if run >= 5 else 0
        for pat in ("10111010000", "00001011101"):
            start = line.find(pat)
            while start != -1:
                score += 40
                start = line.find(pat, start + 1)
    for r in range(n - 1):
        for c in range(n - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    dark = sum(row.count("1") for row in rows)
    total = n * n
    score += ((abs(dark * 20 - total * 10) + total - 1) // total - 1) * 10
    return score


def make_qr(text):
    """Return the QR matrix (list of lists of bool) for text."""
    payload = text.encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise ValueError(f"Text is too long for a QR code ({len(payload)} bytes, max {MAX_BYTES})")
    version = next(v for v in range(1, 11) if len(payload) <= sum(n * d for n, d in EC_M[v][1]) - (2 if v <= 9 else 3))
    codewords = _interleave(_data_codewords(payload, version), version)
    best = None
    for mask in range(8):
        g = _Grid(version)
        g.place(codewords)
        g.apply_mask(mask)
        g.draw_format(mask)
        s = _penalty(g.m)
        if best is None or s < best[0]:
            best = (s, g.m)
    return best[1]


def to_svg(matrix, quiet=4, size_px=None):
    """Inline SVG: black modules on a white square with the standard 4-module quiet zone."""
    n = len(matrix)
    parts = []
    for r, row in enumerate(matrix):
        c = 0
        while c < n:
            if row[c]:
                start = c
                while c < n and row[c]:
                    c += 1
                parts.append(f"M{start + quiet},{r + quiet}h{c - start}v1h-{c - start}z")
            else:
                c += 1
    dim = n + 2 * quiet
    px = f" width='{size_px}' height='{size_px}'" if size_px else ""
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {dim} {dim}'{px} shape-rendering='crispEdges' role='img' "
            f"aria-label='QR code'><rect width='{dim}' height='{dim}' fill='#fff'/><path d='{''.join(parts)}' fill='#000'/></svg>")
