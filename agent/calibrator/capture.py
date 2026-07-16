# -*- coding: utf-8 -*-
"""
窗口截图：把游戏窗口变成 PIL.Image，供标定 GUI 框选。

坐标一致性原则：为了让标定出的 roi 与 MAA 运行时「同一张截图」的坐标完全对齐，
默认用 MAA 的 Win32Controller 截图（与运行同后端、同裁剪方式）。
无 maa 时回退 GDI（ImageGrab 客户区），用于离线 / 开发测试。
"""
import ctypes.wintypes

import agent.win32.adapter as adapter


def _capture_via_maa(hwnd):
    """用 MAA Win32Controller 截图（与运行时坐标一致）。maa 缺失或失败时抛异常。"""
    import numpy as np
    from maa.controller import Win32Controller

    # 后端枚举名随版本可能微调，逐一兜底尝试，避免硬编码写死。
    sm = (getattr(Win32Controller, "screencap_method_DXGI_DesktopDup", None)
          or getattr(Win32Controller, "screencap_method_DXGI", None))
    mm = (getattr(Win32Controller, "input_method_Seize", None)
          or getattr(Win32Controller, "input_method_SEND_MSG", None)
          or getattr(Win32Controller, "input_method_SendMessage", None))
    ctrl = Win32Controller(hwnd=int(hwnd),
                           screencap_method=sm,
                           mouse_method=mm,
                           keyboard_method=mm)
    ctrl.post_connection().wait()
    ctrl.post_screencap().wait()
    buf = ctrl.cached_image
    arr = buf.get() if hasattr(buf, "get") else np.asarray(buf)
    from PIL import Image
    # MAA 图像缓冲为 BGR，转 RGB。
    return Image.fromarray(arr[..., ::-1].copy(), "RGB")


def _capture_via_gdi(hwnd):
    """GDI 回退：截客户区（不含标题栏）。仅用于无 maa 的离线/测试场景。"""
    from PIL import ImageGrab
    adapter.set_dpi_aware()
    hwnd = int(hwnd)
    pt = ctypes.wintypes.POINT(0, 0)
    adapter._user32.ClientToScreen(hwnd, ctypes.byref(pt))
    rc = ctypes.wintypes.RECT()
    adapter._user32.GetClientRect(hwnd, ctypes.byref(rc))
    left, top = pt.x, pt.y
    right, bottom = left + rc.right, top + rc.bottom
    if right <= left or bottom <= top:
        raise RuntimeError("窗口客户区尺寸为 0（可能已最小化）")
    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    return img.convert("RGB")


def capture_window(hwnd, engine="maa"):
    """hwnd: 游戏窗口句柄。engine: 'maa'（默认，坐标与运行时一致）或 'gdi'。"""
    if engine == "maa":
        try:
            return _capture_via_maa(hwnd)
        except Exception as e:  # 回退 GDI 并提示
            print(f"[calibrator] maa 截图失败，回退 GDI: {e}")
    return _capture_via_gdi(hwnd)


def load_image_file(path):
    """从磁盘加载截图文件（离线标定用，绕开客户端）。"""
    from PIL import Image
    return Image.open(path).convert("RGB")
