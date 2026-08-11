import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    # python-dotenv 가 없는 환경(예: openclaw 게이트웨이 python3)에서도
    # 저장 경로가 죽지 않도록 no-op 로 대체. .env 는 서버 systemd/venv 에서 이미 로드됨.
    def load_dotenv(*args, **kwargs):
        return False

DEFAULT_BASE_DIR = Path("/home/ubuntu/pt_system")
BASE_DIR = DEFAULT_BASE_DIR if DEFAULT_BASE_DIR.exists() else Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "pt_data.db"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")