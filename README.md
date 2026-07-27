# JavCode — 个人 AV 影片收藏

输入番号，从 **JavDB** / **JavLibrary** 检索元数据，自动分类、打标签，并翻译为**简体中文**；本地收藏支持按番号、女优、标签快速查找。

## 功能

- 番号检索 → 解析标题 / 女优 / 标签 / 封面等
- 自动分类与标签增强（片商、前缀、共演、年份等）
- 繁体 → 简体（zhconv）；日文等需 **AI** 翻译为简体中文
- **AI API**：配置 Key 后，用大模型翻译标题/女优、分类、打标签（OpenAI 兼容，含 xAI Grok）
- 本地 SQLite 收藏库
- 搜索：番号、女优、标签
- 资料库 / 女优列表分页
- 详情页观看入口（MissAV / Jable 按番号搜索）

## 快速开始

```bash
cd /root/javcode
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

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

环境变量：

| 变量 | 说明 |
|------|------|
| `JAVCODE_DB` | SQLite 路径（默认 `data/collection.db`） |
| `JAVCODE_HOST` / `JAVCODE_PORT` | 服务监听 |
| `JAVCODE_AI_API_KEY` | AI API Key（也识别 `XAI_API_KEY` / `OPENAI_API_KEY`） |
| `JAVCODE_AI_BASE_URL` | Chat Completions 基址，默认 `https://api.x.ai/v1` |
| `JAVCODE_AI_MODEL` | 模型名，默认 `grok-2-latest` |
| `JAVCODE_AI_ENABLED` | `0` 强制关闭 AI；有 Key 时默认开启 |
| `JAVCODE_AI_TIMEOUT` | 请求超时秒数（默认 60） |
| `JAVCODE_PROXY` | 全局 HTTP/HTTPS 代理 |
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
  fetchers.py       # 在线 HTTP（JavDB / JavLibrary）
  parsers.py        # HTML 解析
  translate.py      # 繁体→简体
  classify.py       # 规则分类 / 标签
  ai.py             # AI 翻译 / 分类
  enrich.py         # enrichment 管道
  store.py          # SQLite
  settings.py       # 设置覆盖
  auth.py           # 管理员鉴权
  search.py         # 过滤
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
