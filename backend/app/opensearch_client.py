from opensearchpy import OpenSearch
from .config import settings


def get_opensearch_client() -> OpenSearch:
    return OpenSearch(
        hosts=[{"host": settings.opensearch_host, "port": settings.opensearch_port}],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )


# Index mappings
COMPANY_INDEX = "companies"
PERSON_INDEX = "persons"

COMPANY_MAPPING = {
    "mappings": {
        "properties": {
            "company_id": {"type": "keyword"},
            "raw_name": {"type": "text", "analyzer": "german", "fields": {"keyword": {"type": "keyword"}}},
            "legal_name": {"type": "text", "analyzer": "german", "fields": {"keyword": {"type": "keyword"}}},
            "legal_form": {"type": "keyword"},
            "status": {"type": "keyword"},
            "terminated": {"type": "boolean"},
            "register_unique_key": {"type": "keyword"},
            "register_id": {"type": "keyword"},
            "address_city": {"type": "keyword"},
            "address_postal_code": {"type": "keyword"},
            "address_country": {"type": "keyword"},
            "segment_codes_wz": {"type": "keyword"},
            "segment_codes_nace": {"type": "keyword"},
            "last_update_time": {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "german": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "german_normalization", "german_stemmer"]
                }
            },
            "filter": {
                "german_stemmer": {"type": "stemmer", "language": "german"},
                "german_normalization": {"type": "german_normalization"}
            }
        }
    }
}

PERSON_MAPPING = {
    "mappings": {
        "properties": {
            "person_id": {"type": "keyword"},
            "first_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "last_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "full_name": {"type": "text", "analyzer": "german"},
            "birth_year": {"type": "integer"},
            "address_city": {"type": "keyword"},
            "company_ids": {"type": "keyword"},  # Array of company_ids this person is related to
            "roles": {
                "type": "nested",
                "properties": {
                    "company_id": {"type": "keyword"},
                    "company_name": {"type": "text"},
                    "role_type": {"type": "keyword"},
                    "role_date": {"type": "date"}
                }
            }
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0
    }
}


def init_opensearch_indices(client: OpenSearch):
    """Create indices if they don't exist."""
    if not client.indices.exists(COMPANY_INDEX):
        client.indices.create(COMPANY_INDEX, body=COMPANY_MAPPING)

    if not client.indices.exists(PERSON_INDEX):
        client.indices.create(PERSON_INDEX, body=PERSON_MAPPING)
