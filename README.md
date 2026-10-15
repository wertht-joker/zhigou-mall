# 企业知识库系统（RAG · 多租户 · 混合检索）

基于 **FastAPI + LangChain + Milvus + DeepSeek + PostgreSQL/Redis** 的企业级知识库系统：
多格式文档入库、**带引用来源的智能问答**、**完整多租户隔离**、**角色/权限**、**混合检索（向量 + BM25 + RRF）**、
结构化日志与 `trace_id` 可观测、Alembic 迁移、Docker Compose 与 CI。

> 完整需求见 [需求文档.md](./需求文档.md)　|　部署与面试演示见 [部署与演示说明.md](./部署与演示说明.md)

---

## 一、功能特性

**检索与问答**
- **Agent 智能问答（ReAct + Function Calling）**：模型自主决定调哪个工具、调几轮，再汇总回答
- **混合检索**：向量语义召回 + BM25 关键词召回，用 **RRF** 融合；`hybrid_retrieval_enabled=false` 可回退纯向量
- **可配置 Rerank**：`none`（不精排）/ `always`（总是精排）/ `conditional`（候选数达阈值才精排）
- **查询缓存**：查询向量与检索结果进 Redis（键含 `tenant_id + query + 参数`，带 TTL）
- 答案**附带引用来源**，可溯源到原文片段
- 多格式文档入库：PDF / Word / Excel / Markdown，自动解析、切分、向量化

**多租户与权限**
- **完整多租户**：`tenants` 表 + 各业务表 `tenant_id` + 复合索引；JWT 携带 `tenant_id`；
  仓储层**强制**按租户过滤；Milvus 采用**单集合 + `partition_key`（tenant_id）**，检索/删除带 `expr` 隔离
- **角色 → 权限点**：`admin`（文档/分类/反馈/租户）/ `editor`（文档/分类）/ `viewer`（仅问答）；`require_permission(...)` 依赖工厂
- 登录返回租户信息，前端按租户展示数据空间

**工程化与可观测**
- **分层架构**：`api`（路由）→ `services`（业务）→ `repositories`（数据访问）→ `models`
- **统一响应契约** `{code, message, data, trace_id}` + 全局异常处理器（真实 HTTP 状态码，路由无散落 `try/except`）
- **结构化 JSON 日志** + `X-Request-ID` → `trace_id` 全链路透传（纯 ASGI 中间件，不影响 SSE）
- **Redis 令牌桶限流**（Lua 脚本，Redis 不可用时降级为进程内实现）
- **Alembic 迁移**：启动自动 `upgrade head`；模型变更可 `autogenerate`
- **健康检查**：`/health`（liveness）+ `/health/ready`（探 DB / Milvus / Redis）
- **Docker Compose** 一键起 PostgreSQL + Redis + Milvus + 后端 + 前端；**GitHub Actions** 跑测试
- **检索评测**：`evals/` 提供 hit rate / MRR / recall@k 指标脚本（mock 模型，CI 可离线跑）

---

## 二、技术栈

| 组件 | 选型 | 说明 |
|---|---|---|
| 后端框架 | FastAPI | 异步、自动生成 OpenAPI 文档 |
| 分层 | api / services / repositories / models | 路由不碰 ORM，业务不拼响应结构 |
| 关系库 | PostgreSQL（默认 SQLite 可回退） | 元数据、租户、权限、订单 |
| 迁移 | Alembic | 启动自动 `upgrade head`，历史库自动 stamp |
| 缓存 / 限流 | Redis（不可用时自动降级） | 查询缓存 + 令牌桶限流 |
| 向量库 | Milvus（Docker 部署） | 单集合 + partition_key 隔离租户 |
| RAG 框架 | LangChain | 文本加载与切分 |
| 混合检索 | jieba + rank_bm25 + RRF | 关键词通路与向量通路融合 |
| 对话模型 | DeepSeek（deepseek-chat） | OpenAI 兼容接口，带指数退避重试 |
| Embedding | sentence-transformers（BAAI/bge-base-zh-v1.5） | 本地向量化，免 API Key |
| Rerank | BGE-reranker（可配置开关） | 二阶段精排 |
| 文档解析 | PyMuPDF / python-docx / openpyxl | 分格式解析，表格结构化 |
| 前端 | Vue3 + Element Plus | 问答界面 + 管理后台 |
| 可观测 | 结构化 JSON 日志 + trace_id | 每请求一条访问日志，响应头回写 `X-Request-ID` |
| 测试 | pytest（内存 SQLite + 全打桩） | 不联网、不依赖真实模型，CI 可跑 |

---

## 三、目录结构

```
knowledge-base
├── 需求文档.md
├── 部署与演示说明.md
├── docker-compose.yml            # postgres + redis + milvus + backend + frontend
├── .github/workflows/ci.yml      # CI：pytest（全打桩）
├── samples/客服FAQ.md
├── backend/
│   ├── requirements.txt
│   ├── alembic/                  # 数据库迁移（versions/ 含基线 + 多租户）
│   ├── evals/                    # ★ 检索评测：dataset.json + run_eval.py
│   ├── tests/                    # ★ 52 个用例（内存库 + 全打桩）
│   └── app/
│       ├── main.py               # 入口：迁移 + 默认租户/管理员/演示订单 + 路由注册
│       ├── core/                 # config / errors / response / logging / middleware / redis / rate_limit / migrations
│       ├── models/               # SQLAlchemy 模型（tenant + 各业务表均带 tenant_id）
│       ├── schemas/              # Pydantic 请求/响应模型
│       ├── repositories/         # ★ 数据访问层：统一 scoped()/apply_tenant() 强制租户过滤
│       ├── services/             # ★ 业务编排：文档/问答/会话/反馈/分类/租户/工具/订单源
│       ├── utils/security.py     # JWT：payload 含 user_id / role / tenant_id
│       ├── api/                  # 路由：health/documents/chat/sessions/feedback/categories/tenants/auth
│       └── rag/                  # ★ RAG 链路
│           ├── loader.py         #   文档解析（四格式）
│           ├── splitter.py       #   文本切分
│           ├── embedding.py      #   BGE 向量化
│           ├── vector_store.py   #   Milvus（tenant_id 分区键 + fetch_chunks 供 BM25）
│           ├── bm25.py           #   BM25 关键词通路（jieba + rank_bm25）
│           ├── fusion.py         #   RRF 融合多路召回
│           ├── retriever.py      #   混合召回 + RRF + rerank + 缓存
│           ├── reranker.py       #   BGE-reranker 精排
│           └── generator.py      #   DeepSeek 生成（含重试）
└── frontend/                     # Vue3 前端（登录带租户编码、展示当前租户）
```

---

## 四、环境准备

- Python 3.10+
- Node.js 18+（前端）
- Docker Desktop（PostgreSQL / Redis / Milvus）
- DeepSeek API Key（platform.deepseek.com）

> **零依赖也能跑**：不配 PostgreSQL/Redis 时，后端默认回退 **SQLite**，缓存的限流自动降级为进程内实现，
> 只有 Milvus 是必须的（向量检索）。

---

## 五、启动步骤

### 1. 安装依赖

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r requirements.txt  # 首次拉 torch，约 200MB，耐心等
```

### 2. 配置环境变量

```bash
copy .env.example .env
```

编辑 `.env`，至少填入 DeepSeek Key（`DEEPSEEK_API_KEY`）。可选：
`DATABASE_URL` 切 PostgreSQL、`REDIS_URL` 指 Redis、`MILVUS_COLLECTION` 指明新集合。
如需接入真实订单，再按[「订单数据源接入」](#订单数据源接入)配好 `ORDER_*` 项。

### 3. 启动依赖（Docker）

```bash
# 回到项目根目录
cd ..
docker compose up -d postgres redis milvus   # 只起依赖，后端本地跑（便于调试）
docker compose ps                            # 确认容器 healthy
```

> 想一键起全套（含后端 + 前端）：`docker compose up -d`，前端在 http://localhost:8080。

### 4. 启动后端

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

启动时会自动：**执行 Alembic 迁移** → 创建**默认租户** → 创建默认管理员 → 写入演示订单。

### 5. 启动前端（Vue3）

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 http://localhost:5173（开发服务器已配置代理，自动转发 /api 到后端）。

> npm 安装慢/失败时，先换镜像：`npm config set registry https://registry.npmmirror.com`

### 6. 验证

- 前端页面：http://localhost:5173
- 存活探针：http://localhost:8000/api/v1/health
- **就绪探针**：http://localhost:8000/api/v1/health/ready（探 DB + Milvus + Redis）
- 接口文档：http://localhost:8000/docs

---

## 六、接口列表

统一前缀 `/api/v1`，响应结构 `{ code, message, data, trace_id }`，
**失败不再返回 HTTP 200 + code 500**，而是真实状态码（400/401/403/404/409/429/500/503）。

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | /health | 存活探针 | 公开 |
| GET | /health/ready | 就绪探针（DB/Milvus/Redis） | 公开 |
| POST | /auth/register | 注册（body 含可选 `tenant_code`，留空=默认租户） | 公开 |
| POST | /auth/login | 登录，返回 `token + user + tenant` | 公开 |
| GET | /tenants | 租户列表 | `tenant:manage`（admin） |
| POST | /documents/upload | 上传文档（multipart，file 字段） | `document:manage` |
| GET | /documents | 文档列表（仅本租户） | `document:manage` |
| DELETE | /documents/{id} | 删除文档（同步删向量） | `document:manage` |
| POST | /chat | 智能问答（body: `{"question","session_id"}` 续接多轮） | 登录 |
| POST | /chat/stream | 流式问答（SSE） | 登录 |
| GET | /sessions | 会话列表（仅本租户） | 登录 |
| GET | /sessions/{id}/messages | 会话消息（跨租户返回 404） | 登录 |
| POST | /feedback | 回答反馈（`{"message_id","type":"up"/"down"}`） | 登录 |
| GET | /feedback/stats | 反馈统计 | `feedback:view` |
| GET / POST | /categories | 分类列表 / 新增 | `category:manage` |
| PUT / DELETE | /categories/{id} | 分类修改 / 删除 | `category:manage` |

### 统一错误示例

```json
{
  "code": 403,
  "message": "需要权限：document:manage",
  "data": null,
  "trace_id": "8f2c1e0b9d4a4b0e"
}
```

响应头同时回写 `X-Request-ID: 8f2c1e0b9d4a4b0e`，可据此在日志里检索整条请求链路。

---

## 七、账号、租户与权限

- **默认租户**：`default`（默认租户，首次启动自动创建）；各表历史数据迁移时统一归入该租户
- **默认管理员**：**admin / admin123**（在默认租户下自动创建）

| 角色 | 权限点 | 能做什么 |
|---|---|---|
| `admin` | `document:manage`、`category:manage`、`feedback:view`、`tenant:manage` | 知识库全管理 + 查看反馈 + 租户门面 |
| `editor` | `document:manage`、`category:manage` | 上传/删除文档、管理分类 |
| `viewer`（含历史 `user`） | 无 | 问答、查看会话、反馈 |

> 除注册/登录与健康检查外，所有接口需带 `Authorization: Bearer <token>`；权限不足返回 403。

### 多租户隔离怎么用

1. 登录/注册时可传 `tenant_code`（前端登录页有「租户编码」输入框），留空使用默认租户；
2. 登录返回租户信息，前端在顶栏展示当前租户名；
3. 后端从 JWT 解析 `tenant_id` → `get_current_tenant` → 仓储层强制 `where tenant_id = ?`；
4. 向量库检索/删除带 `expr: tenant_id == x`，**A 租户的文档与问答结果对 B 租户完全不可见**。

---

## 八、使用流程

```
1. 上传文档：POST /documents/upload
   → 解析（四格式） → 切分 chunk → BGE 向量化 → 写入 Milvus（带 tenant_id 分区）
2. 提问：POST /chat（或 /chat/stream）
   → Agent 决定是否调工具 → 混合召回（向量 + BM25） → RRF 融合 → rerank 精排
   → 拼 prompt（带原文片段） → DeepSeek 生成 → 返回答案 + 引用来源
```

> 前端聊天页默认走 `/chat/stream` 流式接口，答案逐字显示。
> 流式事件共 4 种：`step`（Agent 正在调用某工具，前端渲染成灰色步骤标签）、
> `meta`（会话 ID + 引用来源）、`delta`（答案增量）、`done`（结束 + 消息 ID）。

### 检索链路可控开关

| 配置项 | 取值 | 作用 |
|---|---|---|
| `HYBRID_RETRIEVAL_ENABLED` | true / false | 是否启用 BM25 关键词通路（false=纯向量） |
| `RERANK_STRATEGY` | none / always / conditional | 是否精排、以及是否按候选数触发 |
| `RETRIEVAL_CACHE_ENABLED` | true / false | 查询向量/检索结果是否走 Redis 缓存 |
| `RRF_K` | int（默认 60） | RRF 融合平滑参数 |

### Agent 工具

| 工具 | 作用 | 触发场景 |
|---|---|---|
| `search_knowledge_base` | 混合检索知识库（按租户隔离） | 产品、售后、物流、积分、公司介绍等企业知识 |
| `query_order` | 按订单号查状态与物流（按租户隔离） | 询问某个具体订单的进度 |

### 订单数据源接入

`query_order` 不绑死数据源，由 `ORDER_PROVIDER` 在两种实现间切换（见 `app/services/order_provider.py`）：

| 取值 | 实现 | 说明 |
|---|---|---|
| `local`（默认） | `LocalDbOrderProvider` | 查关系库 `orders` 表（演示订单，开箱即用） |
| `openapi` | `OpenApiOrderProvider` | 调用第三方电商平台 OpenAPI，查**真实订单** |

> 演示订单（仅 `local` 模式）：`DD20260901001`（已发货）、`DD20260912002`（已完成）、`DD20260920003`（待付款），首次启动自动写入默认租户。

**接入真实订单**：拿到平台凭证后只改 `.env`，业务代码无需改动：

```ini
ORDER_PROVIDER=openapi
ORDER_API_BASE_URL=https://open.example-mall.com
ORDER_API_ORDER_PATH=/open/orders/{order_no}
ORDER_APP_KEY=你的app_key
ORDER_ACCESS_TOKEN=你的access_token
ORDER_API_TIMEOUT=5
```

**接口约定**（通用 REST 约定，平台不同只需改两个地方）：

- **请求**：`GET {ORDER_API_BASE_URL}{ORDER_API_ORDER_PATH}`，订单号作路径参数，同时以查询参数带 `order_no`、`access_token`；请求头带 `X-App-Key`
- **响应**：沿用统一结构 `{"code": 0, "message": "ok", "data": {...}}`，`code` 为 0 视为成功
- **字段**：`data` 内为 `order_no` / `product_name` / `amount` / `status` / `logistics`
- **适配点**：① 平台要求签名 → 在 `_build_params` 补签名；② 字段名不同 → 在 `_to_order_info` 改映射

**设计要点**：订单查询失败（未配置、超时、鉴权失败、平台返回错误）一律返回明确失败提示，**不会静默降级到演示数据**；`ORDER_PROVIDER` 配了未知值也会直接报错而非回退。

---

## 九、检索质量评测

`backend/evals/` 提供一套可复现的评测：`dataset.json` 存「问题 → 期望命中文档」，
`run_eval.py` 用 mock 向量 + mock reranker 跑完整「混合召回 → RRF → rerank」链路，
输出 **hit rate / MRR / recall@k**。

```bash
cd backend
python -m evals.run_eval
```

输出示例（当前小语料，4 条 query）：

```json
{
  "queries": 4,
  "top_k": 3,
  "hit_rate": 1.0,
  "mrr": 1.0,
  "recall_at_k": 1.0
}
```

> 评测不依赖真实 Milvus / BGE，CI 与无网环境都能跑；把 mock 换成真实模型即可用于线上评测。

---

## 十、测试

```bash
cd backend
python -m pytest -q      # 52 passed
```

- 测试用**内存 SQLite（StaticPool）**覆盖 `get_db`，**打桩** LLM / Milvus / BGE / 上传目录，不联网；
- 覆盖：接口冒烟、统一错误契约、`trace_id` 可观测、订单 Provider、**多租户隔离**、**混合检索/RRF/rerank/评测**。

## 十一、当前进度

- [x] M1 项目骨架
- [x] M2 文档管理（上传/解析/向量化入库）
- [x] M3 RAG 问答（检索 + 生成 + 引用溯源）
- [x] M4 多轮对话 + 反馈 + 分类
- [x] M5 前端（Vue3）
- [x] **R1 分层解耦 + 统一响应与异常**
- [x] **R2 工程化：Alembic + PostgreSQL + 结构化日志/trace_id + Redis/限流 + Docker/CI + 重试**
- [x] **R3 完整多租户 + 角色/权限 + Milvus 租户隔离**
- [x] **R4 混合检索（向量+BM25+RRF）+ 可配置 rerank + 查询缓存 + 评测指标**

---

## 面试高频问题（结合本项目）

> 面试官会围绕你简历上的这个知识库项目追问，以下问题建议都能用自己的话讲清楚。

### RAG 基础

**Q1：什么是 RAG？为什么需要它？**
RAG（检索增强生成）＝ 先检索、后生成。传统大模型有「幻觉」问题（会编造不存在的内容），且不知道企业私有知识。RAG 先从企业自己的知识库检索相关片段，再把片段拼进 prompt 让大模型基于真实资料回答，既解决了幻觉，又能回答私有领域问题，还能给出引用来源。

**Q2：这个项目 RAG 的完整流程？**
文档上传 → 解析（PDF/Word/Excel/Markdown）→ 切分 chunk → BGE 向量化 → 存入 Milvus；提问时：向量召回 + BM25 关键词召回 → RRF 融合 → Rerank 精排取 top-k → 拼 prompt → DeepSeek 流式生成 → 返回答案 + 引用来源。

**Q3：为什么用 Milvus？和 Chroma/FAISS 有什么区别？**
Milvus 是企业级分布式向量数据库，支持海量向量、高并发、持久化，适合生产环境；Chroma 是轻量嵌入式，适合本地开发/小数据；FAISS 是向量检索库，不是数据库，需要自己管理存储。选 Milvus 是为了贴近企业级生产架构。

**Q4：Embedding 为什么用本地 BGE 模型？**
① 数据不出内网，保护企业隐私；② 零 API 费用；③ BGE 中文语义效果好。代价是要本地加载模型、首次下载较大。

**Q5：如何解决大模型幻觉？**
三道防线：① system prompt 明确约束「只根据知识内容回答，没有就说未找到」；② 检索不到时直接返回"未找到"，不让模型自由发挥；③ 答案附带引用来源，可溯源。

**Q6：多轮对话怎么处理"那这个呢"这种指代？**
Agent 版把历史对话直接放进 messages，让模型在生成 `tool_calls` 时自己决定检索用的 query —— 改写动作被吸收进模型推理里。并在工具描述里写明「query 必须是完整独立、不含指代的问题，例如『那多久到账』应改写为『退货退款多久到账』」，用工具描述引导模型产出高质量检索词。

**Q7：什么是 Rerank？为什么需要？**
向量检索（双塔模型）速度快但精度一般，召回 top20 后，用 Rerank 模型（CrossEncoder，query 和 passage 一起算相关度）对这 20 条精排，取最相关的 top-k。两阶段检索「召回 + 精排」能明显提升答案准确率。本项目 Rerank 策略可配：`always` 总是精排、`conditional` 候选数达阈值才精排、`none` 关闭。

**Q8：流式输出怎么实现？**
后端用 DeepSeek 的 stream 模式，FastAPI 用 `StreamingResponse` 以 SSE（text/event-stream）逐段返回；前端用 `fetch` + `ReadableStream` 边读边渲染。`trace_id` 中间件用**纯 ASGI** 实现而非 `BaseHTTPMiddleware`，避免包装层缓冲影响 SSE 实时性。

**Q9：文档切分（chunk）的策略？**
用 `RecursiveCharacterTextSplitter`，按段落/换行/中文标点（。！？）优先切分，chunk 大小 500 字 + 10% 重叠，避免把一个完整语义切断。

**Q10：向量相似度怎么算？**
Embedding 把文本映射成 768 维向量，相似度用余弦相似度（归一化后即内积）。Milvus 里建索引时指定 `metric_type=COSINE`，检索时返回相似度最高的 top-K。

**Q11：文档更新或删除后怎么处理？**
删除文档时同步删除 Milvus 里的向量（按 `doc_id` + `tenant_id` 过滤删除）。更新文档则删除旧向量后重新解析入库。元数据存关系库，向量存 Milvus，两边通过 `doc_id` 关联。

### 检索质量（企业级）

**Q12：为什么要做混合检索？纯向量不够吗？**
纯向量擅长「语义相近」，但对**精确关键词**（型号、专有名词、代码、订单号）容易漏召；BM25 关键词通路正好互补。两者用 **RRF** 融合后召回更稳。这也是「企业级 RAG」与「demo 级 RAG」最明显的分水岭之一。

**Q13：什么是 RRF？为什么不用加权求和？**
RRF（Reciprocal Rank Fusion）公式 `score(d) = Σ 1/(k + rank_i(d))`，**只看每条通路里的排名，不看分数绝对值**。因为向量分数（余弦）和 BM25 分数（TF-IDF 量纲）不可比，归一化又容易受异常值影响；RRF 天然规避了「跨通路分数量纲」问题，简单且稳健。`k` 通常取 60。

**Q14：为什么 BM25 语料要按租户拉？**
BM25 是**全语料统计**（IDF 依赖文档总数与词频），如果跨租户混算，不仅会串数据，还会让租户的分数受别人文档影响。所以 `fetch_chunks` 带 `tenant_id`，语料严格限定本租户。

**Q15：检索质量怎么度量？**
`evals/` 里有 question→期望文档 的评测集，脚本算三个指标：**hit rate**（top-k 里有没有命中）、**MRR**（第一个正确结果排名的倒数，衡量「排得靠不靠前」）、**recall@k**（召回了多少应召回的）。CI 里用 mock 向量/mock reranker 保证可离线复现，换真实模型即可用于版本对比与回归。

**Q16：查询缓存会不会导致数据串租户或读到过期结果？**
缓存键是 `tenant_id + query + top_k + 检索参数` 的哈希，**租户维度已在键里**，不会串；同时带 TTL（默认 300s），且文档增删时旧键自然过期。Redis 不可用时缓存直接跳过，不影响功能。

### 架构与工程化

**Q17：项目的分层是怎么设计的？**
`api`（路由：鉴权、参数、响应组装）→ `services`（业务编排：事务、跨模块协作）→ `repositories`（数据访问：查询构造、租户过滤）→ `models`（ORM）。**约束**：路由不直接碰 ORM，业务不手拼响应结构，仓储是唯一拼 SQL/ORM 查询的地方。好处是换存储、加过滤、写单测都只改一层。

**Q18：为什么失败返回真实 HTTP 状态码，而不是 200 + code 500？**
旧写法「HTTP 200 + body 里 code 500」让网关、监控、前端拦截器都无法用标准状态码判断成败。改造后：业务代码只抛 `AppError` 子类（`NotFoundError`/`ForbiddenError`/`ConflictError`…），**全局异常处理器**统一映射成真实状态码 + `{code,message,data,trace_id}`，路由层不再散落 `try/except`。

**Q19：trace_id 是怎么串起整条链路的？**
纯 ASGI 中间件从 `X-Request-ID` 请求头读取上游 id（没有则生成），写入 `scope["state"]`，响应头回写。结构化日志、错误响应体都带同一个 `trace_id`，出问题时用它能一次性捞出该请求的全部日志。

**Q20：限流怎么实现的？Redis 挂了会怎样？**
Redis 令牌桶（Lua 脚本保证「取令牌 + 补令牌」原子性），按用户维度限流重接口（chat/upload）。Redis 不可用时自动降级为**进程内 MemoryTokenBucket**，绝不让「本地没起 Redis」阻断演示。

**Q21：数据库迁移是怎么管的？**
Alembic。启动时自动 `alembic upgrade head`；对「已有数据但没迁移记录」的历史库会先 `stamp head` 再升级。测试用 `create_all` 建表，不依赖迁移。SQLite 与 PostgreSQL 差异用 `render_as_batch` 处理。

**Q22：健康检查为什么分两个接口？**
`/health`（liveness）只判断进程活着，不探外部依赖——否则依赖抖动会导致容器被反复重启；`/health/ready`（readiness）探 DB + Milvus + Redis，未就绪返回 503，让负载均衡把流量摘走。Redis/LLM 未配置算「可降级项」，不算不就绪。

### 多租户与权限

**Q23：多租户是怎么做的？为什么选「单库 + tenant_id」而不是每租户一个库/schema？**
租户信息存 `tenants` 表，业务表统一加 `tenant_id` 并建 `tenant_id + 业务键` 复合索引。链路是：JWT 携带 `tenant_id` → `get_current_tenant` 依赖 → 仓储层**强制** `where tenant_id = ?`。
不选「每租户独立库/schema」是因为：动态建库/迁移代价高、跨租户运营查询困难；而 `tenant_id` 过滤 + 索引在**演示与中小规模**下足够，未来要隔离升级也只需改数据源路由，不动业务代码。

**Q24：怎么保证租户隔离不会漏？**
四道保险：① `repositories/base.py` 统一提供 `scoped()/apply_tenant()`，查询必须过这一层；② 会话/消息这类间接资源先校验归属（跨租户读消息直接 404，不泄露「存在性」）；③ Milvus 用 `partition_key`（tenant_id），检索/删除都带 `expr`；④ 有**专门的隔离测试**（A 租户看不到 B 的文档/会话/检索结果）。

**Q25：Milvus 怎么做租户隔离？**
**单集合 + `partition_key`**：集合里加 `tenant_id` 字段并设为分区键，检索 `expr: tenant_id == x`。相比每租户独立集合，免去动态建表/建索引、元数据规模可控，且未来可平滑升级为按租户命名集合。注意加分区键是**破坏性变更**，所以改了集合名（`kb_documents_v2`），旧集合需 drop 或忽略、新集合需清库重灌。

**Q26：权限怎么设计的？为什么不用一个大而全的 RBAC？**
用「角色 → 权限点」映射 + `require_permission("document:manage")` 依赖工厂：路由上声明需要哪个权限点，角色不含就 403。相比完整 RBAC（权限表 + 角色表 + 关联表 + 管理界面）更轻，符合本项目规模；扩展时只需在 `ROLE_PERMISSIONS` 里加权限点。历史 `user` 角色等同 `viewer`，保证老数据平滑。

**Q27：登录时怎么确定用户属于哪个租户？**
请求带可选 `tenant_code`（前端登录页有输入框，留空=默认租户），后端 `resolve_tenant` 定位租户，注册/登录都限定在该租户内，登录返回 `token + user + tenant`。历史用户由迁移统一回填到默认租户，所以老数据、老前端仍能跑。

### Agent 部分

**Q28：什么是 Function Calling（工具调用）？**
大模型本身只会生成文本，不能查数据库、调接口。Function Calling 是让它具备"调用外部能力"的机制：开发者用 JSON Schema 声明有哪些工具、各自要什么参数，随请求一起发给模型；模型判断需要时**不直接回答**，而是返回结构化的 `tool_calls`（工具名 + 参数 JSON）；程序执行后把结果回传，模型再基于结果继续推理或作答。本项目用 DeepSeek 的 function calling 声明了 `search_knowledge_base` 和 `query_order` 两个工具。

**Q29：什么是 ReAct？你的 Agent 循环怎么实现的？**
ReAct = Reasoning + Acting，让模型"边想边做"：推理该用什么工具 → 执行 → 观察结果 → 再推理，循环直到能作答。实现是一个 for 循环（上限 `agent_max_steps` 轮）：把 system + 历史 + 当前问题发给模型 → 若返回 `tool_calls` 就执行工具、把结果以 `tool` 角色追加进 messages、进入下一轮 → 若模型不再调工具，说明它准备作答，退出循环，最后流式输出答案。

**Q30：怎么防止模型无限调用工具？**
两层防护：① **硬上限** —— 循环最多 `agent_max_steps`（5）轮，超了强制退出，用已拿到的工具结果生成答案；② **提示词约束** —— system prompt 里明确「不需要查资料的问题直接回答」。此外工具自身要做参数校验（订单号为空直接返回提示，不查库）。

**Q31：工具执行的结果怎么让模型知道？**
把结果作为一条 `role="tool"` 的消息追加进 messages，并带上 `tool_call_id` 对应上模型那次调用。assistant 消息里的 `tool_calls` 有 id，`tool` 消息必须用同一个 id 回填，模型才知道"哪个调用的结果是这个"。

**Q32：Agent 版和之前的 RAG 版有什么本质区别？**
RAG 版是**写死的流水线**：不管问什么都走「改写 → 检索 → 生成」。Agent 版把「要不要检索、检索什么」的决定权交给模型：问「你好」直接回答，问订单就查订单表，问政策才检索知识库。区别在于**控制流由模型产生，而不是代码写死**——这才是 Agent 和普通 LLM 应用的分界线。代价是延迟变高，所以简单问题要尽量避免绕路。

**Q33：Agent 的中间步骤怎么让用户看到？**
后端在每次执行工具前，通过 SSE 推一条 `step` 事件（如「🛠 检索知识库：退货政策」）。前端把标签追加到该条消息的 steps 数组，渲染成气泡上方的灰色小标签。既是等待反馈，也是 Agent 可解释性的一部分。

**Q34：订单查询为什么抽象成 Provider？接真实订单怎么做的？**
把「订单数据从哪来」和「Agent 怎么用订单结果」解耦：`OrderProvider` 只定义 `query(order_no, tenant_id) -> OrderInfo | None`，本地演示库、第三方平台 OpenAPI 各是一个实现，由 `ORDER_PROVIDER` 配置切换 —— 典型的**适配器模式**。接真实平台只改两处：`_to_order_info`（字段映射）和 `_build_params`（平台签名）。两个取舍：**失败不降级**（超时/鉴权失败返回明确错误，不悄悄回退演示数据）；**配置错误要吵闹**（`ORDER_PROVIDER` 写错直接报错）。

**Q35：这个系统还能怎么改进？**
① **异步解析**：大文档解析/向量化放到任务队列，不阻塞上传请求（当前刻意不引入 Celery/MQ，保持演示轻量）；② **细粒度 RBAC + SSO/审计日志**；③ **Milvus 内建 sparse 向量**替代内存 BM25 语料，支持更大规模；④ **评测接入 LLM 打分**（答案正确性、忠实度）做端到端评估；⑤ **按租户独立向量集群**以满足强隔离合规场景。

---

## 首次运行说明

- **BGE 模型下载**：首次调用向量化会从 HuggingFace 下载模型（约 400MB）。代码已内置 `hf-mirror.com` 镜像加速。
- **Milvus 镜像拉取**：首次 `docker compose up` 拉取镜像较大，国内可在 Docker Desktop 里配置镜像加速。
- **新集合名**：多租户改造后集合改为 `kb_documents_v2`（新增 `tenant_id` 分区键）。若你之前跑过旧版，请忽略/手动 drop 旧集合 `kb_documents` 并重新上传文档。
