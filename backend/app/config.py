from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # PostgreSQL
    database_url: str = "postgresql+asyncpg://companydb:companydb@localhost:5432/companydb"
    database_url_sync: str = "postgresql://companydb:companydb@localhost:5432/companydb"

    # OpenSearch (optional - set host to empty string to disable)
    opensearch_host: str = "localhost"
    opensearch_port: int = 9200
    opensearch_enabled: bool = True  # Set to False to skip OpenSearch

    # Import settings
    data_directory: Path = Path(__file__).parent.parent.parent / "data"
    import_batch_size: int = 5000  # Increased from 1000 for better performance

    # PostgreSQL performance settings (for import optimization)
    # These can be set in .env file for fine-tuning
    pg_work_mem: str = "256MB"  # Increase for larger sort operations
    pg_maintenance_work_mem: str = "512MB"  # Increase for index creation
    pg_shared_buffers: str = "2GB"  # Adjust based on available RAM

    class Config:
        env_file = ".env"


settings = Settings()
