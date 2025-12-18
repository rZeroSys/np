#!/usr/bin/env python3
"""Find logos without transparent backgrounds and copy to new folder"""

import os
import shutil
from pathlib import Path
from PIL import Image

INPUT_DIR = "/Users/forrestmiller/Desktop/organization_logos"
OUTPUT_DIR = "/Users/forrestmiller/Desktop/logos_no_transparency"

def has_transparency(img_path):
    """Check if image has any transparent pixels"""
    try:
        img = Image.open(img_path)

        # If no alpha channel, definitely not transparent
        if img.mode != 'RGBA':
            return False

        # Check if any pixel has alpha < 255 (not fully opaque)
        alpha = img.getchannel('A')
        if alpha.getextrema()[0] < 255:
            return True
        return False
    except Exception as e:
        print(f"Error checking {img_path}: {e}")
        return True  # Assume transparent on error, don't include

def main():
    Path(OUTPUT_DIR).mkdir(exist_ok=True)

    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]
    print(f"Checking {len(files)} logos for transparency...")
    print("-" * 50)

    non_transparent = 0

    for i, filename in enumerate(files, 1):
        filepath = os.path.join(INPUT_DIR, filename)

        if not has_transparency(filepath):
            shutil.copy2(filepath, os.path.join(OUTPUT_DIR, filename))
            non_transparent += 1
            print(f"No transparency: {filename}")

        if i % 200 == 0:
            print(f"Progress: {i}/{len(files)}")

    print("-" * 50)
    print(f"DONE! Found {non_transparent} logos WITHOUT transparent backgrounds")
    print(f"Copied to: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
