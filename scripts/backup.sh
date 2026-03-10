#!/usr/bin/env bash
#
# Megaphone backup script
# Safe to run on cron. Idempotent. Ships to git + 2 cloud destinations.
#
# Usage: ./scripts/backup.sh
# Cron:  0 */4 * * * cd /home/matt/dev/megaphone && ./scripts/backup.sh >> /tmp/megaphone-backup.log 2>&1

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$REPO_DIR/backups"
DB_FILE="$REPO_DIR/megaphone.db"
CONFIG_FILE="$REPO_DIR/config.yaml"
RCLONE_DEST="megaphone-backup"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

mkdir -p "$BACKUP_DIR"

# --- 1. SQLite safe backup ---
if [ -f "$DB_FILE" ]; then
    log "Backing up SQLite database..."
    sqlite3 "$DB_FILE" ".backup '$BACKUP_DIR/megaphone.db'"

    # SQL text dump for git (diffable history)
    sqlite3 "$DB_FILE" ".dump" > "$BACKUP_DIR/megaphone.sql"
    log "Database backup complete."
else
    log "No database found at $DB_FILE — skipping DB backup."
fi

# --- 2. Copy config files ---
if [ -f "$CONFIG_FILE" ]; then
    cp "$CONFIG_FILE" "$BACKUP_DIR/config.yaml"
    log "Config copied."
fi

# --- 3. Git commit (SQL dump + config only — not the binary DB) ---
cd "$REPO_DIR"
[ -f "$BACKUP_DIR/megaphone.sql" ] && git add backups/megaphone.sql
[ -f "$BACKUP_DIR/config.yaml" ] && git add backups/config.yaml

if ! git diff --cached --quiet 2>/dev/null; then
    git commit -m "backup: data snapshot $TIMESTAMP"
    log "Git commit created."

    # Push if remote is configured and reachable
    if git remote get-url origin &>/dev/null; then
        git push origin HEAD --quiet 2>/dev/null && log "Pushed to GitHub." || log "Push failed (offline?). Will push next time."
    fi
else
    log "No changes to commit."
fi

# --- 4. rclone to Google Drive ---
if command -v rclone &>/dev/null; then
    rclone copy "$BACKUP_DIR" "gdrive:$RCLONE_DEST" --quiet 2>/dev/null \
        && log "Synced to Google Drive." \
        || log "Google Drive sync failed."

    rclone copy "$BACKUP_DIR" "dropbox:$RCLONE_DEST" --quiet 2>/dev/null \
        && log "Synced to Dropbox." \
        || log "Dropbox sync failed."
else
    log "rclone not found — skipping cloud sync."
fi

log "Backup complete."
