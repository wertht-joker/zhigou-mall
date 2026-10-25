# 智购商城 · 多商家电商平台 + AI 智能客服（RAG · ReAct Agent · 混合检索）

基于 **FastAPI + LangChain + Milvus + DeepSeek + PostgreSQL/Redis + Vue3** 的京东风格电商平台：
**多商家入驻**、商品/购物车/订单全流程、**AI 智能客服**（查订单 / 商品导购 / 售后政策问答，答案带引用来源）、
**完整商家（多租户）隔离**、**混合检索（向量 + BM25 + RRF）**、结构化日志与 `trace_id` 可观测、Alembic 迁移、Docker Compose 与 CI。

> 本项目由「RAG 智能客服知识库」重构而来：多租户语义升级为**商家/店铺**，新增**电商交易域**，
> AI 客服 Agent 从 2 个工具扩展为 3 个工具（知识库检索 / 查我的订单 / 商品导购）。
> 完整需求见 [需求文档.md](./需求文档.md)　|　部署与面试演示见 [部署与演示说明.md](./部署与演示说明.md)

---

## 一、功能特性

**电商平台（业务域）**
- **商品与分类**：平台级商品分类导航 + 商家商品管理（上新/改价/库存/上下架），前台全平台浏览搜索
- **购物车**：加购自动合并数量、库存上限校验、修改/移除/清空
- **收货地址簿**：增删改查 + 默认地址，下单锁定地址快照
- **订单全状态机**：待付款 → 待发货 → 已发货 → 已完成（可取消/确认收货），下单扣库存、取消回补，
  订单明细保存商品名称/价格快照
- **商家发货**：商家（租户）只能看到并操作「包含本店商品」的订单，填写物流后流转状态
- **商家入驻**：注册即建店（自动创建租户 + 店铺管理员），店铺编码唯一

**AI 智能客服（RAG 核心）**
- **Agent 智能问答（ReAct + Function Calling）**：模型自主决定调哪个工具、调几轮，再汇总回答
- **三个工具**：
  | 工具 | 作用 | 触发场景 |
  |---|---|---|
  | `search_knowledge_base` | 混合检索平台知识库（按商家隔离） | 售后政策、退换货、物流、积分等规则类问题 |
  | `query_my_orders` | 查**当前顾客自己**的订单（可按单号精确查） | 「我买的到哪了」「帮我查下单」 |
  | `recommend_products` | 商品导购（关键词 + 预算过滤，只推真实在售商品） | 「有没有降噪耳机推荐」「两千预算买什么」 |
- **混合检索**：向量语义召回 + BM25 关键词召回，用 **RRF** 融合；`hybrid_retrieval_enabled=false` 可回退纯向量
- **可配置 Rerank**：`none`（不精排）/ `always`（总是精排）/ `conditional`（候选数达阈值才精排）
- **查询缓存**：查询向量与检索结果进 Redis（键含 `tenant_id + query + 参数`，带 TTL）
- 答案**附带引用来源**，可溯源到原文片段；前端 **AI 客服悬浮窗**全站可用（SSE 流式）

**商家（多租户）与权限**
- **完整多租户 = 多商家**：`tenants` 表（即店铺）+ 各业务表 `tenant_id` + 复合索引；JWT 携带 `tenant_id`；
  仓储层**强制**按租户过滤；Milvus 采用**单集合 + `partition_key`（tenant_id）**，检索/删除带 `expr` 隔离
- **角色 → 权限点**：`admin`（商家管理员：商品/订单/知识库/分类/反馈/租户）/ `editor`（商家运营）/ `customer`（顾客：逛商城下单，无管理权限）；`require_permission(...)` 依赖工厂
- 登录自动按用户名定位所属商家（用户名平台级唯一），顾客/商家都无需记忆租户编码

**工程化与可观测**
- **分层架构**：`api`（路由）→ `services`（业务）→ `repositories`（数据访问）→ `models`
- **统一响应契约** `{code, message, data, trace_id}` + 全局异常处理器（真实 HTTP 状态码，路由无散落 `try/except`）
- **结构化 JSON 日志** + `X-Request-ID` → `trace_id` 全链路透传（纯 ASGI 中间件，不影响 SSE）
- **Redis 令牌桶限流**（Lua 脚本，Redis 不可用时降级为进程内实现）
- **Alembic 迁移**：启动自动 `upgrade head`；电商表结构为独立 revision（`b4d8c2e61f07`）
- **健康检查**：`/health`（liveness）+ `/health/ready`（探 DB / Milvus / Redis）
- **Docker Compose** 一键起 PostgreSQL + Redis + Milvus + 后端 + 前端；**GitHub Actions** 跑测试
- **检索评测**：`evals/` 提供 hit rate / MRR / recall@k 指标脚本（mock 模型，CI 可离线跑）

---

## 二、技术栈

| 组件 | 选型 | 说明 |
|---|---|---|
| 后端框架 | FastAPI | 异步、自动生成 OpenAPI 文档 |
| 分层 | api / services / repositories / models | 路由不碰 ORM，业务不拼响应结构 |
| 关系库 | PostgreSQL（默认 SQLite 可回退） | 商品/订单/购物车/商家/用户/知识文档 |
| 迁移 | Alembic | 启动自动 `upgrade head`，历史库自动 stamp |
| 缓存 / 限流 | Redis（不可用时自动降级） | 查询缓存 + 令牌桶限流 |
| 向量库 | Milvus（Docker 部署） | 单集合 + partition_key 隔离商家 |
| RAG 框架 | LangChain | 文本加载与切分 |
| 混合检索 | jieba + rank_bm25 + RRF | 关键词通路与向量通路融合 |
| 对话模型 | DeepSeek（deepseek-chat） | OpenAI 兼容接口，带指数退避重试 |
| Embedding | sentence-transformers（BAAI/bge-base-zh-v1.5） | 本地向量化，免 API Key，延迟导入 |
| Rerank | BGE-reranker（可配置开关） | 二阶段精排 |
| 文档解析 | PyMuPDF / python-docx / openpyxl | 分格式解析，表格结构化 |
| 前端 | Vue3 + Element Plus | 京东红主题商城 + 商家后台 + AI 客服悬浮窗 |
| 可观测 | 结构化 JSON 日志 + trace_id | 每请求一条访问日志，响应头回写 `X-Request-ID` |
| 测试 | pytest（内存 SQLite + 全打桩） | 不联网、不依赖真实模型，CI 可跑（53 用例） |

---

## 三、目录结构

```
knowledge-base
├── 需求文档.md
├── 部署与演示说明.md
├── docker-compose.yml            # postgres + redis + milvus + backend + frontend
├── .github/workflows/ci.yml      # CI：pytest（全打桩）+ 前端构建
├── samples/                      # 平台知识库文档（启动时自动导入）
│   ├── 售后服务政策.md / 物流配送说明.md / 会员与积分.md ...
│   └── 智购商城购物指南.md
├── backend/
│   ├── requirements.txt
│   ├── alembic/                  # 迁移（基线 + 多租户 + 电商 schema）
│   ├── evals/                    # ★ 检索评测：dataset.json + run_eval.py
│   ├── tests/                    # ★ 53 个用例（内存库 + 全打桩，含电商全链路）
│   └── app/
│       ├── main.py               # 入口：迁移 + 商城演示数据种子 + 路由注册
│       ├── core/                 # config / errors / response / logging / middleware / redis / rate_limit / migrations
│       ├── models/               # product / product_category / cart / address / order(+item) / tenant / user / document ...
│       ├── schemas/              # Pydantic 请求/响应模型
│       ├── repositories/         # ★ 数据访问层：统一 scoped()/apply_tenant() 强制租户过滤
│       ├── services/             # ★ product / cart / address / order / auth / seed / 文档 / 问答 / 工具
│       ├── utils/security.py     # JWT：payload 含 user_id / role / tenant_id
│       ├── api/                  # 路由：products / cart / orders / addresses / chat / documents / auth / ...
│       └── rag/                  # ★ RAG 链路（loader/splitter/embedding/vector_store/bm25/fusion/retriever/reranker/generator）
└── frontend/                     # Vue3 京东风商城
    └── src/
        ├── components/           # MallLayout（顶栏+搜索+购物车）/ ProductCard / ChatWidget（AI 客服悬浮窗）
        ├── views/                # 登录 / 首页 / 搜索 / 详情 / 购物车 / 结算 / 我的订单
        └── views/admin/          # 商家后台：商品管理 / 订单发货 / 知识库 / 知识分类
```

---

## 四、环境准备

- Python 3.10+
- Node.js 18+（前端）
- Docker Desktop（PostgreSQL / Redis / Milvus）
- DeepSeek API Key（platform.deepseek.com）

> **零依赖也能跑**：不配 PostgreSQL/Redis 时，后端默认回退 **SQLite**，缓存与限流自动降级为进程内实现，
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

编辑 `.env`，至少填入 DeepSeek Key（`DEEPSEEK_API_KEY`）。

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

启动时会自动：**执行 Alembic 迁移** → 写入**商城演示数据**（两家店铺、12 件商品、
演示顾客的历史订单）→ 把 `samples/` 下的客服知识文档**自动导入平台知识库**。

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

## 六、演示账号

| 账号 | 密码 | 角色 | 说明 |
|---|---|---|---|
| `demo` | `demo123` | 顾客 | 有历史订单（已发货/已完成/待付款各一单），可直接演示 AI 客服查订单 |
| `admin` | `admin123` | 平台管理员 | 智购自营官方旗舰店（默认租户），商品/知识库/发货全权限 |
| `shop` | `shop123` | 商家管理员 | 星辰数码旗舰店（租户 `star`），演示多商家隔离 |

注册页可自助「顾客注册」或「商家入驻」（入驻自动建店 + 店铺管理员）。

---

## 七、接口列表

统一前缀 `/api/v1`，响应结构 `{ code, message, data, trace_id }`，
**失败返回真实状态码**（400/401/403/404/409/429/500/503）。

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | /health、/health/ready | 存活 / 就绪探针 | 公开 |
| POST | /auth/register | 注册：顾客（默认）/ 商家入驻（`register_type=merchant` + `merchant_name`） | 公开 |
| POST | /auth/login | 登录（无需租户编码，自动按用户名定位商家） | 公开 |
| GET | /tenants | 商家列表 | `tenant:manage`（admin） |
| GET | /products | 商品列表（公开，keyword/category_id 过滤，按销量排序） | 公开 |
| GET | /product-categories | 商品分类（公开，平台级） | 公开 |
| GET | /products/{id} | 商品详情 | 公开 |
| GET/POST/PUT/DELETE | /merchant/products | 商家商品管理（**仅本店**） | `product:manage` |
| GET/POST | /cart、/cart/items | 购物车查看 / 加购 / 改量 / 移除 | 登录（本人） |
| GET/POST/PUT/DELETE | /addresses | 收货地址簿 | 登录（本人） |
| POST | /orders | 下单（购物车条目 + 地址，扣库存、清购物车） | 登录（本人） |
| GET | /orders、/orders/{id} | 我的订单（列表/详情，**仅本人**） | 登录 |
| POST | /orders/{id}/pay · /cancel · /confirm | 支付 / 取消 / 确认收货 | 登录（本人） |
| GET | /merchant/orders | 商家订单列表（仅含本店商品的订单） | `order:manage` |
| POST | /merchant/orders/{id}/ship | 商家发货（填物流单号） | `order:manage` |
| POST | /chat、/chat/stream | AI 客服问答（SSE 流式） | 登录 |
| GET | /sessions、/sessions/{id}/messages | 会话与消息（跨商家 404） | 登录 |
| POST | /feedback、GET /feedback/stats | 客服回答反馈 / 统计 | 登录 / `feedback:view` |
| POST | /documents/upload、GET /documents | 知识库文档（AI 客服知识来源） | `document:manage` |

### 统一错误示例

```json
{
  "code": 403,
  "message": "需要权限：product:manage",
  "data": null,
  "trace_id": "8f2c1e0b9d4a4b0e"
}
```

响应头同时回写 `X-Request-ID: 8f2c1e0b9d4a4b0e`，可据此在日志里检索整条请求链路。

---

## 八、核心流程

```
顾客购物：首页/搜索 → 商品详情 → 加购 → 结算（地址快照 + 扣库存） → 支付 → 商家发货 → 确认收货

AI 客服：提问 → Agent 决定调哪个工具
  ├─ 规则类问题 → search_knowledge_base（向量+BM25 → RRF → rerank，按商家隔离）→ 带引用回答
  ├─ 查订单    → query_my_orders（限定当前 user_id，别人查不到你的单）
  └─ 求推荐    → recommend_products（在售商品 + 预算过滤，不编造商品）
→ DeepSeek 流式生成 → SSE 推送（step 工具步骤 / meta 引用 / delta 增量 / done）
```

### 检索链路可控开关

| 配置项 | 取值 | 作用 |
|---|---|---|
| `HYBRID_RETRIEVAL_ENABLED` | true / false | 是否启用 BM25 关键词通路（false=纯向量） |
| `RERANK_STRATEGY` | none / always / conditional | 是否精排、以及是否按候选数触发 |
| `RETRIEVAL_CACHE_ENABLED` | true / false | 查询向量/检索结果是否走 Redis 缓存 |
| `RRF_K` | int（默认 60） | RRF 融合平滑参数 |

---

## 九、检索质量评测

`backend/evals/` 提供一套可复现的评测：`dataset.json` 存「问题 → 期望命中文档」，
`run_eval.py` 用 mock 向量 + mock reranker 跑完整「混合召回 → RRF → rerank」链路，
输出 **hit rate / MRR / recall@k**。

```bash
cd backend
python -m evals.run_eval
```

> 评测不依赖真实 Milvus / BGE，CI 与无网环境都能跑；把 mock 换成真实模型即可用于线上评测。

---

## 十、测试

```bash
cd backend
python -m pytest -q      # 53 passed
```

- 测试用**内存 SQLite（StaticPool）**覆盖 `get_db`，**打桩** LLM / Milvus / BGE / 上传目录，不联网；
- 覆盖：接口冒烟、统一错误契约、`trace_id` 可观测、**电商全链路**（加购→下单→支付→发货→收货、
  库存扣减/回补、越权 404）、**商家隔离**（商品/订单/会话/检索）、**AI 客服工具**（查我的订单、
  商品导购、预算过滤）、多租户与权限、混合检索/RRF/rerank/评测。

---

## 十一、当前进度

- [x] M1 项目骨架（由知识库系统重构为电商平台）
- [x] M2 电商域：商品 / 购物车 / 地址 / 订单状态机 / 商家入驻
- [x] M3 AI 客服：3 工具 Agent（知识库 / 我的订单 / 商品导购）+ 引用溯源
- [x] M4 多商家隔离 + 角色权限（admin / editor / customer）
- [x] M5 京东风前端：商城 + 商家后台 + AI 客服悬浮窗
- [x] **R2 工程化：Alembic + PostgreSQL + 结构化日志/trace_id + Redis/限流 + Docker/CI + 重试**
- [x] **R4 混合检索（向量+BM25+RRF）+ 可配置 rerank + 查询缓存 + 评测指标**

---

## 面试高频问题（结合本项目）

### 电商业务

**Q1：订单状态机是怎么设计的？**
状态只有五个：待付款 → 待发货 → 已发货 → 已完成，外加待付款可取消、取消后「已取消」终态。
每个流转都在服务层独立方法里（`pay_order` / `ship_order` / `cancel_order` / `confirm_receive`），
方法内先校验当前状态是否允许流转，非法流转抛 400。不允许「跳状态」，比如只有待发货能发货、
只有已发货能确认收货——把业务规则集中在状态机里而不是散落在路由判断中。

**Q2：库存怎么保证不多扣不少扣？**
下单流程「先校验后扣减」：先遍历明细核对每件商品的库存与在售状态，任何一件不足就整体报错（不下单），
校验通过后统一扣减，再生成订单与明细。取消订单时按明细快照回补库存。演示规模下单行事务足够；
生产环境要防超卖可以把「校验 + 扣减」改成数据库条件更新（`update ... set stock=stock-n where stock>=n`）
或 Redis 预扣，这是量级驱动的一致性升级。

**Q3：订单为什么要存商品快照而不是外键引用？**
商品会改价、改名甚至下架删除，历史订单必须忠实反映「成交那一刻」的信息。所以订单明细冗余了
`product_name / price / image` 快照，同时保留 `product_id` 便于售后定位商品，`merchant_id`
便于商家圈定自己的订单。这是电商系统「快照 vs 引用」的经典取舍。

**Q4：多商家是怎么隔离的？和 SaaS 多租户什么关系？**
本项目里**商家 = 租户**（`tenants` 表即店铺表）。商品管理、知识库、商家订单都按 `tenant_id` 强制过滤
（仓储层统一 `scoped()`），前台商品浏览则是刻意的跨租户（真实商城就是全平台逛）。商家发货前会校验
订单明细里是否包含本店商品（`OrderItem.merchant_id`），不包含返回 403。AI 客服的订单工具只认
JWT 里的 `user_id`——顾客永远只能查到自己的单。

**Q5：下单时的地址为什么要快照？**
地址簿是可变的（用户随时改、删地址），订单收货信息不能跟着变。下单时把 `receiver / phone / region + detail`
拼成完整地址写进订单，之后地址簿的任何变化都不影响已提交订单。

**Q6：支付是真实的吗？**
是**模拟支付**：`POST /orders/{id}/pay` 把待付款订单流转为待发货。真实接入时只需在这一步对接
支付网关（下单→预支付→异步回调→验签→流转状态），状态机与回调幂等的设计已预留。

### RAG 与 AI 客服

**Q7：AI 客服为什么用 Agent 而不是写死的 RAG 流水线？**
客服问题分三类：规则类（要查知识库）、订单类（要查订单表）、导购类（要搜商品）。写死的流水线
对每个问题都走「检索 → 生成」，查订单和求推荐根本不该检索知识库。Agent 把「用哪个工具、参数是什么、
调几轮」交给模型：问「你好」直接答，问订单就调 `query_my_orders`，问政策才检索知识库。
**控制流由模型产生，而不是代码写死**——这是 Agent 和普通 LLM 应用的分界线。

**Q8：查订单工具怎么保证用户只能查自己的单？**
工具执行时用的是服务端 JWT 解析出的 `user_id`，不是模型生成的参数——模型只能传 `order_no`（可选），
归属过滤在工具内部完成：按单号查到订单后再核对 `order.user_id == 当前用户`，不匹配一律按
「没有找到属于您的订单」处理，不泄露订单存在性。这是「模型不可信」原则：模型输出只当意图，权限边界在代码里。

**Q9：商品导购怎么避免模型编造商品和价格？**
模型自己不生成商品信息，只负责从用户话术里提炼搜索词（和预算），真实商品由 `recommend_products`
工具从数据库查询（在售商品、关键词匹配、预算过滤、按销量排序），把带价格的结果喂回模型，
system prompt 明确要求「按返回结果推荐并附上价格，不要编造商品」。搜索不到就如实说没有，
再引导用户补充需求。

**Q10：什么是 RAG？为什么客服场景必须有引用来源？**
RAG（检索增强生成）＝ 先检索、后生成，让模型基于真实文档回答，解决幻觉与私有知识问题。
客服场景对「口径」要求极高（退换货规则说错一版就是客诉），所以答案必须附带引用来源
（命中的知识文档名 + 原文片段），用户可点开溯源，运营可据此定位知识盲区。

**Q11：混合检索为什么必要？RRF 是什么？**
纯向量擅长「语义相近」，但对精确关键词（订单号规则、政策编号）容易漏召；BM25 关键词通路互补。
两者用 **RRF**（Reciprocal Rank Fusion，`score = Σ 1/(k + rank)`）融合——只看排名不看分数绝对值，
天然规避向量分与 BM25 分「量纲不可比」的问题，简单稳健，`k` 通常取 60。

**Q12：多轮对话里「那这个多久到账」怎么处理？**
历史对话放进 messages，让模型在生成 `tool_calls` 时自己把带指代的问题改写成完整独立问题
（工具描述里明确要求），改写动作被吸收进模型推理。检索质量用 `evals/` 的 hit rate / MRR / recall@k 度量。

**Q13：Embedding / Rerank 为什么用本地 BGE 模型？**
① 数据不出内网；② 零 API 费用；③ BGE 中文效果好。两者都是**延迟导入**——模块 import 不加载
torch，真正调用才加载，缺失时报清晰错误而不是启动崩溃。Rerank 策略可配（none/always/conditional），
失败时降级为召回结果，不阻断问答。

### 架构与工程化

**Q14：项目的分层是怎么设计的？**
`api`（路由：鉴权、参数、响应组装）→ `services`（业务编排：事务、状态机、跨模块协作）→
`repositories`（数据访问：查询构造、租户过滤）→ `models`（ORM）。约束：路由不碰 ORM、
业务不手拼响应结构、仓储是唯一拼查询的地方。换存储、加过滤、写单测都只改一层。

**Q15：trace_id 是怎么串起整条链路的？**
纯 ASGI 中间件从 `X-Request-ID` 读取上游 id（没有则生成），写入 `scope["state"]`，响应头回写；
结构化 JSON 日志、错误响应体都带同一 `trace_id`，出问题能一次性捞出该请求全部日志。
用纯 ASGI 而非 `BaseHTTPMiddleware` 是避免包装层缓冲影响 SSE 实时性。

**Q16：限流怎么实现的？Redis 挂了会怎样？**
Redis 令牌桶（Lua 保证「取令牌 + 补令牌」原子），按用户维度限流 chat/upload 等重接口；
Redis 不可用自动降级进程内实现，不让本地没起 Redis 阻断演示。

**Q17：Milvus 怎么做商家隔离？**
单集合 + `partition_key`（tenant_id），检索/删除都带 `expr: tenant_id == x`；
BM25 语料也按租户拉取（`fetch_chunks(tenant_id)`），避免跨商家混算 IDF。

**Q18：测试怎么做到不联网也能跑全链路？**
内存 SQLite（StaticPool）覆盖 `get_db`，LLM 三种调用（tools/text/stream）全部 monkeypatch 成固定回答，
Milvus/BGE/上传目录打桩。电商链路（加购→下单→支付→发货→收货）、库存回补、越权 404、
AI 工具的归属过滤与预算过滤都有专门断言，53 个用例 20 秒跑完。

**Q19：这个系统还能怎么改进？**
① 库存防超卖升级为条件更新/Redis 预扣；② 大文档解析进任务队列（当前刻意保持轻量）；
③ 真实支付网关 + 回调幂等；④ Milvus sparse 向量替代内存 BM25 支撑更大语料；
⑤ 评测接入 LLM 打分（正确性/忠实度）做端到端评估；⑥ 商家结算/分账域。

---

## 首次运行说明

- **BGE 模型下载**：首次调用向量化会从 HuggingFace 下载模型（约 400MB）。代码已内置 `hf-mirror.com` 镜像加速。
- **Milvus 镜像拉取**：首次 `docker compose up` 拉取镜像较大，国内可在 Docker Desktop 里配置镜像加速。
- **旧库升级**：从知识库版本升级时，Alembic 会自动执行电商迁移（旧演示订单表被重建）；
  若之前跑过旧版，向量集合仍用 `kb_documents_v2`，知识文档删除后重新导入即可。
