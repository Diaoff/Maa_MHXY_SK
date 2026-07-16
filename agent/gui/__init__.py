# -*- coding: utf-8 -*-
"""时空版统一控制台 GUI（Tkinter，标准库自带，无额外依赖）。

整合：实例列表 + 组队握手面板 + 三重急停 + 启动多开。与多开引擎 / CLI 共享同一份
状态文件（runtime/team/ 与 runtime/emergency_stop.flag），因此即使引擎跑在另一进程，
控制台也能观察并操控组队握手与急停。
"""
from agent.gui.console import ConsoleApp  # noqa: F401
