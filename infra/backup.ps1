# meetgraph backups (P5): pg_dump both DBs + recordings dir (plan §6 P5).
# Schedule via Task Scheduler (Windows) or cron (VPS: use backup.sh equivalent).
param(
    [string]$OutDir = ".\backups"
)
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
New-Item -ItemType Directory -Force $OutDir | Out-Null
pg_dump -U meetgraph -d meetgraph -F c -f "$OutDir\meetgraph-$stamp.dump"
pg_dump -U meetgraph -d meetgraph_cognee -F c -f "$OutDir\meetgraph_cognee-$stamp.dump"
Compress-Archive -Path ".\recordings" -DestinationPath "$OutDir\recordings-$stamp.zip" -CompressionLevel Fastest
# Retention: keep 14 most recent of each
Get-ChildItem $OutDir | Sort-Object LastWriteTime -Descending | Select-Object -Skip 42 | Remove-Item -Force
