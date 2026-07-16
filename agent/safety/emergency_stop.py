# -*- coding: utf-8 -*-
"""
三重急停（Triple Emergency Stop）。

在 MAA 外层提供三条相互独立的急停通道，任一触发即调用所有已注册 MaaTasker 的
``stop()``（设计原则：增强全部外置，不侵入 MAA 核心）。

三条通道（对应设计文档「三重急停机制」）：
  1. 全局热键（Global Hotkey）：任意窗口焦点下按组合键即可急停
     （纯 ctypes RegisterHotKey + 消息泵，无需第三方库）。
  2. 鼠标甩屏角（Mouse Fling to Corner）：把鼠标快速「甩」进任一屏幕角即急停
     （低层鼠标钩子 WH_MOUSE_LL 测瞬时速度 + 屏幕角判定）。
  3. 哨兵文件（Kill-switch Sentinel）：监视一个标志文件，任何进程 / 外部脚本 /
     GUI 按钮创建它即可跨实例广播急停（多开场景下尤其关键——一条命令停掉所有号）。

设计要点：
  - 纯 ctypes 实现，零新增依赖（不引入 pynput / keyboard），Windows 上无需额外安装；
    非 Windows 平台 start() 自动降级为仅启用哨兵文件（仍是跨平台可用的兜底通道）。
  - 触发后「锁存」（latched），不会因触发条件消失而自动恢复；需显式 reset()。
  - 监听线程均为 daemon，主程序退出即随之结束；单个监听出错仅记日志不抛异常，
    不影响其余通道与主线任务。
  - 对外可手动 trigger(reason)（如 GUI 急停按钮），也可用 reset() 解除锁存。
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import time
from ctypes import wintypes

logger = logging.getLogger("MHXY_SK.safety")

IS_WIN = sys.platform == "win32"

# 通道默认配置（用户 config 会按字段覆盖此结构）
EMERGENCY_STOP_DEFAULT = {
    "enabled": True,
    "hotkey": {"enabled": True, "modifiers": ["ctrl", "shift"], "key": "X"},
    "mouse_corner": {"enabled": True, "corner_margin": 24, "min_speed": 1500},
    "sentinel_file": {"enabled": True, "path": "runtime/emergency_stop.flag"},
}

# ---- 键码 / 修饰键映射（仅 Windows 热键通道用） ----
_VK_MAP = {
    "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdn": 0x22,
    "pause": 0x13, "printscreen": 0x2C, "insert": 0x2D,
}
_MOD_MAP = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}

_WM_HOTKEY = 0x0312
_WM_QUIT = 0x12
_WH_MOUSE_LL = 14
_WM_MOUSEMOVE = 0x200


def _resolve_vk(key):
    """名字 -> Windows 虚拟键码(VK)。失败返回 0。"""
    if not key:
        return 0
    k = str(key).lower()
    if k in _VK_MAP:
        return _VK_MAP[k]
    if k.startswith("f") and k[1:].isdigit() and 1 <= int(k[1:]) <= 24:
        return 0x70 + int(k[1:]) - 1
    if len(k) == 1 and k.isalnum():
        try:
            res = ctypes.windll.user32.VkKeyScanW(ord(k.upper()))
            return res & 0xFF
        except Exception:
            return 0
    return 0


# ----------------------------------------------------------------

class EmergencyStop:
    """三重急停协调器：独立的三条触发通道，任一触发即停掉所有已 arm 的 tasker。"""

    def __init__(self, config=None):
        self.config = _deep_merge(EMERGENCY_STOP_DEFAULT, config or {})
        self.enabled = bool(self.config.get("enabled", True))

        hk = self.config.get("hotkey", {})
        self._hk_enabled = self.enabled and bool(hk.get("enabled", True))
        self._hk_modifiers = [str(m).lower() for m in hk.get("modifiers", [])]
        self._hk_key = hk.get("key", "X")

        mc = self.config.get("mouse_corner", {})
        self._mc_enabled = self.enabled and bool(mc.get("enabled", True))
        self._mc_margin = int(mc.get("corner_margin", 24))
        self._mc_min_speed = float(mc.get("min_speed", 1500))

        sf = self.config.get("sentinel_file", {})
        self._sf_enabled = self.enabled and bool(sf.get("enabled", True))
        self._sentinel_path = sf.get("path", "runtime/emergency_stop.flag")

        self._taskers = []
        self._callbacks = []
        self._triggered = threading.Event()
        self._stop_ev = threading.Event()
        self._started = False
        self._threads = []
        self._hotkey_tid = 0
        self._mouse_tid = 0
        self._hook = 0
        self._hook_proc = None
        self._last = None  # 鼠标速度检测用：(x, y, t_ms)
        self._lock = threading.Lock()

    # ---- 对外 API ----
    def arm(self, taskers):
        """登记需要在急停时调用 stop() 的 MaaTasker 列表。"""
        if taskers is None:
            self._taskers = []
        else:
            self._taskers = list(taskers)
        return self

    def register_callback(self, fn):
        """注册触发回调 fn(reason)。可多次注册。"""
        if callable(fn):
            self._callbacks.append(fn)
        return self

    def is_triggered(self):
        return self._triggered.is_set()

    def triggered_reason(self):
        return getattr(self, "_reason", None)

    def wait(self, timeout=None):
        """阻塞直到触发；触发返回 True，超时返回 False。"""
        return self._triggered.wait(timeout)

    def reset(self):
        """解除锁存（不停止监听线程）。如需删除外部哨兵文件请另行处理。"""
        with self._lock:
            self._triggered.clear()
            self._reason = None

    def trigger(self, reason="manual"):
        """手动触发（如 GUI 急停按钮调用）。"""
        self._fire(reason)

    def start(self):
        """启动所有已启用的监听通道。重复调用安全。"""
        if not self.enabled:
            logger.info("[estop] 全局禁用，不启动任何监听通道")
            return self
        if self._started:
            return self
        self._stop_ev.clear()

        # 哨兵文件父目录预创建，方便用户/脚本知道往哪放
        if self._sf_enabled and self._sentinel_path:
            try:
                d = os.path.dirname(os.path.abspath(self._sentinel_path))
                if d:
                    os.makedirs(d, exist_ok=True)
            except Exception:
                pass

        if IS_WIN:
            if self._hk_enabled:
                t = threading.Thread(target=self._hotkey_loop, daemon=True)
                t.start()
                self._threads.append(t)
            if self._mc_enabled:
                t = threading.Thread(target=self._mouse_loop, daemon=True)
                t.start()
                self._threads.append(t)
        else:
            if self._hk_enabled or self._mc_enabled:
                logger.warning(
                    "[estop] 非 Windows 平台，热键/鼠标甩角通道不可用，"
                    "仅哨兵文件通道生效")

        if self._sf_enabled:
            t = threading.Thread(target=self._sentinel_loop, daemon=True)
            t.start()
            self._threads.append(t)

        self._started = True
        armed = []
        if IS_WIN and self._hk_enabled:
            armed.append(
                f"热键({' + '.join(m.capitalize() for m in self._hk_modifiers)}"
                f"+{self._hk_key.upper()})")
        if IS_WIN and self._mc_enabled:
            armed.append(f"鼠标甩角(速度≥{self._mc_min_speed:.0f}px/s 进 {self._mc_margin}px 屏幕角)")
        if self._sf_enabled:
            armed.append(f"哨兵文件({self._sentinel_path})")
        logger.warning("[estop] 三重急停已启动: " + " | ".join(armed))
        return self

    def stop(self):
        """停止所有监听通道。tasker 不会被自动 shut_down（由调用方 finally 处理）。"""
        if not self._started:
            return
        self._stop_ev.set()
        # 唤醒被 GetMessage 阻塞的 Windows 消息泵线程
        for tid in (getattr(self, "_hotkey_tid", 0), getattr(self, "_mouse_tid", 0)):
            if tid:
                try:
                    ctypes.windll.user32.PostThreadMessageW(tid, _WM_QUIT, 0, 0)
                except Exception:
                    pass
        for th in self._threads:
            try:
                th.join(timeout=1.0)
            except Exception:
                pass
        self._threads = []
        self._started = False
        logger.info("[estop] 监听通道已停止")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    # ---- 触发核心 ----
    def _fire(self, reason):
        with self._lock:
            if self._triggered.is_set():
                return
            self._reason = reason
        logger.warning("[estop] ⚠ 急停触发 [通道=%s]，正在停止所有任务实例…", reason)
        for cb in self._callbacks:
            try:
                cb(reason)
            except Exception:  # noqa: BLE001
                logger.exception("[estop] 触发回调异常")
        for t in self._taskers:
            try:
                if t is not None and hasattr(t, "stop"):
                    t.stop()
            except Exception as e:  # noqa: BLE001
                logger.warning("[estop] tasker.stop() 失败: %s", e)
        # 锁存在「所有 tasker 都已 stop」之后才对外可见，避免调用方误判竞态
        self._triggered.set()

    # ---- 通道 3：哨兵文件 ----
    def _sentinel_loop(self):
        path = self._sentinel_path
        while not self._stop_ev.is_set():
            try:
                if path and os.path.exists(path):
                    self._fire("sentinel_file")
                    return
            except Exception:  # noqa: BLE001
                pass
            self._stop_ev.wait(0.2)

    # ---- 通道 1：全局热键（仅 Windows） ----
    def _resolve_hotkey(self):
        vk = _resolve_vk(self._hk_key)
        mods = 0
        for m in self._hk_modifiers:
            mods |= _MOD_MAP.get(m, 0)
        return vk, mods

    def _hotkey_loop(self):
        try:
            user32 = ctypes.windll.user32
            vk, mods = self._resolve_hotkey()
            if not vk:
                logger.warning("[estop] 热键解析失败，热键通道禁用")
                return
            hotkey_id = 0x5865  # 固定 id（"Xe" 玩笑号），避免与其它程序撞
            if not user32.RegisterHotKey(0, hotkey_id, mods, vk):
                logger.warning("[estop] RegisterHotKey 失败（可能被占用），"
                               "热键通道禁用")
                return
            self._hotkey_tid = ctypes.windll.kernel32.GetCurrentThreadId()
            msg = wintypes.MSG()
            while not self._stop_ev.is_set():
                r = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
                if r == 0 or r == -1:
                    break
                if msg.message == _WM_HOTKEY:
                    self._fire("hotkey")
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as e:  # noqa: BLE001
            logger.exception("[estop] 热键监听异常: %s", e)
        finally:
            try:
                ctypes.windll.user32.UnregisterHotKey(0, 0x5865)
            except Exception:
                pass
            self._hotkey_tid = 0

    # ---- 通道 2：鼠标甩屏角（仅 Windows） ----
    def _mouse_loop(self):
        try:
            user32 = ctypes.windll.user32

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            class MSLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("pt", POINT),
                    ("mouseData", ctypes.c_ulong),
                    ("flags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
                ]

            margin = self._mc_margin
            min_speed = self._mc_min_speed
            sw = user32.GetSystemMetrics(0)  # SM_CXSCREEN
            sh = user32.GetSystemMetrics(1)  # SM_CYSCREEN

            def hook_proc(n_code, w_param, l_param):
                try:
                    if n_code >= 0 and w_param == _WM_MOUSEMOVE and l_param:
                        info = MSLLHOOKSTRUCT.from_address(int(l_param))
                        x, y = info.pt.x, info.pt.y
                        now = time.time() * 1000.0
                        last = self._last
                        if last is not None:
                            dt = now - last[2]
                            if dt > 0:
                                dx = x - last[0]
                                dy = y - last[1]
                                dist = (dx * dx + dy * dy) ** 0.5
                                speed = dist / dt * 1000.0
                                if (speed >= min_speed
                                        and (x <= margin or x >= sw - margin)
                                        and (y <= margin or y >= sh - margin)):
                                    self._fire("mouse_corner")
                        self._last = (x, y, now)
                except Exception:  # noqa: BLE001
                    pass
                return user32.CallNextHookEx(0, n_code, w_param, l_param)

            HOOKPROC = ctypes.WINFUNCTYPE(
                ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
            self._hook_proc = HOOKPROC(hook_proc)
            self._hook = user32.SetWindowsHookExW(
                _WH_MOUSE_LL, self._hook_proc, 0, 0)
            if not self._hook:
                logger.warning("[estop] 鼠标钩子安装失败，鼠标甩角通道禁用")
                return
            self._mouse_tid = ctypes.windll.kernel32.GetCurrentThreadId()
            msg = wintypes.MSG()
            while not self._stop_ev.is_set():
                r = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
                if r <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as e:  # noqa: BLE001
            logger.exception("[estop] 鼠标监听异常: %s", e)
        finally:
            try:
                if getattr(self, "_hook", 0):
                    ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
            self._hook = 0
            self._hook_proc = None
            self._mouse_tid = 0


def _deep_merge(base, override):
    """嵌套 dict 合并：override 的叶子值覆盖 base，不丢失 base 的其它键。"""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
