#!/usr/bin/env bash
#
# Megaphone restore script
# Pulls backup from cloud or git and places files in the right locations.
#
# Usage: ./scripts/restore.sh [source]
#   source: gdrive (default), dropbox, git

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$REPO_DIR/backups"
DB_FILE="$REPO_DIR/megaphone.db"
CONFIG_FILE="$REPO_DIR/config.yaml"
RCLONE_DEST="megaphone-backup"
SOURCE="${1:-gdrive}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

mkdir -p "$BACKUP_DIR"

# --- Safety check ---
if [ -f "$DB_FILE" ]; then
    echo "WARNING: $DB_FILE already exists."
    read -rp "Overwrite? (y/N) " confirm
    if [[ "$confirm" != [yY] ]]; then
        echo "Aborted."
        exit 1
    fi
fi

# --- Pull backup files ---
case "$SOURCE" in
    gdrive)
        log "Pulling from Google Drive..."
        rclone copy "gdrive:$RCLONE_DEST" "$BACKUP_DIR" --quiet
        ;;
    dropbox)
        log "Pulling from Dropbox..."
        rclone copy "dropbox:$RCLONE_DEST" "$BACKUP_DIR" --quiet
        ;;
    git)
        log "Using backup from git (backups/ directory)..."
        if [ ! -f "$BACKUP_DIR/megaphone.sql" ] && [ ! -f "$BACKUP_DIR/megaphone.db" ]; then
            echo "No backup found in $BACKUP_DIR. Try gdrive or dropbox instead."
            exit 1
        fi
        ;;
    *)
        echo "Unknown source: $SOURCE (use gdrive, dropbox, or git)"
        exit 1
        ;;
esac

# --- Restore database ---
if [ -f "$BACKUP_DIR/megaphone.db" ]; then
    log "Restoring database from binary backup..."
    cp "$BACKUP_DIR/megaphone.db" "$DB_FILE"
    log "Database restored."
elif [ -f "$BACKUP_DIR/megaphone.sql" ]; then
    log "Restoring database from SQL dump..."
    sqlite3 "$DB_FILE" < "$BACKUP_DIR/megaphone.sql"
    log "Database restored from SQL dump."
else
    log "No database backup found."
fi

# --- Restore config ---
if [ -f "$BACKUP_DIR/config.yaml" ]; then
    cp "$BACKUP_DIR/config.yaml" "$CONFIG_FILE"
    log "Config restored."
fi

log "Restore complete."
echo ""
echo "Next steps:"
echo "  1. Verify: sqlite3 megaphone.db '.tables'"
echo "  2. Set up env vars (ANTHROPIC_API_KEY, OPENAI_API_KEY)"
echo "  3. Install Python dependencies"
