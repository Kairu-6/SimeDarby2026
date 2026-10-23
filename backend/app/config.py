from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_path: str = "data/simeloop.sqlite3"
    demo_mode: bool = True
    device_api_key: str = "hackathon-device-key-change-me"
    cors_origins: str = "http://localhost:8081,http://127.0.0.1:8081"
    vision_model: str = "openai/clip-vit-base-patch32"
    vision_enabled: bool = True
    vision_threshold: float = 0.60
    push_notifications_enabled: bool = False
    session_ttl_seconds: int = 900
    food_points_per_kg: int = 50
    recyclable_points_per_kg: int = 100
    max_item_kg: float = 4.0
    min_item_g: float = 10.0
    empty_plate_g: float = 5.0
    weight_tolerance_g: float = 5.0
    telemetry_max_age_seconds: int = 15
    classification_max_age_seconds: int = 60
    full_bin_blocks_station: bool = False
    kiosk_api_key: str = ""
    public_app_url: str = "http://localhost:8081"
    kiosk_qr_ttl_seconds: int = 180
    web_build_path: str = ""
    public_preview: bool = False

    @property
    def db_path(self) -> Path:
        return Path(self.database_path)


settings = Settings()
