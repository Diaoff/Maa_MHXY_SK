# -*- coding: utf-8 -*-
"""
拟人化点击（Humanized Click）。

包装 CustomAction：把原本「post_click(x, y)」的瞬时点击，替换为拟人化输入——
贝塞尔曲线移动 + 随机落点 + 间隔抖动 + 偶尔走神（见 agent/utils/humanize.py）。

pipeline 用法示例：
    "custom_action": "HumanizedClick",
    "custom_action_param": {
        "click_target": [x1, y1, x2, y2],   // 相对游戏窗口截图的 box；不填则点击识别结果中心
        "window_offset": [left, top],        // 游戏窗口在屏幕上的左上角，用于转绝对坐标；
                                              // 不填则取环境变量 MHXY_WIN_OFFSET（"left,top"）
        "jitter_radius_ratio": 0.012,        // 可选：覆盖落点随机半径
        "drift_probability": 0.04            // 可选：覆盖走神概率
    }

安全说明：
  - 本 action 与「演练模式（dry_run）」正交：dry_run 由 safety 层拦截，命中时根本不会
    进入点击逻辑；本 action 本身只在真正执行点击时拟人化。
  - 拟人化坐标使用「屏幕绝对坐标」，因此必须提供正确的 window_offset（窗口左上角），
    否则会点错位置。引擎在点击前应已把该窗口切到前台。
"""

import os
import json
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context

from utils import logger
from agent.utils import humanize


def _parse_offset(param: dict):
    off = param.get("window_offset")
    if isinstance(off, (list, tuple)) and len(off) == 2:
        return (int(off[0]), int(off[1]))
    env = os.environ.get("MHXY_WIN_OFFSET")
    if env:
        try:
            a, b = env.split(",")
            return (int(a.strip()), int(b.strip()))
        except Exception:
            pass
    return (0, 0)


@AgentServer.custom_action("HumanizedClick")
class HumanizedClick(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        try:
            param = json.loads(argv.custom_action_param or "{}")
        except Exception:
            param = {}

        # 可选：本节点临时覆盖拟人化参数
        if any(k in param for k in (
            "jitter_radius_ratio", "drift_probability", "curve_steps",
            "pre_click_delay", "post_click_delay", "enabled",
        )):
            humanize.configure({k: param[k] for k in (
                "jitter_radius_ratio", "drift_probability", "curve_steps",
                "pre_click_delay", "post_click_delay", "enabled",
            ) if k in param})

        offset = _parse_offset(param)

        # 1) 确定相对窗口的 box
        box = param.get("click_target")
        if not box:
            # 退化为点击当前识别结果中心
            rd = getattr(argv, "reco_detail", None)
            if rd is not None and getattr(rd, "box", None):
                b = rd.box
                box = [b[0], b[1], b[0] + b[2], b[1] + b[3]]
            else:
                logger.warning("[HumanizedClick] 未提供 click_target 且无识别结果，跳过")
                return CustomAction.RunResult(success=True)

        if len(box) == 2:
            # 直接给的点
            rel = (int(box[0]), int(box[1]))
            abs_pt = (rel[0] + offset[0], rel[1] + offset[1])
            executed = humanize.humanized_click(abs_pt)
        else:
            x1, y1, x2, y2 = [int(v) for v in box]
            executed = humanize.humanized_click_box(
                (x1, y1, x2 - x1, y2 - y1), window_offset=offset
            )

        if not executed:
            # 无头 / 禁用：安全降级为 MAA 原生点击（保持功能可用）
            cx = (box[0] + box[2] // 2) if len(box) == 4 else box[0]
            cy = (box[1] + box[3] // 2) if len(box) == 4 else box[1]
            logger.debug("[HumanizedClick] 拟人化不可用，降级为 MAA post_click")
            context.tasker.controller.post_click(cx, cy).wait()

        return CustomAction.RunResult(success=True)
