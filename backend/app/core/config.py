from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ServiceNow Agentic AIOps"
    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8910
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:8910,http://localhost:5173,http://127.0.0.1:8910"

    # Auth (JWT)
    secret_key: str = "change-me-in-production-servicenow-aiops-agentic"
    jwt_algorithm: str = "HS256"
    # Demo-friendly session length (7 days). Override via ACCESS_TOKEN_EXPIRE_MINUTES.
    access_token_expire_minutes: int = 60 * 24 * 7

    # PostgreSQL (SQLite fallback for local)
    database_url: str = "sqlite+aiosqlite:///./aiops.db"

    # Redis cache
    redis_url: str = "redis://localhost:6379/0"

    # Vector DB (Qdrant primary; Pinecone/Milvus via adapter flags)
    vector_backend: str = "qdrant"  # qdrant | milvus | pinecone | memory
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "incident_knowledge"
    pinecone_api_key: str = ""
    pinecone_index: str = "aiops-incidents"
    milvus_uri: str = "http://localhost:19530"

    # Neo4j GraphRAG
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # ServiceNow REST
    servicenow_instance_url: str = ""
    servicenow_username: str = ""
    servicenow_password: str = ""

    # n8n workflow
    n8n_webhook_url: str = ""

    # LLM providers: openai | anthropic | ollama | local
    llm_provider: str = "local"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "gpt-4o-mini"
    embedding_dim: int = 384

    # Agent framework preference: langgraph | crewai | autogen
    agent_framework: str = "langgraph"

    # SMTP email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "aiops@example.com"
    smtp_use_tls: bool = True

    # Slack / Teams / SMS notifications
    slack_webhook_url: str = ""
    teams_webhook_url: str = ""
    sms_webhook_url: str = ""  # Twilio-compatible or generic SMS gateway webhook
    sms_from: str = ""

    # OCR (Tesseract)
    tesseract_cmd: str = ""  # e.g. C:\\Program Files\\Tesseract-OCR\\tesseract.exe
    ocr_enabled: bool = True

    # Monitoring
    enable_metrics: bool = True

    # SLA Breach cron (seconds); 0 disables background cron
    sla_breach_cron_seconds: int = 300

    # SLA targets in hours
    sla_p1_hours: float = 2.0
    sla_p2_hours: float = 4.0
    sla_p3_hours: float = 6.0

    # Local/demo: skip remote probes for Redis/Qdrant/Neo4j
    use_inmemory_fallback: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
