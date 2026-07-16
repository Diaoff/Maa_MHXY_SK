# -*- coding: utf-8 -*-
"""
拟人化输入（Humanized Input）。

设计目标（对应设计文档「拟人化输入」）：让自动化点击更接近真人操作，降低行为特征，
对抗时空版可能更严的反作弊检测。四大要素：

  1. 贝塞尔曲线移动（Bezier move）：鼠标从当前位置沿一条带随机控制点的三次贝塞尔曲线
     滑向目标，而非直线瞬移——这是「像人手」最关键的一步。
  2. 随机落点（Random landing）：目标点附近加一个可控半径的随机偏移，避免每次都点正中心。
  3. 间隔抖动（Jitter delay）：每次点击前后插入随机时长的停顿，模拟思考/反应时间。
  4. 偶尔走神（Occasional drift）：小概率在当前动作后「发呆」——鼠标小幅游走或停留更久，
     模拟真人偶尔分心。

实现要点：
  - 直接用 ctypes 驱动 Windows 鼠标（绝对屏幕坐标 + 贝塞尔轨迹），与 MAA 的 Controller
    输入管道解耦。这样既能做真正拟人化的轨迹，又不依赖 MAA 是否暴露 swipe 接口，
    也天然适配「游戏管理员权限运行时需管理员输入」的情形（与 adapter.py 同一层级）。
  - 全部数值用相对屏幕分辨率归一化，缩放无关。
  - 所有随机都用模块级可配置参数，且可整体开关（disable 时退化为「直接移动+点击」）。

本模块不依赖 maa，可独立 import 与无头测试（无头时 move/click 会安全降级为 no-op）。
"""

from __future__ import annotations

import ctypes
import math
import os
import random
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

@dataclass
class HumanizeConfig:
    """拟人化输入参数（用户 config 可按字段覆盖）。"""
    enabled: bool = True
    # 落点随机半径（占屏幕短边的比例，0~0.02 较自然）
    jitter_radius_ratio: float = 0.012
    # 轨迹分段数（越多越平滑，也越慢）
    curve_steps: int = 24
    # 单段移动基准间隔（秒），实际叠加随机抖动
    move_step_delay: float = 0.006
    # 点击前最小/最大停顿（秒）
    pre_click_delay: Tuple[float, float] = (0.05, 0.22)
    # 点击后最小/最大停顿（秒）
    post_click_delay: Tuple[float, float] = (0.08, 0.35)
    # 贝塞尔控制点横向扰动（占位移比例）
    control_jitter: float = 0.25
    # 走神概率（每次点击后）
    drift_probability: float = 0.04
    # 走神停留时长（秒）
    drift_idle: Tuple[float, float] = (0.6, 2.4)
    # 走神游走半径（占屏幕短边比例）
    drift_wander_ratio: float = 0.05

    def as_dict(self):
        d = asdict(self)
        d["pre_click_delay"] = list(self.pre_click_delay)
        d["post_click_delay"] = list(self.post_click_delay)
        d["drift_idle"] = list(self.drift_idle)
        return d


# 强制无副作用模式（不操作鼠标），用于测试或 dry_run 演练。可由环境变量
# MHXY_HUMANIZE_DRYRUN=1 开启，或由 configure 设置。
_force_dryrun = os.environ.get("MHXY_HUMANIZE_DRYRUN", "").lower() in ("1", "true", "yes")


def set_force_dryrun(v: bool):
    global _force_dryrun
    _force_dryrun = bool(v)


# 模块级默认（可被 rotation 配置覆盖）
_default_cfg = HumanizeConfig()


def configure(cfg: dict):
    """用用户/引擎 config 的字段覆盖默认（未提供的项保留默认）。"""
    global _default_cfg
    for k, v in (cfg or {}).items():
        if hasattr(_default_cfg, k):
            if isinstance(v, (list, tuple)) and k in (
                "pre_click_delay", "post_click_delay", "drift_idle"
            ):
                setattr(_default_cfg, k, tuple(v))
            else:
                setattr(_default_cfg, k, v)


def get_config() -> HumanizeConfig:
    return _default_cfg


# ---------------------------------------------------------------------------
# Win32 鼠标驱动（ctypes）
# ---------------------------------------------------------------------------

# Windows API 常量
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

SM_CXSCREEN = 0
SM_CYSCREEN = 1


def _user32():
    return ctypes.windll.user32


def _screen_size():
    u = _user32()
    return u.GetSystemMetrics(SM_CXSCREEN), u.GetSystemMetrics(SM_CYSCREEN)


def _has_win32_mouse() -> bool:
    try:
        return hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32")
    except Exception:
        return False


def _send_input(*inputs):
    """通过 SendInput 下发一组 INPUT 结构。"""
    u = _user32()
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    u.SendInput(n, ctypes.byref(arr), ctypes.sizeof(INPUT))


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", INPUTUNION)]


def _now():
    return ctypes.windll.kernel32.GetTickCount() if _has_win32_mouse() else 0


def _move_abs(x: int, y: int):
    """绝对坐标移动（归一化到 0..65535，覆盖整个虚拟桌面）。"""
    sx, sy = _screen_size()
    nx = int(round(x * 65535 / max(sx, 1)))
    ny = int(round(y * 65535 / max(sy, 1)))
    mi = MOUSEINPUT(
        dx=nx, dy=ny, mouseData=0,
        dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
        time=0, dwExtraInfo=None,
    )
    _send_input(INPUT(type=0, union=INPUTUNION(mi=mi)))


def _click_down_up(x: int, y: int):
    sx, sy = _screen_size()
    nx = int(round(x * 65535 / max(sx, 1)))
    ny = int(round(y * 65535 / max(sy, 1)))

    def _mi(flags):
        return MOUSEINPUT(
            dx=nx, dy=ny, mouseData=0,
            dwFlags=flags | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
            time=0, dwExtraInfo=None,
        )
    _send_input(INPUT(type=0, union=INPUTUNION(mi=_mi(MOUSEEVENTF_LEFTDOWN))))
    time.sleep(random.uniform(0.02, 0.06))  # 按下保持，像真人
    _send_input(INPUT(type=0, union=INPUTUNION(mi=_mi(MOUSEEVENTF_LEFTUP))))


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def get_cursor_pos() -> Tuple[int, int]:
    if not _has_win32_mouse():
        return (0, 0)
    pt = _POINT()
    _user32().GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


# ---------------------------------------------------------------------------
# 贝塞尔轨迹
# ---------------------------------------------------------------------------

def bezier_path(start: Tuple[int, int], end: Tuple[int, int],
                steps: int, jitter: float, rng: random.Random) -> List[Tuple[int, int]]:
    """生成三次贝塞尔曲线的离散点序列（不含起点，含终点）。

    start/end 为绝对屏幕坐标；控制点在线段法向做随机扰动以产生弧度。
    """
    steps = max(2, int(steps))
    x0, y0 = start
    x1, y1 = end
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)

    # 法向量（用于把控制点推离直线，制造弧线）
    if dist < 1e-3:
        nx, ny = 0.0, 0.0
    else:
        nx, ny = -dy / dist, dx / dist

    # 两个控制点：沿法向随机偏移，符号也可能相反（弧线方向随机）
    def _cp(t):
        mag = dist * jitter * rng.uniform(0.4, 1.0)
        sgn = rng.choice((-1, 1))
        offx = nx * mag * sgn
        offy = ny * mag * sgn
        # 控制点落在 0.3~0.7 的线段位置附近（贝塞尔的天然属性由 t 决定，这里只加扰动）
        bx = x0 + dx * t + offx
        by = y0 + dy * t + offy
        return bx, by

    c1 = _cp(0.33 + rng.uniform(-0.05, 0.05))
    c2 = _cp(0.66 + rng.uniform(-0.05, 0.05))

    pts: List[Tuple[int, int]] = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        bx = (u * u * u * x0
              + 3 * u * u * t * c1[0]
              + 3 * u * t * t * c2[0]
              + t * t * t * x1)
        by = (u * u * u * y0
              + 3 * u * u * t * c1[1]
              + 3 * u * t * t * c2[1]
              + t * t * t * y1)
        pts.append((int(round(bx)), int(round(by))))
    return pts


# ---------------------------------------------------------------------------
# 对外高阶 API
# ---------------------------------------------------------------------------

def humanized_click(target: Tuple[int, int],
                     cfg: Optional[HumanizeConfig] = None,
                     rng: Optional[random.Random] = None) -> bool:
    """在绝对屏幕坐标 target 处执行一次拟人化点击（默认即屏幕/前台窗口坐标）。

    返回是否真的执行了（无头/禁用时返回 False 且不做任何系统操作）。
    注意：坐标应使用「屏幕绝对坐标」。MAA 的识别 box 是相对于游戏窗口截图的，
    调用方需自行把窗口左上角偏移加上去（见 agent/win32/adapter.py 的窗口矩形）。
    """
    cfg = cfg or _default_cfg
    rng = rng or random._inst
    if not cfg.enabled or _force_dryrun:
        return False
    if not _has_win32_mouse():
        # 无头环境：安全降级，不操作鼠标
        return False

    sx, sy = _screen_size()
    short = min(sx, sy)

    # 1) 随机落点
    jr = cfg.jitter_radius_ratio * short
    tx = int(target[0] + rng.uniform(-jr, jr))
    ty = int(target[1] + rng.uniform(-jr, jr))
    tx = max(0, min(sx - 1, tx))
    ty = max(0, min(sy - 1, ty))

    # 2) 贝塞尔轨迹移动
    start = get_cursor_pos()
    path = bezier_path(start, (tx, ty), cfg.curve_steps, cfg.control_jitter, rng)
    for px, py in path[:-1]:
        _move_abs(px, py)
        time.sleep(cfg.move_step_delay * rng.uniform(0.6, 1.6))
    _move_abs(tx, ty)

    # 3) 点击前停顿（反应时间）
    time.sleep(rng.uniform(*cfg.pre_click_delay))

    # 4) 点击
    _click_down_up(tx, ty)

    # 5) 点击后停顿
    time.sleep(rng.uniform(*cfg.post_click_delay))

    # 6) 偶尔走神
    if rng.random() < cfg.drift_probability:
        _drift(rng, sx, sy, cfg)

    return True


def humanized_click_box(box: Tuple[int, int, int, int],
                        window_offset: Tuple[int, int] = (0, 0),
                        cfg: Optional[HumanizeConfig] = None,
                        rng: Optional[random.Random] = None) -> bool:
    """对 MAA 识别 box [x, y, w, h]（相对窗口截图）做一次拟人化点击。

    window_offset 为游戏窗口在屏幕上的左上角 (left, top)，用于把相对坐标转绝对坐标。
    """
    x, y, w, h = box
    cx = x + w // 2
    cy = y + h // 2
    return humanized_click(
        (cx + window_offset[0], cy + window_offset[1]),
        cfg=cfg, rng=rng,
    )


def _drift(rng: random.Random, sx: int, sy: int, cfg: HumanizeConfig):
    """走神：鼠标小幅游走 + 停留更久。"""
    # 先原地停一会儿
    time.sleep(rng.uniform(*cfg.drift_idle))
    # 小幅游走 1~2 步
    cur = get_cursor_pos()
    wr = cfg.drift_wander_ratio * min(sx, sy)
    for _ in range(rng.randint(1, 2)):
        wx = max(0, min(sx - 1, cur[0] + int(rng.uniform(-wr, wr))))
        wy = max(0, min(sy - 1, cur[1] + int(rng.uniform(-wr, wr))))
        _move_abs(wx, wy)
        time.sleep(rng.uniform(0.15, 0.5))
        cur = (wx, wy)
    # 走神结束稍微回到原位置附近（可选，这里不强制）


def humanized_delay(cfg: Optional[HumanizeConfig] = None,
                    rng: Optional[random.Random] = None) -> float:
    """仅产生一次间隔抖动（不点击），供「两次动作之间的停顿」复用。返回实际停顿秒数。"""
    cfg = cfg or _default_cfg
    rng = rng or random._inst
    if not cfg.enabled:
        return 0.0
    d = rng.uniform(*cfg.post_click_delay)
    time.sleep(d)
    return d


def _self_test():
    """极简自测：无头环境下应安全降级（不操作鼠标），返回 True。"""
    print("has_win32:", _has_win32_mouse())
    cfg = HumanizeConfig(enabled=True)
    ok = humanized_click((100, 100), cfg=cfg)
    print("click executed:", ok)
    return True


if __name__ == "__main__":
    _self_test()
