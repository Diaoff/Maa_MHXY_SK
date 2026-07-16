# -*- coding: utf-8 -*-
"""
组队角色分支自定义 recognition：供 pipeline 按「当前实例是队长还是队员」分流。

参数（custom_recognition_param JSON）：
  {"role": "leader"}   # leader | member

返回 hit=True 当且仅当当前实例角色与 role 匹配。当前实例序号取自：
  1) 环境变量 MHXY_TEAM_INDEX（多进程五开时由启动脚本注入）
  2) teaming.set_current_member_index（单进程顺序轮转时由引擎注入）
队长序号取自 coordinator meta（set_roles 写入）。

约定：匹配时返回整屏 box（让 MAA 判定为 hit）；不匹配返回空 box（miss），
从而让 pipeline 用 next / OnHit / OnMiss 分支到队长 / 队员不同路径。
"""

import json

from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context

from agent.multi_instance import teaming


def _img_size(img):
    """兼容 numpy.ndarray 与 PIL.Image，返回 (h, w)。"""
    if hasattr(img, "shape"):
        return int(img.shape[0]), int(img.shape[1])
    if hasattr(img, "size"):
        return int(img.size[1]), int(img.size[0])
    return 1, 1


@AgentServer.custom_recognition("TeamRole")
class TeamRole(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        coord = teaming.get_coordinator()
        try:
            p = json.loads(argv.custom_recognition_param or "{}")
        except Exception:
            p = {}
        want = (p.get("role") or "leader").lower()
        idx = teaming.current_member_index()
        is_leader = (idx == coord.leader_index)
        matched = (want == "leader") == is_leader

        if matched:
            # 取当前截图尺寸，返回整屏 box 以表示 hit
            try:
                img = context.tasker.controller.post_screencap().wait().get()
                h, w = _img_size(img)
            except Exception:
                h, w = 1, 1
            box = (0, 0, max(1, w), max(1, h))
        else:
            box = (0, 0, 0, 0)
        detail = (f"role={want} current_index={idx} "
                  f"leader_index={coord.leader_index} matched={matched}")
        return CustomRecognition.AnalyzeResult(box=box, detail=detail)
