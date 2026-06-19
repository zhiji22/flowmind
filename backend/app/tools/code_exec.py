"""代码执行工具：在 AST 沙箱中安全执行 Python 计算。

安全策略（白名单）：
  - 解析为 AST，只允许白名单内的节点类型
  - 禁止 import / 属性访问 / 函数定义 / 类定义 / 全局声明
  - 只允许调用白名单内置函数（abs/round/len/min/max/sum/int/float/str...）
  - 允许算术、比较、布尔、列表/字典/元组/下标/切片

这样无需引入 RestrictedPython 依赖，也从根本上杜绝危险操作。
适合数值计算、字符串处理、数据转换。
"""
import ast
import logging
import operator
from typing import Any

from app.tools.base import BaseTool, registry

logger = logging.getLogger(__name__)

class _SandboxError(Exception):
    """沙箱校验异常。"""


# 限制：指数大小、可迭代输入大小、AST 深度，防止 CPU/内存 DoS
_MAX_POW_EXPONENT = 1024
_MAX_ITERABLE_LEN = 10_000
_MAX_RANGE_LEN = 100_000
_MAX_AST_DEPTH = 100
# 允许的二元运算符
_SAFE_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    # ast.Pow 单独处理（需要做指数大小校验）
}

# 允许的一元运算符
_SAFE_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}

# 允许的比较运算符（含 in / not in，专门处理）
_SAFE_CMPOPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
_CONTAINMENT_OPS = {
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

def _safe_range(*args):
    """带长度上限的 range，避免 range(10**12) 之类构造大对象。"""
    r = range(*args)
    if len(r) > _MAX_RANGE_LEN:
        raise _SandboxError(f"range 长度超过上限 {_MAX_RANGE_LEN}")
    return r


def _check_iterable_len(value):
    """对可迭代输入做长度上限检查（仅当对象有 __len__ 时）。"""
    try:
        n = len(value)
    except TypeError:
        return
    if n > _MAX_ITERABLE_LEN:
        raise _SandboxError(f"输入长度 {n} 超过上限 {_MAX_ITERABLE_LEN}")


def _safe_sorted(iterable, *args, **kwargs):
    _check_iterable_len(iterable)
    return sorted(iterable, *args, **kwargs)


def _safe_sum(iterable, *args, **kwargs):
    _check_iterable_len(iterable)
    return sum(iterable, *args, **kwargs)


def _safe_min(*args, **kwargs):
    if len(args) == 1:
        _check_iterable_len(args[0])
    return min(*args, **kwargs)


def _safe_max(*args, **kwargs):
    if len(args) == 1:
        _check_iterable_len(args[0])
    return max(*args, **kwargs)


# 允许调用的内置函数（部分包了大小校验）
_SAFE_BUILTINS = {
    "abs": abs,
    "round": round,
    "len": len,
    "min": _safe_min,
    "max": _safe_max,
    "sum": _safe_sum,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "sorted": _safe_sorted,
    "range": _safe_range,
}


class SafeEvaluator(ast.NodeVisitor):
    """递归求值器：遍历 AST 求值，遇到非白名单节点立即抛错。"""

    def __init__(self, env: dict[str, Any]):
        self.env = env

    def run(self, tree: ast.Module) -> Any:
        """依次执行每条语句，返回最后一条表达式的结果。"""
        result = None
        for stmt in tree.body:
            result = self.visit(stmt)
        return result

    # ----- 语句 -----
    def visit_Assign(self, node: ast.Assign) -> Any:
        # 只支持单个简单变量赋值：x = expr
        value = self.visit(node.value)
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            raise _SandboxError("只支持简单变量赋值，如 x = ...")
        self.env[node.targets[0].id] = value
        return value

    def visit_Expr(self, node: ast.Expr) -> Any:
        return self.visit(node.value)
    
    # ----- 表达式 -----
    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value
    
    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in _SAFE_BUILTINS:
            return _SAFE_BUILTINS[node.id]
        if node.id in self.env:
            return self.env[node.id]
        raise _SandboxError(f"未定义的名称: {node.id}")

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)
        # ** 指数运算单独处理：限制指数大小，避免巨整数 DoS
        if isinstance(node.op, ast.Pow):
            if isinstance(right, (int, float)) and right > _MAX_POW_EXPONENT:
                raise _SandboxError(f"指数过大（>{_MAX_POW_EXPONENT}）")
            return left ** right
        op = _SAFE_BINOPS.get(type(node.op))
        if op is None:
            raise _SandboxError(f"不支持的运算符: {type(node.op).__name__}")
        return op(left, right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        op = _SAFE_UNARYOPS.get(type(node.op))
        if op is None:
            raise _SandboxError(f"不支持的一元运算符: {type(node.op).__name__}")
        return op(operand)

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if isinstance(node.op, ast.And):
            result = True
            for v in node.values:
                result = self.visit(v)
                if not result:
                    return result
            return result
        if isinstance(node.op, ast.Or):
            val: Any = False
            for v in node.values:
                val = self.visit(v)
                if val:
                    return val
            return val
        raise _SandboxError("不支持的布尔运算")

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for op_node, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            containment = _CONTAINMENT_OPS.get(type(op_node))
            if containment is not None:
                ok = containment(left, right)
            else:
                op = _SAFE_CMPOPS.get(type(op_node))
                if op is None:
                    raise _SandboxError(
                        f"不支持的比较运算符: {type(op_node).__name__}"
                    )
                ok = op(left, right)
            if not ok:
                return False
            left = right
        return True

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        if self.visit(node.test):
            return self.visit(node.body)
        return self.visit(node.orelse)

    def visit_Call(self, node: ast.Call) -> Any:
        func = self.visit(node.func)
        # 只允许调用白名单内置函数本身
        if func not in _SAFE_BUILTINS.values():
            raise _SandboxError("只允许调用白名单内置函数")
        if node.keywords:
            raise _SandboxError("不支持关键字参数")
        args = [self.visit(a) for a in node.args]
        return func(*args)

    def visit_List(self, node: ast.List) -> Any:
        return [self.visit(e) for e in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> Any:
        return tuple(self.visit(e) for e in node.elts)

    def visit_Dict(self, node: ast.Dict) -> Any:
        return {
            self.visit(k): self.visit(v)
            for k, v in zip(node.keys, node.values)
        }

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        value = self.visit(node.value)
        index = node.slice
        # 切片：a[1:3]
        if isinstance(index, ast.Slice):
            lower = self.visit(index.lower) if index.lower else None
            upper = self.visit(index.upper) if index.upper else None
            step = self.visit(index.step) if index.step else None
            return value[lower:upper:step]
        # 普通下标：a[0]
        return value[self.visit(index)]

    def generic_visit(self, node: ast.AST) -> Any:
        # 任何未覆盖的节点类型一律拒绝（import、属性访问、函数定义等）
        raise _SandboxError(f"禁止的操作: {type(node).__name__}")


def _ast_depth(node: ast.AST) -> int:
    """计算 AST 最大嵌套深度，用于拦截 RecursionError DoS。"""
    depth = 1
    for child in ast.iter_child_nodes(node):
        depth = max(depth, _ast_depth(child) + 1)
    return depth


def _safe_eval(code: str, env: dict[str, Any] | None = None) -> Any:
    """在沙箱中执行代码，返回最后一个表达式的结果。"""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        raise _SandboxError(f"语法错误: {e}") from e

    depth = _ast_depth(tree)
    if depth > _MAX_AST_DEPTH:
        raise _SandboxError(
            f"AST 嵌套深度 {depth} 超过上限 {_MAX_AST_DEPTH}（疑似 DoS）"
        )

    return SafeEvaluator(env or {}).run(tree)
    

class CodeExecTool(BaseTool):
    name = "code_exec"
    description = (
        "在安全沙箱中执行 Python 计算表达式。"
        "支持算术、比较、列表/字典/字符串操作，以及 abs/round/len/min/max/sum/int/float/str 等内置函数。"
        "禁止 import、网络、文件、属性访问。适合数值计算和数据转换。"
        "可通过 variables 参数传入上一步的数据。"
    )

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要执行的 Python 代码，如 'celsius * 1.8 + 32'",
                },
                "variables": {
                    "type": "object",
                    "description": "可选的变量字典，键名可在代码中直接使用",
                },
            },
            "required": ["code"],
        }

    async def execute(self, **kwargs) -> str:
        code = kwargs.get("code", "")
        variables = kwargs.get("variables")

        if not code:
            return "缺少 code 参数"
        if variables is not None and not isinstance(variables, dict):
            return "variables 必须是对象"

        try:
            # 复制一份 env，避免污染
            result = _safe_eval(code, dict(variables or {}))
            return f"结果: {result!r}"
        except _SandboxError as e:
            return f"沙箱拒绝执行: {e}"
        except Exception as e:
            return f"执行出错: {e}"


registry.register(CodeExecTool())
