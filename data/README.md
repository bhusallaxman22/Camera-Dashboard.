# Application data

This directory is bind-mounted into the containers as `/data` (and `data/postgres`
into the Postgres container). It only ever contains **generated** state:

| Path          | Contents                                              |
| ------------- | ----------------------------------------------------- |
| `thumbnails/` | WebP thumbnails (256 / 512 / 1024 px)                 |
| `previews/`   | JPEG previews (2560 px long edge)                     |
| `cache/`      | Scratch space (embedded RAW previews, temp files)     |
| `postgres/`   | PostgreSQL 16 data directory                          |
| `redis/`      | Redis append-only file                                |

Original photos are never written here and nothing here is required to recover
originals. Thumbnails/previews can be rebuilt with
`python -m app.cli rebuild-thumbnails`.
