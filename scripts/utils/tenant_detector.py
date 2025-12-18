import csv
import os
import base64
import time
import json
from datetime import datetime
from openai import OpenAI

# Config
API_KEY = os.environ.get("OPENAI_API_KEY", "")
IMAGES_DIR = "/Users/forrestmiller/Desktop/nationwide-prospector/assets/images"
OCR_RESULTS = "/Users/forrestmiller/Desktop/image analysis/ocr_results.csv"
OUTPUT_FILE = "/Users/forrestmiller/Desktop/image analysis/tenant_detection.csv"

client = OpenAI(api_key=API_KEY)

def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def detect_tenant(image_path):
    """Use OpenAI Vision to detect tenant from building image"""
    try:
        base64_image = encode_image(image_path)
        ext = image_path.lower().split('.')[-1]
        mime = "image/jpeg" if ext in ["jpg", "jpeg"] else f"image/{ext}"

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Analyze this building image. Look for any visible signage, logos, or text that indicates a tenant or business occupying the building.

Return JSON only:
{"tenant_name": "Name of tenant/business or null if none found", "confidence": "high/medium/low/none", "reasoning": "brief explanation"}

If you see multiple tenants, return the most prominent one. If no tenant is identifiable, set tenant_name to null and confidence to "none"."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{base64_image}"}
                        }
                    ]
                }
            ],
            max_tokens=300
        )

        result_text = response.choices[0].message.content.strip()
        # Parse JSON from response
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        result = json.loads(result_text)
        return result
    except Exception as e:
        return {"tenant_name": None, "confidence": "error", "reasoning": str(e)}

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Tenant Detection Starting")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Watching: {OCR_RESULTS}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Output: {OUTPUT_FILE}")
    print("=" * 80)

    # Initialize output CSV
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['building_id', 'image_file', 'tenant_name', 'confidence', 'reasoning'])

    # Track processed images
    processed = set()
    with open(OUTPUT_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            processed.add(row['image_file'])

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Already processed: {len(processed)} images")

    last_size = 0
    images_with_text = []

    while True:
        # Check if OCR results file exists and has new content
        if os.path.exists(OCR_RESULTS):
            current_size = os.path.getsize(OCR_RESULTS)

            if current_size != last_size:
                last_size = current_size
                # Re-read the file
                images_with_text = []
                try:
                    with open(OCR_RESULTS, 'r') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row.get('text_detected', '').lower() == 'true':
                                if row['image_file'] not in processed:
                                    images_with_text.append(row)
                except:
                    pass

                print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(images_with_text)} new images with text to process")

        # Process pending images
        for i, row in enumerate(images_with_text):
            img_file = row['image_file']
            building_id = row['building_id']
            img_path = os.path.join(IMAGES_DIR, img_file)

            if img_file in processed:
                continue

            if not os.path.exists(img_path):
                print(f"[{datetime.now().strftime('%H:%M:%S')}] SKIP {building_id}: Image not found - {img_file}")
                processed.add(img_file)
                continue

            print(f"[{datetime.now().strftime('%H:%M:%S')}] ANALYZING {building_id}: {img_file}...")

            result = detect_tenant(img_path)
            tenant = result.get('tenant_name')
            confidence = result.get('confidence', 'unknown')
            reasoning = result.get('reasoning', '')[:100].replace(',', ';').replace('\n', ' ')

            if tenant:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ TENANT FOUND: {tenant} (confidence: {confidence})")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ No tenant identified (confidence: {confidence})")

            # Save result
            with open(OUTPUT_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([building_id, img_file, tenant or '', confidence, reasoning])

            processed.add(img_file)

            # Small delay to avoid rate limits
            time.sleep(0.5)

        # Clear processed list
        images_with_text = []

        # Wait before checking for new results
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting for new OCR results... (Ctrl+C to stop)")
        time.sleep(5)

if __name__ == "__main__":
    main()
