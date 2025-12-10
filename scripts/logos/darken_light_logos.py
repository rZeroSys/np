#!/usr/bin/env python3
"""
Darken light logos by reducing brightness 25% while preserving transparency.
"""

from PIL import Image, ImageEnhance
import os

LOGOS_DIR = '/Users/forrestmiller/Desktop/nationwide propector/Logos'
WHITE_LOGOS_LIST = os.path.join(LOGOS_DIR, 'white_logos_list.txt')
BRIGHTNESS_FACTOR = 0.75  # 25% darker

def darken_logo(filepath):
    """Darken a logo while preserving alpha channel."""
    try:
        img = Image.open(filepath)

        # Handle different image modes
        if img.mode == 'RGBA':
            # Split into RGB and Alpha
            r, g, b, a = img.split()
            rgb_img = Image.merge('RGB', (r, g, b))

            # Darken RGB
            enhancer = ImageEnhance.Brightness(rgb_img)
            darkened_rgb = enhancer.enhance(BRIGHTNESS_FACTOR)

            # Recombine with original alpha
            r2, g2, b2 = darkened_rgb.split()
            darkened = Image.merge('RGBA', (r2, g2, b2, a))

        elif img.mode == 'P':
            # Palette mode - convert to RGBA first
            img = img.convert('RGBA')
            r, g, b, a = img.split()
            rgb_img = Image.merge('RGB', (r, g, b))

            enhancer = ImageEnhance.Brightness(rgb_img)
            darkened_rgb = enhancer.enhance(BRIGHTNESS_FACTOR)

            r2, g2, b2 = darkened_rgb.split()
            darkened = Image.merge('RGBA', (r2, g2, b2, a))

        elif img.mode == 'RGB':
            enhancer = ImageEnhance.Brightness(img)
            darkened = enhancer.enhance(BRIGHTNESS_FACTOR)

        elif img.mode == 'LA':
            # Grayscale with alpha
            l, a = img.split()
            enhancer = ImageEnhance.Brightness(l.convert('RGB'))
            darkened_rgb = enhancer.enhance(BRIGHTNESS_FACTOR)
            darkened_l = darkened_rgb.convert('L')
            darkened = Image.merge('LA', (darkened_l, a))

        else:
            # Convert to RGB and darken
            rgb_img = img.convert('RGB')
            enhancer = ImageEnhance.Brightness(rgb_img)
            darkened = enhancer.enhance(BRIGHTNESS_FACTOR)

        # Save back
        darkened.save(filepath, 'PNG')
        return True

    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False

def main():
    # Read list of light logos
    with open(WHITE_LOGOS_LIST, 'r') as f:
        lines = f.readlines()

    success = 0
    failed = 0

    for line in lines:
        line = line.strip()
        if not line or ',' not in line:
            continue

        filename = line.split(',')[0]
        filepath = os.path.join(LOGOS_DIR, filename)

        if os.path.exists(filepath):
            print(f"Darkening: {filename}")
            if darken_logo(filepath):
                success += 1
            else:
                failed += 1
        else:
            print(f"Not found: {filename}")
            failed += 1

    print(f"\nDone! Darkened: {success}, Failed: {failed}")

if __name__ == '__main__':
    main()
