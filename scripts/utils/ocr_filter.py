import csv
import os
import glob
from PIL import Image
import pytesseract
from datetime import datetime

# Paths
csv_file = "../data/source/portfolio_data.csv"
images_dir = "/Users/forrestmiller/Desktop/nationwide-prospector/assets/images"
results_file = "/Users/forrestmiller/Desktop/image analysis/ocr_results.csv"

# Read building IDs from CSV
building_ids = []
with open(csv_file, 'r') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)
    building_ids = [row['id_building'] for row in rows]

print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting OCR processing for {len(building_ids)} buildings")
print(f"[{datetime.now().strftime('%H:%M:%S')}] Results will be saved to: {results_file}")
print("-" * 80)

# Initialize results CSV
with open(results_file, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['building_id', 'image_file', 'text_detected', 'text_length', 'sample_text'])

# Track buildings with/without text
buildings_with_text = set()
buildings_no_text = set()
processed = 0

for building_id in building_ids:
    processed += 1
    # Find images for this building
    pattern = os.path.join(images_dir, f"{building_id}_*")
    images = glob.glob(pattern)

    if not images:
        print(f"[{processed}/{len(building_ids)}] {building_id}: No images found")
        buildings_no_text.add(building_id)
        continue

    text_found_for_building = False

    for img_path in images:
        img_name = os.path.basename(img_path)
        try:
            # Run OCR
            image = Image.open(img_path)
            text = pytesseract.image_to_string(image).strip()
            text_length = len(text)
            has_text = text_length > 0

            if has_text:
                text_found_for_building = True
                sample = text[:50].replace('\n', ' ').replace(',', ' ')
                print(f"[{processed}/{len(building_ids)}] {building_id}: ✓ TEXT FOUND ({text_length} chars) - {img_name}")
            else:
                print(f"[{processed}/{len(building_ids)}] {building_id}: ✗ No text - {img_name}")

            # Save result incrementally
            with open(results_file, 'a', newline='') as f:
                writer = csv.writer(f)
                sample_text = text[:100].replace('\n', ' ').replace(',', ';') if text else ''
                writer.writerow([building_id, img_name, has_text, text_length, sample_text])

        except Exception as e:
            print(f"[{processed}/{len(building_ids)}] {building_id}: ERROR processing {img_name} - {e}")
            with open(results_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([building_id, img_name, False, 0, f'ERROR: {str(e)[:50]}'])

    if text_found_for_building:
        buildings_with_text.add(building_id)
    else:
        buildings_no_text.add(building_id)

    # Progress update every 100
    if processed % 100 == 0:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Progress: {processed}/{len(building_ids)} | With text: {len(buildings_with_text)} | No text: {len(buildings_no_text)}\n")

print("\n" + "=" * 80)
print(f"[{datetime.now().strftime('%H:%M:%S')}] OCR COMPLETE")
print(f"Buildings with text: {len(buildings_with_text)}")
print(f"Buildings without text: {len(buildings_no_text)}")
print("=" * 80)

# Update portfolio CSV - remove rows without text
print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Updating portfolio CSV - removing {len(buildings_no_text)} rows without text...")

rows_to_keep = [row for row in rows if row['id_building'] in buildings_with_text]

with open(csv_file, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows_to_keep)

print(f"[{datetime.now().strftime('%H:%M:%S')}] Done! Portfolio CSV now has {len(rows_to_keep)} rows")
print(f"[{datetime.now().strftime('%H:%M:%S')}] OCR results saved to: {results_file}")
