#!/bin/bash

# Default parameters (can be overridden)
LOCAL_PATH="${1:-/Volumes/data_2/onedrive}"
REMOTE_PATH="${2:-onedrive:}"
EXCLUDE_FILE="${3:-$HOME/.config/rclone/bisync-filters.txt}"
LOG_DIR="${4:-$HOME/Library/Logs/rclone-onedrive}"
MAX_LOGS=20

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Generate log filename with timestamp
LOG_FILE="$LOG_DIR/sync-$(date '+%Y%m%d-%H%M%S').log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

echo "=== Sync started at $DATE ===" > "$LOG_FILE"
echo "Local: $LOCAL_PATH" >> "$LOG_FILE"
echo "Remote: $REMOTE_PATH" >> "$LOG_FILE"
echo "Exclude file: $EXCLUDE_FILE" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Run bisync
/opt/homebrew/bin/rclone bisync "$LOCAL_PATH" "$REMOTE_PATH" \
  --filter-from="$EXCLUDE_FILE" \
  --log-file="$LOG_FILE" \
  --resilient \
  --recover \
  --check-access \
  --metadata \
  --update \
  --ignore-errors \
  --retries 3 \
  --retries-sleep 10s \
  --tpslimit 4 \
  --transfers 4 \
  -vv

SYNC_EXIT_CODE=$?

echo "" >> "$LOG_FILE"
echo "=== Sync completed at $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG_FILE"
echo "Exit code: $SYNC_EXIT_CODE" >> "$LOG_FILE"

# Log rotation: keep only the last MAX_LOGS log files
cd "$LOG_DIR"
ls -t sync-*.log | tail -n +$((MAX_LOGS + 1)) | xargs -r rm --

exit $SYNC_EXIT_CODE