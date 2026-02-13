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




def _from_logo(path: Path, size: int, remove_light_bg: bool) -> "Image.Image":
    from PIL import Image

    img = Image.open(path).convert("RGBA")
    if remove_light_bg:
        img = _remove_light_background(img)
    
    w, h = img.size
    if w <= 0 or h <= 0:
        raise ValueError("Invalid logo image")
    
    # Scale to fit within the icon size while maintaining aspect ratio
    scale = min(size / w, size / h)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    
    # High-quality resize
    img = img.resize((nw, nh), Image.LANCZOS)
    
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - nw) // 2
    y = (size - nh) // 2
    canvas.alpha_composite(img, (x, y))
    return canvas


def _remove_light_background(img: "Image.Image") -> "Image.Image":
    from PIL import Image

    rgba = img.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    if w <= 2 or h <= 2:
        return rgba

    def sample(x: int, y: int) -> tuple[int, int, int]:
        r, g, b, _a = px[x, y]
        return int(r), int(g), int(b)

    samples = [
        sample(0, 0),
        sample(w - 1, 0),
        sample(0, h - 1),
        sample(w - 1, h - 1),
        sample(w // 2, 0),
        sample(w // 2, h - 1),
        sample(0, h // 2),
        sample(w - 1, h // 2),
    ]
    bg_r = sum(s[0] for s in samples) / len(samples)
    bg_g = sum(s[1] for s in samples) / len(samples)
    bg_b = sum(s[2] for s in samples) / len(samples)

    def dist2(r: int, g: int, b: int) -> float:
        dr = r - bg_r
        dg = g - bg_g
        db = b - bg_b
        return dr * dr + dg * dg + db * db

    max_bg_dist2 = 55.0 * 55.0
    soften_dist2 = 95.0 * 95.0

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out_px = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            d2 = dist2(r, g, b)
            if lum >= 235 and d2 <= soften_dist2:
                if d2 <= max_bg_dist2:
                    continue
                t = (d2 - max_bg_dist2) / (soften_dist2 - max_bg_dist2)
                na = int(round(a * max(0.0, min(1.0, t))))
                if na <= 0:
                    continue
                out_px[x, y] = (r, g, b, na)
            else:
                out_px[x, y] = (r, g, b, a)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="Output .ico path")
    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logo_path = (out_path.parent / "logo.png").resolve()
    if not logo_path.exists():
        raise FileNotFoundError(f"Logo not found: {logo_path}")
    use_logo = True
    remove_light_bg = False

    sizes = [16, 20, 24, 32, 48, 64, 128, 256]
    images = [(_from_logo(logo_path, s, remove_light_bg) if use_logo else _draw_icon(s)) for s in sizes]
    images[0].save(out_path, format="ICO", sizes=[(s, s) for s in sizes])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

