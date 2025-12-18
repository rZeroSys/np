#!/bin/bash
# Regenerate homepage only (no building reports)
cd "$(dirname "$0")"
python3 -m src.generators.html_generator
