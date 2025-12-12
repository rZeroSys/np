#!/bin/bash
# Regenerate Homepage and Building Reports, then Push to GitHub
# Usage: ./scripts/regenerate_and_push.sh [commit_message]
#
# This script:
# 1. Regenerates the homepage (index.html)
# 2. Regenerates all building reports (~23,881 files)
# 3. Commits and pushes to GitHub
#
# Run from the nationwide-prospector directory:
#   ./scripts/regenerate_and_push.sh "Your commit message here"

set -e  # Exit on error

# Get the directory where this script is located, then go up to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "======================================"
echo "Nationwide Prospector - Regenerate & Push"
echo "======================================"

# Default commit message if none provided
COMMIT_MSG="${1:-Regenerate homepage and building reports}"

echo ""
echo "[1/4] Regenerating homepage..."
python3 -m src.generators.html_generator
echo "Homepage regenerated."

echo ""
echo "[2/4] Regenerating building reports (this takes a few minutes)..."
python3 -m src.generators.building_report
echo "Building reports regenerated."

echo ""
echo "[3/4] Staging changes..."
git add -A
git status --short | head -20
echo "..."

echo ""
echo "[4/4] Committing and pushing to GitHub..."
git commit -m "$COMMIT_MSG

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

git push

echo ""
echo "======================================"
echo "Done! All changes pushed to GitHub."
echo "======================================"
