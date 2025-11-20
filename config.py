"""Configuration settings for AI Product Search App"""

import os


class Config:
    """Application configuration"""

    # Flask settings
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = True

    # OpenAI settings
    OPENAI_API_KEY = None
    EMBEDDING_MODEL = "text-embedding-3-small"
    CHAT_MODEL = (
        "gpt-5-mini"  # Note: Newer models use max_completion_tokens (not max_tokens)
    )
    MAX_COMPLETION_TOKENS = 8000

    # Product data
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PRODUCT_DATA_FILE = os.path.join(
        BASE_DIR, "product_aware_complete_20251008_150843.json"
    )

    # Search settings
    TOP_K_SEMANTIC = 30  # Number of products from semantic search
    TOP_K_FINAL = 15  # Final number of products to return
    SIMILARITY_THRESHOLD = 0.3  # Minimum similarity score

    # Cache settings
    CACHE_EMBEDDINGS = True
    EMBEDDINGS_CACHE_FILE = os.path.join(BASE_DIR, "embeddings_cache.pkl")

    # Database settings (for EPD Screener)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'epd_scans.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    @staticmethod
    def load_openai_key():
        """Load OpenAI API key from multiple sources"""
        # Try environment variable first
        env_key = os.environ.get("OPENAI_API_KEY")
        if env_key:
            return env_key

        # Try loading from file
        possible_paths = [
            "openai-api.md",
            "openai_apikey.md",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "openai-api.md"),
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "openai_apikey.md"
            ),
        ]

        for key_file in possible_paths:
            if os.path.exists(key_file):
                try:
                    with open(key_file, "r") as f:
                        key = f.read().strip()
                        if key and len(key) > 10:
                            return key
                except Exception:
                    pass

        return None

    @classmethod
    def init_app(cls):
        """Initialize application configuration"""
        cls.OPENAI_API_KEY = cls.load_openai_key()
        if not cls.OPENAI_API_KEY:
            print(
                "WARNING: OpenAI API key not found. Please set OPENAI_API_KEY environment variable or create openai-api.md file."
            )
