import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change_this_secret_key")
    DATABASE = os.path.join(BASE_DIR, "instance", "social.db")

    UPLOAD_FOLDER_POSTS = os.path.join(BASE_DIR, "static", "uploads", "posts")
    UPLOAD_FOLDER_PROFILES = os.path.join(BASE_DIR, "static", "uploads", "profiles")

    MAX_CONTENT_LENGTH = 100 * 1024 * 1024

    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    ALLOWED_VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm"}

    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))