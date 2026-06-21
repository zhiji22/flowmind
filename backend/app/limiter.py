"""全局限流器（slowapi）。

放在独立模块，避免 routers 和 main 之间的循环导入：
  - main.py 注册 app.state.limiter + 异常处理器
  - 各 router 从这里导入 limiter 给端点加 @limiter.limit(...)
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# 默认内存存储、按客户端 IP 计数。
# 生产多 worker 想要全局限流，可改 Limiter(key_func=..., storage_uri=settings.REDIS_URL)。
limiter = Limiter(key_func=get_remote_address)
