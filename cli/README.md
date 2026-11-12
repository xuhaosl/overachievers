# overachievers CLI

把「卷王之王」暴露为 Agent 可调用的命令行接口（CLI-Anything 风格）。

```bash
pip install -e .
export OA_BASE_URL=http://127.0.0.1:8100
oa health
oa --json children list
oa status child --name 小明
oa agent chat --bot-id 1 "分析一下最近的数学成绩" --show-steps
```

- 全局选项 `--base-url` / `--token` / `--json` 写在子命令之前。
- 完整命令说明见 [`overachievers_cli/skills/overachievers-cli/SKILL.md`](overachievers_cli/skills/overachievers-cli/SKILL.md)。
- 退出码：0 成功、1 业务错误、2 参数错误、3 连接失败。
