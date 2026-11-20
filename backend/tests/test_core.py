"""后端核心能力测试（标准库 unittest，无需 pytest）。

运行：
    cd backend && python -m unittest discover -s tests -v

覆盖：
- API Key 静态加密与往返
- 出站 URL 安全校验（拒绝本机/内网/保留地址）
- magpie 风格脱敏：稳定占位符、可逆、流式跨分片
- Agent 写操作待确认流程与批量导入 dry-run
"""
from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# 临时库放在工作区内（backend/.tmp），退出时关闭 engine 再删除，避免 Windows 文件占用
_TMP_ROOT = BACKEND / ".tmp"
_TMP_ROOT.mkdir(parents=True, exist_ok=True)
_TMP = Path(tempfile.mkdtemp(prefix="tests-", dir=_TMP_ROOT))
os.environ["DATA_DIR"] = str(_TMP)
os.environ.pop("APP_SECRET", None)
os.environ["PRIVACY_GUARD_MODEL"] = "off"


def _cleanup() -> None:
    try:
        from app.database import engine

        engine.dispose()
    except Exception:
        pass
    shutil.rmtree(_TMP, ignore_errors=True)


atexit.register(_cleanup)

from app import crypto  # noqa: E402
from app.privacy import PrivacyEngine, StreamRestorer  # noqa: E402
from app.security import validate_outbound_url  # noqa: E402


class CryptoTest(unittest.TestCase):
    def test_roundtrip(self):
        self.assertTrue(crypto.check_secret_roundtrip())
        secret = "sk-test-" + "a" * 24
        enc = crypto.encrypt_secret(secret)
        self.assertTrue(crypto.is_encrypted(enc))
        self.assertNotIn(secret, enc)
        self.assertEqual(crypto.decrypt_secret(enc), secret)

    def test_idempotent(self):
        secret = "sk-test-" + "b" * 24
        enc = crypto.encrypt_secret(secret)
        self.assertEqual(crypto.encrypt_secret(enc), enc)

    def test_plaintext_passthrough(self):
        self.assertEqual(crypto.decrypt_secret("plain-legacy-key"), "plain-legacy-key")
        self.assertEqual(crypto.encrypt_secret(""), "")

    def test_mask(self):
        self.assertEqual(crypto.mask_key(""), "")
        self.assertEqual(crypto.mask_key("short"), "****")
        self.assertEqual(crypto.mask_key("sk-test-00000000001234"), "sk-t****1234")

    def test_placeholder_stable(self):
        a = crypto.placeholder_for("CHILD", "张三")
        b = crypto.placeholder_for("CHILD", "张三")
        c = crypto.placeholder_for("CHILD", "李四")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertRegex(a, r"^\{\{CHILD_[A-Z2-7]{8}\}\}$")


class SecurityTest(unittest.TestCase):
    def test_rejects_non_http(self):
        for url in ("ftp://example.com", "file:///etc/passwd", "javascript:alert(1)", ""):
            with self.assertRaises(Exception):
                validate_outbound_url(url)

    def test_rejects_localhost_and_private(self):
        for url in (
            "http://localhost:8100",
            "http://127.0.0.1:8100",
            "http://127.1.2.3",
            "http://10.0.0.5/v1",
            "http://192.168.1.10/v1",
            "http://172.16.5.5/v1",
            "http://169.254.169.254/latest/meta-data",
            "http://[::1]:8100",
            "http://0.0.0.0:8100",
            "http://metadata.google.internal",
            "http://foo.local",
        ):
            with self.assertRaises(Exception, msg=url):
                validate_outbound_url(url)

    def test_rejects_credentials_in_url(self):
        with self.assertRaises(Exception):
            validate_outbound_url("https://user:pass@api.deepseek.com")

    def test_allows_public_host(self):
        self.assertEqual(validate_outbound_url("https://api.deepseek.com"), "https://api.deepseek.com")


class PrivacyTest(unittest.TestCase):
    def setUp(self):
        self.engine = PrivacyEngine(
            {"CHILD": {"张三"}, "SCHOOL": {"实验小学"}, "CLASS": {"3班"}, "PERSON": {"李四"}},
            level="standard",
        )

    def test_lexicon_and_rules(self):
        text = "张三在实验小学3班，电话13800138000，邮箱zhangsan@example.com，李四老师说明天见。"
        out = self.engine.redact(text)
        for needle in ("张三", "实验小学", "3班", "13800138000", "zhangsan@example.com", "李四"):
            self.assertNotIn(needle, out)
        self.assertIn("{{CHILD_", out)
        self.assertIn("{{PHONE_", out)
        self.assertIn("{{EMAIL_", out)

    def test_roundtrip(self):
        text = "张三这次数学 92 分，学校是实验小学。"
        out = self.engine.redact(text)
        self.assertEqual(self.engine.restore(out), text)

    def test_stable_across_turns(self):
        first = self.engine.redact("张三")
        second = self.engine.redact("张三")
        self.assertEqual(first, second)

    def test_off_level(self):
        engine = PrivacyEngine({"CHILD": {"张三"}}, level="off")
        self.assertEqual(engine.redact("张三"), "张三")

    def test_keeps_ordinary_words(self):
        # 以姓氏开头的教育词汇不应被误判为人名
        text = "这次成绩不错，单元测试都过了，数学也有进步。"
        self.assertEqual(self.engine.redact(text), text)

    def test_stream_split_placeholder(self):
        token = self.engine.redact("张三")
        restorer = StreamRestorer(self.engine)
        parts = [token[:3], token[3:8], token[8:]]
        chunks = [restorer.feed(p) for p in parts]
        self.assertEqual("".join(chunks) + restorer.flush(), "张三")

    def test_stream_plain_text(self):
        restorer = StreamRestorer(self.engine)
        self.assertEqual(restorer.feed("普通文本"), "普通文本")
        self.assertEqual(restorer.flush(), "")

    def test_unresolved_placeholder_detected(self):
        self.assertTrue(self.engine.unresolved_placeholders("{{CHILD_NOTEXIST}}"))
        token = self.engine.redact("张三")
        self.assertEqual(self.engine.unresolved_placeholders(token), [])

    def test_stats(self):
        self.engine.redact("张三考了 92 分，电话 13800138000")
        stats = self.engine.snapshot()
        self.assertGreaterEqual(stats["placeholders"], 2)
        self.assertIn("CHILD", stats["counts"])
        self.assertIn("PHONE", stats["counts"])


class AgentToolTest(unittest.TestCase):
    """Agent 写操作：必须走待确认流程；导入支持 dry-run。"""

    @classmethod
    def setUpClass(cls):
        from app.main import app  # noqa: F401  建表 + 迁移
        from app.database import SessionLocal
        from app.models import AgentProfile, AiBot, AiConversation, Child, Score, Subject

        cls.SessionLocal = SessionLocal
        cls.models = dict(Child=Child, Score=Score, Subject=Subject, AiBot=AiBot,
                          AiConversation=AiConversation, AgentProfile=AgentProfile)

    def setUp(self):
        from app.agent.tools import ToolContext
        from app.privacy import engine_for_db

        self.db = self.SessionLocal()
        for model in (self.models["Score"], self.models["Subject"], self.models["Child"]):
            self.db.query(model).delete()
        self.db.commit()
        self.bot = self.models["AiBot"](name="t", provider="deepseek", model="m")
        self.db.add(self.bot)
        self.db.flush()
        self.conv = self.models["AiConversation"](bot_id=self.bot.id, mode="agent")
        self.db.add(self.conv)
        self.db.commit()
        self.profile = self.db.query(self.models["AgentProfile"]).first()
        self.engine = engine_for_db(self.db, level="standard", use_model=False)
        self.ctx = ToolContext(db=self.db, profile=self.profile, conversation_id=self.conv.id,
                               bot_id=self.bot.id, auto_approve=False, allow_write=True,
                               engine=self.engine)

    def tearDown(self):
        self.db.close()

    def test_write_requires_confirmation(self):
        from app.agent.tools import execute_tool

        res = execute_tool("create_child", {"name": "测试孩子"}, self.ctx)
        self.assertEqual(res.get("status"), "pending_confirmation")
        self.assertTrue(res.get("token"))
        self.assertEqual(self.db.query(self.models["Child"]).count(), 0)

    def test_confirm_executes(self):
        from app.agent.tools import confirm_pending, execute_tool

        res = execute_tool("create_child", {"name": "测试孩子"}, self.ctx)
        out = confirm_pending(self.ctx, res["token"])
        self.assertTrue(out["ok"])
        self.assertEqual(self.db.query(self.models["Child"]).count(), 1)

    def test_duplicate_confirm_rejected(self):
        from app.agent.tools import ToolError, confirm_pending, execute_tool

        res = execute_tool("create_child", {"name": "测试孩子"}, self.ctx)
        confirm_pending(self.ctx, res["token"])
        with self.assertRaises(ToolError):
            confirm_pending(self.ctx, res["token"])

    def test_import_dry_run_does_not_write(self):
        from app.agent.tools import execute_tool

        payload = {
            "dry_run": True,
            "payload": {
                "children": [{"name": "导入孩子"}],
                "subjects": [{"name": "语文", "child": "导入孩子"}],
                "scores": [{"child": "导入孩子", "subject": "语文", "date": "2026-11-01",
                            "regular_score": 88, "regular_total": 100}],
            },
        }
        res = execute_tool("import_records", payload, self.ctx)
        self.assertTrue(res["ok"])
        self.assertTrue(res["dry_run"])
        self.assertEqual(self.db.query(self.models["Child"]).count(), 0)

    def test_import_invalid_rows_rejected(self):
        from app.agent.tools import execute_tool

        payload = {"dry_run": True, "payload": {"scores": [{"regular_score": "abc"}]}}
        res = execute_tool("import_records", payload, self.ctx)
        self.assertFalse(res["ok"])
        self.assertTrue(res["errors"])

    def test_readonly_profile_blocks_write(self):
        from app.agent.tools import execute_tool

        # 运行时按 profile 构造 ctx；只读配置会在 ctx.allow_write=False 时拒绝写入
        self.profile.allow_write = False
        self.db.commit()
        self.ctx.allow_write = False
        res = execute_tool("create_child", {"name": "测试孩子"}, self.ctx)
        self.assertFalse(res["ok"])
        self.assertIn("只读", res["error"])

    def test_model_cannot_self_confirm(self):
        """模型自己调用 confirm_pending_action 时必须被拒绝（用户未确认）。"""
        from app.agent.tools import execute_tool

        res = execute_tool("create_child", {"name": "测试孩子"}, self.ctx)
        token = res["token"]
        blocked = execute_tool("confirm_pending_action", {"token": token}, self.ctx)
        self.assertFalse(blocked["ok"])
        self.assertIn("尚未确认", blocked["error"])
        self.assertEqual(self.db.query(self.models["Child"]).count(), 0)

        # 用户本轮明确确认后才放行
        self.ctx.user_confirmed = True
        ok = execute_tool("confirm_pending_action", {"token": token}, self.ctx)
        self.assertTrue(ok["ok"])
        self.assertEqual(self.db.query(self.models["Child"]).count(), 1)


if __name__ == "__main__":
    unittest.main()
