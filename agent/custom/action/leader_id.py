# -*- coding: utf-8 -*-
"""
队长ID库自定义动作（Leader ID）。

pipeline 中可用来「激活某队长」（把其模板字节覆盖到 user/image/tm_leader_id.png），
或「登记当前队长ID截图」。

pipeline 用法：
    "custom_action": "LeaderId",
    "custom_action_param": {
        "op": "activate",          // activate | register | current | ensure
        "name": "队长角色名",       // activate/register 必填
        "image_path": "..."        // register 时队长ID截图路径（可选，亦可省略由外部登记）
    }

说明：真正「换队长」的通常入口是引擎（rotation 设置 leader_index 时调用 activate），
本 action 主要供 pipeline 内临机切换 / 校验使用。路径串恒定（铁律）。
"""

import json
import os
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context

from utils import logger
from agent.multi_instance.leader_history import get_history


@AgentServer.custom_action("LeaderId")
class LeaderId(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        try:
            param = json.loads(argv.custom_action_param or "{}")
        except Exception:
            param = {}
        op = str(param.get("op", "activate")).lower()
        hist = get_history()

        if op == "ensure":
            hist.ensure_image_file()
            return CustomAction.RunResult(success=True)

        name = param.get("name")
        if op == "activate":
            if not name:
                logger.warning("[LeaderId] activate 缺少 name")
                return CustomAction.RunResult(success=False)
            ok = hist.activate(name)
            logger.info("[LeaderId] 激活队长 %s -> %s", name, "OK" if ok else "失败(未登记?)")
            return CustomAction.RunResult(success=ok)

        if op == "register":
            if not name:
                logger.warning("[LeaderId] register 缺少 name")
                return CustomAction.RunResult(success=False)
            img = param.get("image_path")
            ok = hist.register(name, image_path=img)
            logger.info("[LeaderId] 登记队长 %s -> %s", name, "OK" if ok else "失败(无图?)")
            return CustomAction.RunResult(success=ok)

        if op == "current":
            cur = hist.current_leader()
            logger.info("[LeaderId] 当前激活队长: %s", cur)
            return CustomAction.RunResult(success=True)

        logger.warning("[LeaderId] 未知 op: %s", op)
        return CustomAction.RunResult(success=False)
