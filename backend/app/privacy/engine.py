"""可逆脱敏引擎（magpie 架构的 Python 实现）。

核心思路与 magpie 的 `internal/redact` / `internal/pii` 一致：

1. **稳定占位符**：同一个值在同一主密钥下始终得到同一个
   `{{KIND_8位Base32}}`，因此多轮对话、缓存前缀、工具参数都能保持一致；
2. **可逆**：占位符→原值只保存在本次请求的内存 vault 中，模型回传后原样还原；
3. **流式安全**：SSE 分片可能把 `{{CHILD_` 和 `xxxx}}` 拆开，`StreamRestorer`
   会暂存可能是占位符前缀的尾部，等下一片到齐再还原；
4. **多来源检测**：数据库词表（孩子/学校/班级/竞争对手/学号）+ 正则
   （手机/邮箱/身份证/银行卡/地址/密钥）+ 中文姓名上下文规则 +
   可选 AstrLink Guard 本地模型；
5. **最小暴露**：默认只把脱敏后的文本发给第三方模型，原始数据留在本地。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..crypto import placeholder_for

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z][A-Z0-9_]{0,24}_[A-Z2-7]{4,16}\}\}")
LEVELS = ("off", "standard", "strict")

KIND_LABELS = {
    "CHILD": "孩子姓名",
    "PERSON": "个人姓名",
    "SCHOOL": "学校",
    "CLASS": "班级",
    "STUDENT_NO": "学号/考号",
    "PHONE": "电话",
    "EMAIL": "邮箱",
    "ID_CARD": "身份证号",
    "BANK_CARD": "银行卡号",
    "ADDRESS": "地址",
    "BIRTHDATE": "出生日期",
    "API_KEY": "密钥/令牌",
    "URL_CRED": "URL 凭据",
    "PRIVATE_KEY": "私钥",
    "IP": "内网 IP",
    "SOCIAL": "社交账号",
    "PII": "个人信息",
}

SOURCE_PRIORITY = {"lexicon": 4, "astrlink": 3, "zh_name": 2, "rule": 1}


@dataclass(frozen=True)
class Finding:
    kind: str
    value: str
    start: int
    end: int
    source: str = "rule"
    score: float = 1.0


@dataclass
class PrivacyStats:
    level: str = "standard"
    counts: dict[str, int] = field(default_factory=dict)
    placeholders: int = 0
    chars: int = 0
    entities: int = 0
    sources: dict[str, int] = field(default_factory=dict)

    def add(self, finding: Finding) -> None:
        self.counts[finding.kind] = self.counts.get(finding.kind, 0) + 1
        self.sources[finding.source] = self.sources.get(finding.source, 0) + 1
        self.placeholders += 1
        self.chars += len(finding.value)
        self.entities += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "counts": dict(self.counts),
            "labels": {k: KIND_LABELS.get(k, k) for k in self.counts},
            "placeholders": self.placeholders,
            "chars": self.chars,
            "entities": self.entities,
            "sources": dict(self.sources),
        }


# ---------------------------------------------------------------------------
# 中文姓名上下文规则
# ---------------------------------------------------------------------------

ZH_SURNAMES = set(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖萧田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付傅方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹申欧耿关兰焦俞左柳甘祝包宁尚符舒阮柯纪梅童凌毕单季裴霍涂成苗谷盛曲翁冉骆蓝路游辛靳管柴蒙鲍华喻祁蒲房滕屈饶解牟艾尤阳时穆农司卓古吉缪简车项连芦麦褚娄窦戚岑景党宫费卜冷晏席卫米柏宗瞿桂全佟应臧闵苟邬边卞姬师仇栾隋商刁沙荣巫寇桑郎甄丛仲虞敖巩佘池查麻苑迟邝"
)
ZH_COMPOUND = {
    "欧阳", "司马", "上官", "诸葛", "东方", "皇甫", "尉迟", "公孙", "慕容", "令狐",
    "司徒", "夏侯", "长孙", "宇文", "轩辕", "端木", "独孤", "南宫", "西门", "钟离",
    "呼延", "申屠", "闻人", "澹台", "拓跋", "万俟",
}
ZH_NICK_SURNAMES = set("王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘蒋蔡杜叶程苏魏吕丁沈姚卢姜崔钟谭陆汪范金廖贾夏方邹孟熊秦江薛段雷侯史陶贺顾毛郝龚邵钱严武戴孔汤")
ZH_NOT_GIVEN = set(
    "的了在是和与跟同说他她它我你您们这那个不也都就还把被给到对从向为以等及或并而吗呢吧啊去来有没要会能让请已将再又很更最先后上下里外时年日号发打回写问讲叫找用做看想知道得地着过之其此每各某该所反表认提负"
)
# 以姓氏开头、但明显是普通词/教育词汇，避免把“成绩”“单元”当人名
ZH_WORDS = set(
    """
    成绩 单元 测试 期中 期末 考试 语文 数学 英语 物理 化学 生物 历史 地理 政治 科学 道法
    班级 学校 年级 学期 老师 同学 家长 孩子 姓名 排名 分数 错题 试卷 作业 学习 复习 预习
    上课 下课 暑假 寒假 周末 今天 明天 昨天 时间 日期 方法 方面 方案 方向 文件 文本 文档
    文字 文章 文化 文明 文献 文法 文具 安全 安装 安排 完成 成功 成为 成本 成员 成果 成熟
    解决 解释 解析 查询 查看 查找 检查 简单 简介 简历 简化 游戏 游客 商品 商店 商业 费用
    舒服 辛苦 纪律 管道 项目 关键 关注 关心 关联 关于 关系 关闭 连接 应用 应该 单位 单独
    司机 路径 路由 林业 龙头 柏林 米饭 宁可 师傅 老板 老婆 老公 老家 小时 小心 小说
    小姐 小孩 小组 周一 周二 周三 周四 周五 周六 周日 周天 文案 文风 文学 方块 方针 方程
    方框 段落 章节 颜色 蓝色 包装 包名 时区 时长 时段 时刻 时代 季度 严格 严重 曾经 麻烦
    安卓 谷歌 常规 常数 边框 边界 边缘 付费 付款 路线 简洁 范例 左边 左侧 焦点 毕竟 尚未
    陆续 连续 连线 林间 林区 谢谢 顾客 顾问 房间 房子 高端 高层 古代 古典 农业 司法 施工
    卫生 荣誉 宗旨 齐全 凌晨 冷却 蒙版 曲线 黄金 白天 白板 白名 金钱 石油 夏天 夏季 唐朝
    宋朝 秦朝 申请 符号 景色 席位 车间 何时 何况 于是 余下 杜绝 罗列 程式 叶片 涂层 沙发
    池子 巩固 迟到 仲裁 钟点 钟表 向导 史诗 易懂 马路 马虎 汤汁 朱红 阳光 任职 董事 边距
    边栏 尚需 张量 张开 张贴 高度 高效 高级 高速 高亮 高手 高兴 王国 王者 黄河 黄色 方便
    程度 温度 白色 金额 金融 江湖 石头 马上 周期 周末 周围 周边 余额 钱包 叶子 毛病 毛利
    毛重 毛坯 毛巾 毛衣 万一 雷达 宋体 常量 常用 常见 向量 向上 全部 全局 全面 史上 易用
    武器 时候 明确 明白 任何 任务 任意 华为 管理 许多 许可 包括 包含 兑换 兄弟 光明 免费
    """
)
ZH_NOUN_ENDS = set("词单字性率值码型键框栏库器类表量度点线层期区图版式页数论员价计费件名夹帧戳")
ZH_COLOURS = set("红橙黄绿蓝紫黑白灰褐棕粉赤")
ZH_ROLES = ("客户", "联系人", "作者", "提交者", "审核人", "审批人", "负责人", "经办人", "收件人",
            "发件人", "收货人", "申请人", "报告人", "同事", "姓名", "名字", "署名", "签名",
            "我叫", "他叫", "她叫", "名叫", "叫做", "尊敬的", "亲爱的", "致", "@")
ZH_BEFORE = ("给", "找", "问", "让", "告诉", "通知", "联系", "抄送", "转给", "交给", "一下",
             "叫", "和", "与", "跟", "说", "请", "我是", "他是", "她是")
ZH_AFTER = ("先生", "女士", "小姐", "老师", "同学", "同志", "经理", "总监", "主任", "师傅",
            "医生", "律师", "教授", "博士", "说", "讲", "表示", "认为", "反馈", "提到", "提交",
            "负责", "告诉", "回复", "发", "打", "明天", "今天", "昨天", "已经", "他", "她")
ZH_TITLES = ("先生", "女士", "小姐", "老师", "同学", "同志", "经理", "总监", "主任", "师傅",
             "医生", "律师", "教授", "博士")


def _word_shaped(value: str) -> bool:
    if len(value) < 2:
        return False
    if value in ZH_WORDS:
        return True
    if all(ch in ZH_COLOURS for ch in value) or value.endswith("色"):
        return True
    if len(value) == 3 and value[:2] in ZH_WORDS and value[2] in ZH_NOUN_ENDS:
        return True
    return False


def zh_name_findings(text: str, aggressive: bool = False) -> list[Finding]:
    out: list[Finding] = []
    n = len(text)
    i = 0
    while i < n:
        surname_len = 0
        if i + 1 < n and text[i : i + 2] in ZH_COMPOUND:
            surname_len = 2
        elif text[i] in ZH_SURNAMES:
            surname_len = 1
        if not surname_len:
            i += 1
            continue
        # 昵称：小王、老李
        nick = i > 0 and text[i - 1] in "小老" and surname_len == 1
        matched = False
        for given_len in (2, 1):
            start = i - 1 if nick else i
            end = i + surname_len + given_len
            if end > n:
                continue
            given = text[i + surname_len : end]
            if not given or any(ch in ZH_NOT_GIVEN or not ("\u4e00" <= ch <= "\u9fff") for ch in given):
                continue
            candidate = text[start:end]
            if len(candidate) < 2 or _word_shaped(candidate):
                continue
            before = text[max(0, start - 8) : start]
            after = text[end : end + 8]
            role_before = any(before.endswith(w) for w in ZH_ROLES)
            verb_before = any(before.endswith(w) for w in ZH_BEFORE)
            title_after = any(after.startswith(w) for w in ZH_TITLES)
            verb_after = any(after.startswith(w) for w in ZH_AFTER)
            if nick or role_before or title_after or (verb_before and verb_after) or aggressive:
                # 避免把句首普通词（“成绩已经…”）当人名：aggressive 也要求不是教育词
                if aggressive and not (nick or role_before or title_after or verb_before or verb_after):
                    if len(candidate) < 3:
                        continue
                out.append(Finding("PERSON", candidate, start, end, "zh_name", 0.72 if aggressive else 0.9))
                i = end
                matched = True
                break
        if not matched:
            i += surname_len
    return out


# ---------------------------------------------------------------------------
# 正则规则
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    kind: str
    pattern: re.Pattern[str]
    group: int = 0
    validator: Any = None


def _luhn(number: str) -> bool:
    digits = [int(ch) for ch in re.sub(r"\D", "", number)]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for idx, digit in enumerate(digits):
        if idx % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _private_ip(value: str) -> bool:
    import ipaddress

    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


RULES: list[Rule] = [
    Rule("PRIVATE_KEY", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z0-9 ]*PRIVATE KEY-----")),
    Rule("API_KEY", re.compile(r"\bsk-(?:ant-|proj-|or-|svcacct-|admin-)?[A-Za-z0-9_-]{16,}")),
    Rule("API_KEY", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|glpat-[A-Za-z0-9_-]{20,})")),
    Rule("API_KEY", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    Rule("API_KEY", re.compile(r"\bxox[abposr]-[0-9A-Za-z-]{10,}\b")),
    Rule("API_KEY", re.compile(r"(?:api[_-]?key|access[_-]?token|secret[_-]?key|password|passwd|pwd)\s*[:=：]\s*[\"']?([A-Za-z0-9_\-./+]{8,})", re.I), 1),
    Rule("EMAIL", re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])")),
    Rule("PHONE", re.compile(r"(?<!\d)(?:\+?86[-\s]?)?(?:1[3-9]\d{9}|0\d{2,3}[-\s]?\d{7,8})(?!\d)")),
    Rule("ID_CARD", re.compile(r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")),
    Rule("BANK_CARD", re.compile(r"(?<!\d)(?:\d[ -]?){16,19}(?!\d)"), validator=_luhn),
    Rule("BIRTHDATE", re.compile(r"(?:出生|生日|生于)\s*[:：]?\s*(?:19|20)\d{2}\s*[-年/.]\s*\d{1,2}\s*[-月/.]\s*\d{1,2}\s*日?")),
    Rule("STUDENT_NO", re.compile(r"(?:学号|学籍号|考号|准考证号)\s*[:：]?\s*([A-Za-z0-9-]{4,24})", re.I), 1),
    Rule("ADDRESS", re.compile(
        r"[\u4e00-\u9fa5]{2,8}(?:省|自治区|特别行政区)[\u4e00-\u9fa5]{2,8}(?:市|自治州|地区)"
        r"[\u4e00-\u9fa5]{2,8}(?:区|县|旗)[\u4e00-\u9fa5A-Za-z0-9]{2,25}(?:路|街|巷|号|小区|苑|花园|大厦|楼|栋|单元|室)"
    )),
    Rule("ADDRESS", re.compile(r"[\u4e00-\u9fa5]{2,10}(?:小区|花园|苑|公寓|大厦)[A-Za-z0-9]{0,8}(?:栋|号楼|单元|室|层)")),
    Rule("ADDRESS", re.compile(r"[\u4e00-\u9fa5]{2,8}(?:市|区|县)[\u4e00-\u9fa5]{2,20}(?:路|街|巷|号)")),
    Rule("URL_CRED", re.compile(r"https?://[^\s/:@]+:[^\s/@]+@[^\s]+", re.I)),
    Rule("SOCIAL", re.compile(r"(?:微信|wechat|QQ|qq)\s*(?:号|ID)?\s*[:：]?\s*[A-Za-z0-9_-]{5,20}")),
    Rule("IP", re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)"), validator=_private_ip),
]


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------

class PrivacyEngine:
    def __init__(
        self,
        lexicon: dict[str, Iterable[str]] | None = None,
        level: str = "standard",
        guard: Any = None,
        aggressive_names: bool | None = None,
    ):
        self.level = level if level in LEVELS else "standard"
        self.guard = guard
        self.aggressive_names = (self.level == "strict") if aggressive_names is None else aggressive_names
        self.vault: dict[str, str] = {}
        self._by_value: dict[str, str] = {}
        self.stats = PrivacyStats(level=self.level)
        self.lexicon = {k: set(v) for k, v in (lexicon or {}).items() if v}
        self._lexicon_re: dict[str, re.Pattern[str]] = {}
        self._compile_lexicon()

    # ---------- 词表 ----------
    def _compile_lexicon(self) -> None:
        for kind, values in self.lexicon.items():
            cleaned = [v.strip() for v in values if isinstance(v, str) and len(v.strip()) >= 2]
            # 过滤明显无意义的占位值
            cleaned = [v for v in cleaned if v not in ("无", "未知", "None", "null")]
            if not cleaned:
                continue
            cleaned = sorted(set(cleaned), key=len, reverse=True)
            parts = []
            for value in cleaned:
                esc = re.escape(value)
                if value[0].isascii() and value[0].isalnum():
                    esc = r"(?<![A-Za-z0-9])" + esc
                if value[-1].isascii() and value[-1].isalnum():
                    esc = esc + r"(?![A-Za-z0-9])"
                parts.append(esc)
            try:
                self._lexicon_re[kind] = re.compile("|".join(parts), re.I)
            except re.error:
                continue

    # ---------- 检测 ----------
    def detect(self, text: str) -> list[Finding]:
        if not text:
            return []
        findings: list[Finding] = []
        for kind, pattern in self._lexicon_re.items():
            for m in pattern.finditer(text):
                findings.append(Finding(kind, m.group(0), m.start(), m.end(), "lexicon", 1.0))
        for rule in RULES:
            for m in rule.pattern.finditer(text):
                value = m.group(rule.group)
                if not value:
                    continue
                if rule.validator and not rule.validator(value):
                    continue
                start, end = m.span(rule.group)
                findings.append(Finding(rule.kind, value, start, end, "rule", 0.95))
        findings.extend(zh_name_findings(text, self.aggressive_names))
        if self.guard is not None and getattr(self.guard, "available", False):
            for ent in self.guard.detect(text) or []:
                start, end = int(ent.get("start", 0)), int(ent.get("end", 0))
                value = text[start:end]
                if value and end > start:
                    findings.append(Finding(ent.get("kind", "PII"), value, start, end, "astrlink",
                                            float(ent.get("score", 0.9))))
        return self._merge(findings)

    @staticmethod
    def _merge(findings: list[Finding]) -> list[Finding]:
        # 先按起点、再按长度降序、再按来源优先级
        findings = sorted(
            findings,
            key=lambda f: (f.start, -(f.end - f.start), -SOURCE_PRIORITY.get(f.source, 0), -f.score),
        )
        chosen: list[Finding] = []
        last_end = -1
        for f in findings:
            if f.start < last_end or f.end <= f.start:
                continue
            chosen.append(f)
            last_end = f.end
        return chosen

    # ---------- 脱敏 ----------
    def redact(self, text: str) -> str:
        if not text or self.level == "off":
            return text
        findings = [f for f in self.detect(text) if not PLACEHOLDER_RE.fullmatch(f.value)]
        if not findings:
            return text
        out: list[str] = []
        pos = 0
        for f in findings:
            out.append(text[pos : f.start])
            token = self._token(f.kind, f.value)
            out.append(token)
            pos = f.end
            self.stats.add(f)
        out.append(text[pos:])
        return "".join(out)

    def _token(self, kind: str, value: str) -> str:
        existing = self._by_value.get(value)
        if existing:
            return existing
        token = placeholder_for(kind, value)
        self.vault[token] = value
        self._by_value[value] = token
        return token

    def redact_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.redact(obj)
        if isinstance(obj, list):
            return [self.redact_obj(v) for v in obj]
        if isinstance(obj, tuple):
            return tuple(self.redact_obj(v) for v in obj)
        if isinstance(obj, dict):
            return {k: self.redact_obj(v) for k, v in obj.items()}
        return obj

    # ---------- 还原 ----------
    def restore(self, text: str) -> str:
        if not text or not self.vault:
            return text

        def sub(m: re.Match[str]) -> str:
            return self.vault.get(m.group(0), m.group(0))

        return PLACEHOLDER_RE.sub(sub, text)

    def restore_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.restore(obj)
        if isinstance(obj, list):
            return [self.restore_obj(v) for v in obj]
        if isinstance(obj, tuple):
            return tuple(self.restore_obj(v) for v in obj)
        if isinstance(obj, dict):
            return {k: self.restore_obj(v) for k, v in obj.items()}
        return obj

    def unresolved_placeholders(self, obj: Any) -> list[str]:
        found: list[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, str):
                for m in PLACEHOLDER_RE.finditer(value):
                    if m.group(0) not in self.vault:
                        found.append(m.group(0))
            elif isinstance(value, (list, tuple)):
                for v in value:
                    walk(v)
            elif isinstance(value, dict):
                for v in value.values():
                    walk(v)

        walk(obj)
        return list(dict.fromkeys(found))

    # ---------- 状态 ----------
    def status(self) -> dict[str, Any]:
        guard_status = self.guard.status() if self.guard is not None and hasattr(self.guard, "status") else None
        return {
            "level": self.level,
            "guard": guard_status,
            "rules": ["lexicon", "regex", "zh_name"] + (["astrlink"] if guard_status and guard_status.get("available") else []),
            "kinds": KIND_LABELS,
            "stats": self.stats.as_dict(),
        }

    def snapshot(self) -> dict[str, Any]:
        return self.stats.as_dict()


# ---------------------------------------------------------------------------
# 流式恢复
# ---------------------------------------------------------------------------

class StreamRestorer:
    """处理 SSE 分片：把可能被拆开的 `{{KIND_hash}}` 暂存到下一片。"""

    def __init__(self, engine: PrivacyEngine, max_token_len: int = 64):
        self.engine = engine
        self.max_token_len = max_token_len
        self.buf = ""

    def feed(self, delta: str) -> str:
        if not delta:
            return ""
        self.buf += delta
        out: list[str] = []
        while True:
            idx = self.buf.find("{{")
            if idx < 0:
                # 结尾的单个 "{" 可能是下一片占位符的开头
                if self.buf.endswith("{"):
                    out.append(self.buf[:-1])
                    self.buf = "{"
                else:
                    out.append(self.buf)
                    self.buf = ""
                break
            if idx > 0:
                out.append(self.buf[:idx])
                self.buf = self.buf[idx:]
            end = self.buf.find("}}")
            if end < 0:
                if len(self.buf) > self.max_token_len:
                    out.append(self.buf)
                    self.buf = ""
                break
            token = self.buf[: end + 2]
            out.append(self.engine.restore(token))
            self.buf = self.buf[end + 2 :]
        return "".join(out)

    def flush(self) -> str:
        rest = self.engine.restore(self.buf)
        self.buf = ""
        return rest


# ---------------------------------------------------------------------------
# 数据库词表
# ---------------------------------------------------------------------------

def build_lexicon(db: Any) -> dict[str, set[str]]:
    """从本地库提取需要稳定的实体词。只读，不落盘。"""
    from sqlalchemy import select

    from ..models import Child, Exam, SchoolClass, Score, rival_names

    lexicon: dict[str, set[str]] = {"CHILD": set(), "PERSON": set(), "SCHOOL": set(),
                                    "CLASS": set(), "STUDENT_NO": set()}
    for child in db.scalars(select(Child)).all():
        if child.name:
            lexicon["CHILD"].add(child.name.strip())
    for cls in db.scalars(select(SchoolClass)).all():
        if cls.school:
            lexicon["SCHOOL"].add(cls.school.strip())
        if cls.name:
            lexicon["CLASS"].add(cls.name.strip())
        if cls.student_no:
            lexicon["STUDENT_NO"].add(cls.student_no.strip())
        for name in rival_names(cls.rivals or ""):
            if name and len(name) >= 2:
                lexicon["PERSON"].add(name.strip())
    for row in db.scalars(select(Score).where(Score.high_scorer != "")).all():
        for name in (row.high_scorer or "").split("、"):
            if name and len(name.strip()) >= 2:
                lexicon["PERSON"].add(name.strip())
    for row in db.scalars(select(Exam).where(Exam.high_scorer != "")).all():
        for name in (row.high_scorer or "").split("、"):
            if name and len(name.strip()) >= 2:
                lexicon["PERSON"].add(name.strip())
    return lexicon


def default_level() -> str:
    import os

    raw = (os.environ.get("PRIVACY_LEVEL") or "standard").strip().lower()
    return raw if raw in LEVELS else "standard"


def engine_for_db(db: Any, level: str | None = None, use_model: bool | None = None) -> PrivacyEngine:
    from .astrlink import AstrLinkGuard

    lvl = level or default_level()
    if use_model is None:
        use_model = (__import__("os").environ.get("PRIVACY_GUARD_MODEL", "auto") or "auto").lower() != "off"
    guard = AstrLinkGuard() if use_model else None
    return PrivacyEngine(build_lexicon(db), level=lvl, guard=guard)


def privacy_status() -> dict[str, Any]:
    from .astrlink import AstrLinkGuard

    guard = AstrLinkGuard()
    return {
        "default_level": default_level(),
        "levels": list(LEVELS),
        "kinds": KIND_LABELS,
        "guard": guard.status(),
        "architecture": "magpie-style stable placeholders + reversible vault + streaming holdback",
    }
