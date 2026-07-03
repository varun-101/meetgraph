#!/usr/bin/env bash
# meetgraph backups — VPS/cron variant of backup.ps1 (P5).
# Cron: 0 3 * * * /opt/meetgraph/infra/backup.sh /var/backups/meetgraph
set -euo pipefail

OUT_DIR="${1:-./backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT_DIR"

pg_dump -U meetgraph -d meetgraph -F c -f "$OUT_DIR/meetgraph-$STAMP.dump"
pg_dump -U meetgraph -d meetgraph_cognee -F c -f "$OUT_DIR/meetgraph_cognee-$STAMP.dump"
tar -czf "$OUT_DIR/recordings-$STAMP.tar.gz" recordings/ 2>/dev/null || true

# Retention: keep the 14 most recent of each artifact type
ls -t "$OUT_DIR"/meetgraph-*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f
ls -t "$OUT_DIR"/meetgraph_cognee-*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f
ls -t "$OUT_DIR"/recordings-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
echo "backup complete: $OUT_DIR ($STAMP)"
