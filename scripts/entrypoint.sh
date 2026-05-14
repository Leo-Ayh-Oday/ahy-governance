#!/bin/bash
# Entrypoint: restore SQLite backup if available, then start the app.
# /app/data is tmpfs (volatile). /app/data_backup is persistent (host volume).

BACKUP_DIR="/app/data_backup"
DATA_DIR="/app/data"

mkdir -p "$DATA_DIR"

# Restore from backup if tmpfs is empty but backup exists
if [ ! -f "$DATA_DIR/ahy_governance.db" ] && [ -f "$BACKUP_DIR/ahy_governance.db" ]; then
    echo "[entrypoint] Restoring database from backup..."
    cp "$BACKUP_DIR/ahy_governance.db" "$DATA_DIR/ahy_governance.db" 2>/dev/null || true
    cp "$BACKUP_DIR/auth.db" "$DATA_DIR/auth.db" 2>/dev/null || true
    echo "[entrypoint] Restore complete."
fi

# Start background backup loop (every 60s, copy db to persistent volume)
(
    while true; do
        sleep 60
        for db in "$DATA_DIR"/*.db; do
            [ -f "$db" ] && cp "$db" "$BACKUP_DIR/$(basename "$db")" 2>/dev/null
        done
        # Also copy WAL/SHM for safety
        for f in "$DATA_DIR"/*.db-wal "$DATA_DIR"/*.db-shm; do
            [ -f "$f" ] && cp "$f" "$BACKUP_DIR/$(basename "$f")" 2>/dev/null
        done
    done
) &

exec python -m uvicorn web.server:app --host 0.0.0.0 --port 8080
