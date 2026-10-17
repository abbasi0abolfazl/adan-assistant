from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    provider: Literal['openai', 'gemini'] = 'openai'
    openai_api_key: SecretStr = SecretStr('')
    gemini_api_key: SecretStr = SecretStr('')
    openai_base_url: str = 'https://api.openai.com/v1'
    llm_model: str = 'gpt-5.4-mini-2026-03-17'
    gemini_model: str = 'gemini-2.5-flash'
    embedding_model: str = 'text-embedding-3-small'
    gemini_embedding_model: str = 'gemini-embedding-001'
    embedding_dimensions: int = Field(1536, ge=256, le=3072)
    data_dir: Path = Path('data')
    runtime_dir: Path = Path('runtime')
    chunk_words: int = Field(180, ge=50, le=500)
    chunk_overlap: int = Field(30, ge=0, le=100)
    retrieval_top_k: int = Field(4, ge=1, le=8)
    retrieval_min_score: float = Field(0.25, ge=-1, le=1)
    provider_timeout_seconds: float = Field(40, ge=1, le=120)
    request_deadline_seconds: float = Field(150, ge=10, le=600)
    sql_timeout_seconds: float = Field(1.0, gt=0, le=10)
    sql_max_rows: int = Field(100, ge=1, le=500)
    sql_vm_steps: int = Field(100000, ge=1000, le=1000000)
    max_inflight: int = Field(4, ge=1, le=32)

    @property
    def db_path(self) -> Path:
        return self.runtime_dir / 'store.sqlite3'

    @property
    def active_api_key(self) -> SecretStr:
        return self.gemini_api_key if self.provider == 'gemini' else self.openai_api_key

    @property
    def active_llm_model(self) -> str:
        return self.gemini_model if self.provider == 'gemini' else self.llm_model

    @property
    def active_embedding_model(self) -> str:
        return self.gemini_embedding_model if self.provider == 'gemini' else self.embedding_model
