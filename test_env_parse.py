from pydantic_settings import BaseSettings
from typing import List

class S(BaseSettings):
    TELEGRAM_ALLOWED_CHAT_IDS: List[int] = []
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

print(S().TELEGRAM_ALLOWED_CHAT_IDS)
