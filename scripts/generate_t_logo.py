from PIL import Image, ImageDraw, ImageFont

def generate_t_logo(path):
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw a rounded square background (optional, or just the letter)
    # Let's make it look like an app icon: Dark background with light T
    bg_color = (30, 30, 35, 255) # Dark gray/blueish
    t_color = (66, 165, 245, 255) # Blue
    
    # Background shape
    margin = 20
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=50,
        fill=bg_color
    )

    # Draw T
    # Since we can't rely on system fonts, we draw it manually or use default
    # Drawing a thick T manually
    
    # T dimensions
    stem_w = 50
    bar_h = 50
    t_w = 140
    t_h = 160
    
    # Center position
    cx = size // 2
    cy = size // 2
    
    # Top bar rect
    bar_x0 = cx - t_w // 2
    bar_y0 = cy - t_h // 2 + 10 # slightly shifted down
    bar_x1 = bar_x0 + t_w
    bar_y1 = bar_y0 + bar_h
    
    # Stem rect
    stem_x0 = cx - stem_w // 2
    stem_y0 = bar_y1
    stem_x1 = stem_x0 + stem_w
    stem_y1 = bar_y0 + t_h
    
    # Draw T parts
    draw.rectangle((bar_x0, bar_y0, bar_x1, bar_y1), fill=t_color)
    draw.rectangle((stem_x0, stem_y0, stem_x1, stem_y1), fill=t_color)
    
    img.save(path)
    print(f"Generated logo at {path}")

if __name__ == "__main__":
    import sys
    from pathlib import Path
    out = Path("assets/new_logo.png").resolve()
    if len(sys.argv) > 1:
        out = Path(sys.argv[1]).resolve()
    generate_t_logo(out)
