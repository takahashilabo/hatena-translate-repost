from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    source_hatena_id: str
    source_blog_id: str
    source_api_key: str
    target_hatena_id: str
    target_blog_id: str
    target_api_key: str
    lm_studio_base_url: str
    lm_studio_model: str
    request_timeout_seconds: float
    state_path: Path

    @classmethod
    def load(cls, env_file: Path | None = None) -> Settings:
        if env_file is None:
            load_dotenv(override=False)
        else:
            load_dotenv(env_file, override=False)

        def required(name: str) -> str:
            value = os.getenv(name)
            if value:
                return value
            raise ValueError(f"Missing required environment variable: {name}")

        return cls(
            source_hatena_id=os.getenv("SOURCE_HATENA_ID", ""),
            source_blog_id=os.getenv("SOURCE_BLOG_ID", ""),
            source_api_key=os.getenv("SOURCE_API_KEY", ""),
            target_hatena_id=required("TARGET_HATENA_ID"),
            target_blog_id=required("TARGET_BLOG_ID"),
            target_api_key=required("TARGET_API_KEY"),
            lm_studio_base_url=os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"),
            lm_studio_model=os.getenv("LM_STUDIO_MODEL", "qwen3-8b"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "180")),
            state_path=Path(os.getenv("STATE_PATH", ".hatena-translate-repost/state.json")),
        )
