"""卷王之王 CLI：把家庭成绩管理暴露给 Agent 的命令行接口。

设计遵循 CLI-Anything 的约定：
- 每个命令既支持 `--json` 机器可读输出，也支持人类可读摘要；
- 只通过 HTTP 访问本机/自托管服务，不直接碰数据库；
- 退出码：0 成功、1 业务错误、2 参数错误、3 连接失败；
- `oa agent chat` 流式输出工具调用与回答，便于 Agent 观测每一步。
"""
from __future__ import annotations

__version__ = "1.0.0"
