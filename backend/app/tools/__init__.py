# 导入各工具模块即完成注册（每个模块底部调用 registry.register）
from app.tools.base import registry  # noqa: F401
from app.tools.web_search import WebSearchTool  # noqa: F401
from app.tools.email_send import EmailSendTool  # noqa: F401
from app.tools.http_request import HttpRequestTool  # noqa: F401
from app.tools.code_exec import CodeExecTool  # noqa: F401
