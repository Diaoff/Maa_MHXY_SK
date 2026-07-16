# -*- coding: utf-8 -*-
"""
启动《梦幻西游：时空》动态标定工具（GUI）。

把客户端实时截图（或指定图片）上框选的区域，落盘为 MAA 格式的覆盖资源：
  - 模板图 → assets/resource/user/image/<task>/<name>.png
  - 坐标/模板引用 → assets/resource/user/pipeline/<task>.override.json
（interface.json 中「时空版-用户标定覆盖」资源后加载，按节点名覆盖官方 base 层。）

用法：
  python tools/calibrate.py                                   # 启动 GUI，自动探测客户端窗口
  python tools/calibrate.py --image shot.png                  # 用指定截图标定（无需客户端，离线）
  python tools/calibrate.py --engine gdi                      # 强制 GDI 截图（无 maa 时）
  python tools/calibrate.py --task shimen_renwu --node "师门完成确定-图片识别" --mode roi
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tkinter as tk  # noqa: E402

from agent.calibrator.gui import CalibratorApp  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="梦幻西游·时空版 动态标定工具")
    p.add_argument("--image", help="用指定截图文件标定（不连接客户端）")
    p.add_argument("--engine", choices=["maa", "gdi"], default="maa",
                   help="实时截图引擎（默认 maa，坐标与运行时一致；无 maa 自动回退 gdi）")
    p.add_argument("--task", help="预选任务名（如 shimen_renwu）")
    p.add_argument("--node", help="预选节点名")
    p.add_argument("--mode", choices=["template", "roi", "click", "swipe"], default="template")
    args = p.parse_args()

    root = tk.Tk()
    root.title("梦幻西游·时空版 动态标定工具")
    root.geometry("1300x680")
    CalibratorApp(root, image_path=args.image, engine=args.engine,
                  task=args.task, node=args.node, mode=args.mode)
    root.mainloop()


if __name__ == "__main__":
    main()
