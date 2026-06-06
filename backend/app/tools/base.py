from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    def get_parameters_schema(self) -> dict[str, Any]:
        """
        返回JSON Schema 格式的参数定义，用于传给LLM的function calling
        """

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """
        执行工具，返回结果字符串
        """
    
    def to_openai_tool(self) -> dict[str, Any]:
        """转换为OpenAI function calling格式"""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.get_parameters_schema(),
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)
    
    def get_all_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_openai_tool() for tool in self._tools.values()]
    
    def list_names(self) -> list[str]:
        return list(self._tools.keys())
    

registry = ToolRegistry()