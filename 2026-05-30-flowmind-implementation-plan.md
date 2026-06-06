# FlowMind 实施计划

> **模式**：你写代码，我引导方向 + review。每完成一步告诉我，我检查后进入下一步。

---

## 项目目录结构（最终目标）

```
flowmind/
├── backend/                    # Python 后端
│   ├── app/
│   │   ├── main.py            # FastAPI 入口
│   │   ├── config.py          # 配置管理
│   │   ├── database.py        # 数据库连接
│   │   ├── models/            # SQLAlchemy 模型
│   │   │   ├── user.py
│   │   │   ├── workflow.py
│   │   │   └── execution.py
│   │   ├── schemas/           # Pydantic 请求/响应模型
│   │   │   ├── auth.py
│   │   │   ├── workflow.py
│   │   │   └── execution.py
│   │   ├── routers/           # API 路由
│   │   │   ├── auth.py
│   │   │   ├── workflows.py
│   │   │   ├── executions.py
│   │   │   └── tools.py
│   │   ├── services/          # 业务逻辑
│   │   │   ├── auth_service.py
│   │   │   ├── agent_engine.py
│   │   │   ├── workflow_engine.py
│   │   │   └── execution_engine.py
│   │   ├── tools/             # 内置工具
│   │   │   ├── base.py
│   │   │   ├── web_search.py
│   │   │   ├── http_request.py
│   │   │   ├── email_send.py
│   │   │   └── code_exec.py
│   │   └── tasks/             # Celery 异步任务
│   │       └── workflow_tasks.py
│   ├── alembic/               # 数据库迁移
│   ├── alembic.ini
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                   # Next.js 前端
│   ├── src/
│   │   ├── app/               # App Router 页面
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx       # 首页/重定向
│   │   │   ├── login/
│   │   │   ├── dashboard/
│   │   │   ├── chat/
│   │   │   └── workflows/
│   │   │       └── [id]/
│   │   │           ├── edit/
│   │   │           └── run/
│   │   ├── components/        # 可复用组件
│   │   │   ├── ui/            # 基础 UI 组件
│   │   │   ├── workflow/      # 工作流相关组件
│   │   │   └── chat/          # 聊天相关组件
│   │   ├── lib/               # 工具函数
│   │   │   ├── api.ts         # API 客户端
│   │   │   └── auth.ts        # 认证工具
│   │   └── types/             # TypeScript 类型
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Step 1: 项目脚手架 + Docker 环境

**目标**：搭建项目骨架，Docker Compose 能跑起来，前后端能互相通信。

### 你需要做的事：

#### 1.1 创建项目根目录

```bash
mkdir flowmind && cd flowmind
```

#### 1.2 创建 docker-compose.yml

在项目根目录创建 `docker-compose.yml`，包含以下服务：
- `postgres`: PostgreSQL 15，暴露 5432 端口，设置环境变量 POSTGRES_DB=flowmind
- `redis`: Redis 7，暴露 6379 端口
- `api`: 后端服务，build context 为 `./backend`，暴露 8000 端口，depends_on postgres 和 redis
- `web`: 前端服务，build context 为 `./frontend`，暴露 3000 端口，depends_on api

**关键点**：
- 使用 `volumes` 持久化 PostgreSQL 数据
- 所有服务放到同一个 `network`
- 使用 `.env` 文件管理环境变量

#### 1.3 搭建后端骨架 (backend/)

```bash
mkdir -p backend/app
cd backend
```

创建 `requirements.txt`，包含核心依赖：
- `fastapi` + `uvicorn` (Web框架)
- `sqlalchemy` + `asyncpg` (ORM + 异步PostgreSQL驱动)
- `alembic` (数据库迁移)
- `celery` + `redis` (异步任务)
- `python-jose` + `passlib` (JWT + 密码哈希)
- `httpx` (异步HTTP客户端)
- `pydantic` + `pydantic-settings` (数据验证 + 配置)
- `openai` (兼容Qwen的DashScope API)

创建 `app/main.py`：
- FastAPI 应用实例
- CORS 中间件（允许前端跨域）
- `/api/health` 健康检查端点
- lifespan 事件（启动时连接数据库，关闭时断开）

创建 `app/config.py`：
- 使用 `pydantic-settings` 的 `BaseSettings`
- 从环境变量读取：DATABASE_URL, REDIS_URL, DASHSCOPE_API_KEY, JWT_SECRET
- 创建 `.env.example` 列出所有需要的环境变量

创建 `backend/Dockerfile`：
- 基于 `python:3.12-slim`
- 安装依赖、复制代码
- CMD 启动 uvicorn

#### 1.4 搭建前端骨架 (frontend/)

```bash
npx create-next-app@latest frontend --typescript --tailwind --app --src-dir
```

创建 `frontend/Dockerfile`：
- 多阶段构建（build → production）
- 基于 `node:20-alpine`

#### 1.5 创建 .env.example

在项目根目录：
```
POSTGRES_DB=flowmind
POSTGRES_USER=flowmind
POSTGRES_PASSWORD=your_password_here

DATABASE_URL=postgresql+asyncpg://flowmind:your_password_here@postgres:5432/flowmind
REDIS_URL=redis://redis:6379/0

DASHSCOPE_API_KEY=your_dashscope_api_key
JWT_SECRET=your_jwt_secret_here
JWT_ALGORITHM=HS256
```

### 验证标准

1. `docker-compose up --build` 能成功启动所有服务
2. 访问 `http://localhost:8000/api/health` 返回 `{"status": "ok"}`
3. 访问 `http://localhost:3000` 能看到 Next.js 默认页面

### 完成后告诉我，我会检查你的代码并给出 Step 2 的指引。

---

## Step 2: 数据库模型 + 迁移

**目标**：定义所有数据表，Alembic 迁移能正确创建表。

### 你需要做的事：

#### 2.1 配置 SQLAlchemy

创建 `app/database.py`：
- `async_sessionmaker` 创建异步 session
- `Base = declarative_base()` 定义模型基类
- `get_db()` 依赖注入函数（yield session）

#### 2.2 创建数据模型

创建 `app/models/` 目录，按以下结构定义模型：

**user.py** - User 模型：
- id (UUID, 主键)
- email (String, unique, indexed)
- password_hash (String)
- created_at (DateTime, 默认 now)

**workflow.py** - Workflow + Step + Schedule 模型：
- Workflow: id, user_id(FK), name, description, dag_json(JSON), status(draft/active/paused), created_at, updated_at
- Step: id, workflow_id(FK), type(trigger/tool/condition/approval), tool_name(nullable), config_json(JSON), position_json(JSON), order(Integer)
- Schedule: id, workflow_id(FK), cron_expr(String), next_run(DateTime), enabled(Boolean)

**execution.py** - Execution + StepExecution + ApprovalRequest 模型：
- Execution: id, workflow_id(FK), status(pending/running/success/failed), started_at, finished_at, result_json(JSON)
- StepExecution: id, execution_id(FK), step_id(FK), status, input_json, output_json, started_at, finished_at, error_message
- ApprovalRequest: id, execution_id(FK), step_id(FK), status(pending/approved/rejected), requested_at, resolved_at, resolver_id(FK User)

#### 2.3 配置 Alembic

```bash
cd backend
alembic init alembic
```

- 修改 `alembic/env.py`：导入你的 Base，设置 `target_metadata = Base.metadata`
- 修改 `alembic.ini`：设置 `sqlalchemy.url` 从环境变量读取
- 生成迁移：`alembic revision --autogenerate -m "initial tables"`
- 执行迁移：`alembic upgrade head`

### 验证标准

1. `alembic upgrade head` 成功执行
2. 用 `psql` 或 pgAdmin 查看数据库，确认所有表和关系正确创建
3. 外键约束存在，索引正确

### 完成后告诉我。

---

## Step 3: 用户认证 (JWT)

**目标**：实现注册、登录、获取当前用户，前端能调用API完成认证流程。

### 你需要做的事：

#### 3.1 后端认证

创建 `app/schemas/auth.py` (Pydantic schemas)：
- RegisterRequest: email, password
- LoginRequest: email, password
- TokenResponse: access_token, token_type
- UserResponse: id, email, created_at

创建 `app/services/auth_service.py`：
- `hash_password(password)` → 使用 passlib 的 bcrypt
- `verify_password(plain, hashed)` → 验证密码
- `create_access_token(user_id)` → 使用 python-jose 生成 JWT，设置过期时间
- `get_current_user(token)` → 从 JWT 解析用户，查数据库返回 User 对象

创建 `app/routers/auth.py`：
- `POST /api/auth/register` → 创建用户，返回 token
- `POST /api/auth/login` → 验证密码，返回 token
- `GET /api/auth/me` → 需要认证，返回当前用户信息

在 `main.py` 中注册路由：`app.include_router(auth_router, prefix="/api/auth", tags=["auth"])`

#### 3.2 前端认证

创建 `src/lib/api.ts`：
- 封装 fetch，自动带上 Authorization header
- 统一错误处理

创建 `src/lib/auth.ts`：
- `login(email, password)` → 调用API，存 token 到 localStorage
- `register(email, password)` → 调用API，存 token
- `logout()` → 清除 token
- `getToken()` → 获取当前 token

创建登录页面 `src/app/login/page.tsx`：
- 简洁的登录/注册表单
- 登录成功后跳转到 `/dashboard`

创建 `src/app/layout.tsx` 的基础布局：
- 导航栏（根据登录状态显示不同菜单）

### 验证标准

1. 能注册新用户
2. 能登录获取 token
3. 用 token 调用 `/api/auth/me` 返回用户信息
4. 前端登录后跳转到 dashboard

### 完成后告诉我。

---

## Step 4: Qwen API 集成 + Agent 引擎

**目标**：后端能调用 Qwen 模型，实现 ReAct Agent 循环，能流式返回结果。

### 你需要做的事：

#### 4.1 Qwen API 客户端

Qwen 的 DashScope API 兼容 OpenAI SDK 格式，所以可以直接用 `openai` 库：

创建 `app/services/llm_client.py`：
```python
from openai import OpenAI

client = OpenAI(
    api_key=settings.DASHSCOPE_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible_mode/v1"
)

# 模型选择：
# qwen-turbo - 便宜快速，日常对话
# qwen-plus  - 平衡，复杂推理
# qwen-max   - 最强，Agent核心推理用
```

#### 4.2 ReAct Agent 引擎

创建 `app/services/agent_engine.py`：

核心是 ReAct 循环：
```
循环:
  1. 思考 (Thought): LLM 分析当前状态，决定下一步
  2. 行动 (Action): 选择一个工具并执行
  3. 观察 (Observation): 获取工具执行结果
  4. 如果任务完成 → 返回最终结果
  5. 如果未完成 → 把 Observation 加入上下文，回到步骤1
```

关键设计：
- **System Prompt**: 定义 Agent 的角色、可用工具列表、输出格式
- **工具描述**: 每个工具的 name + description + parameters (JSON Schema)
- **Function Calling**: 使用 Qwen 的 tool_choice 功能让模型选择工具
- **最大迭代次数**: 防止死循环（建议 10 次）
- **流式输出**: 使用 SSE (Server-Sent Events) 逐步返回 Agent 的思考过程

#### 4.3 工具基础框架

创建 `app/tools/base.py`：
- `BaseTool` 抽象基类
  - `name`: 工具名称
  - `description`: 工具描述
  - `parameters`: JSON Schema 格式的参数定义
  - `execute(**kwargs) -> str`: 执行方法，返回结果字符串
- `ToolRegistry`: 工具注册中心
  - `register(tool)`: 注册工具
  - `get(name)`: 获取工具
  - `get_all_schemas()`: 获取所有工具的 schema（传给 LLM）

#### 4.4 实现第一个工具：WebSearch

创建 `app/tools/web_search.py`：
- 继承 `BaseTool`
- 使用 DuckDuckGo 搜索（免费，无需 API key）
- 依赖：`duckduckgo-search` 库
- 返回搜索结果摘要

#### 4.5 测试 Agent 引擎

创建 `app/routers/chat.py`：
- `POST /api/chat` 接收用户消息
- 内部调用 Agent 引擎
- **先不用 SSE**，用普通 JSON 响应测试基本功能
- 返回 Agent 的完整对话过程（thoughts, actions, observations, final_answer）

### 验证标准

1. 给 Agent 一个简单任务（如"搜索 Python 最新版本"），能正确调用搜索工具并返回结果
2. Agent 能完成多步任务（如"搜索今天的天气，然后计算华氏温度"）
3. 达到最大迭代次数时优雅退出

### 完成后告诉我。

---

## Step 5: 工作流引擎核心

**目标**：Agent 能从自然语言生成工作流 DAG，工作流可以存储到数据库并执行。

### 你需要做的事：

#### 5.1 工作流 DAG 数据结构

定义工作流的 JSON 格式：
```json
{
  "name": "竞品价格监控",
  "description": "每天查竞品价格...",
  "steps": [
    {
      "id": "step_1",
      "type": "trigger",
      "config": {"schedule": "0 9 * * *"},
      "next": ["step_2"]
    },
    {
      "id": "step_2",
      "type": "tool",
      "tool_name": "web_search",
      "config": {"query": "竞品价格"},
      "next": ["step_3"]
    },
    {
      "id": "step_3",
      "type": "condition",
      "config": {"field": "$step_2.result", "operator": "contains", "value": "降价"},
      "next_yes": ["step_4"],
      "next_no": []
    },
    {
      "id": "step_4",
      "type": "tool",
      "tool_name": "email_send",
      "config": {"to": "user@example.com", "subject": "竞品降价通知"}
    }
  ]
}
```

#### 5.2 DAG 生成 (通过 LLM)

创建 `app/services/workflow_engine.py`：

添加一个专门的 Prompt，让 Qwen 从自然语言生成上述 JSON 格式的工作流 DAG：
- System Prompt 中包含所有可用的工具及其参数 schema
- 要求 LLM 输出严格的 JSON 格式
- 后端验证生成的 JSON 格式是否合法
- 验证通过后存入数据库

#### 5.3 工作流执行引擎

在 `app/services/execution_engine.py` 中：
- `execute_workflow(workflow_id)` → 从数据库加载 DAG，拓扑排序，逐步执行
- 每个步骤：读取配置 → 调用对应工具 → 记录结果到 StepExecution
- 条件节点：根据配置判断走哪个分支
- 状态管理：更新 Execution 和 StepExecution 的状态

#### 5.4 工作流 API

创建 `app/routers/workflows.py`：
- `GET /api/workflows` → 列出当前用户的工作流
- `POST /api/workflows` → 从自然语言创建（调用 LLM 生成 DAG → 存储）
- `GET /api/workflows/:id` → 获取工作流详情
- `PUT /api/workflows/:id` → 编辑工作流
- `DELETE /api/workflows/:id` → 删除工作流

创建 `app/routers/executions.py`：
- `POST /api/workflows/:id/execute` → 触发执行
- `GET /api/executions/:id` → 获取执行状态和每步结果

### 验证标准

1. 输入自然语言，能生成合法的工作流 JSON
2. 工作流能正确存储到数据库
3. 手动触发执行，每步状态正确更新
4. 条件分支能正确判断走向

### 完成后告诉我。

---

## Step 6: 前端 Dashboard + Chat UI

**目标**：前端有完整的交互界面，能对话创建工作流，查看工作流列表。

### 你需要做的事：

#### 6.1 API 客户端完善

完善 `src/lib/api.ts`：
- 封装所有后端 API 调用
- 统一的错误处理和 token 刷新

#### 6.2 Dashboard 页面

创建 `src/app/dashboard/page.tsx`：
- 工作流卡片列表（名称、状态、最近执行时间）
- "新建工作流"按钮 → 跳转到 /chat
- 快速操作：编辑、执行、删除

#### 6.3 Chat 页面（核心交互）

创建 `src/app/chat/page.tsx`：
- 聊天界面：用户输入自然语言
- 消息气泡：显示 Agent 的思考过程
- **关键**：调用 `POST /api/workflows` 创建工作流后，展示生成的工作流预览
- 确认按钮 → 保存工作流 → 跳转到编辑器

创建 `src/components/chat/` 目录：
- `ChatMessage.tsx` - 单条消息组件
- `ChatInput.tsx` - 输入框组件
- `WorkflowPreview.tsx` - 工作流预览卡片

### 验证标准

1. 在 Chat 页面输入自然语言，能看到 AI 回复
2. AI 能生成工作流并在页面预览
3. Dashboard 正确显示所有工作流

### 完成后告诉我。

---

## Step 7: React Flow 可视化编辑器

**目标**：工作流以 DAG 图形展示，可拖拽编辑节点。

### 你需要做的事：

#### 7.1 安装 React Flow

```bash
npm install reactflow
```

#### 7.2 自定义节点类型

创建 `src/components/workflow/` 目录：
- `TriggerNode.tsx` - 触发器节点（时钟图标）
- `ToolNode.tsx` - 工具节点（显示工具名和参数）
- `ConditionNode.tsx` - 条件分支节点（菱形）
- `ApprovalNode.tsx` - 审批节点（人物图标）

#### 7.3 工作流编辑器页面

创建 `src/app/workflows/[id]/edit/page.tsx`：
- 加载工作流数据，转换为 React Flow 格式（nodes + edges）
- 自定义节点的渲染
- 支持拖拽调整位置
- 侧边栏：点击节点显示参数编辑面板
- 保存按钮 → PUT 请求更新工作流

#### 7.4 执行监控页面

创建 `src/app/workflows/[id]/run/page.tsx`：
- 复用编辑器的 DAG 展示
- 每个节点根据 StepExecution 状态显示颜色（灰=待执行，蓝=执行中，绿=成功，红=失败）
- 底部显示执行日志

### 验证标准

1. 工作流以 DAG 图形正确展示
2. 不同类型节点有不同外观
3. 点击节点能编辑参数
4. 执行状态通过颜色直观展示

### 完成后告诉我。

---

## Step 8: 流式响应 + WebSocket

**目标**：Agent 对话改为 SSE 流式推送，工作流执行状态实时更新。

### 你需要做的事：

#### 8.1 后端 SSE 流式

修改 `app/routers/chat.py`：
- 使用 FastAPI 的 `StreamingResponse`
- Agent 每完成一个 thought/action/observation 就推送一个 SSE 事件
- 事件格式：`event: thought|action|observation|final\ndata: {...}`

修改 `app/services/agent_engine.py`：
- 改为 async generator
- 每次 yield 一个事件对象

#### 8.2 WebSocket 执行推送

在 `app/routers/executions.py` 添加 WebSocket 端点：
- `WS /ws/executions/:id` → 实时推送执行状态变更
- 当 StepExecution 状态变更时，通过 Redis pub/sub 通知
- 前端连接后实时更新节点颜色

#### 8.3 前端对接

- Chat 页面使用 EventSource API 接收 SSE
- 执行监控页面使用 WebSocket 接收状态更新
- 实时更新 UI（打字机效果 + 节点颜色变化）

### 验证标准

1. Chat 页面 Agent 回复有打字机效果
2. 执行工作流时，节点颜色实时变化
3. 网络断开后 WebSocket 能自动重连

### 完成后告诉我。

---

## Step 9: 更多工具 + 人工审批

**目标**：实现所有内置工具，添加人工审批机制。

### 你需要做的事：

#### 9.1 实现剩余工具

- `app/tools/http_request.py`: 使用 httpx 发送 GET/POST/PUT/DELETE 请求
- `app/tools/email_send.py`: 使用 aiosmtplib 发送邮件（可先 mock）
- `app/tools/code_exec.py`: 使用 RestrictedPython 在沙箱中执行简单计算

#### 9.2 人工审批

修改执行引擎：
- 遇到 approval 类型节点时，暂停执行
- 创建 ApprovalRequest 记录
- 通过 WebSocket 通知前端
- 创建审批 API：
  - `GET /api/approvals/pending` → 列出待审批项
  - `POST /api/approvals/:id/approve` → 通过，继续执行
  - `POST /api/approvals/:id/reject` → 拒绝，中止工作流

创建前端审批页面 `src/app/approvals/page.tsx`：
- 列出待审批项
- 显示审批上下文（哪个工作流、哪一步、输入数据是什么）
- 通过/拒绝按钮

### 验证标准

1. 工作流包含审批节点时，执行到该节点暂停
2. 审批通过后工作流继续执行
3. 审批拒绝后工作流正确中止

### 完成后告诉我。

---

## Step 10: Celery 定时调度

**目标**：工作流支持 cron 定时执行。

### 你需要做的事：

#### 10.1 Celery 配置

创建 `app/tasks/celery_app.py`：
- 配置 Celery broker=Redis, backend=Redis
- 注册任务模块

创建 `app/tasks/workflow_tasks.py`：
- `execute_workflow_task(workflow_id)` → Celery 任务，调用执行引擎
- `schedule_workflow(workflow_id, cron_expr)` → 动态添加定时任务

#### 10.2 调度管理

修改工作流 API：
- 创建/更新工作流时，如果有 schedule 配置，自动注册 Celery Beat 定时任务
- 删除工作流时，移除对应定时任务
- 暂停/恢复定时任务

#### 10.3 Docker 更新

在 `docker-compose.yml` 添加：
- `worker` 服务：运行 Celery worker
- `beat` 服务：运行 Celery Beat 调度器

### 验证标准

1. 设置一个每分钟执行的工作流，能自动触发
2. 暂停后不再触发
3. Worker 日志中能看到任务执行记录

### 完成后告诉我。

---

## Step 11: 生产化 + 部署

**目标**：添加日志、监控、CI/CD，部署上线。

### 你需要做的事：

#### 11.1 结构化日志

- 使用 `structlog` 替代 print
- JSON 格式日志，包含 request_id、user_id、workflow_id
- 不同级别：DEBUG(开发), INFO(生产), WARNING, ERROR

#### 11.2 错误处理

- 全局异常处理器（FastAPI exception_handler）
- Agent 执行超时处理
- 工具执行失败重试（指数退避）
- 优雅关闭（处理中的任务完成后再退出）

#### 11.3 CI/CD

创建 `.github/workflows/ci.yml`：
- Push 时自动运行：lint (ruff) + 类型检查 (mypy) + 测试 (pytest)
- PR 时同样触发
- Main 分支 push 时自动部署到 Railway

#### 11.4 部署

- Railway 账号 + 连接 GitHub 仓库
- 配置环境变量
- 添加自定义域名（可选）
- 确保 HTTPS

#### 11.5 README

- 项目介绍 + 架构图
- 本地开发指南
- 技术亮点列表
- 在线 Demo 链接
- 截图/录屏

### 验证标准

1. CI pipeline 绿色通过
2. 线上 Demo 可以正常访问和使用
3. README 清晰展示项目价值
4. 面试官能自己注册、创建工作流、看到执行结果

### 完成后告诉我。

---

## 面试准备清单

项目完成后，准备好以下问题的回答：

1. **架构**：为什么选择这个架构？有哪些权衡？
2. **Agent**：ReAct 循环怎么实现的？如何防止死循环？工具选择怎么做？
3. **工作流**：DAG 怎么存储和执行的？并行节点怎么处理？
4. **数据库**：为什么这样设计表结构？索引怎么加的？
5. **缓存**：Redis 在项目中有哪些用途？
6. **安全**：JWT 怎么实现的？工具沙箱怎么做的？
7. **部署**：Docker 化有什么好处？CI/CD 流程是怎样的？
8. **监控**：出了问题怎么排查？日志怎么组织？
9. **性能**：如果用户量增大，哪些地方会成为瓶颈？怎么优化？
10. **AI**：Prompt 怎么设计的？Token 怎么控制？模型选择怎么做的？
