from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # PostgreSQL
    database_url: str = "postgresql+asyncpg://companydb:companydb@localhost:5432/companydb"
    database_url_sync: str = "postgresql://companydb:companydb@localhost:5432/companydb"

    # OpenSearch
    opensearch_host: str = "localhost"
    opensearch_port: int = 9200

    # Import settings
    data_directory: Path = Path(__file__).parent.parent.parent.parent / "data"
    import_batch_size: int = 1000

    class Config:
        env_file = ".env"


settings = Settings()
