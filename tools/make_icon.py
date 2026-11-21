"""Generate JinyIcon.tga (64x64 32-bit uncompressed RGBA, bottom-left origin)."""

from pathlib import Path
import math
import struct


WIDTH = 64
HEIGHT = 64
SUPERSAMPLE = 4

BG_DARK = (0x13, 0x19, 0x26)
GOLD_RING = (0xD4, 0xAF, 0x37)
STAR_LIGHT = (0x69, 0xCC, 0xF0)
STAR_DARK = (0x2B, 0x6C, 0xB0)
STAR_STROKE = (0xE2, 0xF4, 0xFF)


def lerp_color(c0: tuple[int, int, int], c1: tuple[int, int, int], t: float) -> tuple[float, float, float]:
    t = max(0.0, min(1.0, t))
    return (
        c0[0] + (c1[0] - c0[0]) * t,
        c0[1] + (c1[1] - c0[1]) * t,
        c0[2] + (c1[2] - c0[2]) * t,
    )


def build_quadrant_curve(steps: int = 48) -> list[tuple[float, float]]:
    """Sample the first-quadrant quadratic Bezier from (0, 8.6) -> (1.1, 1.1) -> (8.6, 0)."""
    p0 = (0.0, 8.6)
    p1 = (1.1, 1.1)
    p2 = (8.6, 0.0)
    pts: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1.0 - t
        x = mt * mt * p0[0] + 2.0 * mt * t * p1[0] + t * t * p2[0]
        y = mt * mt * p0[1] + 2.0 * mt * t * p1[1] + t * t * p2[1]
        pts.append((x, y))
    return pts


CURVE_PTS = build_quadrant_curve()


def point_to_segment_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx = bx - ax
    vy = by - ay
    wx = px - ax
    wy = py - ay
    seg_len_sq = vx * vx + vy * vy
    if seg_len_sq <= 1e-12:
        return math.hypot(wx, wy)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / seg_len_sq))
    cx = ax + t * vx
    cy = ay + t * vy
    return math.hypot(px - cx, py - cy)


def eval_star(vx: float, vy: float) -> tuple[bool, float]:
    """Return (is_inside, distance_to_boundary) in 24x24 viewBox space."""
    dx = abs(vx - 12.0)
    dy = abs(vy - 12.0)

    min_dist = float("inf")
    inside = False

    for i in range(len(CURVE_PTS) - 1):
        ax, ay = CURVE_PTS[i]
        bx, by = CURVE_PTS[i + 1]
        d = point_to_segment_dist(dx, dy, ax, ay, bx, by)
        if d < min_dist:
            min_dist = d
        if ax <= dx <= bx and bx > ax:
            frac = (dx - ax) / (bx - ax)
            y_curve = ay + frac * (by - ay)
            if dy <= y_curve:
                inside = True

    return inside, min_dist


def sample_subpixel(vx: float, vy: float) -> tuple[float, float, float, float]:
    """Evaluate RGBA (0..255 floats) at viewBox coordinate (vx, vy)."""
    dist_center = math.hypot(vx - 12.0, vy - 12.0)

    # Circle radius 10.5, gold stroke width 1.4 => outer edge 11.2, inner ring 9.8
    if dist_center > 11.2:
        return (0.0, 0.0, 0.0, 0.0)

    if dist_center >= 9.8:
        r, g, b = float(GOLD_RING[0]), float(GOLD_RING[1]), float(GOLD_RING[2])
    else:
        r, g, b = float(BG_DARK[0]), float(BG_DARK[1]), float(BG_DARK[2])

    inside_star, edge_dist = eval_star(vx, vy)
    stroke_half = 0.325

    if inside_star:
        # Linear gradient from (3.6, 3.6) to (20.4, 20.4)
        grad_t = ((vx - 3.6) + (vy - 3.6)) / (2.0 * (20.4 - 3.6))
        r, g, b = lerp_color(STAR_LIGHT, STAR_DARK, grad_t)

    if edge_dist <= stroke_half:
        r, g, b = float(STAR_STROKE[0]), float(STAR_STROKE[1]), float(STAR_STROKE[2])

    return (r, g, b, 255.0)


def generate_tga(output_path: Path) -> None:
    header = struct.pack(
        "<BBBHHBHHHHBB",
        0,       # ID length
        0,       # Color map type (no color map)
        2,       # Image type (uncompressed true-color)
        0,       # Color map first entry index
        0,       # Color map length
        0,       # Color map entry size
        0,       # X-origin
        0,       # Y-origin
        WIDTH,   # Width
        HEIGHT,  # Height
        32,      # Pixel depth (32-bit BGRA)
        0x08,    # Image descriptor: 8 alpha bits, bottom-left origin
    )

    pixels = bytearray(WIDTH * HEIGHT * 4)
    inv_ss = 1.0 / (SUPERSAMPLE * SUPERSAMPLE)

    idx = 0
    for py in range(HEIGHT):
        for px in range(WIDTH):
            acc_r = 0.0
            acc_g = 0.0
            acc_b = 0.0
            acc_a = 0.0

            for sy in range(SUPERSAMPLE):
                # Bottom-left origin: py=0 is bottom (vy near 24), py=HEIGHT-1 is top (vy near 0)
                sub_y = py + (sy + 0.5) / SUPERSAMPLE
                vy = 24.0 * (1.0 - sub_y / HEIGHT)
                for sx in range(SUPERSAMPLE):
                    sub_x = px + (sx + 0.5) / SUPERSAMPLE
                    vx = 24.0 * (sub_x / WIDTH)

                    r, g, b, a = sample_subpixel(vx, vy)
                    alpha_norm = a / 255.0
                    acc_r += r * alpha_norm
                    acc_g += g * alpha_norm
                    acc_b += b * alpha_norm
                    acc_a += alpha_norm

            avg_a = acc_a * inv_ss
            if avg_a > 1e-6:
                out_r = min(255, max(0, int(round((acc_r * inv_ss) / avg_a))))
                out_g = min(255, max(0, int(round((acc_g * inv_ss) / avg_a))))
                out_b = min(255, max(0, int(round((acc_b * inv_ss) / avg_a))))
                out_a = min(255, max(0, int(round(avg_a * 255.0))))
            else:
                out_r = out_g = out_b = out_a = 0

            pixels[idx] = out_b
            pixels[idx + 1] = out_g
            pixels[idx + 2] = out_r
            pixels[idx + 3] = out_a
            idx += 4

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(header + bytes(pixels))


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    output_path = repo_root / "Jiny" / "Assets" / "JinyIcon.tga"
    generate_tga(output_path)
    size = output_path.stat().st_size
    print(f"Generated {output_path} ({size} bytes)")


if __name__ == "__main__":
    main()
