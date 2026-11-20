# AGENTS.md

## 项目定位

「卷王之王（overachievers）」：家庭自用的孩子成绩与错题管理系统。单文件 SQLite
存储，可自托管；后端 FastAPI，前端 Vue3 + Element Plus。除成绩管理外，v1.6 起提供
多 Provider AI 助手、Agent 工具调用、儿童隐私脱敏，以及 CLI-Anything 风格的 `oa` 命令行。

## 目录与边界

```
backend/
  app/
    main.py            应用入口：建表、轻量迁移、路由注册、静态资源
    database.py        SQLite 连接（DATA_DIR/overachievers.db）
    models.py          SQLAlchemy 模型（孩子/学科/单元/班级/场次/成绩/错题/AI/Agent/隐私审计）
    schemas.py         Pydantic 请求响应模型
    auth.py            APP_PASSWORD 可选登录
    crypto.py          API Key 静态加密（AES-256-GCM，缺失时 HMAC 流）
    security.py        出站 URL 校验（拒绝本机/内网/保留地址）
    providers.py       多 Provider 注册表、请求构造、Key 读写
    term.py / grading.py  学期与年级推算
    uploads.py         图片上传与清理
    privacy/           magpie 风格脱敏引擎 + AstrLink Guard 适配
    agent/             Agent 工具、运行时、系统提示
    routers/           HTTP 路由（ai / agent / mistakes / scores / ...）
  tests/               标准库 unittest 测试
  static/              前端构建产物（由后端托管）
frontend/src/          Vue 源码（views / components / api.js / router.js）
cli/                   独立可安装的 oa 命令行包（CLI-Anything 风格）
docs/agent-privacy.md  Provider / Agent / 隐私架构说明
```

**边界规则**

- 路由层不直接拼 SQL；迁移里的动态标识符必须走白名单或 SQLAlchemy 反射。
- 所有服务端主动发起的 HTTP 请求必须先过 `security.validate_outbound_url()`。
- API Key 只允许以 `crypto.encrypt_secret()` 的密文写入数据库，读取统一走
  `providers.bot_api_key()`；禁止在响应中返回明文。
- 发送给第三方模型的文本必须经过 `privacy.PrivacyEngine.redact()`；模型返回内容
  必须经过 `restore()` 或 `StreamRestorer` 还原后才展示或落库。
- Agent 写操作必须经过 `AgentPendingAction` 确认流程；`POST /api/agent/tools/{name}`
  只开放只读工具。
- `confirm_pending_action` 受 `ToolContext.user_confirmed` 保护：只有用户本轮明确说
  “确认/执行”时才放行，禁止模型自问自答直接落库。新增写工具时必须保留这条约束。
- 前端不直接调用第三方模型接口，一律走后端代理。

## 命令

```bash
# 后端（端口 8100，首次启动自动建库与迁移）
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8100

# 后端测试（标准库 unittest，不需要 pytest）
cd backend
python -m unittest discover -s tests -v

# 前端（改前端代码时才需要）
cd frontend
npm install
npm run build     # 产物输出到 dist，发布时复制到 backend/static

# CLI（独立安装）
pip install -e ./cli
oa health
oa --json children list
```

## 环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `APP_PASSWORD` | 访问密码；为空则局域网免登录 | 空 |
| `DATA_DIR` | 数据目录（SQLite + 上传图片 + 主密钥） | 容器 `/app/data`，本地 `./data` |
| `APP_SECRET` | API Key 加密主密钥（任意长字符串） | 空，自动生成 `DATA_DIR/.app_secret` |
| `APP_SECRET_FILE` | 从文件读取主密钥 | 空 |
| `PRIVACY_LEVEL` | 默认脱敏级别 `off/standard/strict` | `standard` |
| `PRIVACY_GUARD_MODEL` | AstrLink Guard 开关 `auto/off` | `auto` |
| `ASTR_GUARD_DIR` | AstrLink Guard 模型目录 | `DATA_DIR/models/astrlink-guard` |
| `OA_BASE_URL` / `OA_TOKEN` | CLI 客户端连接配置 | `http://127.0.0.1:8100` / 空 |

## 非显然注意事项

- **主密钥不可丢**：`DATA_DIR/.app_secret` 丢失后已加密的 API Key 无法解密，只能重新填写。
  迁移/备份数据时要一并保留，或改用固定的 `APP_SECRET`。
- **AstrLink Guard 不随仓库分发**：模型缺失时脱敏自动退化为内置规则（词表 + 正则 +
  中文姓名上下文），不影响启动。启用方式见 `docs/agent-privacy.md`。
- **占位符一致性依赖主密钥**：同一值跨轮次得到同一 `{{KIND_xxxxxxxx}}`，多轮对话与
  缓存前缀才稳定；更换主密钥会让历史会话里的占位符无法还原。
- **流式回填**：SSE 分片可能把占位符拆开，必须用 `StreamRestorer` 而不是直接
  `str.replace`，否则会向用户漏出半截占位符。
- **Agent 写入确认**：`import_records` 的 `dry_run=true` 只校验不写库；确认后由
  `confirm_pending()` 执行，重复确认会被拒绝，30 分钟过期。
- **出站 URL 校验会做 DNS 解析**：离线或 DNS 异常时，配置自定义接口地址可能报
  “无法解析”，这是预期行为，不是 bug。
- **前端构建产物入库**：仓库跟踪 `backend/static/`；改了前端源码要重新 build 并提交产物，
  否则运行中的服务仍是旧界面。
- **不要用 `pip install -r` 之外的方式引入新依赖**：`backend/requirements.txt` 是唯一
  后端依赖清单；`cryptography`、`onnxruntime` 等均为可选，缺失时自动降级。

## 指令文件维护规则（长期有效）

- 项目结构、构建/测试命令、架构边界、开发约定，或本文件记录的其他事实发生变化时，
  必须在同一次改动中同步更新本文件；用当前事实替换过期表述，不逐次追加变更历史。
- 本文件只保留当前规则、命令、架构边界和非显然注意事项；
  详细架构说明、事故复盘与实验记录放入带链接的独立文档（如 `docs/agent-privacy.md`），
  仅在任务相关时读取。
- 修改或删除本文件已有内容前，先提出方案并取得用户明确同意；
  保留所有有效要求及其作用域，不得为压缩篇幅而静默摘要或截断已有指令。
