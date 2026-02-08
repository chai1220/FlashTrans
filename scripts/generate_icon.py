from __future__ import annotations

import argparse
from pathlib import Path


def _draw_icon(size: int) -> "Image.Image":
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = max(1, size // 10)
    bar_h = max(2, size // 5)
    stem_w = max(2, size // 5)
    stem_h = max(2, size - margin * 2 - bar_h)

    bar_radius = max(1, bar_h // 2)
    stem_radius = max(1, stem_w // 2)

    draw.rounded_rectangle(
        (margin, margin, size - margin, margin + bar_h),
        radius=bar_radius,
        fill=(0, 0, 0, 255),
    )
    stem_x = (size - stem_w) // 2
    stem_y = margin + bar_h
    draw.rounded_rectangle(
        (stem_x, stem_y, stem_x + stem_w, stem_y + stem_h),
        radius=stem_radius,
        fill=(0, 0, 0, 255),
    )

    return img


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="Output .ico path")
    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sizes = [16, 20, 24, 32, 48, 64, 128, 256]
    images = [_draw_icon(s) for s in sizes]
    images[0].save(out_path, format="ICO", sizes=[(s, s) for s in sizes])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

