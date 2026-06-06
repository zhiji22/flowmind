from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    #数据库
    DATABASE_URL: str = "postgresql+asyncpg://flowmind:flowmind_secret_123@postgres:5432/flowmind"
    
    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # LLM
    DASHSCOPE_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_DEFAULT: str = "qwen-plus"
    LLM_MODEL_FAST: str = "qwen-turbo"
    LLM_MODEL_STRONG: str = "qwen-max"

    # Auth
    JWT_SECRET: str = "dev_jwt_secret_not_for_production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Search
    TAVILY_API_KEY: str = ""

     # Agent
    AGENT_MAX_ITERATIONS: int = 10
    
    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()