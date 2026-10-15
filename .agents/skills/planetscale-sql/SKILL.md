---
name: planetscale-sql
description: Production database schema hygiene, migration branching, and query performance fundamentals for MySQL and relational databases.
---

# PlanetScale SQL & Database Engineering Hygiene

Guidelines for designing resilient relational schemas, managing zero-downtime migrations, and preventing query performance collapse at scale.

## 1. Branching & Migration Discipline
- **Never Modify Production Directly:** Always author migrations on isolated development branches.
- **Online Schema Changes (DDL):** Ensure all table mutations (`ALTER TABLE`, `ADD COLUMN`) are non-blocking and safe under active production load.
- **Backwards-Compatible Evolutions:** Follow the Expand/Contract pattern:
  1. Add new column/table.
  2. Deploy application code that writes to both old and new.
  3. Backfill existing records.
  4. Deploy application code that reads only from new.
  5. Drop old column/table.

## 2. Query Performance & Index Fundamentals
- **Prevent Full Table Scans:** Every `WHERE`, `JOIN`, and `ORDER BY` clause on high-cardinality tables must be backed by a composite index matching query column order (Equality -> Range).
- **Detect and Eliminate N+1 Queries:** Never execute relational queries inside a loop in application code. Use batch fetching (`WHERE id IN (...)`) or structured `JOIN`s.
- **Covering Indexes:** Design indexes that include all columns needed by the query so the database engine can satisfy the request entirely from the B-tree index without hitting the primary clustered index.

## 3. ID Strategy & Pagination
- **Keyset / Cursor Pagination:** Never use `OFFSET 50000 LIMIT 20` on large tables (which requires scanning and discarding 50,000 rows). Use keyset pagination: `WHERE id > :last_seen_id ORDER BY id ASC LIMIT 20`.
- **Primary Keys:** Use sorted unique identifiers (UUIDv7 or BigInt AUTO_INCREMENT) to preserve B-tree spatial locality and avoid page splits.
