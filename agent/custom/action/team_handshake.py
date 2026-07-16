# -*- coding: utf-8 -*-
"""
组队握手自定义 action：供 pipeline JSON 调用，驱动 TeamCoordinator。

参数（custom_action_param JSON）：
  {
    "op": "signal_leader" | "wait_leader" | "member_ready" | "wait_all" | "reset",
    "state": "accepted",          # 阶段名（任意字符串）
    "timeout": 30,                # wait_* 的超时（秒）
    "member_index": 2,            # member_ready 时指定队员序号；缺省取当前实例身份
    "indices": [1, 2, 3]          # wait_all 时指定等待哪些队员；缺省取 meta 里登记的队员
  }

示例 pipeline 节点：
  "组队-队长发邀请": {
    "action": "TeamHandshake",
    "custom_action_param": {"op": "signal_leader", "state": "inviting"}
  },
  "组队-队员等邀请": {
    "recognition": "TeamRole",
    "custom_recognition_param": {"role": "member"},
    "action": "TeamHandshake",
    "custom_action_param": {"op": "wait_leader", "state": "inviting", "timeout": 30}
  }
"""

import json

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context

from agent.multi_instance import teaming


@AgentServer.custom_action("TeamHandshake")
class TeamHandshake(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg):
        coord = teaming.get_coordinator()
        try:
            p = json.loads(argv.custom_action_param or "{}")
        except Exception:
            p = {}
        op = (p.get("op") or "").lower()
        state = p.get("state")
        timeout = float(p.get("timeout", 30))

        if op == "signal_leader":
            coord.signal_leader(state)
            return CustomAction.RunResult(success=True)
        if op == "wait_leader":
            ok = coord.wait_leader(state, timeout)
            return CustomAction.RunResult(success=ok)
        if op == "member_ready":
            idx = p.get("member_index")
            if idx is None:
                idx = teaming.current_member_index()
            coord.signal_member(idx, state)
            return CustomAction.RunResult(success=True)
        if op == "wait_all":
            idxs = p.get("indices") or coord.member_indices
            ok = coord.wait_all_members(state, timeout, idxs)
            return CustomAction.RunResult(success=ok)
        if op == "reset":
            coord.reset()
            return CustomAction.RunResult(success=True)
        # 未知 op
        return CustomAction.RunResult(success=False)
