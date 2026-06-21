# FlowMind — AI 智能工作流平台

> 用自然语言描述任务，AI 自动生成可视化工作流 DAG，确认后执行。支持定时触发、人工审批、实时监控。

一个用于展示企业级 AI 应用全栈能力的项目：从对话式创建 → 可视化编辑 → DAG 执行引擎 → 实时监控 → 定时调度，完整覆盖一个生产级 AI 产品的核心链路。

## ✨ 核心特性

- **对话式创建**：自然语言 → LLM 生成结构化工作流 DAG
- **ReAct Agent**：思考 → 行动 → 观察循环，工具调用 + 流式输出
- **可视化编辑器**：基于 React Flow 的 DAG，节点可拖拽、参数可编辑
- **DAG 执行引擎**：拓扑排序、条件分支、并行执行、失败重试、断点续跑
- **执行监控**：Celery 异步执行 + 前端轮询，节点状态按执行进度着色（成功/失败/跳过）
- **人工审批**：执行到审批节点暂停，通过/拒绝后断点续跑
- **定时调度**：Celery Beat + 数据库驱动，cron 表达式
- **内置工具**：Web 搜索、HTTP 请求（SSRF 防护）、邮件、代码沙箱（AST 白名单）
- **生产级**：结构化日志、CI/CD、Docker 化、优雅关闭

## 🏗️ 架构

```
┌────────────┐     ┌──────────────────────────────────┐
│  Next.js   │────▶│           FastAPI (async)         │
│  React     │ SSE │  ┌───────────┐  ┌──────────────┐  │
│  React Flow│◀───│  │  Agent    │  │ Execution    │  │
└────────────┘Poll│  │  Engine   │  │ Engine (DAG) │  │
                  │  └─────┬─────┘  └──────┬───────┘  │
                  │        │               │          │
                  │   ┌────▼───────────────▼────┐     │
                  │   │   工具集 (web/http/...) │     │
                  │   └─────────────────────────┘     │
                  └───┬──────────────┬────────────────┘
                      │              │
                ┌─────▼─────┐  ┌─────▼─────┐  ┌──────────┐
                │ PostgreSQL│  │   Redis   │  │  Qwen    │
                │  (持久化) │  │ (队列/Pub)│  │ (DashScope)│
                └───────────┘  └─────┬─────┘  └──────────┘
                                     │
                              ┌──────▼──────┐
                              │ Celery      │
                              │ worker+beat │
                              └─────────────┘
```

## 🛠️ 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Next.js (App Router) + React Flow + Tailwind CSS |
| 后端 | FastAPI + SQLAlchemy (async) + Pydantic |
| 数据库 | PostgreSQL 15 |
| 缓存/队列 | Redis 7 |
| 任务队列 | Celery + Beat |
| LLM | 通义千问 Qwen (DashScope，兼容 OpenAI SDK) |
| 部署 | Docker Compose / Railway |
| CI/CD | GitHub Actions |

## 🚀 本地开发

### 前置

- Docker + Docker Compose
- DashScope API Key（[阿里云百炼](https://bailian.console.aliyun.com/)）

### 步骤

```bash
# 1. 克隆
git clone https://github.com/zhiji22/flowmind.git
cd flowmind

# 2. 配置环境变量
cp .env.example .env
#   填入 DASHSCOPE_API_KEY，生成 JWT_SECRET：
#   python -c "import secrets;print(secrets.token_hex(48))"

# 3. 一键启动所有服务
docker-compose up -d --build

# 4. 访问
#   前端：http://localhost:3000
#   API 文档：http://localhost:8001/docs
```

### 本地非 Docker 开发

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001

# 前端
cd frontend
npm install
npm run dev

# Celery（新终端）
celery -A app.tasks.celery_app.celery_app worker --loglevel=info
celery -A app.tasks.celery_app.celery_app beat --loglevel=info
```

## 📁 项目结构

```
flowmind/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口 + 中间件
│   │   ├── config.py            # 配置（pydantic-settings）
│   │   ├── logging_config.py    # structlog 结构化日志
│   │   ├── models/              # SQLAlchemy 模型
│   │   ├── schemas/             # Pydantic 请求/响应
│   │   ├── routers/             # API 路由（auth/chat/workflows/executions/approvals）
│   │   ├── services/            # 业务逻辑（agent/workflow/execution/scheduler）
│   │   ├── tools/               # 内置工具（web_search/http_request/email/code_exec）
│   │   └── tasks/               # Celery 任务 + 调度
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/                 # 页面（login/dashboard/chat/workflows/approvals）
│       ├── components/          # 组件（chat/workflow）
│       └── lib/                 # API 客户端 + SSE 流式解析
├── docker-compose.yml
└── .env.example
```

## 📡 API 速览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` `/login` | 注册 / 登录 |
| POST | `/api/chat` | SSE 流式 Agent 对话 |
| GET/POST | `/api/workflows` | 列表 / 自然语言创建 |
| PUT/DELETE | `/api/workflows/{id}` | 编辑 / 删除 |
| POST | `/api/workflows/{id}/execute` | 触发执行（Celery 异步） |
| GET | `/api/executions/{id}` | 查询执行进度（前端轮询） |
| GET/POST | `/api/approvals` | 待审批 / 通过·拒绝 |
| POST | `/api/workflows/{id}/schedule` | 设置 cron 定时 |

完整文档：`http://localhost:8001/docs`

## 🔒 安全设计

- JWT 认证（密钥强度校验，弱密钥拒绝启动）
- `http_request` 工具 SSRF 防护（解析 IP，拒绝内网/环回）
- `code_exec` 工具 AST 白名单沙箱（禁 import/属性访问/文件）
- 输入校验（Pydantic）+ ORM 防 SQL 注入
- CORS 白名单 + 结构化错误（不泄露堆栈）

## 📈 可观测性

- 结构化日志（JSON，含 request_id）
- 全局异常处理 + request_id 追踪
- 每步执行输入/输出完整记录
- 健康检查端点 `/api/health`

## 🚢 部署

见 [DEPLOY.md](./DEPLOY.md)（Railway 完整流程）。

## 📝 License

MIT
