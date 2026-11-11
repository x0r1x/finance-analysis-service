"""Настройки FAS (§10.1). Без Redis сервис не стартует."""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    fas_data_dir: str = Field(default="./data", alias="FAS_DATA_DIR")
    fas_s3_bucket: str | None = Field(default=None, alias="FAS_S3_BUCKET")
    fas_s3_prefix: str = Field(default="fas", alias="FAS_S3_PREFIX")
    fas_s3_endpoint: str | None = Field(default=None, alias="FAS_S3_ENDPOINT")
    fas_s3_region: str = Field(default="us-east-1", alias="FAS_S3_REGION")
    fas_s3_access_key: str | None = Field(default=None, alias="FAS_S3_ACCESS_KEY")
    fas_s3_secret_key: str | None = Field(default=None, alias="FAS_S3_SECRET_KEY")
    fas_s3_ssl: bool | None = Field(default=None, alias="FAS_S3_SSL")
    fas_read_only: bool = Field(default=False, alias="FAS_READ_ONLY")
    fas_redis_url: str | None = Field(default=None, alias="FAS_REDIS_URL")
    fas_in_container: bool = Field(default=False, alias="FAS_IN_CONTAINER")
    fas_host: str = Field(default="127.0.0.1", alias="FAS_HOST")
    fas_port: int = Field(default=8080, alias="FAS_PORT")

    lock_ttl_ms: int = Field(default=60_000, alias="LOCK_TTL_MS")
    builder_base_url: str | None = Field(default=None, alias="BUILDER_BASE_URL")
    load_sync_sec: float = Field(default=20, alias="LOAD_SYNC_SEC")
    etag_ttl: int = Field(default=300, alias="ETAG_TTL")

    wren_engine_pool: int = Field(default=32, alias="WREN_ENGINE_POOL")
    wren_pool_memory_mb: int = Field(default=8192, alias="WREN_POOL_MEMORY_MB")
    wren_duckdb_memory_mb: int = Field(default=512, gt=0, alias="WREN_DUCKDB_MEMORY_MB")
    wren_duckdb_threads: int = Field(default=2, gt=0, alias="WREN_DUCKDB_THREADS")
    wren_engine_queue_max: int = Field(default=8, alias="WREN_ENGINE_QUEUE_MAX")
    wren_hot_queue: int = Field(default=3, alias="WREN_HOT_QUEUE")
    wren_engines_per_book: int = Field(default=2, alias="WREN_ENGINES_PER_BOOK")
    wren_threads: int = Field(default=8, alias="WREN_THREADS")
    cpu_threads: int = Field(default=8, alias="CPU_THREADS")

    api_max_inflight: int = Field(default=64, alias="API_MAX_INFLIGHT")
    sync_deadline_ms: int = Field(default=10_000, alias="SYNC_DEADLINE_MS")
    sync_max_periods: int = Field(default=120, alias="SYNC_MAX_PERIODS")
    operation_wait_max_ms: int = Field(default=30_000, alias="OPERATION_WAIT_MAX_MS")
    sse_enabled: bool = Field(default=True, alias="SSE_ENABLED")
    sse_heartbeat_sec: int = Field(default=15, alias="SSE_HEARTBEAT_SEC")

    idempotency_ttl: int = Field(default=86_400, alias="IDEMPOTENCY_TTL")
    rate_user_rps: float = Field(default=10, alias="RATE_USER_RPS")
    rate_user_burst: int = Field(default=20, alias="RATE_USER_BURST")
    rate_client_rps: float = Field(default=50, alias="RATE_CLIENT_RPS")
    rate_client_burst: int = Field(default=100, alias="RATE_CLIENT_BURST")
    rate_anon_rps: float = Field(default=50, alias="RATE_ANON_RPS")
    user_max_inflight: int = Field(default=8, alias="USER_MAX_INFLIGHT")
    redis_max_connections: int = Field(default=64, alias="REDIS_MAX_CONNECTIONS")

    gc_incomplete_age: str = Field(default="1h", alias="GC_INCOMPLETE_AGE")
    gc_cron: str = Field(default="0 3 * * *", alias="GC_CRON")
    retry_max: int = Field(default=2, alias="RETRY_MAX")
    user_max_queued: int = Field(default=20, alias="USER_MAX_QUEUED")
    taskiq_idle_timeout_ms: int = Field(default=60_000, alias="TASKIQ_IDLE_TIMEOUT_MS")
    taskiq_lease_refresh_sec: float = Field(default=15, alias="TASKIQ_LEASE_REFRESH_SEC")
    taskiq_reclaim_interval_sec: float = Field(default=10, alias="TASKIQ_RECLAIM_INTERVAL_SEC")
    taskiq_reclaim_lock_sec: float = Field(default=30, alias="TASKIQ_RECLAIM_LOCK_SEC")
    taskiq_stream_maxlen: int = Field(default=100_000, alias="TASKIQ_STREAM_MAXLEN")
    op_heartbeat_sec: float = Field(default=15, alias="OP_HEARTBEAT_SEC")
    op_stale_sec: float = Field(default=120, alias="OP_STALE_SEC")
    task_retry_max: int = Field(default=2, alias="TASK_RETRY_MAX")
    task_retry_base_sec: float = Field(default=5, alias="TASK_RETRY_BASE_SEC")
    task_retry_max_delay_sec: float = Field(default=300, alias="TASK_RETRY_MAX_DELAY_SEC")
    heavy_stage_timeout_sec: float = Field(default=1800, alias="HEAVY_STAGE_TIMEOUT_SEC")
    heavy_stage_kill_grace_sec: float = Field(default=5, alias="HEAVY_STAGE_KILL_GRACE_SEC")
    heavy_stage_memory_mb: int = Field(default=4096, alias="HEAVY_STAGE_MEMORY_MB")
    cb_failures: int = Field(default=5, alias="CB_FAILURES")
    cb_open_sec: int = Field(default=30, alias="CB_OPEN_SEC")
    shutdown_grace_sec: int = Field(default=25, alias="SHUTDOWN_GRACE_SEC")
    fas_embedded_workers: bool = Field(default=False, alias="FAS_EMBEDDED_WORKERS")
    fas_embedded_restart_backoff_sec: float = Field(
        default=1.0, gt=0, alias="FAS_EMBEDDED_RESTART_BACKOFF_SEC"
    )

    embed_model: str = Field(default="", alias="EMBED_MODEL")
    rerank_model: str = Field(default="", alias="RERANK_MODEL")
    clm_model: str = Field(default="", alias="CLM_MODEL")
    llm_model: str = Field(default="", alias="LLM_MODEL")
    embed_base_url: str | None = Field(default=None, alias="EMBED_BASE_URL")
    rerank_base_url: str | None = Field(default=None, alias="RERANK_BASE_URL")
    rerank_dialect: str = Field(default="cohere", pattern="^(cohere|tei)$", alias="RERANK_DIALECT")
    clm_base_url: str | None = Field(default=None, alias="CLM_BASE_URL")
    clm_api_key: str | None = Field(default=None, alias="CLM_API_KEY")
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    embed_timeout_sec: float = Field(default=2, alias="EMBED_TIMEOUT_SEC")
    rerank_timeout_sec: float = Field(default=3, alias="RERANK_TIMEOUT_SEC")
    clm_timeout_sec: float = Field(default=10, alias="CLM_TIMEOUT_SEC")
    llm_timeout_sec: float = Field(default=30, alias="LLM_TIMEOUT_SEC")
    embed_max_concurrency: int = Field(default=16, gt=0, alias="EMBED_MAX_CONCURRENCY")
    rerank_max_concurrency: int = Field(default=8, gt=0, alias="RERANK_MAX_CONCURRENCY")
    llm_max_concurrency: int = Field(default=4, gt=0, alias="LLM_MAX_CONCURRENCY")
    clm_max_concurrency: int = Field(default=4, gt=0, alias="CLM_MAX_CONCURRENCY")
    cb_window_sec: float = Field(default=30, alias="CB_WINDOW_SEC")
    retry_budget_per_min: int = Field(default=60, alias="RETRY_BUDGET_PER_MIN")
    clm_max_calls_per_book: int = Field(default=50, ge=0, alias="CLM_MAX_CALLS_PER_BOOK")
    mapping_deadline_ms: int = Field(default=60_000, alias="MAPPING_DEADLINE_MS")
    recall_top_k: int = Field(default=20, alias="RECALL_TOP_K")
    rerank_top_k: int = Field(default=5, alias="RERANK_TOP_K")
    question_max_candidates: int = Field(default=5, alias="QUESTION_MAX_CANDIDATES")
    # Стартовые пороги вывода типа модели. Калибровка — позже, на eval-корпусе (§5.10.6).
    model_type_accept: float = Field(default=0.6, ge=0, le=1, alias="FAS_MODEL_TYPE_ACCEPT")
    model_type_gap: float = Field(default=0.15, ge=0, le=1, alias="FAS_MODEL_TYPE_GAP")
    model_type_max_labels: int = Field(default=3, ge=1, alias="FAS_MODEL_TYPE_MAX_LABELS")
    knn_k: int = Field(default=5, alias="KNN_K")
    examples_refresh_sec: float = Field(default=60, alias="EXAMPLES_REFRESH_SEC")

    propose_min_books: int = Field(default=3, alias="PROPOSE_MIN_BOOKS")
    unmapped_cluster_cron: str = Field(default="0 4 * * *", alias="UNMAPPED_CLUSTER_CRON")
    unmapped_min_cluster: int = Field(default=2, ge=2, alias="UNMAPPED_MIN_CLUSTER")
    glossary_mine_cron: str = Field(default="30 4 * * *", alias="GLOSSARY_MINE_CRON")
    compact_cron: str = Field(default="0 2 * * *", alias="COMPACT_CRON")
    glossary_auto_promote: bool = Field(default=False, alias="GLOSSARY_AUTO_PROMOTE")
    glossary_auto_min_books: int = Field(default=3, alias="GLOSSARY_AUTO_MIN_BOOKS")
    glossary_auto_min_confirmations: int = Field(default=2, alias="GLOSSARY_AUTO_MIN_CONFIRMATIONS")
    glossary_shadow_recent_books: int = Field(default=50, alias="GLOSSARY_SHADOW_RECENT_BOOKS")
    glossary_canary_share: int = Field(default=10, ge=0, le=100, alias="GLOSSARY_CANARY_SHARE")
    glossary_canary_hours: int = Field(default=48, alias="GLOSSARY_CANARY_HOURS")
    glossary_canary_min_books: int = Field(default=10, alias="GLOSSARY_CANARY_MIN_BOOKS")
    glossary_canary_min_rows: int = Field(default=200, alias="GLOSSARY_CANARY_MIN_ROWS")
    glossary_canary_max_hours: int = Field(default=168, alias="GLOSSARY_CANARY_MAX_HOURS")
    remap_batch_books: int = Field(default=20, gt=0, alias="REMAP_BATCH_BOOKS")
    remap_books_per_min: int = Field(default=60, gt=0, alias="REMAP_BOOKS_PER_MIN")
    recalibrate_every: int = Field(default=500, alias="RECALIBRATE_EVERY")
    calibrator_max_risk: float = Field(default=0.02, alias="CALIBRATOR_MAX_RISK")
    fas_eval_dir: str = Field(default="eval", alias="FAS_EVAL_DIR")
    fas_admin_token: str | None = Field(default=None, alias="FAS_ADMIN_TOKEN")
    fas_require_admin_token: bool = Field(default=False, alias="FAS_REQUIRE_ADMIN_TOKEN")

    @model_validator(mode="after")
    def _storage_complete(self) -> Settings:
        bucket = self.fas_s3_bucket
        key = self.fas_s3_access_key
        secret = self.fas_s3_secret_key
        if (bucket or key or secret or self.fas_s3_endpoint) and not (bucket and key and secret):
            raise ValueError(
                "частичная конфигурация S3: нужны FAS_S3_BUCKET, FAS_S3_ACCESS_KEY и FAS_S3_SECRET_KEY"
            )
        if self.fas_s3_ssl is None:
            endpoint = self.fas_s3_endpoint or ""
            self.fas_s3_ssl = not endpoint.startswith("http://")
        if self.fas_in_container and _loopback(self.fas_redis_url):
            raise ValueError(
                "FAS_REDIS_URL внутри контейнера указывает на сам контейнер. "
                "Нужен адрес Redis в его сети."
            )
        if self.fas_require_admin_token and not (self.fas_admin_token or "").strip():
            raise ValueError(
                "FAS_REQUIRE_ADMIN_TOKEN=true требует непустой FAS_ADMIN_TOKEN "
                "(fail-closed prod perimeter)"
            )
        return self

    @property
    def s3_enabled(self) -> bool:
        return bool(self.fas_s3_bucket and self.fas_s3_access_key and self.fas_s3_secret_key)

    @property
    def wren_source(self) -> str:
        if not self.s3_enabled:
            return "local_file"
        if self.fas_s3_endpoint:
            return "minio_file"
        return "s3_file"

    @property
    def engine_pool_size(self) -> int:
        per = max(self.wren_duckdb_memory_mb, 1)
        by_memory = max(self.wren_pool_memory_mb // per, 1)
        return max(1, min(self.wren_engine_pool, by_memory))

    def gc_age_seconds(self) -> int:
        raw = self.gc_incomplete_age.strip().lower()
        if raw.endswith("h"):
            return int(float(raw[:-1]) * 3600)
        if raw.endswith("m"):
            return int(float(raw[:-1]) * 60)
        if raw.endswith("s"):
            return int(float(raw[:-1]))
        return int(raw)


def _loopback(url: str | None) -> bool:
    if not url:
        return False
    return urlparse(url).hostname in {"127.0.0.1", "localhost", "::1"}


def load_settings() -> Settings:
    return Settings()
