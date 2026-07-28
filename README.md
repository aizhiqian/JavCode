# JavCode — 个人 AV 影片收藏

输入番号，从 **JavDB** / **JavLibrary** 检索元数据，自动分类、打标签，并翻译为**简体中文**；本地收藏支持按番号、女优、标签快速查找。

## 功能

- 番号检索 → 解析标题 / 女优 / 标签 / 封面等
- 自动分类与标签增强（片商、前缀、共演、年份等）
- 繁体 → 简体（zhconv）；日文等需 **AI** 翻译为简体中文
- **AI API**：配置 Key 后，用大模型翻译标题/女优、分类、打标签（OpenAI 兼容，含 xAI Grok）
- 收藏库：默认 **SQLite**，可选 **MySQL** / **PostgreSQL**
- 搜索：番号、女优、标签
- 资料库 / 女优列表分页
- 详情页观看入口（MissAV / Jable 按番号搜索）

## 快速开始

### 本地 Python

```bash
cd /root/javcode
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# 使用 MySQL / PostgreSQL 时再装驱动：
# .venv/bin/pip install -r requirements-db.txt

# 启动 Web UI（默认 http://127.0.0.1:8765/）
.venv/bin/python run.py

# CLI：在线检索并收藏
.venv/bin/python -m src enrich SSIS-001

# 启用 AI 增强
export JAVCODE_AI_API_KEY=你的密钥
.venv/bin/python -m src enrich SSIS-001
.venv/bin/python -m src ai-status

# 搜索
.venv/bin/python -m src search --actress 葵つかさ
.venv/bin/python -m src search --tag 美乳
```

### Docker Compose 部署

1. 复制环境变量（可选，也可在 Web 设置页配置 AI / 代理）：

```bash
cp .env.example .env
# 编辑 .env 填入 JAVCODE_AI_API_KEY 等
```

2. **使用已发布镜像**（推荐；镜像在 GitHub Actions 中**手动**构建，见下文）：

```bash
# 公开包可直接拉；若 GHCR 包为 private，需先登录：
# echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

docker compose pull
docker compose up -d
```

3. **或本地构建**（不依赖 GHCR）：

```bash
docker compose up -d --build
```

访问 http://127.0.0.1:8765/ 。默认数据目录 `./data` 挂载到容器（SQLite）；设置与收藏写入同一数据库。

```bash
docker compose logs -f      # 日志
docker compose down         # 停止
```

**使用 MySQL / PostgreSQL：**

```bash
# 一并启动官方 MySQL 8 容器，应用连到它
# （compose 服务名 mysql/postgres 与 localhost 默认不强制 TLS）
JAVCODE_DB=mysql://javcode:javcode@mysql:3306/javcode \
  docker compose --profile mysql up -d

# 或 PostgreSQL 16
JAVCODE_DB=postgresql://javcode:javcode@postgres:5432/javcode \
  docker compose --profile postgres up -d
```

也可把 `JAVCODE_DB` 写进 `.env`，指向 Compose 内或**外部**数据库（如 Aiven）。首次连接会自动建表（`movies` / `app_meta`）。**远程 host 默认要求 TLS**；本地 / compose 服务名默认明文。可用 `?ssl=disable` 或 `?sslmode=require` 覆盖。

### 手动构建并推送镜像（GitHub Actions）

推送代码**不会**自动构建镜像。需要时在仓库页面：

1. **Actions** → **Build Docker Image** → **Run workflow**
2. 可选：自定义 tag（默认 `latest`）；`push` 默认开启
3. 产物推送到 GHCR：`ghcr.io/<owner>/javcode:<tag>` 与 `…:sha-<短 SHA>`

工作流文件：`.github/workflows/docker-image.yml`（仅 `workflow_dispatch`）。

环境变量：

| 变量 | 说明 |
|------|------|
| `JAVCODE_DB` | 数据库位置：SQLite 路径（默认 `data/collection.db`），或 `mysql://…` / `postgresql://…` URL（远程默认 TLS；localhost/compose 服务名默认明文；`?ssl=` / `?sslmode=` 可覆盖） |
| `JAVCODE_HOST` / `JAVCODE_PORT` | 服务监听 |
| `JAVCODE_AI_API_KEY` | AI API Key（也识别 `XAI_API_KEY` / `OPENAI_API_KEY`） |
| `JAVCODE_AI_BASE_URL` | Chat Completions 基址，默认 `https://api.x.ai/v1` |
| `JAVCODE_AI_MODEL` | 模型名，默认 `grok-2-latest` |
| `JAVCODE_AI_ENABLED` | `0` 强制关闭 AI；有 Key 时默认开启 |
| `JAVCODE_AI_TIMEOUT` | 请求超时秒数（默认 60） |
| `JAVCODE_PROXY` | 全局代理 URL（抓取 + AI；默认空=直连） |
| `JAVCODE_ADMIN_USERNAME` / `JAVCODE_ADMIN_PASSWORD` | 首次启动引导管理员 |

### 管理员与设置

- 首次打开 Web 需初始化唯一管理员。
- 登录后可访问资料库；未登录时 API 返回 401。
- **设置**页可改 AI Key、代理等，优先于 `.env`；清空某项并保存可回退 env。

### AI 翻译说明

1. 抓取并解析 JavDB / JavLibrary
2. zhconv 繁体 → 简体
3. 调用 AI（已配置且启用时）生成简体标题、女优译名、标签与分类
4. 规则分类 / 打标签补充

未配置 AI 或请求失败时，保留步骤 2 与 4 的结果。

## 架构

```
src/
  constants.py      # AI 等共享默认值（避免 settings↔ai 循环依赖）
  env.py            # .env 加载
  fetchers.py       # 在线 HTTP（JavDB / JavLibrary）
  parsers.py        # HTML 解析
  media.py          # 封面 URL 规范化（唯一实现）
  labels.py         # to_simplified / 标签去重合并
  translate.py      # 条目规范化（简繁 + cover + labels）
  classify.py       # 规则分类 / 标签
  ai.py             # AI 翻译 / 分类（AIConfig.resolve 单路径）
  enrich.py         # enrichment 管道
  db.py             # SQLite / MySQL / PostgreSQL 连接与 schema
  store.py          # 收藏持久化；写/读边界规范化 cover；search 门面
  settings.py       # 设置覆盖；resolve_proxy_dict（仅入口调用，注入 fetcher/AI）
  auth.py           # 管理员鉴权
  search.py         # 过滤（由 store 调用）
  relationships.py  # 女优索引 / 拼音
  server.py         # Flask API + 静态 UI
public/
  index.html
  js/               # ES modules：app 入口 setRoutes 接线；router 提供 goCatalog/goDetail
  css/              # base/layout/components 共享 + 按页面样式
```

## 测试

```bash
.venv/bin/pytest -q
```

## 非目标

不提供视频托管、流媒体、种子下载；不做多用户账号。
