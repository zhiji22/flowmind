# FlowMind 部署指南（Railway）

> 目标：把后端 API、前端、PostgreSQL、Redis、Celery worker/beat 全部上线，HTTPS 可访问。

## 架构：Railway 多服务

Railway 支持 docker-compose 部署，每个 service 一个容器：

| 服务 | 来源 | 说明 |
|---|---|---|
| postgres | Railway 内置数据库插件 | 或用 Railway PostgreSQL |
| redis | Railway 内置 Redis 插件 | |
| api | `backend/Dockerfile` | FastAPI |
| web | `frontend/Dockerfile` | Next.js standalone |
| worker | `backend/Dockerfile` + command | Celery worker |
| beat | `backend/Dockerfile` + command | Celery beat |

## 步骤

### 1. 准备仓库

确认代码已推到 GitHub（`main` 分支）。

### 2. Railway 创建项目

1. 登录 [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. 选择仓库，Railway 会识别 `docker-compose.yml`
3. 添加两个内置插件：
   - **Add Database → PostgreSQL**
   - **Add Database → Redis**

### 3. 配置环境变量

在 Railway 的每个服务（或 Variables）中设置（参考 `.env.example`）：

**必填：**
```
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>:5432/<db>   # 用 Railway 提供的 PG 连接串
REDIS_URL=redis://:<pass>@<host>:6379   # Railway Redis 连接串
DASHSCOPE_API_KEY=<你的 key>
JWT_SECRET=<生成的 64 字节 hex>
```

**重要：** `DATABASE_URL` 要把 Railway 给的 `postgresql://` 改成 `postgresql+asyncpg://`（asyncpg 驱动）。

**可选：**
```
CORS_ALLOW_ORIGINS=https://你的前端域名
SMTP_HOST/PORT/USER/PASSWORD/FROM   # 启用邮件工具时
TAVILY_API_KEY                       # 启用 Tavily 搜索时
APP_ENV=production
```

### 4. 配置 Celery worker / beat

这两个服务复用 backend 镜像，但 command 不同。在 Railway 对应 service 设置：

- **worker**: 启动命令 = `celery -A app.tasks.celery_app.celery_app worker --loglevel=info`
- **beat**: 启动命令 = `celery -A app.tasks.celery_app.celery_app beat --loglevel=info`

### 5. 配置前端 API 地址

`web` 服务的 `API_URL` 设为 Railway 给 api 服务的**内部地址**：
```
API_URL=http://api.railway.internal:8000
```
（Next.js rewrite 代理 `/api/*` 到后端；前端运行时只暴露自己的域名。）

### 6. 生成域名 + HTTPS

- 在 `web` 和 `api` service → Settings → Networking → Generate Domain
- Railway 自动提供 `*.up.railway.app` 子域名 + HTTPS
- 如有自定义域名，在 Domains 里绑定（自动签发证书）

### 7. 验证

- 访问前端域名 → 注册登录 → 创建工作流 → 执行
- `https://<api域名>/api/health` 返回 `{"status":"ok"}`
- 查看 Logs：每个请求日志带 `request_id`，JSON 格式

## 成本参考

| 项目 | 月费 |
|---|---|
| Railway（Hobby 计划 $5，含 $5 额度） | ~$5 |
| DashScope（qwen-turbo 很便宜） | ~$5-15 |
| **合计** | **~$10-20** |

## 常见问题

**Q: 数据库连接失败？**
A: 确认 `DATABASE_URL` 用的是 `postgresql+asyncpg://` 前缀。

**Q: Celery 任务不执行？**
A: 检查 worker/beat 日志；确认 `REDIS_URL` 与 api 用的是同一个 Redis。

**Q: 前端调 API 报 CORS？**
A: `CORS_ALLOW_ORIGINS` 要包含前端域名（逗号分隔）。

**Q: WebSocket 连不上？**
A: 前端 `NEXT_PUBLIC_WS_URL` 要设成 `wss://<api域名>`（注意是 wss + 实际域名，不能走 Next.js 代理）。
