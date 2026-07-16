# -*- coding: utf-8 -*-
"""
时空版多开轮转引擎命令行入口。

依赖：仅 --list-windows 走纯 ctypes（adapter），不需要 maa；
      真正执行任务需要 Windows + 已装 MaaFw + 时空版客户端。

示例：
  # 仅探测本机时空版窗口（进程过滤 + 分辨率），不启动 MAA
  python tools/run_multi_instance.py --list-windows

  # 用默认配置（config/multi_instance.json）跑全部号
  python tools/run_multi_instance.py

  # 只跑 2 号窗口，仅执行福利签到 + 师门
  python tools/run_multi_instance.py --account 2 --task fuli_qiandao --task shimen_renwu

  # 指定配置文件
  python tools/run_multi_instance.py --config config/multi_instance.json
"""

import argparse
import json
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "agent")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("run_multi_instance")


def _load_controller_config():
    cfg_path = os.path.join(ROOT, "config", "controller_config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f).get("win32", {})
    except Exception:
        return {}


def cmd_list_windows():
    from agent.win32.adapter import (
        set_game_process,
        set_game_title_substr,
        locate_all_windows,
        _get_window_rect,
    )
    cc = _load_controller_config()
    set_game_process(cc.get("window_process"))
    set_game_title_substr(cc.get("window_title_substr", "梦幻西游"))

    wins = locate_all_windows()
    if not wins:
        print("[list] 未找到任何时空版窗口。"
              "请确认客户端已启动且未最小化，进程名与 config 一致。")
        return
    print(f"[list] 找到 {len(wins)} 个窗口：")
    for i, h in enumerate(wins):
        rect = _get_window_rect(h)
        print(f"  [{i}] HWND={h}  尺寸={rect[2]}x{rect[3]}")


def main():
    parser = argparse.ArgumentParser(description="时空版多开轮转引擎")
    parser.add_argument("--config", default=os.path.join(
        ROOT, "config", "multi_instance.json"))
    parser.add_argument("--list-windows", action="store_true",
                        help="仅探测窗口，不启动 MAA")
    parser.add_argument("--task", action="append", default=[],
                        help="覆写任务列表（可多次），如 --task fuli_qiandao")
    parser.add_argument("--account", type=int, default=None,
                        help="只操作第 N 个窗口（0 起）")
    parser.add_argument("--no-activate", action="store_true",
                        help="关闭切换前强制前台（仅非 Seize 输入可用）")
    parser.add_argument("--no-emergency-stop", action="store_true",
                        help="关闭三重急停（不建议；急停是安全兜底）")
    parser.add_argument("--team", action="store_true",
                        help="启用组队握手（队长/队员角色登记 + 身份注入）")
    parser.add_argument("--leader-name", default=None,
                        help="组队队长角色名（用于队长ID库字节覆盖激活 tm_leader_id.png）")
    args = parser.parse_args()

    if args.list_windows:
        cmd_list_windows()
        return

    from agent.multi_instance.rotation import RotationEngine

    engine = RotationEngine(args.config)
    if args.task:
        engine.set_tasks(args.task)
    if args.account is not None:
        engine.targets = {"multi": False, "single_index": args.account}
    if args.no_activate:
        engine.activate_before_run = False
    if args.no_emergency_stop:
        engine.estop_config["enabled"] = False
        logger.info("已关闭三重急停（--no-emergency-stop）")
    if args.team:
        engine.team_config["enabled"] = True
        logger.info("已启用组队握手（--team）")
    if args.leader_name:
        engine.team_config["leader_name"] = args.leader_name
        logger.info("已指定队长角色名（用于队长ID库激活）: %s", args.leader_name)

    if not engine.tasks:
        logger.error("任务列表为空，退出")
        sys.exit(1)

    logger.info("启动多开轮转：strategy=%s tasks=%s",
                engine.strategy, [t.get("entry") for t in engine.tasks])
    ok = engine.run()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
