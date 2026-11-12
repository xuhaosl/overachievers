# Agent、Provider 与儿童隐私

本文记录 v1.6 引入的三块能力：多 Provider 配置、Agent 工具调用、儿童隐私脱敏。
架构细节与取舍放在这里，`AGENTS.md` 只保留命令与边界。

## 1. 多 Provider

### 注册表

`backend/app/providers.py` 是唯一的厂商注册表，所有厂商都走 OpenAI 兼容
`/chat/completions`：

| key | 说明 | 默认地址 |
|---|---|---|
| `deepseek` | DeepSeek | `https://api.deepseek.com` |
| `qwen` | 通义千问（阿里百炼） | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `kimi` | Kimi（月之暗面） | `https://api.moonshot.cn/v1` |
| `zhipu` | 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` |
| `openai` | OpenAI | `https://api.openai.com/v1` |
| `openrouter` | OpenRouter 聚合 | `https://openrouter.ai/api/v1` |
| `siliconflow` | SiliconFlow | `https://api.siliconflow.cn/v1` |
| `groq` | Groq | `https://api.groq.com/openai/v1` |
| `mistral` | Mistral | `https://api.mistral.ai/v1` |
| `custom` | 任意 OpenAI 兼容服务 | 用户自填 |

模型名只是候选列表，界面允许直接输入任意模型名。

### 每个机器人的参数

- `provider` / `base_url` / `model`
- `temperature`、`max_tokens`、`timeout`
- `extra_headers`：JSON 对象，用于 OpenRouter 的 `HTTP-Referer` 等
- `enabled`、`is_default`
- `fallback_bot_id`：主模型失败时按链式回退（最多 3 个）

### 出站 URL 校验

所有服务端发起的请求都必须先经过 `app.security.validate_outbound_url()`：

- 只允许 `http` / `https`
- 拒绝 URL 内嵌用户名密码
- 拒绝 localhost、回环、私有、链路本地、保留、组播地址
- 域名先做 DNS 解析，任一结果命中上述网段即拒绝
- 结果缓存 60 秒，避免频繁阻塞

### API Key 加密

`app.crypto` 负责静态加密：

- 优先 AES-256-GCM（`cryptography`），缺失时退化为 HMAC-SHA256 计数器流 + HMAC 认证标签
- 主密钥来源优先级：`APP_SECRET` 环境变量 → `APP_SECRET_FILE` → `DATA_DIR/.app_secret`（首次启动自动生成）
- 数据库只存 `api_key_enc = enc:v1:...`，旧库的明文 Key 在启动迁移时自动加密并清空原列
- 接口只返回 `api_key_masked`（如 `sk-1****abcd`）

> 主密钥丢失后已加密的 Key 无法恢复，需要在界面重新填写。备份时请同时备份
> `DATA_DIR/.app_secret`（或自行设置固定的 `APP_SECRET`）。

## 2. Agent

### 组成

| 模块 | 作用 |
|---|---|
| `app/agent/tools.py` | 18 个工具的 schema 与执行器 |
| `app/agent/runtime.py` | 多轮工具调用、SSE 事件、脱敏/还原、落库 |
| `app/agent/prompts.py` | 系统提示 + 本地孩子/学科索引 |
| `app/routers/agent.py` | HTTP API：配置、会话、对话、待确认、隐私 |
| `frontend/src/views/Agent.vue` | 工作台：会话列表、工具时间线、待确认卡片 |

### 工具清单

只读：`list_children`、`list_subjects`、`list_exams`、`list_scores`、`list_mistakes`、
`get_family_overview`、`get_child_status`、`analyze_scores`、`privacy_report`

写入：`create_child`、`create_class`、`create_subject`、`create_exam`、`add_score`、
`create_mistake`、`import_records`

确认：`confirm_pending_action`、`cancel_pending_action`

### 写入确认流程

1. 模型调用写工具 → 生成 `AgentPendingAction`，返回 `status=pending_confirmation` 与 `token`
2. 前端展示预览卡片，用户点“确认执行”或调用 `POST /api/agent/pending/{token}/confirm`
3. 执行成功后才落库；重复确认会被拒绝，30 分钟过期

**模型不能自确认**：`confirm_pending_action` 只有在用户本轮消息里明确表达“确认/执行”
（`runtime.CONFIRM_RE`）时才放行，否则返回“用户尚未确认”。这样即使模型自作主张，
也无法绕过人工审批。界面上点“确认执行”走的是独立 HTTP 请求，不受此限制。

`import_records` 支持 `dry_run=true`：只校验并返回将新增的数量，不写库。

Agent 配置（`AgentProfile`）可以限制可用工具、关闭写入、选择隐私级别，以及
`auto_approve`（跳过确认，默认关闭）。

### SSE 事件

`POST /api/agent/chat` 返回 `text/event-stream`：

```json
{"type":"delta","text":"..."}
{"type":"tool_call","name":"list_children","args":{}}
{"type":"tool_result","name":"list_children","ok":true,"summary":"...","token":null}
{"type":"pending_action","token":"...","summary":"..."}
{"type":"error","error":"..."}
{"type":"done","conversation_id":1,"usage":{},"privacy":{},"steps":[]}
```

## 3. 儿童隐私脱敏

### 与 magpie 的对应关系

| magpie（Go） | 本项目（Python） |
|---|---|
| `internal/redact` 稳定占位符 | `app/privacy/engine.py`：`placeholder_for()` 用 HMAC-SHA256 派生 8 位 Base32 |
| `internal/redact.Writer` 流式回填 | `StreamRestorer`：暂存可能被拆开的 `{{KIND_` 前缀 |
| `internal/redact/zhname.go` 中文姓名规则 | `zh_name_findings()`：姓氏表 + 复合姓 + 上下文线索 + 教育词汇排除 |
| `internal/pii` + `guard` | `app/privacy/astrlink.py`：AstrLink Guard ONNX 适配层 |
| `internal/masking` 本地模型选择 | `PRIVACY_GUARD_MODEL=auto/off` 开关 |

### 检测来源

1. **词表**：孩子姓名、学校、班级、学号、竞争对手、最高得分者（来自本地库，实时构建）
2. **正则**：手机、邮箱、身份证、银行卡（Luhn 校验）、地址、出生日期、学号/考号、
   API Key、私钥、URL 凭据、社交账号、内网 IP
3. **中文姓名上下文**：`我叫/客户/联系人/老师/先生` 等线索；`成绩/单元/数学` 等
   教育词汇不会被误判
4. **AstrLink Guard**（可选）：本地 token 分类模型，找出规则漏掉的人名/地址

### 级别

| 级别 | 行为 |
|---|---|
| `off` | 不脱敏，原样发送 |
| `standard` | 默认；词表 + 正则 + 中文姓名上下文规则 |
| `strict` | 在标准基础上更激进地识别人名 |

全局默认由 `PRIVACY_LEVEL` 控制，Agent 配置与会话可以各自覆盖。

### 可逆性与一致性

- 同一值在同一主密钥下始终得到同一占位符，多轮对话与缓存前缀保持稳定
- 占位符→原值只存在本次请求的内存 vault
- 模型回传的占位符在流式转发时还原；拆在两个分片里的占位符会先暂存
- 无法还原的占位符（模型编造的）会让工具调用直接失败，避免写入脏数据

### 审计

`PrivacyAudit` 只记录数量、类型、级别，不记录原值。`GET /api/agent/privacy/audits`
与界面“隐私与安全”面板可查看。

### AstrLink Guard 模型放置

模型不随仓库分发。若要启用本地模型：

1. 从 Hugging Face `QuantumNous/astrlink-guard` 取 `int8/model_int8.onnx`、
   `int8/model_int8.onnx_data`、`int8/tokenizer.json`（Apache-2.0）；
2. 放到 `DATA_DIR/models/astrlink-guard/`（或 `ASTR_GUARD_DIR` 指定目录），
   文件可直接放该目录，也可放在其 `int8/` 子目录；
3. 安装 `onnxruntime`、`tokenizers`、`numpy`；
4. `GET /api/agent/privacy/status` 中 `guard.available` 变为 `true`。

缺失模型时脱敏引擎自动使用内置规则，不影响其他功能。

## 4. CLI

`cli/` 是独立的可安装包（`pip install -e ./cli`），入口 `oa`。命令与事件格式见
`cli/overachievers_cli/skills/overachievers-cli/SKILL.md`。

CLI 只走 HTTP，不直连数据库；服务端对写工具强制确认流程，`POST /api/agent/tools/{name}`
只开放只读工具。
