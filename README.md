# 云栖湖度假区智能客服 Agent

面向景区咨询场景的全栈智能客服演示项目，覆盖知识问答、票务交易、行程规划、投诉转人工四类业务。后端基于 FastAPI + LangGraph，前端为 Vue3 + Vant4 移动端 H5，支持 SSE 流式输出与多轮会话记忆。

## 演示


https://github.com/user-attachments/assets/613d41bf-f621-40ff-906e-de2ee08f5f16



## 技术栈

- 后端：Python 3.12 / FastAPI / LangGraph / LangChain / SQLAlchemy 2.0（异步）
- 模型：通义千问 qwen-plus（复杂任务）/ qwen-flash（简单任务，成本约为 plus 的 1/3）/ text-embedding-v3（向量化）/ gte-rerank-v2（重排），均走 DashScope API
- 存储：MySQL（业务数据）/ Redis（会话记忆）/ Chroma（嵌入式向量库，本地持久化）
- 外部数据：Open-Meteo 实时天气（免 key，按园区坐标查询）
- 前端：Vue 3 / TypeScript / Vite / Vant 4 / marked
- 可观测：Arize Phoenix（本地全链路 trace）/ loguru（token 消耗与运行日志落盘）

## 整体架构

用户消息经 FastAPI SSE 接口进入 LangGraph 状态图：意图识别节点（LLM 结构化输出）经条件边路由至四类业务分支——RAG 问答（查询改写 → 向量检索 → 重排 → 流式生成）、ReAct 票务（手写工具调用循环）、Plan-and-Execute 行程规划（并行收集事实 → 生成 → 程序化校验；纯建议类咨询只口头回答，不生成行程卡片）、人工兜底（自动建工单）。节点执行过程通过自定义事件实时推送到前端。

## 成本与检索设计

- 模型按任务复杂度分级：意图分类、查询改写、口语化讲解用 qwen-flash，最终回答、行程生成、工具调用用 qwen-plus；各调用点按任务设置 max_tokens 上限
- 知识问答带进程内答案缓存（归一化问题文本为 key，TTL 1 小时），重复问题直接返回不再调用模型；chitchat 意图跳过检索直接生成
- system prompt 固定部分在前、变量在后，兼容 DashScope prefix cache
- embedding 与 rerank 输入加 `文档标题 / 块标题` 前缀提升相关性，向量库中存原文用于展示；检索采用召回 10 条、重排取 4 条的漏斗控制上下文长度

## 目录结构与文件说明

### 后端 backend/

```
backend/
├── app/
│   ├── main.py                  FastAPI 应用入口：CORS、路由注册、生命周期管理
│   ├── config.yaml              集中配置：模型、数据库、检索参数、意图阈值等
│   ├── config.py                配置加载：读取 config.yaml 为全局 settings 单例
│   │
│   ├── agents/                  LangGraph 编排核心
│   │   ├── state.py             状态定义：ChatState 及各结构化模型（意图、行程等）
│   │   ├── graph.py             状态图装配：节点注册、条件边路由、图编译单例
│   │   ├── events.py            事件发射：节点内向 SSE 推送自定义事件的工具函数
│   │   ├── intent_node.py       意图识别：LLM 结构化输出意图/置信度/槽位
│   │   ├── knowledge_node.py    RAG 问答分支：检索命中则流式生成，未命中计数兜底
│   │   ├── service_node.py      办事分支：手写 ReAct 循环编排业务工具
│   │   ├── planner_node.py      规划分支：Plan-and-Execute，事实收集/生成/校验
│   │   ├── handoff_node.py      转人工分支：创建工单并生成安抚话术
│   │   └── prompts/prompts.py   全部提示词：意图、知识、办事、规划、转人工
│   │
│   ├── api/
│   │   ├── chat.py              POST /api/chat：SSE 接口，驱动图执行并转发事件流
│   │   └── schema.py            接口请求/响应模型
│   │
│   ├── rag/                     RAG 链路
│   │   ├── query_rewrite.py     查询改写：结合会话历史补全指代，生成独立检索句
│   │   ├── answer_cache.py      答案缓存：归一化问题为 key 的 LRU + TTL，命中零 token
│   │   ├── embedding.py         向量化：DashScope text-embedding-v3 调用封装
│   │   ├── chroma_store.py      Chroma 嵌入式向量库封装（本地持久化）
│   │   ├── rerank.py            重排：gte-rerank-v2 调用与阈值过滤
│   │   ├── retrieval.py         检索编排：改写 → 向量召回 → 重排的完整流程
│   │   └── ingest/              入库链路：md / docx 统一切块 + 质检统计
│   │       ├── docx_parser.py   DOCX 解析：段落/表格顺序遍历，按逻辑页分块
│   │       ├── page_merge.py    页面块渲染为 Markdown（标题分级/列表/表格）
│   │       ├── splitter.py      md 与 docx 共用的按二级标题切块规则
│   │       └── pipeline.py      入库编排：分块 + 质检报告（重复块/失败/短块）
│   │
│   ├── tools/                   业务工具（LangChain StructuredTool + 内部异步函数）
│   │   ├── ticket.py            票务：票种查询/下单/查单/退票（MySQL 真实落库）
│   │   ├── park.py              园区：项目开放状态/演出时刻/项目清单
│   │   ├── env.py               天气：Open-Meteo 实时接口（免 key）
│   │   └── service.py           工单：创建人工服务工单
│   │
│   ├── db/
│   │   ├── models.py            六张表模型：票种/订单/项目/项目状态/演出/工单
│   │   ├── session.py           异步数据库引擎与会话工厂
│   │   └── seed.py              种子数据：12 个 POI、6 类票种、演出与检修场景
│   │
│   ├── llm/factory.py           LLM 工厂：带缓存的模型实例获取 + token 消耗日志
│   ├── tracing.py               本地全链路追踪：Phoenix 自动埋点（LangGraph/LLM/工具）
│   ├── memory/session_history.py Redis 会话记忆：最近 10 轮历史与未命中计数
│   └── utils/dates.py           日期工具：中文日期归一化（今天/明天/后天等）
│
├── kb/                          知识库原文（10 篇 Markdown + 2 篇 Word，虚构景区信息）
│   └── docx/                    Word 知识文档（11_园区导览手册、12_餐饮住宿指南）
├── scripts/
│   ├── init_db.py               建表 + 灌入种子数据
│   └── ingest_kb.py             知识库切分向量化入 Chroma（--reset 重建）
├── eval/
│   ├── qa.jsonl                 评测集：52 条标注用例（知识/票务/规划/转人工等）
│   └── run_eval.py              评测脚本：直接调用图，输出意图/检索/约束等指标
├── requirements.txt             Python 依赖清单
├── logs/                        运行日志（按天切分，保留 7 天）
├── data/chroma/                 向量库持久化目录（运行后生成，不入库）
├── data/ingest_report.json      入库质检报告（文件数/分块数/重复块/失败项）
└── data/phoenix/                Phoenix trace 数据目录（本地 SQLite，运行后生成）
```

### 前端 frontend/

```
frontend/
├── src/
│   ├── main.ts                  应用入口：挂载 Vue、注册 Vant
│   ├── App.vue                  根组件
│   ├── types.ts                 类型定义：消息、流事件、行程等
│   ├── api/sse.ts               SSE 客户端：fetch + ReadableStream 解析事件流
│   ├── views/ChatView.vue       聊天页：消息列表、输入区、快捷问题、事件分发
│   ├── components/
│   │   ├── MessageBubble.vue    消息气泡：Markdown 渲染、工具进度、来源标签
│   │   └── ItineraryCard.vue    行程卡片：时间轴展示规划结果
│   └── style.css                全局样式
├── vite.config.ts               Vite 配置：端口 8090，/api 代理到后端 8000
└── package.json                 前端依赖（Vue3 / Vant4 / marked）
```

## 运行方式

### 前置条件

- Python 3.12（建议 conda 环境）
- Node.js 20
- MySQL 8 / Redis
- 环境变量（格式见 `backend/app/config.yaml` 注释）：
  - `DASHSCOPE_API_KEY`：通义千问 API Key
  - `MYSQL_ENDPOINT`：如 `mysql+aiomysql://用户:密码@主机:3306/scenic_agent?charset=utf8mb4`
  - `REDIS_ENDPOINT`：如 `redis://主机:6379/1`

### 启动本地追踪（可选）

```powershell
cd ScenicAgent/backend
$env:PHOENIX_WORKING_DIR = "$PWD\data\phoenix"   # trace 数据落在项目内，不设则用 ~/.phoenix
phoenix serve                                    # UI 地址 http://localhost:6006
```

Phoenix 在本机接收 trace，不经过第三方服务。未启动时后端会跳过埋点，不影响正常对话；`app/config.yaml` 的 `tracing.enabled` 可关闭。

### 启动后端

```powershell
cd ScenicAgent/backend
pip install -r requirements.txt

# 初始化数据库（建表 + 种子数据）
python scripts/init_db.py

# 知识库入向量库（--reset 为清空重建）
python scripts/ingest_kb.py --reset

# 启动服务（相对路径以 backend 目录为基准解析，任意目录启动均可）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 启动前端

```powershell
cd ScenicAgent/frontend
npm install
npm run dev -- --host 0.0.0.0
```

浏览器访问 `http://localhost:8090`；手机与电脑同一局域网时访问 `http://<电脑IP>:8090`。

### 运行评测

```powershell
cd ScenicAgent/backend
python eval/run_eval.py          # 全量 52 条
python eval/run_eval.py P01      # 按用例 id 单跑
```

## 评测基线

52 条自建评测集，全量通过率 52/52 = 100%：

| 指标 | 结果 |
|---|---|
| 意图准确率 | 52/52 = 100% |
| RAG 命中 | 24/24 = 100% |
| 期望文档召回 | 24/24 = 100% |
| 办事成功率 | 38/38 = 100% |
| 行程约束满足率 | 10/10 = 100% |
| 转人工成功率 | 4/4 = 100% |

## 声明

- 项目内景区信息（云栖湖度假区、票价、演出、POI 等）均为虚构演示数据，与任何真实景区无关。
- 本项目部分设计参考了 [OmniAgent](https://gitee.com/coting/OmniAgent)（MIT License，Copyright (c) 2024 MingGuang Tian），主要包括：RAG 文档解析与切块思路（按逻辑页分块、按标题层级切分）、SSE 流式事件协议、LangGraph 状态图编排模式。相关代码已按本项目业务场景重写，未直接复制源文件。
