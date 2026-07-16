# -*- coding: utf-8 -*-
"""
组队握手命令行工具（与多开引擎 / 控制台 GUI 共享 runtime/team/ 文件）。

子命令：
  status          打印队长与所有队员当前状态。
  set-leader      登记队长与队员角色（写入 meta.json）。
  signal-leader   队长发信号（写 leader_state.json）。
  signal-member   某队员就位（写 members/<idx>.json）。
  wait-leader     阻塞等待队长到达某状态（超时返回非零）。
  wait-all        阻塞等待所有队员到达某状态（超时返回非零）。
  reset           清除握手状态（保留角色 meta）。

示例：
  python tools/team.py set-leader 0 --members 1,2,3,4
  python tools/team.py signal-leader inviting
  python tools/team.py wait-all accepted --timeout 30
  python tools/team.py status
  python tools/team.py reset
"""

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "agent")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging = __import__("logging")
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("team")


def _default_runtime_dir():
    cfg_path = os.path.join(ROOT, "config", "multi_instance.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        rd = cfg.get("team", {}).get("runtime_dir")
        if rd:
            return rd
    except Exception:
        pass
    return "runtime/team"


def _coord(args):
    from agent.multi_instance.teaming import TeamCoordinator
    return TeamCoordinator({"runtime_dir": args.runtime_dir} if args.runtime_dir else None)


def cmd_status(args):
    c = _coord(args)
    print(f"队长序号: {c.leader_index}")
    print(f"队员序号: {c.member_indices}")
    print(f"队长状态: {c.leader_state() or '（无）'}")
    states = c.members_state()
    if states:
        for idx in sorted(states):
            print(f"  队员 {idx}: {states[idx] or '（无）'}")
    else:
        print("  队员状态: （无）")


def cmd_set_leader(args):
    c = _coord(args)
    members = [int(x) for x in (args.members or "").split(",") if x.strip() != ""]
    c.set_roles(args.index, members)
    print(f"[set-leader] 队长={args.index} 队员={members}")


def cmd_signal_leader(args):
    c = _coord(args)
    c.signal_leader(args.state)
    print(f"[signal-leader] 队长状态 -> {args.state}")


def cmd_signal_member(args):
    c = _coord(args)
    c.signal_member(args.index, args.state)
    print(f"[signal-member] 队员 {args.index} 状态 -> {args.state}")


def cmd_wait_leader(args):
    c = _coord(args)
    ok = c.wait_leader(args.state, timeout=args.timeout)
    print(f"[wait-leader] 等待 '{args.state}': {'达成' if ok else '超时'}")
    sys.exit(0 if ok else 1)


def cmd_wait_all(args):
    c = _coord(args)
    idxs = [int(x) for x in (args.members or "").split(",") if x.strip() != ""] or None
    ok = c.wait_all_members(args.state, timeout=args.timeout, indices=idxs)
    print(f"[wait-all] 等待 '{args.state}': {'达成' if ok else '超时'}")
    sys.exit(0 if ok else 1)


def cmd_reset(args):
    c = _coord(args)
    c.reset()
    print("[reset] 组队握手状态已清除")


def main():
    parser = argparse.ArgumentParser(description="组队握手工具")
    parser.add_argument("--runtime-dir", default=_default_runtime_dir(),
                        help="runtime/team 目录（默认取 config 或 runtime/team）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="打印当前握手状态")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("set-leader", help="登记队长/队员角色")
    p.add_argument("index", type=int, help="队长序号")
    p.add_argument("--members", default="", help="队员序号，逗号分隔")
    p.set_defaults(func=cmd_set_leader)

    p = sub.add_parser("signal-leader", help="队长发信号")
    p.add_argument("state", help="阶段名")
    p.set_defaults(func=cmd_signal_leader)

    p = sub.add_parser("signal-member", help="队员就位")
    p.add_argument("index", type=int, help="队员序号")
    p.add_argument("state", help="阶段名")
    p.set_defaults(func=cmd_signal_member)

    p = sub.add_parser("wait-leader", help="等待队长到达某状态")
    p.add_argument("state", help="阶段名")
    p.add_argument("--timeout", type=float, default=30)
    p.set_defaults(func=cmd_wait_leader)

    p = sub.add_parser("wait-all", help="等待所有队员到达某状态")
    p.add_argument("state", help="阶段名")
    p.add_argument("--timeout", type=float, default=30)
    p.add_argument("--members", default="", help="指定队员序号，逗号分隔（默认取 meta）")
    p.set_defaults(func=cmd_wait_all)

    p = sub.add_parser("reset", help="清除握手状态")
    p.set_defaults(func=cmd_reset)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
