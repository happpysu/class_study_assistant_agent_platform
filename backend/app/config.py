"""应用配置：从环境变量 / .env 读取，集中管理所有可配置项。"""
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

_DEFAULT_SECRET = "dev-secret-change-me-0123456789abcdef0123456789abcdef"

logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
    path.mkdir(parents=True, exist_ok=True)
    (path / "uploads").mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=_data_dir)
    jwt_secret: str = os.getenv("JWT_SECRET", _DEFAULT_SECRET)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "50"))
    cors_origins: tuple = tuple(
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if o.strip()
    )

    @property
    def database_url(self) -> str:
        return os.getenv("DATABASE_URL", f"sqlite:///{self.data_dir / 'app.db'}")

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"


settings = Settings()

if settings.jwt_secret == _DEFAULT_SECRET:
    logger.warning("JWT_SECRET 使用默认值，请在生产环境中通过 .env 配置强随机密钥")
