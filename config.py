"""
Configuration for Market-Zero.

All settings are loaded from environment variables with sensible defaults.
No secrets are hardcoded. Use a .env file for local development.
"""

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on shell env vars


@dataclass
class DatabaseConfig:
    host: str = os.getenv("MZ_DB_HOST", "localhost")
    port: int = int(os.getenv("MZ_DB_PORT", "5488"))
    name: str = os.getenv("MZ_DB_NAME", "market_zero")
    user: str = os.getenv("MZ_DB_USER", "postgres")
    password: str = os.getenv("MZ_DB_PASSWORD", "postgres")

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def async_dsn(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class EmbeddingConfig:
    provider: str = os.getenv("MZ_EMBEDDING_PROVIDER", "openai")
    model: str = os.getenv("MZ_EMBEDDING_MODEL", "text-embedding-3-small")
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    dimensions: int = 1536
    batch_size: int = int(os.getenv("MZ_EMBEDDING_BATCH_SIZE", "100"))


@dataclass
class ConnectorConfig:
    # FDA
    openfda_api_key: str = os.getenv("OPENFDA_API_KEY", "")  # optional, higher rate limits

    # SEC EDGAR (required: company name + email for User-Agent)
    edgar_company_name: str = os.getenv("MZ_EDGAR_COMPANY", "MarketZero")
    edgar_contact_email: str = os.getenv("MZ_EDGAR_EMAIL", "")

    # PubMed (optional, higher rate limits with key)
    ncbi_api_key: str = os.getenv("NCBI_API_KEY", "")

    # Rate limiting
    default_request_delay_seconds: float = float(
        os.getenv("MZ_REQUEST_DELAY", "0.5")
    )


@dataclass
class PipelineConfig:
    # Entity resolution
    fuzzy_match_threshold: float = float(
        os.getenv("MZ_FUZZY_THRESHOLD", "0.85")
    )
    auto_alias_threshold: float = float(
        os.getenv("MZ_AUTO_ALIAS_THRESHOLD", "0.95")
    )

    # Embedding-based resolution
    embedding_similarity_threshold: float = float(
        os.getenv("MZ_EMBEDDING_SIM_THRESHOLD", "0.82")
    )

    # LLM-based resolution (GPT-4o-mini fallback)
    llm_resolution_enabled: bool = os.getenv(
        "MZ_LLM_RESOLUTION", "true"
    ).lower() == "true"
    llm_resolution_model: str = os.getenv("MZ_LLM_RESOLUTION_MODEL", "gpt-4o-mini")
    llm_confidence_threshold: float = float(
        os.getenv("MZ_LLM_CONFIDENCE_THRESHOLD", "0.75")
    )

    # Auto-create entities from credible sources
    auto_create_entities: bool = os.getenv(
        "MZ_AUTO_CREATE_ENTITIES", "true"
    ).lower() == "true"

    # Resolution audit logging
    resolution_audit_enabled: bool = os.getenv(
        "MZ_RESOLUTION_AUDIT", "true"
    ).lower() == "true"

    # Chunking
    chunk_size_tokens: int = int(os.getenv("MZ_CHUNK_SIZE", "500"))
    chunk_overlap_tokens: int = int(os.getenv("MZ_CHUNK_OVERLAP", "50"))

    # Data quality
    quality_enabled: bool = os.getenv(
        "MZ_QUALITY_ENABLED", "true"
    ).lower() == "true"
    quality_fail_threshold: float = float(
        os.getenv("MZ_QUALITY_FAIL_THRESHOLD", "0.3")
    )
    quality_warn_threshold: float = float(
        os.getenv("MZ_QUALITY_WARN_THRESHOLD", "0.6")
    )
    freshness_max_days: int = int(os.getenv("MZ_FRESHNESS_MAX_DAYS", "90"))

    # HITL (Human-in-the-loop)
    # auto: pipeline proceeds, queues reviews asynchronously
    # strict: blocks on critical reviews, continues on warnings
    # manual: all new entities and low-confidence resolutions require approval
    hitl_mode: str = os.getenv("MZ_HITL_MODE", "auto")
    hitl_confidence_threshold: float = float(
        os.getenv("MZ_HITL_CONFIDENCE_THRESHOLD", "0.75")
    )

    # Change detection
    change_detection_enabled: bool = os.getenv(
        "MZ_CHANGE_DETECTION", "true"
    ).lower() == "true"


@dataclass
class LLMConfig:
    """Configuration for LLM-powered narrative synthesis."""
    provider: str = os.getenv("MZ_LLM_PROVIDER", "openai")
    model: str = os.getenv("MZ_LLM_MODEL", "gpt-4o-mini")
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    max_tokens: int = int(os.getenv("MZ_LLM_MAX_TOKENS", "1024"))
    temperature: float = float(os.getenv("MZ_LLM_TEMPERATURE", "0.3"))
    enabled: bool = os.getenv("MZ_LLM_ENABLED", "true").lower() == "true"
    # CTX context mode: "ctx" | "legacy" | "both" (A/B benchmarking)
    ctx_mode: str = os.getenv("MZ_CTX_MODE", "both")


@dataclass
class ResearchConfig:
    """Configuration for Deep Research mode."""
    web_enabled: bool = os.getenv("MZ_RESEARCH_WEB_ENABLED", "true").lower() == "true"
    web_timeout_seconds: float = float(os.getenv("MZ_RESEARCH_WEB_TIMEOUT_SECONDS", "8"))
    max_web_results: int = int(os.getenv("MZ_RESEARCH_MAX_WEB_RESULTS", "6"))
    serpapi_key: str = os.getenv("SERPAPI_API_KEY", "")


@dataclass
class AgentConfig:
    """Configuration for the agentic query layer (LangGraph agents)."""
    llm_provider: str = os.getenv("MZ_AGENT_LLM_PROVIDER", "openai")
    llm_model: str = os.getenv("MZ_AGENT_LLM_MODEL", "gpt-4o-mini")
    llm_temperature: float = float(os.getenv("MZ_AGENT_LLM_TEMPERATURE", "0"))
    team_eval_enabled: bool = os.getenv(
        "MZ_AGENT_TEAM_EVAL", "true"
    ).lower() == "true"
    max_sql_rows: int = int(os.getenv("MZ_AGENT_MAX_SQL_ROWS", "100"))
    enabled: bool = os.getenv("MZ_AGENT_ENABLED", "true").lower() == "true"


@dataclass
class AppConfig:
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    connectors: ConnectorConfig = field(default_factory=ConnectorConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)

    # Therapeutic areas to track (MeSH descriptor IDs)
    # Phase 1: Diabetes + Obesity. Phase 2: Cardiovascular / Heart Failure.
    # Phase 3: Expanded metabolic, cardiovascular, and renal descriptors.
    target_mesh_ids: list[str] = field(default_factory=lambda: [
        # Metabolic / Diabetes / Obesity
        "D003920",  # Diabetes Mellitus
        "D003924",  # Diabetes Mellitus, Type 2
        "D003922",  # Diabetes Mellitus, Type 1
        "D009765",  # Obesity
        "D024821",  # Metabolic Syndrome
        "D006943",  # Hyperglycemia
        # Cardiovascular / Heart Failure
        "D006333",  # Heart Failure
        "D054143",  # Heart Failure, Diastolic
        "D054144",  # Heart Failure, Systolic
        "D002318",  # Cardiovascular Diseases
        "D006331",  # Heart Diseases
        "D006973",  # Hypertension
        "D003324",  # Coronary Artery Disease
        "D001281",  # Atrial Fibrillation
        "D009202",  # Cardiomyopathies
        # Renal (cardiorenal overlap)
        "D051436",  # Chronic Kidney Disease (Renal Insufficiency, Chronic)
        "D003928",  # Diabetic Nephropathies
    ])

    # Target companies for SEC EDGAR (CIK numbers)
    target_company_ciks: list[str] = field(default_factory=lambda: [
        "0001000694",  # Novo Nordisk
        "0000059478",  # Eli Lilly
        "0001121404",  # Sanofi
        "0000816284",  # AstraZeneca
        "0000078003",  # Pfizer
        "0001114448",  # Novartis (Entresto / sacubitril-valsartan)
    ])


# Singleton
config = AppConfig()
