"""Настройки FAS (§10.1). Без Redis сервис не стартует."""

from __future__ import annotations

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
    fas_s3_ssl: bool = Field(default=True, alias="FAS_S3_SSL")
    fas_read_only: bool = Field(default=False, alias="FAS_READ_ONLY")
    fas_redis_url: str | None = Field(default=None, alias="FAS_REDIS_URL")

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
    wren_engine_idle_sec: int = Field(default=600, alias="WREN_ENGINE_IDLE_SEC")
    wren_threads: int = Field(default=8, alias="WREN_THREADS")
    cpu_threads: int = Field(default=8, alias="CPU_THREADS")

    api_max_inflight: int = Field(default=64, alias="API_MAX_INFLIGHT")
    sync_deadline_ms: int = Field(default=10_000, alias="SYNC_DEADLINE_MS")
    sync_max_periods: int = Field(default=120, alias="SYNC_MAX_PERIODS")
    operation_wait_max_ms: int = Field(default=30_000, alias="OPERATION_WAIT_MAX_MS")
    async_slow_callback_ms: int = Field(default=100, alias="ASYNC_SLOW_CALLBACK_MS")

    result_cache_ttl: int = Field(default=86_400, alias="RESULT_CACHE_TTL")
    idempotency_ttl: int = Field(default=86_400, alias="IDEMPOTENCY_TTL")
    rate_user_rps: float = Field(default=10, alias="RATE_USER_RPS")
    rate_user_burst: int = Field(default=20, alias="RATE_USER_BURST")
    rate_client_rps: float = Field(default=50, alias="RATE_CLIENT_RPS")
    rate_client_burst: int = Field(default=100, alias="RATE_CLIENT_BURST")
    rate_anon_rps: float = Field(default=50, alias="RATE_ANON_RPS")
    user_max_inflight: int = Field(default=8, alias="USER_MAX_INFLIGHT")
    redis_max_connections: int = Field(default=64, alias="REDIS_MAX_CONNECTIONS")

    state_compact_every: int = Field(default=200, alias="STATE_COMPACT_EVERY")
    gc_incomplete_age: str = Field(default="1h", alias="GC_INCOMPLETE_AGE")
    retry_max: int = Field(default=2, alias="RETRY_MAX")
    cb_failures: int = Field(default=5, alias="CB_FAILURES")
    cb_open_sec: int = Field(default=30, alias="CB_OPEN_SEC")
    shutdown_grace_sec: int = Field(default=25, alias="SHUTDOWN_GRACE_SEC")

    embed_model: str = Field(default="", alias="EMBED_MODEL")
    rerank_model: str = Field(default="", alias="RERANK_MODEL")
    clm_model: str = Field(default="", alias="CLM_MODEL")
    fas_admin_token: str | None = Field(default=None, alias="FAS_ADMIN_TOKEN")

    @model_validator(mode="after")
    def _storage_complete(self) -> Settings:
        bucket = self.fas_s3_bucket
        key = self.fas_s3_access_key
        secret = self.fas_s3_secret_key
        if (bucket or key or secret or self.fas_s3_endpoint) and not (bucket and key and secret):
            raise ValueError(
                "частичная конфигурация S3: нужны FAS_S3_BUCKET, FAS_S3_ACCESS_KEY и FAS_S3_SECRET_KEY"
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


def load_settings() -> Settings:
    return Settings()
