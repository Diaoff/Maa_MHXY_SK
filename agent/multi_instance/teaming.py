# -*- coding: utf-8 -*-
"""
组队握手协调器（Team Handshake Coordinator）。

设计目标（对应设计文档「组队握手机制」）：多实例（多开账号）之间需要协调组队动作时，
提供一套可靠的握手协议——队长(leader)发信号、队员(member)应答，各阶段互相等待。

通信方式：文件系统 IPC（runtime/team/ 目录下的 JSON 文件）。
  - 之所以用文件而非内存：同一套协议既能支撑「单进程内顺序轮转」（RotationEngine
    把多个 tasker 跑在同一进程），也能支撑「多进程五开」（每个账号一个独立进程），
    跨进程时文件是唯一可靠的共享介质；同时 GUI 控制台和命令行工具也能直接读写同一份
    状态，形成「引擎 / GUI / CLI 三位一体」的观察与操控面。
  - 文件写入采用 temp + os.replace 原子替换；读取每次都读最新内容，单机多进程下足够稳健。

典型握手流程（副本 / 组队任务）：
  队长: signal_leader("inviting")              -> 队员: wait_leader("inviting") 后各自 signal_member(i, "accepted")
  队长: wait_all_members("accepted")            -> 全部就位后 signal_leader("enter_dungeon")
  队员: wait_leader("enter_dungeon")             -> 进副本
  ...
  signal_leader("done") / reset()

本模块不依赖 maa，可独立 import 与单元测试（无头环境即可验证协议本身）。
"""

from __future__ import annotations

import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 组队握手默认配置（用户 config 会按字段覆盖此结构）
TEAM_DEFAULT = {
    "enabled": False,
    "leader_index": 0,
    "leader_name": "",          # 队长角色名（用于队长ID库字节覆盖激活 tm_leader_id.png）
    "runtime_dir": "runtime/team",
    "poll_interval": 0.25,
}

# 常用阶段（仅作 GUI 下拉 / 文档约定，协议本身接受任意字符串）
TEAM_PHASES = [
    "lobby",          # 在长安 / 组队集合点
    "forming",        # 组队中
    "inviting",       # 队长已发起邀请
    "invited",        # 队员收到邀请
    "accepted",       # 队员已入队
    "enter_dungeon",  # 进入副本
    "in_dungeon",     # 副本进行中
    "done",           # 完成
    "abort",          # 中止
]

# 模块级「当前实例身份」（单进程内顺序轮转时由引擎设置）
_current_member_index = -1


def set_current_member_index(i):
    """设置当前进程对应的队员序号（单进程顺序轮转时由引擎在每号切换前调用）。"""
    global _current_member_index
    _current_member_index = int(i)


def current_member_index():
    """当前实例的队员序号：优先取环境变量 MHXY_TEAM_INDEX（多进程五开由启动脚本注入），
    否则取 set_current_member_index 设置的值，都没有返回 -1。"""
    ev = os.environ.get("MHXY_TEAM_INDEX")
    if ev is not None:
        try:
            return int(ev)
        except Exception:
            pass
    return _current_member_index


def current_leader_index():
    """环境变量注入的队长序号（多进程场景）。"""
    ev = os.environ.get("MHXY_TEAM_LEADER_INDEX")
    if ev is not None:
        try:
            return int(ev)
        except Exception:
            pass
    return None


def _atomic_write_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + f".tmp.{os.getpid()}.{int(time.time() * 1000)}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


class TeamCoordinator:
    """基于文件的组队握手协调器。"""

    def __init__(self, config=None, root=None):
        self.root = root or ROOT
        self.config = dict(TEAM_DEFAULT)
        if config:
            self.config.update({k: v for k, v in config.items() if k in TEAM_DEFAULT})
        self.dir = os.path.join(self.root, self.config["runtime_dir"])
        self.leader_file = os.path.join(self.dir, "leader_state.json")
        self.members_dir = os.path.join(self.dir, "members")
        self.meta_file = os.path.join(self.dir, "meta.json")
        self.poll_interval = float(self.config.get("poll_interval", 0.25))

    # ---- 角色配置 ----
    def set_roles(self, leader_index, member_indices=None):
        """登记队长与队员序号，并持久化到 meta.json（供跨进程 / GUI / CLI 共享）。"""
        leader_index = int(leader_index)
        member_indices = [int(i) for i in (member_indices or [])]
        _atomic_write_json(self.meta_file, {
            "leader_index": leader_index,
            "member_indices": member_indices,
            "updated": time.time(),
        })
        return self

    def _meta(self):
        return _read_json(self.meta_file, default={})

    @property
    def leader_index(self):
        li = self._meta().get("leader_index")
        if li is None:
            li = self.config.get("leader_index", 0)
        try:
            return int(li)
        except Exception:
            return 0

    @property
    def member_indices(self):
        idxs = self._meta().get("member_indices")
        if isinstance(idxs, list):
            return [int(i) for i in idxs]
        return []

    def all_indices(self):
        s = set(self.member_indices)
        s.add(self.leader_index)
        return sorted(s)

    # ---- 队长信号 ----
    def signal_leader(self, state):
        _atomic_write_json(self.leader_file, {"state": state, "ts": time.time()})
        return True

    def leader_state(self):
        d = _read_json(self.leader_file)
        return d.get("state") if isinstance(d, dict) else None

    def wait_leader(self, state, timeout=30.0):
        """阻塞等待队长状态变为 state；超时返回 False。"""
        deadline = time.time() + float(timeout)
        while True:
            if self.leader_state() == state:
                return True
            if time.time() >= deadline:
                return False
            time.sleep(self.poll_interval)

    # ---- 队员应答 ----
    def signal_member(self, index, state):
        index = int(index)
        _atomic_write_json(os.path.join(self.members_dir, f"{index}.json"),
                           {"state": state, "ts": time.time()})
        return True

    def member_state(self, index):
        d = _read_json(os.path.join(self.members_dir, f"{int(index)}.json"))
        return d.get("state") if isinstance(d, dict) else None

    def members_state(self):
        """返回 {idx: state}（供 GUI 实时展示）。"""
        out = {}
        try:
            names = os.listdir(self.members_dir)
        except FileNotFoundError:
            return out
        for n in names:
            if n.endswith(".json") and not n.startswith("."):
                idx = n[:-5]
                if idx.isdigit():
                    out[int(idx)] = self.member_state(int(idx))
        return out

    def wait_all_members(self, state, timeout=30.0, indices=None):
        """阻塞等待 indices 中所有队员状态均为 state；超时返回 False。"""
        if indices is None:
            indices = self.member_indices
        indices = [int(i) for i in indices]
        if not indices:
            return True
        deadline = time.time() + float(timeout)
        while True:
            if all(self.member_state(i) == state for i in indices):
                return True
            if time.time() >= deadline:
                return False
            time.sleep(self.poll_interval)

    # ---- 工具 ----
    def reset(self):
        """清除握手状态（保留角色 meta），用于一轮组队结束 / 异常中止后重启。"""
        try:
            if os.path.exists(self.leader_file):
                os.remove(self.leader_file)
        except OSError:
            pass
        try:
            if os.path.isdir(self.members_dir):
                for n in os.listdir(self.members_dir):
                    if n.endswith(".json"):
                        try:
                            os.remove(os.path.join(self.members_dir, n))
                        except OSError:
                            pass
        except OSError:
            pass


_default_coord = None


def get_coordinator():
    """模块级单例：引擎（同进程）与自定义节点共享同一协调器；跨进程则各进程指向同一
    runtime/team 目录，经文件共享状态。"""
    global _default_coord
    if _default_coord is None:
        _default_coord = TeamCoordinator()
    return _default_coord
