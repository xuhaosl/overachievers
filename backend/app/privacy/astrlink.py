"""AstrLink Guard 适配层。

AstrLink Guard（QuantumNous/astrlink-guard，Apache-2.0）是一个约 39MB 的
中英文 token 分类模型，magpie 在本地用它找出规则找不到的人名、地址、密码等。
本模块不强制下载模型，也不新增运行时依赖：

- 若 `ASTR_GUARD_DIR`（或 `DATA_DIR/models/astrlink-guard`）下存在
  `model_int8.onnx` / `model_int8.onnx_data` / `tokenizer.json`，
  且环境安装了 `onnxruntime` + `tokenizers` + `numpy`，则按通用 token
  分类流程加载并返回实体 span；
- 否则 `available=False`，脱敏引擎自动退化为内置规则 + 中文姓名上下文规则。

这样既保留了 AstrLink Guard 的“本地模型兜底”架构，又不会在没有模型文件的机器
上阻塞启动。模型文件与校验值固定在下面，便于用户自行放置或后续做下载器。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# 与 magpie 固定的 AstrLink Guard v0.1.3 文件一致
GUARD_REVISION = "7216b6a3b897ef903d4b1ba367ae6fb95b0fa5e4"
GUARD_FILES = {
    "model_int8.onnx": {"size": 330781, "sha256": "0a070d3113615e33ba3b84d6bd486f663a377c04c4b056e7381732179f51832a"},
    "model_int8.onnx_data": {
        "size": 37124608,
        "sha256": "0ba34216ceead01e0ae2dfd8e46d52b67e7aee80b04f722d9b758613a91c0067",
    },
    "tokenizer.json": {
        "size": 1502881,
        "sha256": "0cf3b235ef125658015a6c8026a5fe6f28088bf825101a990ec18a10200feef4",
    },
}

_LABEL_KINDS = (
    ("PER", "PERSON"),
    ("NAME", "PERSON"),
    ("PERSON", "PERSON"),
    ("LOC", "ADDRESS"),
    ("ADDR", "ADDRESS"),
    ("ORG", "SCHOOL"),
    ("SCHOOL", "SCHOOL"),
    ("PHONE", "PHONE"),
    ("TEL", "PHONE"),
    ("EMAIL", "EMAIL"),
    ("ID", "ID_CARD"),
    ("STUDENT", "STUDENT_NO"),
    ("SECRET", "API_KEY"),
)


def _kind_from_label(label: str) -> str:
    up = (label or "").upper().lstrip("BI-")
    for needle, kind in _LABEL_KINDS:
        if needle in up:
            return kind
    return "PII"


def _model_dir() -> Path:
    raw = os.environ.get("ASTR_GUARD_DIR", "").strip()
    if raw:
        return Path(raw)
    data = os.environ.get("DATA_DIR")
    base = Path(data) if data else Path(__file__).resolve().parents[3] / "data"
    return base / "models" / "astrlink-guard"


def _locate(base: Path) -> dict[str, Path]:
    """允许文件直接放在目录下，或放在 int8/ 子目录。"""
    found: dict[str, Path] = {}
    for name in GUARD_FILES:
        for candidate in (base / name, base / "int8" / name):
            if candidate.is_file():
                found[name] = candidate
                break
    return found


class AstrLinkGuard:
    def __init__(self, model_dir: Path | None = None):
        self.model_dir = model_dir or _model_dir()
        self.files = _locate(self.model_dir)
        self._tokenizer = None
        self._session = None
        self._labels: dict[int, str] = {}
        self._load_error = ""
        self._load_attempted = False

    # ---------- 状态 ----------
    @property
    def missing_files(self) -> list[str]:
        return [name for name in GUARD_FILES if name not in self.files]

    @property
    def available(self) -> bool:
        if self.missing_files:
            return False
        try:
            import numpy  # noqa: F401
            import onnxruntime  # noqa: F401
            import tokenizers  # noqa: F401
        except Exception:
            return False
        return True

    def status(self) -> dict[str, Any]:
        reason = ""
        if self.missing_files:
            reason = "模型文件缺失：" + "、".join(self.missing_files)
        elif not self.available:
            reason = "缺少 onnxruntime/tokenizers/numpy 运行时"
        elif self._load_error:
            reason = self._load_error
        return {
            "name": "AstrLink Guard",
            "revision": GUARD_REVISION,
            "model_dir": str(self.model_dir),
            "installed": not self.missing_files,
            "available": self.available and not self._load_error,
            "reason": reason,
            "files": list(GUARD_FILES),
            "license": "Apache-2.0",
        }

    # ---------- 加载 ----------
    def _load(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True
        if not self.available:
            self._load_error = self.status()["reason"]
            return
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer

            self._tokenizer = Tokenizer.from_file(str(self.files["tokenizer.json"]))
            self._session = ort.InferenceSession(
                str(self.files["model_int8.onnx"]),
                providers=["CPUExecutionProvider"],
            )
            # 标签表通常由 config.json / label_map.json 提供
            for cand in (self.model_dir / "config.json", self.model_dir / "int8" / "config.json",
                         self.model_dir / "label_map.json", self.model_dir / "int8" / "label_map.json"):
                if cand.is_file():
                    raw = json.loads(cand.read_text(encoding="utf-8"))
                    table = raw.get("id2label") or raw.get("labels") or raw
                    if isinstance(table, dict):
                        self._labels = {int(k): str(v) for k, v in table.items()}
                    elif isinstance(table, list):
                        self._labels = {i: str(v) for i, v in enumerate(table)}
                    break
            if not self._labels:
                self._load_error = "模型缺少 id2label 标签表，无法解析实体类型"
            _ = np  # 保持引用，避免被误判为未使用
        except Exception as exc:  # pragma: no cover - 取决于模型文件
            self._load_error = f"加载 AstrLink Guard 失败：{exc.__class__.__name__}: {exc}"

    # ---------- 推理 ----------
    def detect(self, text: str) -> list[dict[str, Any]]:
        if not text:
            return []
        self._load()
        if self._load_error or not self._session or not self._tokenizer or not self._labels:
            return []
        try:
            import numpy as np

            enc = self._tokenizer.encode(text)
            ids = enc.ids[:512]
            if not ids:
                return []
            offsets = enc.offsets[: len(ids)]
            inputs = {
                "input_ids": np.array([ids], dtype=np.int64),
                "attention_mask": np.ones((1, len(ids)), dtype=np.int64),
            }
            names = {i.name for i in self._session.get_inputs()}
            if "token_type_ids" in names:
                inputs["token_type_ids"] = np.zeros((1, len(ids)), dtype=np.int64)
            logits = self._session.run(None, {k: v for k, v in inputs.items() if k in names})[0]
            pred = logits[0].argmax(axis=-1)
            spans: list[dict[str, Any]] = []
            cur: dict[str, Any] | None = None
            for idx, label_id in enumerate(pred.tolist()):
                label = self._labels.get(int(label_id), "O")
                if label in ("O", "o", ""):
                    if cur:
                        spans.append(cur)
                        cur = None
                    continue
                kind = _kind_from_label(label)
                start, end = offsets[idx]
                if start == end:
                    continue
                if cur and cur["kind"] == kind and label.upper().startswith("I-"):
                    cur["end"] = end
                    cur["text"] = text[cur["start"] : end]
                else:
                    if cur:
                        spans.append(cur)
                    cur = {"kind": kind, "start": start, "end": end, "text": text[start:end],
                           "source": "astrlink", "score": 0.9}
            if cur:
                spans.append(cur)
            return [s for s in spans if s["end"] > s["start"]]
        except Exception:
            return []
