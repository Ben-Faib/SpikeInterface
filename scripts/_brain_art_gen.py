"""Dev tool: decode a Braille-art brain, downscale it (Braille -> 1-bit bitmap ->
resize -> Braille), and emit ready-to-paste tiers for the menu's hero crest.

Not imported by the app — run directly to regenerate art:
    uv run python scripts/_brain_art_gen.py
Each Braille glyph (U+2800..28FF) encodes a 2x4 dot grid; that's the bitmap we
resample. Source art lines are padded to a common width so ragged input is fine.
"""
from __future__ import annotations

# Braille dot bit -> (col in 0..1, row in 0..3)
_BITS = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3)]


def decode(lines):
    """Braille lines -> list-of-rows bitmap (1/0), height 4*len, width 2*maxcols."""
    cols = max(len(l) for l in lines)
    H, W = len(lines) * 4, cols * 2
    grid = [[0] * W for _ in range(H)]
    for li, line in enumerate(lines):
        line = line.ljust(cols)
        for ci, ch in enumerate(line):
            o = ord(ch)
            if 0x2800 <= o <= 0x28FF:
                code = o - 0x2800
                for bit, (dx, dy) in enumerate(_BITS):
                    if code & (1 << bit):
                        grid[li * 4 + dy][ci * 2 + dx] = 1
            # any non-braille char (space, emoji, text) -> blank cell
    return grid


def encode(grid):
    """1/0 bitmap (height mult. of 4, width mult. of 2) -> Braille lines."""
    H, W = len(grid), len(grid[0])
    out = []
    for by in range(0, H, 4):
        row = []
        for bx in range(0, W, 2):
            code = 0
            for bit, (dx, dy) in enumerate(_BITS):
                y, x = by + dy, bx + dx
                if y < H and x < W and grid[y][x]:
                    code |= (1 << bit)
            row.append(chr(0x2800 + code))
        out.append("".join(row))
    return out


def resize(grid, out_w_cells, thresh=0.34):
    """Area-average downscale to `out_w_cells` Braille columns, aspect-preserved.
    Returns a new 1/0 bitmap (height padded to a multiple of 4)."""
    in_h, in_w = len(grid), len(grid[0])
    out_w = out_w_cells * 2
    out_h = max(4, round(in_h * out_w / in_w))
    out_h = ((out_h + 3) // 4) * 4  # multiple of 4 (whole Braille rows)
    # cumulative sum for fast area averaging
    import itertools
    cum = [[0] * (in_w + 1) for _ in range(in_h + 1)]
    for y in range(in_h):
        acc = 0
        for x in range(in_w):
            acc += grid[y][x]
            cum[y + 1][x + 1] = cum[y][x + 1] + acc
    def area(y0, y1, x0, x1):
        return cum[y1][x1] - cum[y0][x1] - cum[y1][x0] + cum[y0][x0]
    out = [[0] * out_w for _ in range(out_h)]
    for i in range(out_h):
        y0 = int(i * in_h / out_h); y1 = max(y0 + 1, int((i + 1) * in_h / out_h))
        for j in range(out_w):
            x0 = int(j * in_w / out_w); x1 = max(x0 + 1, int((j + 1) * in_w / out_w))
            frac = area(y0, y1, x0, x1) / ((y1 - y0) * (x1 - x0))
            out[i][j] = 1 if frac >= thresh else 0
    return out


def render(lines):
    return "\n".join(lines)


# ---- source brain: detailed left-facing filled brain (emojicombos) ----
S_NEURON = [
    "⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⣤⣤⣤⣤⡤⣄⣤⣀⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
    "⠀⠀⠀⠀⠀⣠⣴⣾⣿⣿⣿⣿⣽⣿⣿⣿⣿⣿⣿⣾⣿⣦⣤⡀⠀⠀⠀⠀⠀⠀",
    "⠀⠀⢀⣴⣾⢧⣽⣻⠿⢿⠿⠻⣯⣿⠾⢿⡿⣿⣼⡾⠾⣿⣯⣿⣶⡄⠀⠀⠀⠀",
    "⠀⢠⢾⣷⡽⣻⣻⣿⣿⣿⣿⣿⣿⣏⣶⣯⢷⣿⣿⣏⢾⣯⣿⣿⣿⣿⣦⠀⠀⠀",
    "⢰⣿⣿⣿⣿⢻⣿⢿⣿⣿⣿⣿⣿⣿⣿⣾⣿⣿⣟⣧⣼⣿⣿⣿⢕⣽⣾⣧⠀⠀",
    "⠺⣽⣿⣿⣏⣾⣾⣿⣿⣿⣿⣿⣿⣾⣿⣿⣾⡿⣻⣿⣿⣿⣿⣾⣿⣿⣿⣽⡇⠀",
    "⠀⠻⣽⣿⣾⣻⣿⣿⣿⣿⣿⣿⣿⣟⣿⣿⣹⣾⣷⣿⣯⣿⣾⣿⣿⣻⣿⣿⣿⣦",
    "⠀⠀⠈⠛⠿⠿⣿⣿⣿⣿⡿⢿⣿⣿⣿⣿⡯⣻⣿⣿⣿⣿⢽⣿⣿⣿⣿⣿⣿⣿",
    "⠀⠀⠀⠀⠀⠀⠀⢸⡸⢿⣳⣽⣿⣿⣿⣿⣼⣿⣽⣷⣝⣝⣿⣾⣿⣿⣿⣿⣿⣭",
    "⠀⠀⠀⠀⠀⠀⠀⠈⠛⣿⣿⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠏⠀",
    "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠛⠛⠙⢯⣿⣿⣿⢿⣿⣿⡷⣿⣴⡮⣿⠀⠀⠀⠀",
    "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⢹⣿⣿⣿⣿⣿⣿⢿⣟⡿⠋⠀⠀⠀⠀",
    "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⣿⢿⠙⠾⠿⠿⠟⠋⠀⠀⠀⠀⠀⠀",
    "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠸⠿⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
]


_HEIGHTS = [2, 4, 1, 3, 2, 4, 1, 2, 3, 1, 4, 2, 3, 1, 2, 4, 1, 3]


def raster(w_cells):
    """One Braille row of jittered vertical spike ticks, `w_cells` wide."""
    W = w_cells * 2
    grid = [[0] * W for _ in range(4)]
    i, x = 0, 1
    while x < W - 1:
        h = _HEIGHTS[i % len(_HEIGHTS)]
        for dy in range(4 - h, 4):
            grid[dy][x] = 1
        x += 2
        i += 1
    return encode(grid)[0]


def pyliteral(name, lines):
    body = ",\n    ".join(f'"{l}"' for l in lines)
    return f"{name} = [\n    {body},\n]"


def main():
    src = S_NEURON
    base = decode(src)
    # (label, width, has spike raster beneath)
    tiers = [("FULL", 30, True), ("COMPACT", 18, True), ("MINI", 12, False)]
    for label, w, spikes in tiers:
        brain = src if w >= len(src[0]) else encode(resize(base, w))
        wc = len(brain[0])
        ras = [" " * wc, raster(wc)] if spikes else []
        print(f"===== {label}: {wc} cols x {len(brain) + len(ras)} rows "
              f"(brain {len(brain)} + raster {len(ras)}) =====")
        print(render(brain + ras))
        print()
        print(pyliteral(f"_BRAIN_{label}", brain))
        if ras:
            print(pyliteral(f"_BRAIN_{label}_SPK", [ras[-1]]))
        print()


if __name__ == "__main__":
    main()
