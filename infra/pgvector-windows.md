# pgvector on PostgreSQL 18 (Windows) — install notes

Verified 2026-07-03. pgvector is NOT in StackBuilder and has no official Windows
binaries. Two options for the local PG18 install:

## Option 1 — prebuilt unofficial binaries (fastest, fine for dev)

[andreiramani/pgvector_pgsql_windows](https://github.com/andreiramani/pgvector_pgsql_windows)
ships pgvector **v0.8.3 for PostgreSQL 18** (2026-06-25 release).

1. Download the PG18 zip from the releases page; verify checksum.
2. Copy `vector.dll` → `C:\Program Files\PostgreSQL\18\lib`
3. Copy `vector.control` + `vector--*.sql` → `C:\Program Files\PostgreSQL\18\share\extension`
4. In the `meetgraph_cognee` database: `CREATE EXTENSION vector;`

## Option 2 — compile from source (official path, v0.8.4)

Requires Visual Studio C++ tools. In an **x64 Native Tools Command Prompt (admin)**:

```bat
set PGROOT=C:\Program Files\PostgreSQL\18
git clone --branch v0.8.4 https://github.com/pgvector/pgvector.git
cd pgvector
nmake /F Makefile.win
nmake /F Makefile.win install
```

Then `CREATE EXTENSION vector;` as above. Deploy (compose) needs neither — the
`pgvector/pgvector` image ships with it.
