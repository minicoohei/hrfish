"""
Configuration management
Loads from project root .env file
"""

import os
import warnings
from dotenv import load_dotenv

# Load .env file from project root
# Path: MiroFish/.env (relative to backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # If no .env in root, try loading env vars (for production)
    load_dotenv(override=True)


class Config:
    """Flask configuration class"""
    
    # Flask config
    # WARNING: In multi-worker deployments (gunicorn), set SECRET_KEY in .env
    # to ensure all workers share the same key for session consistency.
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24).hex()
    if not os.environ.get('SECRET_KEY'):
        warnings.warn(
            "SECRET_KEY not set in environment. Using auto-generated key. "
            "Set SECRET_KEY in .env for production deployments.",
            stacklevel=1,
        )
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # JSON config - disable ASCII escaping for proper Unicode display
    JSON_AS_ASCII = False

    # CORS config (production should set CORS_ORIGINS explicitly)
    # Debug mode allows multiple ports for parallel frontend dev servers (Vite HMR, Storybook, etc.)
    _DEFAULT_CORS = 'http://localhost:3000'
    if os.environ.get('FLASK_DEBUG', 'False').lower() == 'true':
        _DEFAULT_CORS = 'http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003'
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', _DEFAULT_CORS).split(',')

    # API authentication (None = auth disabled for development)
    API_KEY = os.environ.get('MIROFISH_API_KEY')
    
    # LLM config (unified OpenAI format)
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    LLM_CHAT_MODEL_NAME = os.environ.get('LLM_CHAT_MODEL_NAME')  # インタラクティブチャット用モデル（未設定時はLLM_MODEL_NAME）
    
    # Zep config
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    
    # File upload config
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # Text processing config
    DEFAULT_CHUNK_SIZE = 500  # Default chunk size
    DEFAULT_CHUNK_OVERLAP = 50  # Default overlap size
    
    # OASIS simulation config
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASIS platform action config
    OASIS_TWITTER_ACTIONS = (
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    )
    OASIS_REDDIT_ACTIONS = (
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    )
    
    # Report Agent config
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))

    # Knowledge Curation config
    KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), '../preset_knowledge')
    TAVILY_API_KEY = os.environ.get('TAVILY_API_KEY')
    KNOWLEDGE_MAX_INJECTION_CHARS = int(os.environ.get('KNOWLEDGE_MAX_INJECTION_CHARS', '3000'))
    
    @classmethod
    def validate(cls):
        """Validate required config"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY not configured")
        if not cls.ZEP_API_KEY:
            errors.append("ZEP_API_KEY not configured")
        return errors

