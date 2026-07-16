# -*- coding: utf-8 -*-
"""
队长ID库命令行工具。

子命令：
  ensure                      确保 user/image/tm_leader_id.png 存在（首次占位）
  register <name> [img.png]   登记候选队长（截图可省略，之后用同一 name 再 register 补图）
  list                        列出已登记队长（含使用次数/最近使用）
  activate <name>             字节覆盖激活该队长为当前 tm_leader_id.png（路径串不变）
  current                     反查当前激活的是哪位队长

示例：
  python tools/leader_id.py ensure
  python tools/leader_id.py register 队长A D:/shot/leaderA.png
  python tools/leader_id.py activate 队长A
  python tools/leader_id.py current
"""

import os
import sys

# 允许从项目根目录直接运行（与 tools/team.py 风格一致）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent.multi_instance.leader_history import get_history  # noqa: E402


def _usage():
    print(__doc__)
    return 2


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        return _usage()
    cmd = argv[0]
    hist = get_history()

    if cmd == "ensure":
        created = hist.ensure_image_file()
        print("OK (created)" if created else "already exists")
        return 0

    if cmd == "register":
        if len(argv) < 2:
            print("用法: register <name> [img.png]")
            return 2
        name = argv[1]
        img = argv[2] if len(argv) > 2 else None
        ok = hist.register(name, image_path=img)
        print("register", name, "->", "OK" if ok else "FAILED (缺少截图或文件不存在)")
        return 0 if ok else 1

    if cmd == "list":
        rows = hist.list_leaders()
        if not rows:
            print("(空) 尚无登记队长，先 register")
        for r in rows:
            print(f"  {r['name']}  use_count={r['use_count']}  last_used={r['last_used']}")
        return 0

    if cmd == "activate":
        if len(argv) < 2:
            print("用法: activate <name>")
            return 2
        ok = hist.activate(argv[1])
        print("activate", argv[1], "->", "OK" if ok else "FAILED (未登记?)")
        return 0 if ok else 1

    if cmd == "current":
        cur = hist.current_leader()
        print("current leader:", cur if cur is not None else "(未知/未匹配)")
        return 0

    return _usage()


if __name__ == "__main__":
    sys.exit(main())
