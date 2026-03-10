# Backup & Restore

## What's backed up

- `megaphone.db` — SQLite database (all content, posts, comments, scores)
- `config.yaml` — user configuration

## Where backups go

| Destination | What | Format |
|---|---|---|
| Git (GitHub) | SQL dump + config | Text (diffable) |
| Google Drive | DB binary + SQL dump + config | Files in `megaphone-backup/` |
| Dropbox | DB binary + SQL dump + config | Files in `megaphone-backup/` |

The SQL dump is committed to git so you have version history and can restore even without rclone. The binary DB goes to cloud storage only (not git) to avoid bloating the repo.

## Running a backup

```bash
./scripts/backup.sh
```

This is safe to run anytime — it's idempotent. If nothing changed, no git commit is created.

## Cron setup

Run every 4 hours:

```bash
crontab -e
# Add:
0 */4 * * * cd /home/matt/dev/megaphone && ./scripts/backup.sh >> /tmp/megaphone-backup.log 2>&1
```

Check logs: `tail -f /tmp/megaphone-backup.log`

## Restoring on a new machine

```bash
git clone https://github.com/mattyj718/megaphone.git
cd megaphone

# From Google Drive (default):
./scripts/restore.sh gdrive

# Or from Dropbox:
./scripts/restore.sh dropbox

# Or from git (SQL dump only, always available):
./scripts/restore.sh git
```

The script will warn if a database already exists and ask before overwriting.

## Testing

After restore, verify:

```bash
sqlite3 megaphone.db '.tables'
sqlite3 megaphone.db 'SELECT count(*) FROM content_items;'
```
