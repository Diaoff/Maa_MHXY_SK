# -*- coding: utf-8 -*-
"""
队长ID库（Leader ID Library）。

设计目标（对应设计文档「组队握手机制」的子项——队长ID库）：

在五开组队场景里，不同副本/不同时间常由「不同的号」当队长。MAA_MHXY_SK 的组队流水线
依赖一张「队长ID」模板图来识别谁是队长（模板键名铁律：`tm_leader_id`，改名会让用户已有
标定失效）。传统做法是手动替换这张图；本库把它做成「可切换的队长ID库」：

  - 每个候选队长（角色名 + 其 ID 区域的截图）登记进库；
  - 切换队长 = 把对应队长的模板图**字节覆盖**写到 `user/image/tm_leader_id.png`，
    路径串恒定不变（MAA 资源按文件名加载，路径不变即可被同一 pipeline 复用）；
  - 库本身用 JSON 持久化（记录角色名、使用次数、最近使用时间、模板字节 base64）。

铁律（来自设计文档）：`tm_leader_id.png` 的**路径串不变**，切换队长=字节覆盖不改路径串。
因此 activate() 必须是「写同一路径」，绝不能换文件名或改 interface.json 的资源声明。

字节覆盖而非复制：activate 把库里存的字节直接写回文件，避免外部文件被移动/删除后失效，
也保证 user/ 层优先于 base/ 层加载（interface.json 中 user 置于 base 前）。

本模块不依赖 maa，可独立 import 与无头测试。
"""

from __future__ import annotations

import base64
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 队长ID模板图：恒定路径 user/image/tm_leader_id.png（路径串永不变）
LEADER_ID_REL = os.path.join("assets", "resource", "user", "image", "tm_leader_id.png")
LEADER_ID_PATH = os.path.join(ROOT, LEADER_ID_REL)

# 库元数据文件（记录各候选队长及其模板字节）
META_REL = os.path.join("runtime", "team", "leader_history.json")
META_PATH = os.path.join(ROOT, META_REL)


def _atomic_write_bytes(path: str, data: bytes):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}.{int(time.time() * 1000)}"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _read_bytes(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _read_json(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: str, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class LeaderHistory:
    """队长ID库：登记候选队长，按需字节覆盖激活某队长。"""

    def __init__(self, meta_path: str = META_PATH, leader_id_path: str = LEADER_ID_PATH):
        self.meta_path = meta_path
        self.leader_id_path = leader_id_path
        self._cache = None

    # ---- 内部存储 ----
    def _load(self) -> dict:
        if self._cache is None:
            self._cache = _read_json(self.meta_path, default={"leaders": {}})
            if not isinstance(self._cache, dict) or "leaders" not in self._cache:
                self._cache = {"leaders": {}}
        return self._cache

    def _save(self):
        _write_json(self.meta_path, self._cache)

    # ---- 登记 ----
    def register(self, name: str, image_path: str = None, template_bytes: bytes = None) -> bool:
        """登记一个候选队长。

        name: 角色名（用作库内 key，唯一）。
        image_path: 队长ID区域截图（png）；与 template_bytes 二选一。
        返回是否成功。
        """
        name = str(name).strip()
        if not name:
            return False
        data = None
        if template_bytes is not None:
            data = template_bytes
        elif image_path and os.path.isfile(image_path):
            data = _read_bytes(image_path)
        if not data:
            return False

        store = self._load()
        leaders = store.setdefault("leaders", {})
        prev = leaders.get(name, {})
        leaders[name] = {
            "name": name,
            "template_b64": base64.b64encode(data).decode("ascii"),
            "registered": prev.get("registered", time.time()),
            "last_used": prev.get("last_used"),
            "use_count": int(prev.get("use_count", 0)),
        }
        self._save()
        return True

    def unregister(self, name: str) -> bool:
        store = self._load()
        if name in store.get("leaders", {}):
            del store["leaders"][name]
            self._save()
            return True
        return False

    # ---- 激活（字节覆盖） ----
    def activate(self, name: str) -> bool:
        """把 name 对应的队长模板**字节覆盖**到 user/image/tm_leader_id.png。

        路径串恒定（铁律）。成功返回 True。
        """
        name = str(name).strip()
        store = self._load()
        entry = store.get("leaders", {}).get(name)
        if not entry:
            return False
        data = base64.b64decode(entry["template_b64"])
        if not data:
            return False
        _atomic_write_bytes(self.leader_id_path, data)
        entry["last_used"] = time.time()
        entry["use_count"] = int(entry.get("use_count", 0)) + 1
        self._save()
        return True

    def current_leader(self) -> Optional[str]:
        """根据 user/image/tm_leader_id.png 的字节，反查当前激活的是哪位队长（若有）。"""
        cur = _read_bytes(self.leader_id_path)
        if cur is None:
            return None
        cur_b64 = base64.b64encode(cur).decode("ascii")
        store = self._load()
        for name, e in store.get("leaders", {}).items():
            if e.get("template_b64") == cur_b64:
                return name
        return None

    def list_leaders(self) -> list:
        """返回候选队长列表（含 name/registered/last_used/use_count）。"""
        store = self._load()
        out = []
        for name, e in store.get("leaders", {}).items():
            out.append({
                "name": name,
                "registered": e.get("registered"),
                "last_used": e.get("last_used"),
                "use_count": e.get("use_count", 0),
            })
        return sorted(out, key=lambda x: x.get("last_used") or 0, reverse=True)

    def ensure_image_file(self) -> bool:
        """确保 user/image/tm_leader_id.png 存在（首次无队长时写一个占位，避免 MAA 加载报错）。"""
        if not os.path.exists(self.leader_id_path):
            placeholder = (
                b"\x89PNG\r\n\x1a\n"  # 最小合法 PNG 头；真正使用时由 activate 覆盖为真实模板
            )
            _atomic_write_bytes(self.leader_id_path, placeholder)
            return True
        return False


# 模块级单例（与 TeamCoordinator 同一风格）
_default = None


def get_history() -> LeaderHistory:
    global _default
    if _default is None:
        _default = LeaderHistory()
    return _default
