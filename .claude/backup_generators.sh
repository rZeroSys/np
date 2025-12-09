#!/bin/bash
# Backup script for generator Python files
# Called by Claude Code hooks before editing
# Receives JSON input via stdin

GENERATORS_DIR="/Users/forrestmiller/Desktop/nationwide-prospector/src/generators"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Read file path from JSON stdin
FILE_PATH=$(jq -r '.tool_input.file_path' 2>/dev/null)

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Check if it's one of the generator files we want to backup
case "$FILE_PATH" in
    */src/generators/homepage.py|*/src/generators/html_generator.py)
        BACKUP_DIR="$GENERATORS_DIR/backup_homepage_code"
        FILENAME=$(basename "$FILE_PATH")
        if [ -f "$FILE_PATH" ]; then
            cp "$FILE_PATH" "$BACKUP_DIR/${FILENAME%.py}_${TIMESTAMP}.py" 2>/dev/null
        fi
        ;;
    */src/generators/building_report.py)
        BACKUP_DIR="$GENERATORS_DIR/backup_building_report_code"
        FILENAME=$(basename "$FILE_PATH")
        if [ -f "$FILE_PATH" ]; then
            cp "$FILE_PATH" "$BACKUP_DIR/${FILENAME%.py}_${TIMESTAMP}.py" 2>/dev/null
        fi
        ;;
esac

exit 0
