# Performance-Optimierung für CompanyDB Datenimport

## Übersicht

Die optimierte Import-Funktionalität wurde speziell für große Datenmengen (780.000+ Datensätze, 8GB+) entwickelt und bietet erhebliche Performance-Verbesserungen gegenüber der ursprünglichen Implementation.

## Implementierte Optimierungen

### 1. **Bulk-Insert statt einzelner Inserts**
- Verwendet SQLAlchemy's `bulk_insert_mappings()` für massive Performance-Gewinne
- Batch-Größe von 5.000 Datensätzen (statt 1.000)
- Reduziert Datenbankroundtrips dramatisch

### 2. **Eliminierung von N+1 Query-Problemen**
- Alle existierenden Companies und Persons werden einmalig in den Speicher geladen
- Keine einzelnen DB-Lookups während des Imports
- Relationship-Erstellung erfolgt in Bulk

### 3. **Einmaliges Lesen der Datei**
- Die JSONL-Datei wird nur noch einmal gelesen (statt zweimal)
- Alle Records werden im Speicher gehalten für die Relationship-Erstellung
- Spart 50% der I/O-Zeit

### 4. **Dynamisches Index-Management**
- Non-essential Indizes werden während des Imports deaktiviert
- Nach dem Import werden die Indizes neu erstellt
- Beschleunigt Insert-Operationen erheblich

### 5. **Optimierte OpenSearch-Indexierung**
- Größere Batch-Größe (5.000 statt 1.000)
- Personen-Indexierung nutzt einen einzigen JOIN statt N+1 Queries
- Chunked Processing für bessere Speichereffizienz

### 6. **Optimierter ReIndex-Prozess**
- Streaming-Queries statt Laden aller Daten in den Speicher
- Chunked Processing mit größeren Batches
- Vermeidung von N+1 Queries bei Relationship-Loading

## Erwartete Performance-Verbesserungen

Für 780.000 Datensätze (8GB):
- **Vorher**: Mehrere Stunden
- **Nachher**: 10-30 Minuten (abhängig von Hardware und OpenSearch-Performance)

**Geschätzter Speedup**: 5-10x schneller

## Weitere Optimierungsmöglichkeiten

### PostgreSQL-Konfiguration

Für optimale Performance auf einem Apple M1 Pro mit 16GB RAM empfehlen wir folgende PostgreSQL-Einstellungen:

```bash
# In postgresql.conf oder via ALTER SYSTEM

# Arbeitsspeicher-Einstellungen
shared_buffers = 2GB                # 25% des verfügbaren RAMs
work_mem = 256MB                    # Für Sortier-Operationen
maintenance_work_mem = 512MB        # Für Index-Erstellung
effective_cache_size = 6GB          # 50% des verfügbaren RAMs

# Checkpoint-Einstellungen (für Bulk-Inserts)
checkpoint_timeout = 30min
max_wal_size = 4GB
min_wal_size = 1GB

# Parallel-Queries
max_parallel_workers_per_gather = 4
max_parallel_workers = 8
max_worker_processes = 8

# I/O-Optimierungen
random_page_cost = 1.1              # Für SSD (M1 Pro hat schnellen SSD)
effective_io_concurrency = 200      # Für SSD

# Logging (während Import deaktivieren für bessere Performance)
# fsync = off                       # NUR FÜR IMPORT! Danach wieder einschalten!
# synchronous_commit = off          # NUR FÜR IMPORT! Danach wieder einschalten!
```

### Temporäre Import-Optimierungen

Vor einem großen Import können Sie PostgreSQL temporär für maximale Performance konfigurieren:

```sql
-- Temporär während Import
SET maintenance_work_mem = '1GB';
SET work_mem = '512MB';
SET synchronous_commit = OFF;
SET wal_level = minimal;
SET max_wal_senders = 0;
SET archive_mode = OFF;

-- NACH dem Import wieder zurücksetzen!
```

**WICHTIG**: Diese Einstellungen nur während des Imports verwenden und danach zurücksetzen!

### OpenSearch-Optimierung

```yaml
# In opensearch.yml

# Speicher-Einstellungen (50% des verfügbaren RAMs)
-Xms4g
-Xmx4g

# Bulk-Indexing-Optimierungen
index.refresh_interval: 30s         # Während Import
index.number_of_replicas: 0         # Während Import (danach auf 1 setzen)

# Thread-Pool-Einstellungen
thread_pool.write.queue_size: 1000
thread_pool.search.queue_size: 1000
```

### Environment Variables (.env)

```bash
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://companydb:companydb@localhost:5432/companydb
DATABASE_URL_SYNC=postgresql://companydb:companydb@localhost:5432/companydb

# Import-Einstellungen
IMPORT_BATCH_SIZE=5000              # Kann auf 10000 erhöht werden bei viel RAM

# PostgreSQL Performance
PG_WORK_MEM=256MB
PG_MAINTENANCE_WORK_MEM=512MB
PG_SHARED_BUFFERS=2GB

# OpenSearch
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_ENABLED=true
```

## Monitoring während des Imports

### Logs beobachten
```bash
# Backend-Logs
tail -f backend/logs/app.log

# PostgreSQL-Logs
tail -f /usr/local/var/log/postgresql@14.log

# OpenSearch-Logs (falls verwendet)
tail -f /usr/local/var/log/opensearch/opensearch.log
```

### Ressourcen-Monitoring
```bash
# CPU und Memory
htop

# Disk I/O
iostat -x 5

# PostgreSQL-Aktivität
psql -U companydb -c "SELECT * FROM pg_stat_activity WHERE state = 'active';"
```

## Benchmark-Tipps

### Vor dem Benchmark
1. PostgreSQL neu starten um Cache zu leeren
2. OpenSearch neu starten (falls verwendet)
3. Alte Daten löschen für sauberen Test

### Benchmark durchführen
```bash
# Zeit messen
time curl -X POST http://localhost:8000/api/imports \
  -H "Content-Type: application/json" \
  -d '{"filename": "your-file.jsonl"}'

# Import-Status überwachen
watch -n 5 'curl http://localhost:8000/api/imports/<job-id>'
```

## Troubleshooting

### "Out of Memory" Fehler

**Problem**: Import schlägt mit OOM fehl

**Lösung**:
- Reduzieren Sie `IMPORT_BATCH_SIZE` auf 2000
- Erhöhen Sie Docker/Postgres Memory Limit
- Aktivieren Sie Disk-Swap

### Langsame Index-Erstellung

**Problem**: Index-Recreate dauert sehr lange

**Lösung**:
- Erhöhen Sie `maintenance_work_mem` in PostgreSQL
- Nutzen Sie `CONCURRENTLY` für Index-Erstellung (in Production)

### OpenSearch Timeout

**Problem**: Bulk-Indexing schlägt fehl

**Lösung**:
- Erhöhen Sie OpenSearch Timeout-Einstellungen
- Reduzieren Sie Batch-Größe für OpenSearch (im Code: 5000 → 2000)
- Deaktivieren Sie Replicas während Import

## Weitere Optimierungen für die Zukunft

1. **Parallel Processing**: Mehrere Worker-Threads für Import
2. **COPY Command**: PostgreSQL COPY für noch schnellere Bulk-Inserts
3. **Partitionierung**: Table-Partitioning für sehr große Datensätze
4. **Async OpenSearch**: Non-blocking OpenSearch-Indexierung
5. **Incremental Updates**: Nur geänderte Datensätze importieren

## Support

Bei Performance-Problemen bitte folgende Informationen bereitstellen:
- Hardware-Specs (CPU, RAM, Disk-Typ)
- PostgreSQL-Version und -Konfiguration
- OpenSearch-Version und -Konfiguration
- Datei-Größe und Anzahl der Datensätze
- Import-Logs mit Zeitstempeln
