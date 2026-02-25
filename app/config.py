from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ZEPHYR_")

    health_threshold: float = 0.60
    window_size: int = 100
    probe_interval: int = 10
    degraded_threshold: float = 0.80


settings = Settings()
