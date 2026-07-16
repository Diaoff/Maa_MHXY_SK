# -*- coding: utf-8 -*-
"""
三重急停命令行工具。

子命令：
  trigger   创建哨兵文件，跨进程广播急停（多开场景下一条命令停掉所有号）。
  reset     删除哨兵文件，解除外部急停信号。
  watch     启动独立看门狗，演示/验证三条急停通道（热键 / 鼠标甩角 / 哨兵文件）；
            无 MAA 也能用，按 Ctrl+C 退出。

哨兵文件路径默认取 config 或 runtime/emergency_stop.flag；可用 --path 覆盖。

示例：
  python tools/emergency_stop.py trigger
  python tools/emergency_stop.py reset
  python tools/emergency_stop.py watch --path runtime/emergency_stop.flag
"""

import argparse
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
logger = logging.getLogger("emergency_stop")


def _default_sentinel_path():
    cfg_path = os.path.join(ROOT, "config", "multi_instance.json")
    try:
        import json
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        sf = (cfg.get("emergency_stop", {})
              .get("sentinel_file", {})
              .get("path"))
        if sf:
            return sf
    except Exception:
        pass
    return "runtime/emergency_stop.flag"


def cmd_trigger(args):
    path = os.path.abspath(args.path)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass
    note = args.note or time.strftime("%Y-%m-%d %H:%M:%S 手动触发急停")
    with open(path, "w", encoding="utf-8") as f:
        f.write(note + "\n")
    print(f"[trigger] 已创建哨兵文件: {path}")
    print("[trigger] 正在运行的轮转进程会在 ~0.2s 内检测到并急停所有实例。")


def cmd_reset(args):
    path = os.path.abspath(args.path)
    if os.path.exists(path):
        try:
            os.remove(path)
            print(f"[reset] 已删除哨兵文件: {path}")
        except Exception as e:
            print(f"[reset] 删除失败: {e}")
    else:
        print(f"[reset] 哨兵文件不存在: {path}（无需重置）")


def cmd_watch(args):
    from agent.safety.emergency_stop import EmergencyStop

    config = {}
    if args.no_hotkey:
        config.setdefault("hotkey", {})["enabled"] = False
    if args.no_mouse:
        config.setdefault("mouse_corner", {})["enabled"] = False
    if args.path:
        config.setdefault("sentinel_file", {})["path"] = args.path

    estop = EmergencyStop(config)
    estop.register_callback(lambda reason: print(f"  >>> 触发通道: {reason}"))
    print("[watch] 三重急停看门狗启动，尝试以下方式触发：")
    print("   - 按 Ctrl+Shift+X（全局热键）")
    print("   - 把鼠标快速甩进任一屏幕角")
    print(f"   - 另一终端运行: python tools/emergency_stop.py trigger"
          + (f" --path {args.path}" if args.path else ""))
    print("   按 Ctrl+C 退出。")
    estop.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[watch] 收到 Ctrl+C，退出。")
    finally:
        estop.stop()


def main():
    parser = argparse.ArgumentParser(description="三重急停工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_t = sub.add_parser("trigger", help="创建哨兵文件触发急停")
    p_t.add_argument("--path", default=_default_sentinel_path())
    p_t.add_argument("--note", default="", help="写入哨兵文件的备注")
    p_t.set_defaults(func=cmd_trigger)

    p_r = sub.add_parser("reset", help="删除哨兵文件解除急停")
    p_r.add_argument("--path", default=_default_sentinel_path())
    p_r.set_defaults(func=cmd_reset)

    p_w = sub.add_parser("watch", help="独立看门狗（验证三条通道）")
    p_w.add_argument("--path", default=None,
                     help="哨兵文件路径（默认取 config）")
    p_w.add_argument("--no-hotkey", action="store_true", help="禁用热键通道")
    p_w.add_argument("--no-mouse", action="store_true", help="禁用鼠标甩角通道")
    p_w.set_defaults(func=cmd_watch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
