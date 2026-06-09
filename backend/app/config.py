from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    #数据库
    DATABASE_URL: str  # 必须通过 .env 或环境变量设置

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # LLM
    DASHSCOPE_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_DEFAULT: str = "qwen-plus"
    LLM_MODEL_FAST: str = "qwen-turbo"
    LLM_MODEL_STRONG: str = "qwen-max"

    # Auth
    JWT_SECRET: str  # 必须通过 .env 或环境变量设置
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Search
    TAVILY_API_KEY: str = ""

     # Agent
    AGENT_MAX_ITERATIONS: int = 10
    
    model_config = {"env_file": ".env", "extra": "ignore"}


    # SMTP 邮件
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_TLS: bool = True

settings = Settings()