# 课程学习助手 Agent 平台

针对大学生多门课程学习中「资料分散、重点难找、计划不清、任务易漏」的问题，提供一个通用的课程学习助手平台：管理课程与学习资料，并通过智能体（Agent）实现**基于课程资料的问答（带来源引用）**、**知识点整理**、**学习计划生成**与**待办任务管理**。

> 大型程序设计课程项目 · 第一版（v0.1）

## 功能总览

### 基本功能

| 模块 | 说明 |
| --- | --- |
| 用户认证 | 注册 / 登录（JWT）、个人信息管理（昵称、密码） |
| 课程管理 | 创建 / 编辑 / 删除课程，包含名称、简介、授课教师、学期 |
| 资料管理 | 按课程上传 / 查看 / 下载 / 删除资料（课件、教材笔记、作业要求、实验指导等），txt / md / pdf 自动解析入库 |
| 资料检索 | 按类型、文件名筛选资料；按关键词检索资料**正文片段**（中文按二元词组匹配打分） |
| Agent 对话 | 选择课程后向智能体提问，系统自动检索相关资料片段辅助回答，支持多轮对话与多个对话记录 |
| 学习计划 | 输入学习目标、截止时间、每日可用时间，生成阶段任务 + 每日待办 |
| 待办任务 | 手动添加或由计划自动生成，支持完成勾选、逾期标红、按课程/状态筛选 |
| 个人中心 | 课程 / 计划 / 任务 / 对话统计与快捷入口，资料与账号管理 |

### 高级功能

- **资料来源引用**：Agent 回答时标注参考了哪些资料，答案中以 `[编号]` 对应来源片段，前端可悬浮查看原文摘录
- **知识点整理**：根据课程资料自动提取重点知识点，生成 Markdown 复习提纲
- **智能任务拆解**：输入「我要两周复习完高等数学期末考试」等目标，自动拆解为阶段任务和每日待办并落库为任务
- **多课程学习规划**：根据多门课程的截止时间和任务量，生成综合每日学习安排

### 离线降级模式

未配置 `ANTHROPIC_API_KEY` 时系统仍可完整运行：问答返回检索到的资料片段、计划按天数均匀拆分，接口以 `agent_mode: "fallback"` 标记，前端有对应提示。配置 Key 后自动切换为大模型智能回答。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3 + Vite + Vue Router + Pinia + Element Plus + Axios + Marked |
| 后端 | Python 3.10+ / FastAPI / SQLAlchemy 2.0 / Pydantic v2 |
| 数据库 | SQLite（开发默认，可通过 `DATABASE_URL` 切换） |
| 认证 | JWT（PyJWT）+ PBKDF2 密码哈希 |
| LLM | Anthropic Claude API（默认 `claude-opus-4-8`，结构化输出生成计划 JSON） |
| 检索 | 资料文本切片 + 中英文关键词打分检索（轻量 RAG） |

## 快速开始

### 1. 后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # 编辑 .env，填入 ANTHROPIC_API_KEY（可选）
uvicorn app.main:app --reload --port 8000
```

- 接口文档（Swagger UI）：http://localhost:8000/docs
- 不配置 API Key 也能启动，Agent 功能进入离线降级模式

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173 （开发服务器已配置 `/api` 代理到后端 8000 端口）。

### 3. 运行测试

```bash
cd backend
pytest tests/ -v
```

测试使用独立临时数据库并强制离线模式，不消耗 API 额度。

## 项目结构

```
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口（CORS、路由注册、建表）
│   │   ├── config.py            # 环境配置
│   │   ├── database.py          # SQLAlchemy 引擎与会话
│   │   ├── models/              # ORM 模型（用户/课程/资料/对话/计划/任务）
│   │   ├── schemas/             # Pydantic 请求响应模型（入参校验）
│   │   ├── routers/             # REST API 路由
│   │   │   ├── auth.py          #   认证与个人信息
│   │   │   ├── courses.py       #   课程 CRUD + 知识点整理
│   │   │   ├── materials.py     #   资料上传/检索/下载/删除
│   │   │   ├── chat.py          #   Agent 对话（带引用）
│   │   │   ├── plans.py         #   学习计划（单课程/多课程）
│   │   │   └── tasks.py         #   待办任务
│   │   └── services/
│   │       ├── agent.py         # Claude API 调用 + 离线降级
│   │       ├── retrieval.py     # 资料切片检索
│   │       ├── extraction.py    # 文本抽取与切片
│   │       └── security.py      # 密码哈希 / JWT
│   ├── tests/                   # pytest 测试套件
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── api/                 # Axios 封装与接口定义
│       ├── stores/              # Pinia 状态（登录态）
│       ├── router/              # 路由与登录守卫
│       └── views/               # 登录/注册/课程/课程详情/问答/计划/任务/个人中心
└── README.md
```

## 数据库设计

| 表 | 说明 | 关键字段 |
| --- | --- | --- |
| `users` | 用户 | username、email、password_hash、nickname |
| `courses` | 课程 | owner_id、name、description、teacher、semester |
| `materials` | 资料文件 | course_id、filename、mtype（类型）、stored_path |
| `material_chunks` | 资料文本切片（检索用） | material_id、course_id、seq、content |
| `conversations` | 对话 | user_id、course_id、title |
| `messages` | 消息 | conversation_id、role、content、citations_json（引用） |
| `study_plans` | 学习计划 | user_id、course_id、goal、deadline、content_json |
| `tasks` | 待办任务 | user_id、course_id、plan_id、title、due_date、completed |

## API 概览

所有接口前缀 `/api`，除注册 / 登录外均需 `Authorization: Bearer <token>`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/register` `/auth/login` | 注册 / 登录 |
| GET/PUT | `/auth/me` | 查看 / 修改个人信息 |
| GET/POST | `/courses`，PUT/DELETE `/courses/{id}` | 课程 CRUD |
| POST | `/courses/{id}/knowledge-summary` | 生成知识点提纲 ★ |
| POST/GET | `/courses/{id}/materials` | 上传 / 列出资料 |
| GET | `/courses/{id}/materials/search?q=` | 资料内容检索 |
| GET/DELETE | `/materials/{id}/download`、`/materials/{id}` | 下载 / 删除资料 |
| POST/GET | `/courses/{id}/conversations` | 创建 / 列出对话 |
| GET/POST | `/conversations/{id}/messages` | 查看历史 / 发送消息（返回引用）★ |
| POST | `/plans` | 生成学习计划（自动拆解任务）★ |
| POST | `/plans/multi-course` | 多课程综合规划 ★ |
| GET/POST | `/tasks`，PUT/DELETE `/tasks/{id}` | 任务 CRUD |

★ 为 Agent 相关接口，响应携带 `agent_mode`（`llm` / `fallback`）。

## 环境变量（backend/.env）

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥，缺省时进入离线降级模式 | 空 |
| `ANTHROPIC_MODEL` | 使用的 Claude 模型 | `claude-opus-4-8` |
| `JWT_SECRET` | JWT 签名密钥，生产环境必须修改 | 开发默认值 |
| `JWT_EXPIRE_MINUTES` | 登录有效期（分钟） | 10080（7 天） |
| `MAX_UPLOAD_MB` | 上传大小上限 | 50 |
| `CORS_ORIGINS` | 允许的前端来源 | localhost:5173 |

## 团队分工建议（≤5 人）

| 角色 | 负责内容 |
| --- | --- |
| 后端 A | 认证、课程、资料模块与数据库设计 |
| 后端 B | Agent 服务、检索、计划 / 任务模块 |
| 前端 A | 登录注册、课程管理、资料管理页面 |
| 前端 B | Agent 对话、学习计划、任务、个人中心页面 |
| 测试 / 集成 | 测试用例、联调、部署与文档 |

## Roadmap（后续版本）

- [ ] 向量检索（Embedding）替换关键词检索，提升召回质量
- [ ] 对话流式输出（SSE）
- [ ] 资料支持 docx / pptx 解析
- [ ] 任务提醒与日历视图
- [ ] Docker Compose 一键部署
