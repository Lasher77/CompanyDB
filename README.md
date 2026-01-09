# CompanyDB

Import und Suche von NorthData Firmendaten (JSONL-Dumps).

## Architektur

- **PostgreSQL**: Source of Truth für Companies + Persons
- **OpenSearch**: Volltextsuche + Facetten/Filter
- **FastAPI**: Backend API
- **React/Vite**: Frontend (kommt in Slice 2)

## Schnellstart

### 1. Services starten

```bash
docker compose up -d
```

Services:
- PostgreSQL: `localhost:5432`
- OpenSearch: `localhost:9200`
- OpenSearch Dashboards: `localhost:5601`

### 2. Backend starten

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# .env anlegen (optional, defaults funktionieren mit docker-compose)
cp ../.env.example .env

# Server starten
uvicorn app.main:app --reload
```

API läuft auf: `http://localhost:8000`
Swagger Docs: `http://localhost:8000/docs`

### 3. Import starten

```bash
# Verfügbare Dateien anzeigen
curl http://localhost:8000/imports/files

# Import starten
curl -X POST http://localhost:8000/imports \
  -H "Content-Type: application/json" \
  -d '{"filename": "export2025Q3-DE-XL-de-X.jsonl"}'

# Status prüfen
curl http://localhost:8000/imports/{job-id}
```

## API Endpoints

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/health` | GET | Health-Check (Postgres + OpenSearch) |
| `/imports/files` | GET | Liste verfügbarer JSONL-Dateien in `data/` |
| `/imports` | POST | Import-Job starten (`{"filename": "..."}`) |
| `/imports` | GET | Alle Import-Jobs auflisten |
| `/imports/{id}` | GET | Status eines Import-Jobs |

## Datenstruktur

JSONL-Dateien in `data/` ablegen. Wichtige Felder:

- `id`: Unique Company ID
- `rawName`, `name.name`, `name.legalForm`: Firmenname
- `status`, `terminated`: Firmenstatus
- `address.*`: Adressdaten
- `register.uniqueKey`, `register.id`: Handelsregister
- `segmentCodes.wz`, `segmentCodes.nace`: Branchencodes
- `relatedPersons.items[]`: Verknüpfte Personen mit Rollen

## Projektstruktur

```
CompanyDB/
├── data/                    # JSONL-Dumps hier ablegen
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI App
│   │   ├── config.py        # Settings
│   │   ├── database.py      # DB Connection
│   │   ├── models.py        # SQLAlchemy Models
│   │   ├── schemas.py       # Pydantic Schemas
│   │   ├── opensearch_client.py
│   │   └── routers/
│   │       ├── health.py
│   │       └── imports.py
│   └── requirements.txt
├── docker-compose.yml
└── .env.example
```
