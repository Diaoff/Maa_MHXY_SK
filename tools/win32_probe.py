# -*- coding: utf-8 -*-
"""
时空版 Win32 控制器接入探针（阶段0 PoC 验证工具）。

用途：
  1. 校验本机能否按进程名 MyGame_x64r.exe 找到时空版窗口（进程过滤是否生效）。
  2. 打印各候选窗口的 HWND / 标题 / 屏幕矩形（分辨率），用于【锁定 PC 默认分辨率基准档位】。
  3. 验证前台激活（绕过焦点抢占）是否可用。

运行（在装好时空版客户端的 Windows 上，建议以管理员运行以免 SendInput 被拦截）：
    python tools/win32_probe.py
    python tools/win32_probe.py --activate <hwnd>   # 测试把某窗口切到前台并校验

本工具只依赖标准库 + agent.win32.adapter（ctypes），不启动 MAA，用于在上手 MAA 前先确认
窗口定位与分辨率基准正确。
"""

import argparse
import json
import os
import sys

# 让 import agent.win32 可用（用 agent.win32 绝对导入，避免与 pywin32 的 win32 顶层包冲突）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from agent.win32.adapter import (
    set_dpi_aware,
    set_game_process,
    set_game_title_substr,
    locate_all_windows,
    locate_window,
    _proc_basename,
    _window_title,
    _get_window_rect,
)


def _load_controller_config():
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "config", "controller_config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f).get("win32", {})
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser(description="时空版 Win32 控制器探针")
    parser.add_argument("--activate", type=lambda x: int(x, 0), default=0,
                        help="测试把指定 HWND 切到前台并校验")
    args = parser.parse_args()

    set_dpi_aware()
    cfg = _load_controller_config()
    set_game_process(cfg.get("window_process", "MyGame_x64r.exe"))
    set_game_title_substr(cfg.get("window_title_substr", "梦幻西游"))

    if args.activate:
        from agent.win32.adapter import _force_foreground
        ok = _force_foreground(args.activate)
        print(f"[activate] HWND={args.activate} -> 前台校验: {'成功' if ok else '失败'}")
        return

    wins = locate_all_windows()
    if not wins:
        print("[probe] 未找到任何时空版窗口。请确认：")
        print("  - 客户端已启动且未最小化")
        print("  - 进程名与 config/controller_config.json 的 window_process 一致")
        print("  - 若客户端以管理员运行，本脚本也需以管理员运行")
        return

    print(f"[probe] 找到 {len(wins)} 个候选窗口：")
    sizes = []
    for h in wins:
        title = _window_title(h)
        rect = _get_window_rect(h)
        proc = _proc_basename(h)
        sizes.append(rect)
        print(f"  HWND={h}  进程={proc}  标题={title!r}  矩形={rect}")

    # 推荐基准：取最大窗口尺寸（多开各号应同尺寸，故取统一的基准档位）
    sizes = [s for s in sizes if s]
    if sizes:
        sizes.sort(key=lambda r: r[2] * r[3], reverse=True)
        base = sizes[0]
        print(f"[probe] 推荐 PC 默认分辨率基准档位: {base[2]}x{base[3]}")
        print("[probe] 请将此分辨率填入 config/controller_config.json 的 default_resolution，"
              "并在该档位下重新标定全部任务 ROI。")


if __name__ == "__main__":
    main()
