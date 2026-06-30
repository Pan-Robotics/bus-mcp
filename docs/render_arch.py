"""Render the bus-mcp architecture diagram to a PNG.

Pure-PIL — no `dot`, no `mmdc`, no system fonts beyond DejaVu. Run with:

    python docs/render_arch.py

Writes ``docs/architecture.png`` next to this script.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Canvas + palette
# ---------------------------------------------------------------------------

W, H = 1600, 1800
BG = (250, 250, 252)
INK = (32, 36, 42)
RULE = (180, 184, 192)

# Layer band fills, top → bottom.
LAYER_FILL = {
    "client":   (235, 244, 255),  # cool blue
    "transport":(220, 232, 250),
    "server":   (255, 238, 215),  # warm — bus-mcp core
    "tools":    (255, 232, 200),
    "registry": (255, 226, 196),
    "drivers":  (224, 244, 220),  # green
    "kernel":   (228, 228, 234),  # neutral
    "hardware": (252, 222, 222),  # warm pink
}
LAYER_STROKE = {
    "client":   (135, 165, 215),
    "transport":(110, 142, 196),
    "server":   (210, 152, 60),
    "tools":    (200, 142, 50),
    "registry": (190, 130, 40),
    "drivers":  (90, 158, 80),
    "kernel":   (135, 138, 148),
    "hardware": (200, 100, 100),
}
BOX_FILL = (255, 255, 255)
BOX_STROKE = (60, 64, 72)
ACCENT = (40, 90, 180)

# ---------------------------------------------------------------------------
# Fonts (DejaVu ships with virtually every Linux distro)
# ---------------------------------------------------------------------------

FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/usr/local/share/fonts/dejavu",
]


def _load_font(weight: str, size: int) -> ImageFont.ImageFont:
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
    return ImageFont.load_default()  # last resort — readable but ugly


# ---------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------


def rounded_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int],
    stroke: tuple[int, int, int],
    radius: int = 14,
    width: int = 2,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=stroke, width=width)


def text_center(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int] = INK,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((xy[0] - w / 2, xy[1] - h / 2 - bbox[1]), text, font=font, fill=fill)


def text_left(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int] = INK,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    h = bbox[3] - bbox[1]
    draw.text((xy[0], xy[1] - h / 2 - bbox[1]), text, font=font, fill=fill)


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    color: tuple[int, int, int] = INK,
    width: int = 2,
    head: int = 12,
) -> None:
    draw.line([start, end], fill=color, width=width)
    # Arrowhead — triangle pointing at `end`.
    import math

    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy) or 1
    ux, uy = dx / length, dy / length
    # Perpendicular.
    px, py = -uy, ux
    tip = end
    base = (end[0] - ux * head, end[1] - uy * head)
    left = (base[0] + px * head * 0.5, base[1] + py * head * 0.5)
    right = (base[0] - px * head * 0.5, base[1] - py * head * 0.5)
    draw.polygon([tip, left, right], fill=color)


# ---------------------------------------------------------------------------
# Layout — one helper per layer band
# ---------------------------------------------------------------------------


def draw_diagram() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    title_font = _load_font("bold", 38)
    subtitle_font = _load_font("regular", 20)
    layer_label_font = _load_font("bold", 22)
    box_title_font = _load_font("bold", 22)
    box_body_font = _load_font("regular", 17)
    tag_font = _load_font("mono-bold", 14)
    note_font = _load_font("regular", 16)

    # Title
    text_center(d, (W // 2, 56), "bus-mcp — system architecture",
                font=title_font, fill=INK)
    text_center(d, (W // 2, 96),
                "MCP server exposing Raspberry Pi peripheral buses to AI agents",
                font=subtitle_font, fill=(96, 100, 108))

    # Layer geometry — each band stretches across the canvas.
    LEFT_M, RIGHT_M = 70, 70
    band_x0 = LEFT_M
    band_x1 = W - RIGHT_M

    layers: list[tuple[str, str, list[tuple[str, list[str]]]]] = [
        # (key, label, boxes); height is auto-computed from box contents.
        ("client", "L1  AI agent (MCP client)", [
            ("Claude Desktop", ["stdio child process"]),
            ("Claude Code", ["stdio  or  HTTP /mcp"]),
            ("Custom MCP client", ["streamable-HTTP /mcp"]),
        ]),
        ("transport", "L2  MCP transport", [
            ("stdio  (Claude Desktop / Code native)", ["one process per client"]),
            ("streamable-HTTP   POST /mcp", ["uvicorn  ·  default 127.0.0.1:7820"]),
        ]),
        ("server", "L3  bus-mcp server  (FastMCP)", [
            ("Tool registry — 18 tools",
             ["bus_list · bus_status · bus_close · write_permissions",
              "can_configure / send / receive",
              "serial_configure / send / receive",
              "i2c_read / write / scan",
              "spi_configure / xfer",
              "gpio_configure / read / write"]),
            ("Async dispatch",
             ["@mcp.tool() sync  →  fast point ops",
              "async + asyncio.to_thread  →  blocking",
              "receive / scan calls don’t",
              "freeze the event loop"]),
        ]),
        ("tools", "L4  tool layer  (pure functions over registry + gate)", [
            ("tools.py", [
                "thin functions, no I/O of their own",
                "exercise via fakes in tests",
            ]),
            ("WriteGate", [
                "--allow-write[=can,serial,…]",
                "gates every send / write call",
                "PermissionError → MCP tool error",
            ]),
        ]),
        ("registry", "L5  BusRegistry  (id → driver instance)", [
            ("DiscoveredBus map", [
                "bus_id · kind · device path",
                "config dict — *_configure tools",
                "update + bounce the driver",
            ]),
            ("Discovery", [
                "globs /dev/{i2c-*, spidev*,",
                "ttyUSB*, ttyAMA*, ttyS*, gpiochip*}",
                "+ /sys/class/net (can0 / can1 / …)",
            ]),
            ("Lazy driver factories", [
                "python-can / pyserial / smbus2 /",
                "spidev / lgpio",
                "deferred imports — package",
                "installs without them",
            ]),
        ]),
        ("drivers", "L6  Bus drivers", [
            ("CanBus",    ["python-can", "SocketCAN backend"]),
            ("SerialBus", ["pyserial", "UART + RS485"]),
            ("I2cBus",    ["smbus2"]),
            ("SpiBus",    ["spidev", "per-call speed override"]),
            ("GpioBus",   ["lgpio", "Pi 5 / CM5 compatible"]),
        ]),
        ("kernel", "L7  Linux kernel", [
            ("AF_CAN sockets", ["mcp251x  ·  can_dev"]),
            ("termios serial",  ["/dev/ttyAMA0", "/dev/ttyUSB*"]),
            ("i2c-dev",         ["/dev/i2c-*"]),
            ("spidev",          ["/dev/spidev*"]),
            ("gpiochip",        ["/dev/gpiochip0..N"]),
        ]),
        ("hardware", "L8  Physical buses + devices", [
            ("CAN / CAN-FD", ["MCP2515 / 2518FD HAT", "ECUs, motor drivers"]),
            ("RS485 / UART", ["transceivers", "sensors, modbus slaves"]),
            ("I2C",          ["BME280, MPU6050,", "OLEDs, EEPROMs"]),
            ("SPI",          ["ADC, DAC,", "Lora, NFC, displays"]),
            ("GPIO",         ["buttons, relays,", "LEDs, encoders"]),
        ]),
    ]

    # Auto-size each band so the tallest box inside fits with padding.
    BOX_TITLE_GAP = 32      # title baseline to first body line
    BODY_LINE_GAP = 22
    BOX_BOTTOM_PAD = 16
    LAYER_HEADER = 50       # band top → top of box
    LAYER_BOTTOM_PAD = 14   # band bottom padding under box

    def _layer_height(boxes: list[tuple[str, list[str]]]) -> int:
        max_body = max(len(body) for _t, body in boxes)
        box_h = BOX_TITLE_GAP + max_body * BODY_LINE_GAP + BOX_BOTTOM_PAD
        return LAYER_HEADER + box_h + LAYER_BOTTOM_PAD

    # ── Render layers top-down ─────────────────────────────────────────
    y = 140
    layer_rects: dict[str, tuple[int, int, int, int]] = {}
    BAND_GAP = 24

    # Reserve a horizontal margin on the right side of L1+L2 only, where
    # the Packaging side-car sits. Other bands use the full width.
    SIDE_W = 280
    SIDE_GAP = 18

    for key, label, boxes in layers:
        h = _layer_height(boxes)
        y0, y1 = y, y + h

        # Inset the L1+L2 bands so the Packaging panel on the right has
        # its own column; lower bands span the full width.
        right_inset = SIDE_W + SIDE_GAP if key in ("client", "transport") else 0
        band_right = band_x1 - right_inset

        rounded_box(d, (band_x0, y0, band_right, y1),
                    fill=LAYER_FILL[key], stroke=LAYER_STROKE[key],
                    radius=14, width=2)
        text_left(d, (band_x0 + 18, y0 + 22), label,
                  font=layer_label_font, fill=LAYER_STROKE[key])
        layer_rects[key] = (band_x0, y0, band_x1, y1)

        # Lay out boxes evenly inside the band.
        n = len(boxes)
        inner_left = band_x0 + 24
        inner_right = band_right - 24
        gap = 14
        box_w = (inner_right - inner_left - gap * (n - 1)) // n
        box_top = y0 + LAYER_HEADER
        box_bot = y1 - LAYER_BOTTOM_PAD
        for i, (title, body) in enumerate(boxes):
            bx0 = inner_left + i * (box_w + gap)
            bx1 = bx0 + box_w
            rounded_box(d, (bx0, box_top, bx1, box_bot),
                        fill=BOX_FILL, stroke=BOX_STROKE,
                        radius=10, width=1)
            text_left(d, (bx0 + 14, box_top + 16), title,
                      font=box_title_font, fill=INK)
            for j, line in enumerate(body):
                text_left(d, (bx0 + 14, box_top + BOX_TITLE_GAP + 14 + j * BODY_LINE_GAP),
                          line, font=box_body_font, fill=(72, 76, 84))
        y = y1 + BAND_GAP

    # ── Inter-layer arrows down the centre ─────────────────────────────
    centre_x = (band_x0 + band_x1) // 2
    keys = [k for (k, *_rest) in layers]
    for upper, lower in zip(keys, keys[1:]):
        _, _, _, uy1 = layer_rects[upper]
        _, ly0, _, _ = layer_rects[lower]
        arrow(d, (centre_x, uy1 + 4), (centre_x, ly0 - 4),
              color=ACCENT, width=3, head=14)

    # ── Side-car: packaging panel beside L1+L2 ─────────────────────────
    # Spans the height of the L1 + L2 bands so it neither overlaps the
    # title nor bleeds into L3.
    _, l1_y0, _, _ = layer_rects["client"]
    _, _, _, l2_y1 = layer_rects["transport"]
    sx0 = band_x1 - SIDE_W
    sx1 = band_x1
    sy0 = l1_y0
    sy1 = l2_y1
    rounded_box(d, (sx0, sy0, sx1, sy1),
                fill=(238, 244, 232), stroke=(120, 152, 95),
                radius=14, width=2)
    text_left(d, (sx0 + 18, sy0 + 22), "Packaging",
              font=layer_label_font, fill=(80, 110, 60))
    bullets = [
        ("packaging/install.sh", True),
        ("• venv --system-site-packages", False),
        ("• spi / i2c / gpio / dialout", False),
        ("• renders systemd unit", False),
        ("", False),
        ("bus-mcp.service", True),
        ("• Restart=on-failure", False),
        ("• After=network-online.target", False),
    ]
    for j, (line, bold) in enumerate(bullets):
        font = box_title_font if bold else box_body_font
        text_left(d, (sx0 + 18, sy0 + 60 + j * 22), line,
                  font=font, fill=INK if bold else (72, 76, 84))

    # Footer — legend
    foot_font = _load_font("regular", 13)
    text_left(d, (LEFT_M, H - 50),
              "Arrows: JSON-RPC / tool dispatch / driver call / syscall (top → bottom).",
              font=foot_font, fill=(120, 124, 132))
    text_left(d, (LEFT_M, H - 28),
              "Layer fills only mark distinct concerns; nothing is on a different host until "
              "you change --transport / --host.",
              font=foot_font, fill=(120, 124, 132))

    return img


def main() -> int:
    out = Path(__file__).parent / "architecture.png"
    img = draw_diagram()
    img.save(out, format="PNG", optimize=True)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
