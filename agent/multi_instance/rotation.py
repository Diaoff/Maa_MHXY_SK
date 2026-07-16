# -*- coding: utf-8 -*-
"""
时空版（PC 原生 Win32 窗口）多开轮转引擎。

设计目标（对应设计文档第三阶段「多开轮转引擎」）：
  在 MAA 外层用 Python 管理多个 MaaTasker 实例，每个实例绑定一个《梦幻西游：时空》
  客户端窗口（按 HWND），逐号轮转执行任务。

为什么需要本引擎 + 为什么切换前要激活窗口：
  config/controller_config.json 默认 input_backend="seize"（SendInput）。Seize 输入是发给
  【前台窗口】的，而不是某个 HWND。所以轮到某个号操作时，必须先用 agent.win32.adapter 把它的
  窗口强制切到前台（绕过 Windows 焦点抢占锁），否则点击会落在后台号上被吞/点歪。这正是
  agent/win32/adapter.py 里 _force_foreground / GameWindow.activate() 存在的意义。

MAA 接入采用官方 Python 绑定（MaaFw 5.x）：
  Win32Controller(hwnd=...) + Resource.post_bundle(...) + Tasker.bind(...) + Tasker.post_task(...)

关于自定义 action / recognition：
  项目里的自定义节点用 @AgentServer.custom_action / @AgentServer.custom_recognition 装饰，
  平时由 AgentServer 在 import agent.custom 时自动注册。本引擎用独立 Tasker，因此会在建实例时
  临时 patch 这两个装饰器，捕获注册名后转注册到每个 Resource 上（见 _collect_custom / _register_custom）。

关于可导入性：
  本模块只在「装有 MaaFw 的运行时（Windows + 时空版客户端）」下真正工作。开发环境若未装 maa，
  模块仍可正常 import（maa 为惰性导入）；--list-windows 仅走 adapter（纯 ctypes），完全不需要 maa。

用法见 tools/run_multi_instance.py。
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import pkgutil
import sys

from agent.safety.emergency_stop import (
    EmergencyStop,
    EMERGENCY_STOP_DEFAULT,
)
from agent.multi_instance.teaming import (
    TeamCoordinator,
    TEAM_DEFAULT,
    get_coordinator,
    set_current_member_index,
)

logger = logging.getLogger("MHXY_SK.multi_instance")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENT_DIR = os.path.join(ROOT, "agent")
for _p in (ROOT, AGENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

def _deep_update(base, override):
    """把 override 的字段嵌套合并进 base（原地修改），保留 base 的未覆盖项。"""
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


# config/controller_config.json 的 win32 段里用的是 MAA 风格的字符串，这里映射到枚举成员名。
INPUT_METHODS = {
    "seize": "Seize",
    "sendinput": "SendInput",
    "sendmessage": "SendMessage",
    "postmessage": "PostMessage",
}
SCREENCAP_METHODS = {
    "dxgi_desktopduplication": "DXGIDesktopDuplication",
    "dxgidesktopduplication": "DXGIDesktopDuplication",
    "dxgi_framepool": "FramePool",
    "framepool": "FramePool",
    "gdi": "GDI",
}

DEFAULT_CONFIG = {
    "enabled": False,
    "strategy": "sequential",
    "targets": {
        "multi": True,
        "multi_indices": [],
        "max_windows": 0,
        "single_index": 0,
    },
    "tasks": [
        {"entry": "fuli_qiandao"},
        {"entry": "bangpai_qiandao"},
    ],
    "global_pipeline_override": {},
    "activate_before_run": True,
    "stop_on_error": False,
    "resource_dirs": [
        "./assets/resource/base",
        "./assets/resource/user",
    ],
    "emergency_stop": EMERGENCY_STOP_DEFAULT,
    "team": TEAM_DEFAULT,
}


def _load_controller_config():
    cfg_path = os.path.join(ROOT, "config", "controller_config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f).get("win32", {})
    except Exception:
        return {}


class GameInstance:
    """一个游戏窗口 + 其专属的 controller / resource / tasker 封装。"""

    def __init__(self, window, controller, resource, tasker, name=""):
        self.window = window
        self.controller = controller
        self.resource = resource
        self.tasker = tasker
        self.name = name

    def shut_down(self):
        for obj in (self.tasker, self.resource, self.controller):
            try:
                if obj is not None and hasattr(obj, "shut_down"):
                    obj.shut_down()
            except Exception as e:  # noqa: BLE001
                logger.warning("[instance] %s 关闭失败: %s", self.name, e)


class RotationEngine:
    def __init__(self, config_path=None):
        self.config_path = config_path or os.path.join(
            ROOT, "config", "multi_instance.json")
        self.enabled = False
        self.strategy = "sequential"
        self.targets = {}
        self.tasks = []
        self.global_override = {}
        self.activate_before_run = True
        self.stop_on_error = False
        self.resource_dirs = []
        self.title_substr = "梦幻西游"
        self.win_config = {}
        self.estop_config = dict(EMERGENCY_STOP_DEFAULT)
        self.team_config = dict(TEAM_DEFAULT)
        self.load_config(self.config_path)

    # ---- 配置 ----
    def load_config(self, path):
        cfg = DEFAULT_CONFIG.copy()
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg.update(user_cfg)
        except FileNotFoundError:
            logger.warning("[config] 未找到 %s，使用默认配置", path)
        except Exception as e:  # noqa: BLE001
            logger.warning("[config] 读取 %s 失败(%s)，使用默认配置", path, e)

        self.enabled = cfg.get("enabled", False)
        self.strategy = cfg.get("strategy", "sequential")
        self.targets = cfg.get("targets", {})
        self.tasks = cfg.get("tasks", [])
        self.global_override = cfg.get("global_pipeline_override", {})
        self.activate_before_run = cfg.get("activate_before_run", True)
        self.stop_on_error = cfg.get("stop_on_error", False)
        self.resource_dirs = [
            d if os.path.isabs(d) else os.path.join(ROOT, d)
            for d in cfg.get("resource_dirs", DEFAULT_CONFIG["resource_dirs"])
        ]
        self.win_config = _load_controller_config()
        self.title_substr = self.win_config.get("window_title_substr", "梦幻西游")
        # 三重急停配置（按字段覆盖默认，保留未出现的默认项）
        estop = EMERGENCY_STOP_DEFAULT.copy()
        user_estop = cfg.get("emergency_stop")
        if isinstance(user_estop, dict):
            _deep_update(estop, user_estop)
        self.estop_config = estop

        # 组队握手配置（按字段覆盖默认，保留未出现的默认项）
        team = TEAM_DEFAULT.copy()
        user_team = cfg.get("team")
        if isinstance(user_team, dict):
            _deep_update(team, user_team)
        self.team_config = team

    def set_tasks(self, entries):
        """用命令行 --task 覆写任务列表。"""
        if entries:
            self.tasks = [{"entry": e} for e in entries]

    # ---- 窗口发现（纯 adapter，不需要 maa） ----
    def discover_windows(self):
        from agent.win32.adapter import (
            set_game_process,
            set_game_title_substr,
            resolve_targets,
        )
        set_game_process(self.win_config.get("window_process"))
        set_game_title_substr(self.title_substr)
        return resolve_targets(self.title_substr, self.targets)

    # ---- 后端枚举解析 ----
    def _resolve_input(self):
        from maa.controller import MaaWin32InputMethodEnum
        key = (self.win_config.get("input_backend") or "seize").strip().lower()
        member = INPUT_METHODS.get(key, "Seize")
        return getattr(MaaWin32InputMethodEnum, member, MaaWin32InputMethodEnum.Seize)

    def _resolve_screencap(self):
        from maa.controller import MaaWin32ScreencapMethodEnum
        key = (self.win_config.get("screencap_backend")
               or "dxgi_desktopduplication").strip().lower()
        member = SCREENCAP_METHODS.get(key, "DXGIDesktopDuplication")
        return getattr(MaaWin32ScreencapMethodEnum, member,
                       MaaWin32ScreencapMethodEnum.DXGIDesktopDuplication)

    # ---- 自定义 action / recognition 注册 ----
    def _collect_custom(self):
        """临时 patch AgentServer 装饰器，导入 agent.custom 整棵子树，捕获 (name, cls)。"""
        from maa.agent.agent_server import AgentServer

        actions, recogs = {}, {}
        orig_a = AgentServer.custom_action
        orig_r = AgentServer.custom_recognition

        AgentServer.custom_action = (
            lambda name: lambda cls: (actions.__setitem__(name, cls) or cls))
        AgentServer.custom_recognition = (
            lambda name: lambda cls: (recogs.__setitem__(name, cls) or cls))

        try:
            pkg = importlib.import_module("agent.custom")
            for sub in ("action", "recognition"):
                submod = importlib.import_module(f"agent.custom.{sub}")
                for mod in pkgutil.iter_modules(submod.__path__,
                                                f"agent.custom.{sub}."):
                    try:
                        m = importlib.import_module(mod.name)
                        importlib.reload(m)  # 重新触发装饰器（用 patch 后的版本）
                    except Exception as e:  # noqa: BLE001
                        logger.warning("[custom] 加载模块 %s 失败: %s",
                                       mod.name, e)
        finally:
            AgentServer.custom_action = orig_a
            AgentServer.custom_recognition = orig_r

        return actions, recogs

    def _register_custom(self, resource):
        actions, recogs = self._collect_custom()
        for name, cls in actions.items():
            try:
                resource.register_custom_action(name, cls())
            except Exception as e:  # noqa: BLE001
                logger.warning("[custom] 注册 action %s 失败: %s", name, e)
        for name, cls in recogs.items():
            try:
                resource.register_custom_recognition(name, cls())
            except Exception as e:  # noqa: BLE001
                logger.warning("[custom] 注册 recognition %s 失败: %s", name, e)

    # ---- 构建单实例 ----
    def _build_instance(self, window, index):
        from maa.controller import Win32Controller
        from maa.resource import Resource
        from maa.tasker import Tasker

        controller = Win32Controller(
            hwnd=window.hwnd,
            screencap_method=self._resolve_screencap(),
            mouse_method=self._resolve_input(),
            keyboard_method=self._resolve_input(),
        )
        try:
            controller.post_connection().wait()
        except Exception as e:  # noqa: BLE001
            logger.warning("[build] 窗口 %s 连接 wait 异常: %s",
                           window.hwnd, e)

        resource = Resource()
        for d in self.resource_dirs:
            try:
                resource.post_bundle(d).wait()
            except Exception as e:  # noqa: BLE001
                logger.warning("[build] 加载资源 %s 失败: %s", d, e)
        self._register_custom(resource)

        tasker = Tasker()
        tasker.bind(resource, controller)
        if not tasker.inited:
            raise RuntimeError(f"窗口 {window.hwnd} Tasker 初始化失败")
        return GameInstance(
            window=window,
            controller=controller,
            resource=resource,
            tasker=tasker,
            name=f"#{index} {window.title}",
        )

    # ---- 单账号执行 ----
    def _run_account(self, inst, tasks, estop=None):
        for t in tasks:
            if estop is not None and estop.is_triggered():
                return
            entry = t.get("entry")
            if not entry:
                continue
            override = {**self.global_override,
                        **(t.get("pipeline_override") or {})}
            if self.activate_before_run:
                ok = inst.window.activate()
                if not ok:
                    logger.warning("[run] %s 切前台失败，Seize 输入可能点歪",
                                   inst.name)
            logger.info("[run] %s 执行任务 %s", inst.name, entry)
            try:
                detail = inst.tasker.post_task(entry, override).wait().get()
                logger.info("[run] %s 任务 %s 完成: %s",
                            inst.name, entry, detail)
            except Exception as e:  # noqa: BLE001
                logger.error("[run] %s 任务 %s 异常: %s", inst.name, entry, e)
                if self.stop_on_error:
                    raise

    # ---- 主流程 ----
    def run(self):
        from maa.toolkit import Toolkit

        Toolkit.init_option(ROOT)

        windows = self.discover_windows()
        if not windows:
            logger.error("[run] 未发现任何时空版窗口，退出")
            return False

        logger.info("[run] 发现 %d 个窗口，开始轮转", len(windows))
        instances = []
        estop = None
        try:
            for i, w in enumerate(windows):
                inst = self._build_instance(w, i)
                instances.append(inst)

            # 三重急停：把所有实例的 tasker 纳入监管并启动监听通道
            estop = EmergencyStop(self.estop_config)
            estop.arm([inst.tasker for inst in instances]).start()

            # 组队握手：登记队长 / 队员角色，并给每个实例注入身份（供 pipeline 的
            # TeamRole / TeamHandshake 节点判定当前号是队长还是队员）。顺序轮转下
            # 各号分时运行，握手节点通过 runtime/team/ 文件与（可能的）其他进程共享状态。
            coord = None
            if self.team_config.get("enabled"):
                coord = get_coordinator()
                coord.config = dict(self.team_config)
                leader = int(self.team_config.get("leader_index", 0))
                member_indices = [i for i in range(len(instances)) if i != leader]
                coord.set_roles(leader, member_indices)
                logger.info("[run] 组队握手已启用：队长=%d 队员=%s",
                            leader, member_indices)
                # 设队长即激活其 ID 模板（字节覆盖 user/image/tm_leader_id.png，
                # 路径串不变）。队长ID库为空时静默跳过，不影响组队流程。
                leader_name = self.team_config.get("leader_name") or ""
                if leader_name:
                    try:
                        from agent.multi_instance.leader_history import get_history
                        get_history().activate(leader_name)
                        logger.info("[run] 已激活队长ID模板: %s", leader_name)
                    except Exception as e:  # 路径错误/未登记等，不应阻断主流程
                        logger.warning("[run] 激活队长ID模板失败(已忽略): %s", e)

            if self.strategy == "sequential":
                for idx, inst in enumerate(instances):
                    if estop.is_triggered():
                        break
                    if coord is not None:
                        set_current_member_index(idx)
                        os.environ["MHXY_TEAM_INDEX"] = str(idx)
                        os.environ["MHXY_TEAM_LEADER_INDEX"] = str(coord.leader_index)
                    self._run_account(inst, self.tasks, estop)
            else:
                logger.warning("[run] 未知策略 %s，回退到 sequential",
                               self.strategy)
                for idx, inst in enumerate(instances):
                    if estop.is_triggered():
                        break
                    if coord is not None:
                        set_current_member_index(idx)
                        os.environ["MHXY_TEAM_INDEX"] = str(idx)
                        os.environ["MHXY_TEAM_LEADER_INDEX"] = str(coord.leader_index)
                    self._run_account(inst, self.tasks, estop)
            if estop.is_triggered():
                logger.warning("[run] 因急停提前结束轮转")
                return False
            return True
        finally:
            if estop is not None:
                estop.stop()
            for inst in instances:
                inst.shut_down()
