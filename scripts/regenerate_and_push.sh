#!/bin/bash
# Full Data Update, Regenerate, and Push to GitHub
# Usage: ./scripts/regenerate_and_push.sh [commit_message]
#
# This script:
# 1. Runs orchestration (11 data update scripts including NYC handling)
# 2. Regenerates the homepage (index.html)
# 3. Regenerates all building reports (~23,881 files)
# 4. Commits and pushes to GitHub
#
# Run from the nationwide-prospector directory:
#   ./scripts/regenerate_and_push.sh "Your commit message here"

set -e  # Exit on error

# Get the directory where this script is located, then go up to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "======================================"
echo "Nationwide Prospector - Full Update & Push"
echo "======================================"

# Default commit message if none provided
COMMIT_MSG="${1:-Full data update, regenerate homepage and building reports}"

echo ""
echo "[1/5] Running data orchestration (11 scripts including NYC handling)..."
python3 "$SCRIPT_DIR/populate_master/orchestrate.py"
echo "Data orchestration complete."

echo ""
echo "[2/5] Regenerating homepage..."
python3 -m src.generators.html_generator
echo "Homepage regenerated."

echo ""
echo "[3/5] Regenerating building reports (this takes a few minutes)..."
python3 -m src.generators.building_report
echo "Building reports regenerated."

echo ""
echo "[4/5] Staging changes..."
git add -A
git status --short | head -20
echo "..."

echo ""
echo "[5/5] Committing and pushing to GitHub..."
git commit -m "$COMMIT_MSG

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

git push

echo ""
echo "======================================"
echo "Done! All changes pushed to GitHub."
echo "======================================"
