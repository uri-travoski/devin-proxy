from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    devin_api_url: str = "https://api.devin.ai"
    devin_api_key: str = ""
    devin_org_id: str = ""
    proxy_api_key: str = ""
    proxy_port: int = 8000
    session_idle_timeout: int = 1800
    poll_interval: int = 3
    max_poll_duration: int = 600

    model_config = {"env_file": ".env", "env_prefix": ""}


settings = Settings()

MODEL_MAPPING: dict[str, str | None] = {
    "adaptive": "normal",
    "glm5.2-high": "fast",
    "swe1.7-max": "ultra",
}

AVAILABLE_MODELS = list(MODEL_MAPPING.keys())
