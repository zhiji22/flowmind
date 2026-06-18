from pydantic import field_validator
from pydantic_settings import BaseSettings


# JWT 弱密钥黑名单（开发占位 / 常见示例字符串）
_WEAK_JWT_SECRETS = frozenset({
    "dev_jwt_secret_not_for_production",
    "your_jwt_secret_change_in_production",
    "replace_with_random_64_byte_hex_string",
    "secret",
    "changeme",
    "change_me",
})


class Settings(BaseSettings):
    # 数据库
    DATABASE_URL: str  # 必须通过 .env 或环境变量设置

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # LLM
    DASHSCOPE_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_DEFAULT: str = "qwen-plus"
    LLM_MODEL_FAST: str = "qwen-turbo"
    LLM_MODEL_STRONG: str = "qwen-max"
    # 单次 LLM 输出最大字符数（防止 LLM 输出体积爆炸 / DoS）
    LLM_MAX_OUTPUT_CHARS: int = 100_000
    # 工作流单条 DAG 最大步骤数 / 最大嵌套深度
    WORKFLOW_MAX_STEPS: int = 100
    WORKFLOW_CONFIG_MAX_DEPTH: int = 6

    # Auth
    JWT_SECRET: str  # 必须通过 .env 或环境变量设置
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # CORS 允许来源（逗号分隔）
    CORS_ALLOW_ORIGINS: str = "http://localhost:3000"

    # 运行环境：development / staging / production。
    # production 下禁用 dev-only 接口（如直接重置密码），避免安全风险。
    APP_ENV: str = "development"

    # Search
    TAVILY_API_KEY: str = ""

    # Agent
    AGENT_MAX_ITERATIONS: int = 10

    # SMTP 邮件
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_TLS: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------

    @field_validator("JWT_SECRET")
    @classmethod
    def _validate_jwt_secret(cls, v: str) -> str:
        if not v or len(v) < 32:
            raise ValueError(
                "JWT_SECRET 必须至少 32 字符；"
                "可用 `python -c \"import secrets;print(secrets.token_hex(48))\"` 生成"
            )
        if v in _WEAK_JWT_SECRETS:
            raise ValueError("JWT_SECRET 使用了已知的弱密钥占位符，请替换为强随机字符串")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """把 CORS_ALLOW_ORIGINS 拆成 list；空字符串过滤"""
        return [o.strip() for o in self.CORS_ALLOW_ORIGINS.split(",") if o.strip()]


settings = Settings()
