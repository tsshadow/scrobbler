# Analyzer and Scrobbler Data Flow

This document summarizes how the analyzer and scrobbler modules interact with the data layer. The services now operate on dedicated schemas (`medialibrary` and `listens`) that isolate ownership while keeping cross-links through foreign keys.

## Analyzer responsibilities

- The analyzer scans configured filesystem paths, walking through directories, filtering supported audio extensions, and recording file metadata. Each discovered media file is registered through the `LibraryService`, which persists entries in the library tables inside the `medialibrary` schema (`media_files`, `tracks`, `artists`, `genres`, etc.).【F:analyzer/ingestion/filesystem.py†L1-L46】【F:analyzer/services/library_service.py†L14-L93】【F:docs/database-design.md†L7-L119】
- Analyzer jobs enrich canonical metadata (artists, albums, tracks, genres) and update analyzer dashboards that query the normalized library content (e.g., `/api/v1/analyzer/summary`). These dashboards only surface rows that have associated track records in `medialibrary` tables.【F:analyzer/db/repo.py†L500-L610】【F:docs/database-design.md†L121-L150】【F:frontend/src/routes/Analyzer.svelte†L1-L67】

## Scrobbler responsibilities

- The scrobbler ingests ListenBrainz (or similar) payloads. During ingestion it normalizes artist, album, genre, and track metadata, upserts the canonical entities in `medialibrary`, and records listens inside the `listens` schema that reference the created track IDs.【F:scrobbler/app/services/ingest_service.py†L1-L81】【F:scrobbler/app/db/maria.py†L206-L321】【F:docs/database-design.md†L133-L150】
- Scrobbler UI pages focus on listening history, pulling listen records and aggregations from the tables scoped to the `listens` schema (`listens`, `listen_artists`, `listen_genres`, etc.).【F:frontend/src/routes/Scrobbler.svelte†L1-L105】【F:docs/database-design.md†L133-L150】

## Combined behavior

- Running only the analyzer populates library metadata in `medialibrary` but does not create listen events because no ingestion job is performed.【F:analyzer/services/library_service.py†L14-L93】【F:docs/database-design.md†L121-L150】
- Running only the scrobbler still creates track rows (alongside listens) because ingestion upserts canonical track data into `medialibrary`, so analyzer dashboards can see those tracks even without a filesystem scan.【F:scrobbler/app/services/ingest_service.py†L39-L81】【F:scrobbler/app/db/maria.py†L206-L321】【F:docs/database-design.md†L133-L150】
- When both services run, listens and library metadata share track identifiers, enabling enriched listening history that links to canonical metadata throughout the UI. Maintaining the `listens.listens.track_id → medialibrary.tracks.id` relationship preserves this linkage during and after the migration.【F:scrobbler/app/services/ingest_service.py†L39-L81】【F:analyzer/db/repo.py†L500-L610】【F:docs/database-design.md†L133-L150】
