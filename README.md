# CompanyDB

Import und Suche von NorthData Firmendaten (JSONL-Dumps).

## Architektur

- **PostgreSQL 14+**: Source of Truth für Companies + Persons
- **OpenSearch 2.x**: Volltextsuche + Facetten/Filter (optional)
- **FastAPI**: Backend API
- **React/Vite/TypeScript**: Frontend mit Tailwind CSS

---

## Aktueller Stand

### Slice 1: Backend & Import-Infrastruktur ✅
- PostgreSQL-Datenbank mit Companies, Persons, CompanyPerson-Relationen
- OpenSearch-Integration (optional, konfigurierbar)
- Batch-weiser JSONL-Import (1000 Records/Batch)
- Import-Jobs mit Status-Tracking

### Slice 2: Frontend ✅
- Apple-Style UI mit React, Vite, TypeScript
- Tailwind CSS + shadcn/ui Komponenten
- Framer Motion Animationen
- Seiten:
  - **Suche**: Firmen-/Personensuche mit Filtern
  - **Firmen-Detail**: Übersicht, verknüpfte Personen, Events, Raw JSON
  - **Personen-Detail**: Übersicht, verknüpfte Firmen, Raw JSON
  - **Import**: Dateiauswahl, Bestätigung, Fortschrittsanzeige

---

## Schnellstart

### 1. Datenbank einrichten

```bash
# PostgreSQL Datenbank erstellen
sudo -u postgres psql <<EOF
CREATE USER companydb WITH PASSWORD 'companydb';
CREATE DATABASE companydb OWNER companydb;
GRANT ALL PRIVILEGES ON DATABASE companydb TO companydb;
EOF
```

### 2. Backend starten

```bash
cd backend

# Virtual Environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Dependencies
pip install -r requirements.txt

# Server starten
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend starten

```bash
cd frontend

# Dependencies
npm install

# Dev-Server starten
npm run dev
```

### 4. Öffnen

- **Frontend**: http://localhost:5173
- **API Docs**: http://localhost:8000/docs

---

## Installation (Details)

### Option A: Mit Docker (empfohlen)

```bash
docker compose up -d
```

Services:
- PostgreSQL: `localhost:5432`
- OpenSearch: `localhost:9200`
- OpenSearch Dashboards: `localhost:5601`

### Option B: Native Installation (ohne Docker)

#### 1. PostgreSQL installieren

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib

# PostgreSQL starten
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Datenbank und User anlegen
sudo -u postgres psql <<EOF
CREATE USER companydb WITH PASSWORD 'companydb';
CREATE DATABASE companydb OWNER companydb;
GRANT ALL PRIVILEGES ON DATABASE companydb TO companydb;
EOF
```

**macOS (Homebrew):**
```bash
brew install postgresql@16
brew services start postgresql@16

# Datenbank und User anlegen
psql postgres <<EOF
CREATE USER companydb WITH PASSWORD 'companydb';
CREATE DATABASE companydb OWNER companydb;
GRANT ALL PRIVILEGES ON DATABASE companydb TO companydb;
EOF
```

**Windows:**
1. Download: https://www.postgresql.org/download/windows/
2. Installer ausführen (Port 5432, Passwort merken)
3. pgAdmin oder psql öffnen und ausführen:
```sql
CREATE USER companydb WITH PASSWORD 'companydb';
CREATE DATABASE companydb OWNER companydb;
GRANT ALL PRIVILEGES ON DATABASE companydb TO companydb;
```

#### 2. OpenSearch installieren (optional)

OpenSearch ist optional. Ohne OpenSearch funktioniert die Suche über PostgreSQL.

**Ubuntu/Debian:**
```bash
# Java installieren (falls nicht vorhanden)
sudo apt install openjdk-17-jdk

# OpenSearch GPG Key und Repository
curl -o- https://artifacts.opensearch.org/publickeys/opensearch.pgp | sudo gpg --dearmor -o /usr/share/keyrings/opensearch-keyring
echo "deb [signed-by=/usr/share/keyrings/opensearch-keyring] https://artifacts.opensearch.org/releases/bundle/opensearch/2.x/apt stable main" | sudo tee /etc/apt/sources.list.d/opensearch-2.x.list

sudo apt update
sudo apt install opensearch

# Konfiguration für lokale Entwicklung (Security deaktivieren)
sudo tee -a /etc/opensearch/opensearch.yml <<EOF
discovery.type: single-node
plugins.security.disabled: true
EOF

# Starten
sudo systemctl start opensearch
sudo systemctl enable opensearch
```

**macOS (Homebrew):**
```bash
brew install opensearch

# Konfiguration anpassen (~/.opensearch/config/opensearch.yml)
echo "discovery.type: single-node" >> /opt/homebrew/etc/opensearch/opensearch.yml
echo "plugins.security.disabled: true" >> /opt/homebrew/etc/opensearch/opensearch.yml

brew services start opensearch
```

#### 3. Services prüfen

```bash
# PostgreSQL
pg_isready -h localhost -p 5432
# Erwartete Ausgabe: localhost:5432 - accepting connections

# OpenSearch (falls installiert)
curl http://localhost:9200
# Erwartete Ausgabe: JSON mit cluster_name, version etc.
```

---

## API Endpoints

### Health & Import

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/health` | GET | Health-Check (Postgres + OpenSearch) |
| `/imports/files` | GET | Liste verfügbarer JSONL-Dateien in `data/` |
| `/imports` | POST | Import-Job starten (`{"filename": "..."}`) |
| `/imports` | GET | Alle Import-Jobs auflisten |
| `/imports/{id}` | GET | Status eines Import-Jobs |

### Firmen (Companies)

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/companies` | GET | Firmensuche mit Filtern |
| `/companies/{id}` | GET | Firmen-Details mit verknüpften Personen |

**Suchparameter:**
- `q`: Suchbegriff (Name, Register-ID)
- `status`: Firmenstatus filtern
- `legal_form`: Rechtsform filtern
- `city`: Stadt filtern
- `limit`, `offset`: Paginierung

### Personen (Persons)

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/persons` | GET | Personensuche mit Filtern |
| `/persons/{id}` | GET | Personen-Details mit verknüpften Firmen |

**Suchparameter:**
- `q`: Suchbegriff (Name)
- `city`: Stadt filtern
- `limit`, `offset`: Paginierung

---

## Import durchführen

### Via Frontend (empfohlen)

1. Frontend öffnen: http://localhost:5173
2. Auf "Import" klicken
3. Datei auswählen und "Importieren" klicken
4. Fortschritt wird live angezeigt

### Via API

```bash
# 1. Health-Check (prüft DB + OpenSearch)
curl http://localhost:8000/health

# 2. Verfügbare JSONL-Dateien anzeigen
curl http://localhost:8000/imports/files

# 3. Import starten
curl -X POST http://localhost:8000/imports \
  -H "Content-Type: application/json" \
  -d '{"filename": "export2025Q3-DE-XL-de-X.jsonl"}'

# 4. Status prüfen (Job-ID aus Schritt 3)
curl http://localhost:8000/imports/{job-id}

# 5. Alle Jobs auflisten
curl http://localhost:8000/imports
```

---

## Konfiguration

### Backend (.env)

```bash
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://companydb:companydb@localhost:5432/companydb
DATABASE_URL_SYNC=postgresql://companydb:companydb@localhost:5432/companydb

# OpenSearch (optional)
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_ENABLED=true  # auf false setzen, wenn ohne OpenSearch

# Import
DATA_DIRECTORY=./data
IMPORT_BATCH_SIZE=1000
```

### Frontend (.env)

```bash
# API Base URL (optional, default: http://localhost:8000)
VITE_API_BASE_URL=http://localhost:8000
```

---

## Projektstruktur

```
CompanyDB/
├── data/                        # JSONL-Dumps hier ablegen
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI App
│   │   ├── config.py            # Settings
│   │   ├── database.py          # DB Connection
│   │   ├── models.py            # SQLAlchemy Models
│   │   ├── schemas.py           # Pydantic Schemas
│   │   ├── opensearch_client.py
│   │   └── routers/
│   │       ├── health.py        # Health-Check
│   │       ├── imports.py       # Import-Jobs
│   │       ├── companies.py     # Firmen-API
│   │       └── persons.py       # Personen-API
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Layout.tsx       # App-Layout mit Navigation
│   │   │   └── ui/              # shadcn/ui Komponenten
│   │   ├── pages/
│   │   │   ├── SearchPage.tsx   # Suche
│   │   │   ├── CompanyDetailPage.tsx
│   │   │   ├── PersonDetailPage.tsx
│   │   │   └── ImportPage.tsx   # Import-Workflow
│   │   ├── lib/
│   │   │   ├── api.ts           # API-Client
│   │   │   └── utils.ts         # Hilfsfunktionen
│   │   ├── types/index.ts       # TypeScript-Interfaces
│   │   └── App.tsx              # Router
│   ├── package.json
│   ├── tailwind.config.js
│   ├── vite.config.ts
│   └── tsconfig.json
├── docker-compose.yml           # Docker Setup
└── .env.example
```

---

## Datenstruktur (NorthData JSONL)

JSONL-Dateien in `data/` ablegen. Wichtige Felder:

- `id`: Unique Company ID
- `rawName`, `name.name`, `name.legalForm`: Firmenname
- `status`, `terminated`: Firmenstatus
- `address.*`: Adressdaten
- `register.uniqueKey`, `register.id`: Handelsregister
- `segmentCodes.wz`, `segmentCodes.nace`: Branchencodes
- `relatedPersons.items[]`: Verknüpfte Personen mit Rollen

---

## Tech Stack

### Backend
- **FastAPI**: Async Web Framework
- **SQLAlchemy 2.0**: Async ORM
- **PostgreSQL**: Relationale Datenbank
- **OpenSearch**: Volltextsuche (optional)
- **Pydantic**: Datenvalidierung

### Frontend
- **React 18**: UI Framework
- **Vite**: Build Tool
- **TypeScript**: Type Safety
- **Tailwind CSS**: Styling
- **shadcn/ui**: UI-Komponenten (Radix UI)
- **Framer Motion**: Animationen
- **React Router**: Routing
- **Lucide**: Icons
