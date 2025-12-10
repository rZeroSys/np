#!/usr/bin/env python3
"""
Identify white/light logos and invert their colors so they show up on light backgrounds.
Then prepare them for AWS S3 upload.
"""

import os
from PIL import Image, ImageOps, ImageStat
import shutil
from pathlib import Path

# Directories
LOGOS_DIR = '/Users/forrestmiller/Desktop/nationwide propector/Logos'
INVERTED_DIR = '/Users/forrestmiller/Desktop/nationwide propector/Logos/inverted'
BACKUP_DIR = '/Users/forrestmiller/Desktop/nationwide propector/Logos/original_backups'

def calculate_brightness(image):
    """Calculate average brightness of an image (0-255)"""
    # Convert to grayscale
    grayscale = image.convert('L')
    stat = ImageStat.Stat(grayscale)
    return stat.mean[0]

def is_predominantly_white(image_path, threshold=200):
    """
    Check if image is predominantly white/light.
    Returns True if average brightness is above threshold (0-255 scale).
    """
    try:
        with Image.open(image_path) as img:
            # Convert to RGB if needed
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create white background for transparency
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

def invert_logo(input_path, output_path):
    """Invert colors of a logo image"""
    try:
        with Image.open(input_path) as img:
            # Handle transparency
            if img.mode == 'RGBA':
                r, g, b, a = img.split()
                rgb_image = Image.merge('RGB', (r, g, b))
                inverted_rgb = ImageOps.invert(rgb_image)
                r2, g2, b2 = inverted_rgb.split()
                inverted = Image.merge('RGBA', (r2, g2, b2, a))
            elif img.mode == 'P':
                # Convert palette mode to RGBA first
                img = img.convert('RGBA')
                r, g, b, a = img.split()
                rgb_image = Image.merge('RGB', (r, g, b))
                inverted_rgb = ImageOps.invert(rgb_image)
                r2, g2, b2 = inverted_rgb.split()
                inverted = Image.merge('RGBA', (r2, g2, b2, a))
            else:
                # Convert to RGB and invert
                rgb_image = img.convert('RGB')
                inverted = ImageOps.invert(rgb_image)

            # Save inverted image
            inverted.save(output_path, 'PNG')
            return True
    except Exception as e:
        print(f"  ERROR inverting {os.path.basename(input_path)}: {e}")
        return False

def main():
    print("="*60)
    print("WHITE LOGO IDENTIFIER AND INVERTER")
    print("="*60)
    print(f"Logos directory: {LOGOS_DIR}")
    print(f"Inverted output: {INVERTED_DIR}")
    print(f"Backups: {BACKUP_DIR}")
    print("="*60 + "\n")

    # Create output directories
    os.makedirs(INVERTED_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # Get all PNG files
    logo_files = [f for f in os.listdir(LOGOS_DIR)
                  if f.lower().endswith(('.png', '.jpg', '.jpeg'))
                  and os.path.isfile(os.path.join(LOGOS_DIR, f))]

    print(f"Found {len(logo_files)} logo files to analyze\n")

    white_logos = []
    processed_count = 0
    inverted_count = 0

    # Analyze each logo
    for i, filename in enumerate(logo_files, 1):
        filepath = os.path.join(LOGOS_DIR, filename)

        is_white, brightness = is_predominantly_white(filepath)

        if is_white:
            print(f"[{i}/{len(logo_files)}] {filename}")
            print(f"  → Brightness: {brightness:.1f}/255 - WHITE LOGO DETECTED")
            white_logos.append((filename, brightness, filepath))

        processed_count += 1

        # Progress update every 100 files
        if processed_count % 100 == 0:
            print(f"\n--- Processed {processed_count}/{len(logo_files)} files ---\n")

    print("\n" + "="*60)
    print(f"ANALYSIS COMPLETE")
    print(f"Total files analyzed: {processed_count}")
    print(f"White/light logos found: {len(white_logos)}")
    print("="*60 + "\n")

    if not white_logos:
        print("No white logos found. Nothing to invert.")
        return

    # Show white logos sorted by brightness
    print("White logos (brightest first):")
    print("-" * 60)
    white_logos.sort(key=lambda x: x[1], reverse=True)
    for filename, brightness, _ in white_logos:
        print(f"  {filename:<50} (Brightness: {brightness:.1f})")
    print()

    # Auto-confirm (you can comment this out if you want manual confirmation)
    print(f"\nProceeding to invert {len(white_logos)} logos...")
    # Uncomment below lines if you want manual confirmation:
    # response = input(f"Invert colors for these {len(white_logos)} logos? (yes/no): ").strip().lower()
    # if response not in ['yes', 'y']:
    #     print("Cancelled by user.")
    #     return

    print("\n" + "="*60)
    print("INVERTING LOGOS")
    print("="*60 + "\n")

    # Invert each white logo
    for filename, brightness, filepath in white_logos:
        print(f"Processing: {filename}")

        # Backup original
        backup_path = os.path.join(BACKUP_DIR, filename)
        shutil.copy2(filepath, backup_path)
        print(f"  ✓ Backed up to: {BACKUP_DIR}/{filename}")

        # Create inverted version
        inverted_path = os.path.join(INVERTED_DIR, filename)
        if invert_logo(filepath, inverted_path):
            print(f"  ✓ Inverted and saved to: {INVERTED_DIR}/{filename}")

            # Replace original with inverted version
            shutil.copy2(inverted_path, filepath)
            print(f"  ✓ Replaced original in: {LOGOS_DIR}/{filename}")

            inverted_count += 1
        else:
            print(f"  ✗ Failed to invert")
        print()

    print("="*60)
    print("INVERSION COMPLETE")
    print("="*60)
    print(f"Total logos inverted: {inverted_count}/{len(white_logos)}")
    print(f"Originals backed up to: {BACKUP_DIR}")
    print(f"Inverted copies saved to: {INVERTED_DIR}")
    print(f"Original files in {LOGOS_DIR} have been replaced with inverted versions")
    print("="*60)
    print("\nNext step: Run the AWS upload script to update S3")

if __name__ == "__main__":
    main()
