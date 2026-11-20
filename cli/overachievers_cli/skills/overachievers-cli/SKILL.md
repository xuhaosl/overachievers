---
name: "overachievers-cli"
description: "卷王之王（overachievers）家庭成绩管理 CLI：查询孩子/成绩/错题、做近况与趋势分析、用 Agent 对话导入数据。支持 JSON 输出，适合被 AI Agent 直接调用。"
---

# overachievers-cli

把「卷王之王」——家庭自用的孩子成绩与错题管理系统——暴露为 Agent 可调用的命令行接口。

- 数据始终留在用户自己的机器（SQLite + 本地文件），CLI 只通过 HTTP 访问本机/自托管服务
- 所有命令支持 `--json`，便于 Agent 解析
- 写操作分两层：CLI 的 `agent chat` 会先生成预览并要求确认；`oa` 不提供绕过确认的删除能力
- 发送给第三方模型的文本默认经过本地儿童隐私脱敏（可逆占位符）

## 安装

CLI 位于仓库 `cli/` 目录，仅依赖 `click` 与 `httpx`：

```bash
pip install -e ./cli
oa --version
```

## 连接配置

```bash
export OA_BASE_URL=http://127.0.0.1:8100   # 服务地址
export OA_TOKEN=...                        # 仅当服务端设置了 APP_PASSWORD
```

> 全局选项（`--base-url` / `--token` / `--json`）要写在子命令**之前**：
> `oa --json children list`

## 命令

### 基础

```bash
oa health                                  # 连通性、版本、加密与脱敏能力
oa providers list                          # 内置 Provider 注册表
oa providers bots                          # 已配置机器人（Key 打码）
```

### 孩子与成绩

```bash
oa children list
oa children add --name 小明 --first-enroll-year 2022

oa scores list --child-id 1 --limit 20
oa scores add --child-id 1 --subject-id 2 --score 95 --total 100 --date 2026-11-10 --tags 单元测验

oa exams list --child-id 1
```

### 错题

```bash
oa mistakes list --child-id 1 --limit 20
```

### 近况与分析

```bash
oa status family                           # 所有孩子：均分、薄弱学科、未掌握错题
oa status child --name 小明 --days 120      # 单个孩子近况
oa status analyze --child-id 1 --date-from 2026-09-01
```

### Agent 对话（导入 / 查询 / 分析）

```bash
# 只读问答
oa agent chat --bot-id 1 "小明最近数学怎么样？" --show-steps

# 让 Agent 整理并导入一段成绩单文本
oa agent chat --bot-id 1 --show-steps "把下面成绩录入：小明 数学 11月10日 95/100，语文 88/100"

# 输出里的 pending_action 会带 token；确认后才会真正写库
oa agent confirm <token>
oa agent cancel <token>

oa agent profiles                          # Agent 配置（工具集/写入权限/隐私级别）
oa agent tools                             # 18 个可用工具及说明
```

### 隐私

```bash
oa privacy status                          # 默认级别、AstrLink Guard 状态、加密方案
oa privacy preview "小明在实验小学，电话 13800138000" --level standard
oa privacy audits --conversation-id 1      # 只含数量与类型，不含原值
```

## JSON 输出

```bash
oa --json status family
oa --json agent chat --bot-id 1 "分析本学期薄弱点"
```

`agent chat --json` 逐行输出事件对象：

| type | 含义 |
|---|---|
| `delta` | 模型增量文本 |
| `tool_call` | 即将执行的工具及参数 |
| `tool_result` | 工具结果摘要、是否成功、待确认 token |
| `pending_action` | 需要用户确认的写操作 |
| `done` | 本轮结束，含会话 ID、用量、脱敏统计 |

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 业务错误（校验失败、模型报错、未授权） |
| 2 | 参数错误 |
| 3 | 无法连接服务 |

## 典型 Agent 工作流

1. `oa health` 确认服务在线；
2. `oa --json children list` 拿到 `child_id`；
3. `oa --json status child --child-id N` 了解近况；
4. 需要写入时用 `oa agent chat`，把返回的 `pending_action.token` 交还用户确认，再 `oa agent confirm <token>`；
5. 用 `oa privacy audits` 复核本轮脱敏范围。

## 注意

- CLI 不直接读写数据库，所有操作都经过服务端鉴权与校验；
- 服务端对写工具强制走确认流程，HTTP 工具接口只开放只读工具；
- `--json` 输出可能包含孩子姓名等本地数据，转发到外部前请自行脱敏。
