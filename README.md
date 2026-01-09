# CompanyDB

Import und Suche von NorthData Firmendaten (JSONL-Dumps).

## Architektur

- **PostgreSQL 14+**: Source of Truth für Companies + Persons
- **OpenSearch 2.x**: Volltextsuche + Facetten/Filter
- **FastAPI**: Backend API
- **React/Vite**: Frontend (kommt in Slice 2)

---

## Installation

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

#### 2. OpenSearch installieren

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

**Windows / Manuell (alle Plattformen):**
1. Download: https://opensearch.org/downloads.html (TAR/ZIP)
2. Entpacken nach z.B. `C:\opensearch` oder `/opt/opensearch`
3. `config/opensearch.yml` bearbeiten:
```yaml
discovery.type: single-node
plugins.security.disabled: true
```
4. Starten: `bin/opensearch` (Linux/Mac) oder `bin\opensearch.bat` (Windows)

#### 3. Services prüfen

```bash
# PostgreSQL
pg_isready -h localhost -p 5432
# Erwartete Ausgabe: localhost:5432 - accepting connections

# OpenSearch
curl http://localhost:9200
# Erwartete Ausgabe: JSON mit cluster_name, version etc.
```

---

## Backend starten

```bash
cd backend

# Virtual Environment erstellen
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Dependencies installieren
pip install -r requirements.txt

# .env anlegen (optional - defaults passen für Standardinstallation)
cp ../.env.example .env

# Datenbank-Tabellen erstellen + Server starten
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API läuft auf: `http://localhost:8000`
Swagger Docs: `http://localhost:8000/docs`

---

## Import durchführen

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

## API Endpoints

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/health` | GET | Health-Check (Postgres + OpenSearch) |
| `/imports/files` | GET | Liste verfügbarer JSONL-Dateien in `data/` |
| `/imports` | POST | Import-Job starten (`{"filename": "..."}`) |
| `/imports` | GET | Alle Import-Jobs auflisten |
| `/imports/{id}` | GET | Status eines Import-Jobs |

---

## Konfiguration (.env)

```bash
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://companydb:companydb@localhost:5432/companydb
DATABASE_URL_SYNC=postgresql://companydb:companydb@localhost:5432/companydb

# OpenSearch
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200

# Import
DATA_DIRECTORY=./data
IMPORT_BATCH_SIZE=1000
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
├── docker-compose.yml       # Alternative: Docker Setup
├── scripts/
│   └── setup_db.py          # DB-Initialisierung
└── .env.example
```
