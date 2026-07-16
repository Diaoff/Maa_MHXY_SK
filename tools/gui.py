# -*- coding: utf-8 -*-
"""
启动《梦幻西游：时空》统一控制台 GUI（实例列表 + 组队握手 + 三重急停 + 启动多开）。

  python tools/gui.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "agent")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def main():
    try:
        import tkinter  # noqa: F401
    except Exception as e:
        print(f"无法启动 GUI：缺少 tkinter（{e}）")
        sys.exit(1)
    from agent.gui.console import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
