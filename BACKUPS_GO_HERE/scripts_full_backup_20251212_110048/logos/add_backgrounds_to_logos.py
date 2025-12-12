#!/opt/homebrew/bin/python3
"""
Add solid backgrounds to transparent logos so they show up on light backgrounds.
For white logos, invert colors AND add a white/light background.
"""

import os
from PIL import Image, ImageOps, ImageStat
from pathlib import Path

# Directories
LOGOS_DIR = '/Users/forrestmiller/Desktop/nationwide propector/Logos'
PROCESSED_DIR = '/Users/forrestmiller/Desktop/nationwide propector/Logos/with_backgrounds'
BACKUP_DIR = '/Users/forrestmiller/Desktop/nationwide propector/Logos/original_backups'

# Background color for logos (white background)
BACKGROUND_COLOR = (255, 255, 255)  # White background

def calculate_brightness(image):
    """Calculate average brightness of an image (0-255)"""
    grayscale = image.convert('L')
    stat = ImageStat.Stat(grayscale)
    return stat.mean[0]

def is_predominantly_white(image_path, threshold=200):
    """Check if image is predominantly white/light."""
    try:
        with Image.open(image_path) as img:
            # Convert to RGB for brightness calculation
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[-1])
                elif img.mode == 'P' and 'transparency' in img.info:
                    img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            brightness = calculate_brightness(img)
            return brightness >= threshold, brightness
    except Exception as e:
        print(f"  ERROR analyzing {os.path.basename(image_path)}: {e}")
        return False, 0

def process_logo_with_background(input_path, output_path, invert=False):
    """
    Process logo: invert colors if needed, then add solid background.
    """
    try:
        with Image.open(input_path) as img:
            # Convert to RGBA if not already
            if img.mode != 'RGBA':
                if img.mode == 'P' and 'transparency' in img.info:
                    img = img.convert('RGBA')
                elif img.mode == 'RGB':
                    # Add alpha channel (fully opaque)
                    img = img.convert('RGBA')
                else:
                    img = img.convert('RGBA')

            # If we need to invert
            if invert:
                r, g, b, a = img.split()
                rgb_image = Image.merge('RGB', (r, g, b))
                inverted_rgb = ImageOps.invert(rgb_image)
                r2, g2, b2 = inverted_rgb.split()
                img = Image.merge('RGBA', (r2, g2, b2, a))

            # Create background with solid color
            background = Image.new('RGBA', img.size, BACKGROUND_COLOR + (255,))

            # Paste logo onto background using alpha channel as mask
            background.paste(img, (0, 0), img)

            # Convert back to RGB (no transparency)
            final_img = background.convert('RGB')

            # Save as PNG
            final_img.save(output_path, 'PNG')
            return True

    except Exception as e:
        print(f"  ERROR processing {os.path.basename(input_path)}: {e}")
        return False

def main():
    print("="*60)
    print("LOGO BACKGROUND PROCESSOR")
    print("="*60)
    print(f"Logos directory: {LOGOS_DIR}")
    print(f"Output directory: {PROCESSED_DIR}")
    print(f"Background color: RGB{BACKGROUND_COLOR}")
    print("="*60 + "\n")

    # Create output directory
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    # Get all PNG files
    logo_files = [f for f in os.listdir(LOGOS_DIR)
                  if f.lower().endswith(('.png', '.jpg', '.jpeg'))
                  and os.path.isfile(os.path.join(LOGOS_DIR, f))]

    print(f"Found {len(logo_files)} logo files to process\n")

    white_logos = []
    dark_logos = []

    # First pass: identify white vs dark logos
    print("Analyzing logos...")
    for filename in logo_files:
        filepath = os.path.join(LOGOS_DIR, filename)
        is_white, brightness = is_predominantly_white(filepath)

        if is_white:
            white_logos.append((filename, brightness, filepath))
        else:
            dark_logos.append((filename, brightness, filepath))

    print(f"✓ Found {len(white_logos)} white/light logos (will invert + add background)")
    print(f"✓ Found {len(dark_logos)} dark logos (will just add background)\n")

    # Process all logos
    processed_count = 0
    failed_count = 0

    print("="*60)
    print("PROCESSING WHITE LOGOS (INVERT + ADD BACKGROUND)")
    print("="*60 + "\n")

    for filename, brightness, filepath in white_logos:
        output_path = os.path.join(PROCESSED_DIR, filename)
        print(f"[{processed_count+1}/{len(logo_files)}] {filename} (brightness: {brightness:.1f})")

        if process_logo_with_background(filepath, output_path, invert=True):
            print(f"  ✓ Inverted + added background")
            processed_count += 1
        else:
            print(f"  ✗ Failed")
            failed_count += 1

    print("\n" + "="*60)
    print("PROCESSING DARK LOGOS (ADD BACKGROUND ONLY)")
    print("="*60 + "\n")

    for filename, brightness, filepath in dark_logos:
        output_path = os.path.join(PROCESSED_DIR, filename)
        print(f"[{processed_count+1}/{len(logo_files)}] {filename} (brightness: {brightness:.1f})")

        if process_logo_with_background(filepath, output_path, invert=False):
            print(f"  ✓ Added background")
            processed_count += 1
        else:
            print(f"  ✗ Failed")
            failed_count += 1

    print("\n" + "="*60)
    print("PROCESSING COMPLETE")
    print("="*60)
    print(f"Successfully processed: {processed_count}/{len(logo_files)}")
    print(f"Failed: {failed_count}")
    print(f"\nProcessed logos saved to: {PROCESSED_DIR}")
    print("="*60)
    print("\nNext step: Replace originals and upload to AWS")

if __name__ == "__main__":
    main()
