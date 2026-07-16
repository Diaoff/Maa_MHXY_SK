# -*- coding: utf-8 -*-
"""
动态标定工具（从 MYscript 迁移的标定能力，独立为 GUI）。

职责：把《梦幻西游：时空》PC 客户端「实时截图」上用户框选的区域，落盘为 MAA 格式
的覆盖资源——模板图 PNG + pipeline override JSON，覆盖 assets/resource/base 的官方层。

子模块：
  - capture.py : 窗口截图（默认 MAA Win32Controller，坐标与运行时一致；回退 GDI）
  - export.py  : 把标定字段合并进 user override 节点，并导出模板 PNG
  - gui.py     : Tkinter 标定界面（拖框选区域 → 选任务/节点/类型 → 落盘）
入口：tools/calibrate.py
"""
from agent.calibrator import capture, export  # noqa: F401
