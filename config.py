# config.py

import os


# Настройки подключения к БД из переменных окружения
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "BPLA")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "1234")

# Формируем URL подключения к БД
DB_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Настройки приложения
UPLOADS_FOLDER = "uploads"
CACHE_DIR = "cache"
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

# Настройки обработки
RECORDS_TO_PROCESS = 10000
SIMPLIFY_TOLERANCE = 500
AREA_THRESHOLD = 100e6