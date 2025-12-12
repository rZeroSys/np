#!/usr/bin/env python3
"""
AUTO DELETE BAD IMAGES
======================
Monitors the notable_building_images folder for new images.
Uses Claude API to evaluate image quality and deletes shitty ones.
Runs with caffeinate to keep Mac awake.

Usage:
    python3 scripts/images/auto_delete_bad_images.py
"""

import os
import sys
import time
import json
import base64
import signal
import subprocess
import requests
import io
from pathlib import Path
from datetime import datetime
from collections import deque
from PIL import Image

# =============================================================================
# CONFIGURATION
# =============================================================================
ANTHROPIC_API_KEY = "REMOVED_ANTHROPIC_KEY"
WATCH_DIR = Path("/Users/forrestmiller/Desktop/notable_building_images")
REJECTED_DIR = WATCH_DIR / "_rejected"
CHECK_INTERVAL = 2  # seconds between checks
QUALITY_THRESHOLD = 40  # Score 0-100, below this = delete

# Track processed files to avoid re-checking
processed_files = set()
caffeinate_proc = None

# =============================================================================
# TERMINAL OUTPUT HELPERS
# =============================================================================
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def log(msg, color=Colors.WHITE):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Colors.CYAN}[{timestamp}]{Colors.RESET} {color}{msg}{Colors.RESET}")

def log_success(msg):
    log(f"✓ {msg}", Colors.GREEN)

def log_error(msg):
    log(f"✗ {msg}", Colors.RED)

def log_warning(msg):
    log(f"⚠ {msg}", Colors.YELLOW)

def log_info(msg):
    log(f"→ {msg}", Colors.BLUE)

def log_header(msg):
    print(f"\n{Colors.BOLD}{Colors.MAGENTA}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}{msg:^60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}{'='*60}{Colors.RESET}\n")

# =============================================================================
# CAFFEINATE MANAGEMENT
# =============================================================================
def start_caffeinate():
    """Start caffeinate to prevent Mac from sleeping."""
    global caffeinate_proc
    try:
        caffeinate_proc = subprocess.Popen(
            ['caffeinate', '-dims'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        log_success(f"Caffeinate started (PID: {caffeinate_proc.pid}) - Mac will stay awake")
    except Exception as e:
        log_warning(f"Could not start caffeinate: {e}")

def stop_caffeinate():
    """Stop caffeinate process."""
    global caffeinate_proc
    if caffeinate_proc:
        caffeinate_proc.terminate()
        caffeinate_proc.wait()
        log_info("Caffeinate stopped")

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print()
    log_warning("Interrupt received, shutting down...")
    stop_caffeinate()
    sys.exit(0)

# =============================================================================
# CLAUDE API IMAGE EVALUATION
# =============================================================================
def resize_image_if_needed(image_bytes: bytes, max_size_kb: int = 1500) -> bytes:
    """Resize image if it's too large for the API."""
    if len(image_bytes) <= max_size_kb * 1024:
        return image_bytes

    try:
        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if needed
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # Calculate resize ratio
        current_size = len(image_bytes)
        ratio = (max_size_kb * 1024 / current_size) ** 0.5
        new_width = int(img.width * ratio * 0.9)  # 10% buffer
        new_height = int(img.height * ratio * 0.9)

        img = img.resize((new_width, new_height), Image.LANCZOS)

        # Save to bytes
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=80)
        result = output.getvalue()
        log_info(f"  Resized: {len(image_bytes)//1024}KB → {len(result)//1024}KB")
        return result
    except Exception as e:
        log_warning(f"  Could not resize: {e}")
        return image_bytes

def evaluate_image_with_claude(image_path: Path) -> tuple[int, str]:
    """
    Use Claude to evaluate if an image is good quality.
    Returns (score 0-100, reason).
    """
    try:
        # Check if file still exists (race condition with fetch script)
        if not image_path.exists():
            return -2, "File no longer exists"

        # Read and encode image
        with open(image_path, 'rb') as f:
            image_bytes = f.read()

        # Resize if too large
        image_bytes = resize_image_if_needed(image_bytes)

        b64_image = base64.b64encode(image_bytes).decode('utf-8')

        # Always use JPEG after potential resize
        media_type = "image/jpeg"

        # Build the prompt
        prompt = """Evaluate this building image for quality. Rate it 0-100 based on:

1. Is it an EXTERIOR photo of a building? (not interior, logo, map, diagram, or person)
2. Is the building clearly visible and recognizable?
3. Is the image reasonably high quality (not blurry, pixelated, or too dark)?
4. Does it show a real commercial/institutional building?

BAD (0-30): Interior shots, logos, maps, diagrams, people close-ups, blurry, wrong content
MEDIOCRE (31-50): Building visible but poor quality, obscured, or partial view
ACCEPTABLE (51-70): Decent building photo, could be better
GOOD (71-100): Clear, quality exterior building photo

Respond ONLY with JSON:
{"score": <0-100>, "reason": "<brief explanation>"}"""

        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 150,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        }

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            log_error(f"API error {response.status_code}: {response.text[:100]}")
            return -1, f"API error: {response.status_code}"

        result = response.json()
        content = result.get("content", [{}])[0].get("text", "")

        # Parse JSON response
        try:
            # Handle potential markdown code blocks
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            data = json.loads(content.strip())
            score = int(data.get("score", 0))
            reason = data.get("reason", "No reason provided")
            return score, reason
        except (json.JSONDecodeError, ValueError) as e:
            log_warning(f"Could not parse response: {content[:100]}")
            return -1, f"Parse error: {str(e)}"

    except Exception as e:
        log_error(f"Error evaluating {image_path.name}: {e}")
        return -1, str(e)

# =============================================================================
# FILE MONITORING AND PROCESSING
# =============================================================================
def get_image_files() -> list[Path]:
    """Get all image files in watch directory."""
    if not WATCH_DIR.exists():
        return []

    images = []
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']:
        images.extend(WATCH_DIR.glob(ext))

    # Exclude rejected directory
    images = [f for f in images if '_rejected' not in str(f) and f.exists()]

    # Sort with error handling for race conditions
    def safe_mtime(f):
        try:
            return f.stat().st_mtime if f.exists() else 0
        except:
            return 0

    return sorted(images, key=safe_mtime)

def process_new_images():
    """Check for new images and evaluate them."""
    global processed_files

    current_files = set(get_image_files())
    new_files = current_files - processed_files

    if not new_files:
        return

    log_info(f"Found {len(new_files)} new image(s) to evaluate")

    for image_path in sorted(new_files, key=lambda x: x.stat().st_mtime if x.exists() else 0):
        # Mark as processed immediately to avoid re-processing
        processed_files.add(image_path)

        # Check if file still exists (other script may have deleted it)
        if not image_path.exists():
            log_warning(f"Skipped {image_path.name} - already removed by fetch script")
            continue

        # Small delay to ensure file is fully written
        time.sleep(0.3)

        # Double-check file still exists
        if not image_path.exists():
            log_warning(f"Skipped {image_path.name} - removed during wait")
            continue

        try:
            file_size_kb = image_path.stat().st_size / 1024
        except FileNotFoundError:
            log_warning(f"Skipped {image_path.name} - file gone")
            continue

        log_info(f"Evaluating: {image_path.name} ({file_size_kb:.0f}KB)")

        score, reason = evaluate_image_with_claude(image_path)

        if score == -2:
            log_warning(f"  File removed by fetch script - skipping")
            continue

        if score < 0:
            log_warning(f"  Could not evaluate - keeping image")
            continue

        # Display result with color based on score
        if score >= 70:
            color = Colors.GREEN
            status = "EXCELLENT"
        elif score >= QUALITY_THRESHOLD:
            color = Colors.YELLOW
            status = "ACCEPTABLE"
        else:
            color = Colors.RED
            status = "REJECTED"

        print(f"  {color}Score: {score}/100 - {status}{Colors.RESET}")
        print(f"  {Colors.CYAN}Reason: {reason}{Colors.RESET}")

        if score < QUALITY_THRESHOLD:
            # Move to rejected folder instead of deleting
            REJECTED_DIR.mkdir(exist_ok=True)
            rejected_path = REJECTED_DIR / f"{score:02d}_{image_path.name}"

            try:
                if image_path.exists():
                    image_path.rename(rejected_path)
                    log_error(f"  DELETED → Moved to _rejected/")
                else:
                    log_warning(f"  Already removed by fetch script")
            except FileNotFoundError:
                log_warning(f"  Already removed by fetch script")
            except Exception as e:
                log_error(f"  Failed to move: {e}")
        else:
            log_success(f"  KEPT")

        print()

def show_stats():
    """Display current statistics."""
    total_images = len(get_image_files())
    rejected_count = len(list(REJECTED_DIR.glob("*"))) if REJECTED_DIR.exists() else 0

    print(f"\n{Colors.CYAN}{'─'*40}{Colors.RESET}")
    print(f"{Colors.BOLD}Stats:{Colors.RESET} {total_images} kept | {rejected_count} rejected | {len(processed_files)} processed")
    print(f"{Colors.CYAN}{'─'*40}{Colors.RESET}\n")

# =============================================================================
# MAIN
# =============================================================================
def main():
    # Setup signal handler for clean exit
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log_header("AUTO IMAGE QUALITY MONITOR")

    log_info(f"Watching: {WATCH_DIR}")
    log_info(f"Quality threshold: {QUALITY_THRESHOLD}/100")
    log_info(f"Check interval: {CHECK_INTERVAL}s")
    print()

    # Start caffeinate
    start_caffeinate()

    # Create rejected directory
    REJECTED_DIR.mkdir(exist_ok=True)

    # Initial scan of existing files (mark as processed to skip them)
    existing = set(get_image_files())
    log_info(f"Found {len(existing)} existing images (skipping initial scan)")
    processed_files.update(existing)

    print()
    log_success("Monitoring started - waiting for new images...")
    log_info("Press Ctrl+C to stop")
    print()

    # Main monitoring loop
    check_count = 0
    while True:
        try:
            process_new_images()
            time.sleep(CHECK_INTERVAL)

            check_count += 1
            if check_count % 30 == 0:  # Show stats every minute
                show_stats()

        except KeyboardInterrupt:
            break
        except FileNotFoundError:
            # Race condition with fetch script - just continue
            pass
        except Exception as e:
            log_error(f"Error in main loop: {e}")
            time.sleep(2)

    stop_caffeinate()
    log_info("Shutdown complete")

if __name__ == "__main__":
    main()
