"""Render the LinkedIn share card to a PNG.

LinkedIn's link-preview cards are 1.91:1 — we use 1200×627. Pure-PIL,
no external graphics deps.

    python docs/render_linkedin_card.py    # writes docs/linkedin_card.png
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Canvas + palette
# ---------------------------------------------------------------------------

W, H = 1200, 627

# Two-tone background — a deep navy band on the left, off-white right.
NAVY      = (30, 40, 64)
NAVY_DEEP = (22, 30, 50)
PAPER     = (247, 248, 252)
INK       = (28, 32, 44)
INK_DIM   = (96, 104, 122)
ACCENT    = (232, 152, 70)    # warm orange
ACCENT_DK = (200, 120, 50)
LINE      = (210, 214, 222)
WIRE      = (60, 96, 168)

# Layout split — left navy band, right paper band.
NAVY_W = 430


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/usr/local/share/fonts/dejavu",
]


def _font(weight: str, size: int) -> ImageFont.ImageFont:
    name = {
        "regular": "DejaVuSans.ttf",
        "bold":    "DejaVuSans-Bold.ttf",
        "mono":    "DejaVuSansMono.ttf",
        "mono-bold":"DejaVuSansMono-Bold.ttf",
    }[weight]
    for d in FONT_DIRS:
        p = Path(d) / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def rrect(d: ImageDraw.ImageDraw, xy, *, fill, stroke=None, width=1, radius=14) -> None:
    d.rounded_rectangle(xy, radius=radius, fill=fill, outline=stroke, width=width)


def text_at(d, xy, txt, *, font, fill=INK, anchor="lt") -> None:
    d.text(xy, txt, font=font, fill=fill, anchor=anchor)


def arrow(d, start, end, *, color=WIRE, width=4, head=14) -> None:
    d.line([start, end], fill=color, width=width)
    dx, dy = end[0] - start[0], end[1] - start[1]
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    base = (end[0] - ux * head, end[1] - uy * head)
    left = (base[0] + px * head * 0.55, base[1] + py * head * 0.55)
    right = (base[0] - px * head * 0.55, base[1] - py * head * 0.55)
    d.polygon([end, left, right], fill=color)


# ---------------------------------------------------------------------------
# Diagram
# ---------------------------------------------------------------------------


def draw_card() -> Image.Image:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # Left navy band — subtle vertical gradient.
    for y in range(H):
        t = y / H
        r = int(NAVY[0] * (1 - t) + NAVY_DEEP[0] * t)
        g = int(NAVY[1] * (1 - t) + NAVY_DEEP[1] * t)
        b = int(NAVY[2] * (1 - t) + NAVY_DEEP[2] * t)
        d.line([(0, y), (NAVY_W, y)], fill=(r, g, b))

    # Top accent strip across the full width.
    d.rectangle((0, 0, W, 6), fill=ACCENT)

    # ── Left band — wordmark + tagline ─────────────────────────────────
    f_brand_lab = _font("mono-bold", 17)
    f_word = _font("bold", 80)

    text_at(d, (40, 56), "PAN ROBOTICS",
            font=f_brand_lab, fill=(180, 196, 220))

    text_at(d, (40, 218), "bus-mcp",
            font=f_word, fill=(244, 246, 252))

    text_at(d, (40, 318), "AI agents that",
            font=_font("regular", 28), fill=(210, 220, 238))
    text_at(d, (40, 356), "touch silicon.",
            font=_font("bold", 30), fill=ACCENT)

    # MIT + supported boards strip near the bottom.
    text_at(d, (40, 528), "open source · MIT",
            font=_font("mono", 14), fill=(180, 196, 220))
    text_at(d, (40, 552), "Pi 4 · Pi 5 · CM4 · CM5",
            font=_font("mono", 14), fill=(140, 156, 184))
    text_at(d, (40, 576), "github.com/Pan-Robotics/bus-mcp",
            font=_font("mono-bold", 16), fill=ACCENT)

    # Hairline divider between bands.
    d.line([(NAVY_W, 6), (NAVY_W, H)], fill=(60, 70, 92), width=2)

    # ── Right band — workflow diagram ──────────────────────────────────
    # Layout: agent (left) → MCP (centre) → bus-mcp / Pi (right of centre)
    # → bus tags → hardware silhouettes.
    bx0 = NAVY_W + 40
    bx1 = W - 40

    # Section heading.
    f_h = _font("bold", 24)
    f_s = _font("regular", 16)
    text_at(d, (bx0, 56),
            "Model Context Protocol — pointed at hardware",
            font=f_h, fill=INK)
    text_at(d, (bx0, 90),
            "An MCP server on the robot exposes its physical buses as tools",
            font=f_s, fill=INK_DIM)
    text_at(d, (bx0, 112),
            "the agent can call directly.",
            font=f_s, fill=INK_DIM)

    # ── Top row — flow boxes ──────────────────────────────────────────
    row_y = 168
    row_h = 132
    box_w = 178
    box_h = 96

    flow_y0 = row_y
    flow_y1 = row_y + box_h

    # Three big boxes: AGENT, BUS-MCP, HARDWARE
    big_box_w = 168
    centre = (bx0 + bx1) // 2
    agent_x = bx0 + 6
    pi_x = centre - big_box_w // 2
    hw_x = bx1 - big_box_w - 6

    def big_box(x: int, title: str, sub: str, *, fill, stroke) -> None:
        rrect(d, (x, flow_y0, x + big_box_w, flow_y1),
              fill=fill, stroke=stroke, width=2, radius=14)
        f_t = _font("bold", 22)
        f_b = _font("regular", 15)
        text_at(d, (x + big_box_w // 2, flow_y0 + 30), title,
                font=f_t, fill=INK, anchor="mm")
        # Subtitle may have a newline.
        lines = sub.split("\n")
        for i, line in enumerate(lines):
            text_at(d, (x + big_box_w // 2, flow_y0 + 60 + i * 18), line,
                    font=f_b, fill=INK_DIM, anchor="mm")

    big_box(agent_x, "AI agent",
            "Claude, Codex,\nany MCP client",
            fill=(232, 240, 252), stroke=(140, 168, 220))

    big_box(pi_x, "bus-mcp",
            "Raspberry Pi / SBC\nsystemd · stdio · HTTP",
            fill=(255, 242, 222), stroke=ACCENT_DK)

    big_box(hw_x, "the machine",
            "buses · motors\nsensors · actuators",
            fill=(232, 244, 232), stroke=(120, 168, 110))

    # Arrows between boxes, with labels above.
    arrow_y = flow_y0 + box_h // 2
    arrow(d,
          (agent_x + big_box_w + 4, arrow_y),
          (pi_x - 6, arrow_y),
          color=WIRE, width=4, head=12)
    mid_l = (agent_x + big_box_w + pi_x) // 2
    text_at(d, (mid_l, arrow_y - 18), "MCP",
            font=_font("mono-bold", 13), fill=WIRE, anchor="mm")
    text_at(d, (mid_l, arrow_y + 18), "stdio · http",
            font=_font("mono", 10), fill=INK_DIM, anchor="mm")

    arrow(d,
          (pi_x + big_box_w + 4, arrow_y),
          (hw_x - 6, arrow_y),
          color=WIRE, width=4, head=12)
    mid_r = (pi_x + big_box_w + hw_x) // 2
    text_at(d, (mid_r, arrow_y - 18), "tool calls",
            font=_font("mono-bold", 13), fill=WIRE, anchor="mm")
    text_at(d, (mid_r, arrow_y + 18), "syscalls",
            font=_font("mono", 10), fill=INK_DIM, anchor="mm")

    # ── Bus chips row — labels for the 5 buses ────────────────────────
    chip_y = flow_y1 + 60
    chip_h = 44
    chips = [
        ("CAN / CAN-FD",  (244, 226, 226), (200, 100, 100)),
        ("RS485 / UART",  (228, 240, 252), (110, 142, 196)),
        ("I2C",           (240, 232, 248), (160, 130, 200)),
        ("SPI",           (232, 244, 232), (110, 162, 110)),
        ("GPIO",          (252, 240, 220), ACCENT_DK),
    ]
    inner_w = bx1 - bx0
    gap = 12
    chip_w = (inner_w - gap * (len(chips) - 1)) // len(chips)
    for i, (label, fill, stroke) in enumerate(chips):
        x0 = bx0 + i * (chip_w + gap)
        rrect(d, (x0, chip_y, x0 + chip_w, chip_y + chip_h),
              fill=fill, stroke=stroke, width=2, radius=10)
        text_at(d, (x0 + chip_w // 2, chip_y + chip_h // 2), label,
                font=_font("mono-bold", 15), fill=INK, anchor="mm")

    # Caption under the chips.
    cap_y = chip_y + chip_h + 22
    text_at(d, (bx0, cap_y),
            "Telemetry stays on the wire. Control stays in the loop.",
            font=_font("bold", 17), fill=INK)
    text_at(d, (bx0, cap_y + 26),
            "The agent never sees a file system, the data never leaves the device.",
            font=_font("regular", 15), fill=INK_DIM)

    # ── Footer strip on the right band ─────────────────────────────────
    foot_y = H - 36
    text_at(d, (bx1, foot_y),
            "MCP · python-can · pyserial · smbus2 · spidev · lgpio",
            font=_font("mono", 12), fill=(160, 168, 184), anchor="rt")

    return img


def main() -> int:
    out = Path(__file__).parent / "linkedin_card.png"
    img = draw_card()
    img.save(out, format="PNG", optimize=True)
    print(f"wrote {out}  ({img.size[0]}×{img.size[1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
