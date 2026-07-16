# -*- coding: utf-8 -*-
"""
时空版动态标定 GUI（Tkinter，标准库自带，无需额外依赖）。

流程：
  1. 选窗口（按进程名 MyGame_x64r.exe 过滤）→ 截图（默认 MAA Win32Controller，坐标与运行一致）
  2. 在截图上拖框 → 得到 roi = [x, y, w, h]（窗口像素坐标，与 MAA 截图同一坐标系）
  3. 选 任务 / 节点 / 标定类型 → 应用到节点，落盘为 user 覆盖资源

标定类型：
  - 模板图：裁出选中区域存为 user/image/<task>/<name>.png，并写入 roi + template
  - ROI坐标：仅写入 roi（OCR / Custom 等节点的识别范围）
  - 点击目标：写入 action 的 target [x,y,w,h]（Click 节点）
  - 滑动：第一次拖框=begin，第二次=end，写入 begin/end（Swipe / MultiSwipe 节点）
"""
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

import agent.win32.adapter as adapter
from agent.calibrator import capture, export

CANVAS_W, CANVAS_H = 960, 600
MAX_SCALE = 2.0


class CalibratorApp:
    def __init__(self, root, image_path=None, engine="maa", task=None, node=None, mode=None):
        adapter.set_dpi_aware()
        self.root = root
        self.engine = engine

        self.img = None          # PIL.Image (RGB)
        self.tkimg = None        # ImageTk 引用（防止被 GC）
        self.scale = 1.0
        self.drag_start = None   # (canvas_x, canvas_y)
        self.rect_id = None
        self.sel = None          # 主选区 [x, y, w, h]（图像坐标）
        self.swipe_begin = None
        self.swipe_end = None
        self.mode = mode or "template"
        self._windows = []       # [(label, hwnd), ...]

        self._build_ui()

        # 初始化任务下拉
        self.task_cb["values"] = export.list_tasks()
        if task:
            self.task_var.set(task)
            self._on_task_change()
            if node:
                self.node_var.set(node)

        # 预载图片（离线标定 / 开发测试）
        if image_path:
            try:
                self.load_image_file(image_path)
            except Exception as e:
                self._status(f"加载图片失败: {e}")

        self._refresh_windows()

    # ---------------- UI 构建 ----------------
    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        top = ttk.Frame(self.root)
        top.grid(row=0, column=0, sticky="ew", padx=6, pady=4)
        ttk.Label(top, text="窗口:").pack(side="left")
        self.win_var = tk.StringVar()
        self.win_cb = ttk.Combobox(top, textvariable=self.win_var, width=34, state="readonly")
        self.win_cb.pack(side="left", padx=4)
        ttk.Button(top, text="刷新窗口", command=self._refresh_windows).pack(side="left")
        ttk.Button(top, text="截图", command=self._on_capture).pack(side="left", padx=4)
        ttk.Button(top, text="打开图片…", command=self._on_open_image).pack(side="left")
        self.eng_var = tk.StringVar(value=self.engine)
        ttk.Label(top, text="引擎:").pack(side="left", padx=(8, 0))
        ttk.Combobox(top, textvariable=self.eng_var, width=6, state="readonly",
                     values=["maa", "gdi"]).pack(side="left")

        # 主区：左画布 + 右控制面板
        body = ttk.Frame(self.root)
        body.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(body, width=CANVAS_W, height=CANVAS_H,
                                bg="#1e1e1e", cursor="cross")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        right = ttk.Frame(body, width=300)
        right.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self._build_panel(right)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken",
                  anchor="w").grid(row=2, column=0, sticky="ew", padx=6, pady=4)

    def _build_panel(self, parent):
        ttk.Label(parent, text="任务名").pack(anchor="w", pady=(2, 0))
        self.task_var = tk.StringVar()
        self.task_cb = ttk.Combobox(parent, textvariable=self.task_var, width=30)
        self.task_cb.pack(fill="x")
        self.task_cb.bind("<<ComboboxSelected>>", lambda e: self._on_task_change())

        ttk.Label(parent, text="节点名").pack(anchor="w", pady=(6, 0))
        self.node_var = tk.StringVar()
        self.node_cb = ttk.Combobox(parent, textvariable=self.node_var, width=30)
        self.node_cb.pack(fill="x")

        ttk.Label(parent, text="标定类型").pack(anchor="w", pady=(6, 0))
        self.mode_var = tk.StringVar(value=self.mode)
        for m, label in (("template", "模板图（裁图+roi+template）"),
                         ("roi", "ROI 坐标（识别范围）"),
                         ("click", "点击目标（action.target）"),
                         ("swipe", "滑动（begin+end）")):
            ttk.Radiobutton(parent, text=label, variable=self.mode_var, value=m,
                            command=self._on_mode_change).pack(anchor="w")

        ttk.Label(parent, text="模板名（模板图模式）").pack(anchor="w", pady=(6, 0))
        self.tpl_var = tk.StringVar(value="tpl")
        ttk.Entry(parent, textvariable=self.tpl_var, width=30).pack(fill="x")

        ttk.Label(parent, text="当前框选").pack(anchor="w", pady=(6, 0))
        self.sel_var = tk.StringVar(value="（未选择）")
        ttk.Label(parent, textvariable=self.sel_var, relief="groove",
                  anchor="w", wraplength=290).pack(fill="x")

        ttk.Button(parent, text="应用到节点", command=self._on_apply).pack(fill="x", pady=(8, 2))
        ttk.Button(parent, text="复制 JSON 片段", command=self._on_copy).pack(fill="x", pady=2)
        ttk.Button(parent, text="清除选区", command=self._on_clear).pack(fill="x", pady=2)

        ttk.Label(parent, text="说明", font=("", 9, "bold")).pack(anchor="w", pady=(10, 2))
        tip = ("拖动鼠标在截图上框选目标区域。\n"
               "· 模板图：裁出区域存为模板 PNG\n"
               "· ROI/点击：写入坐标\n"
               "· 滑动：拖两次（先 begin 后 end）\n"
               "坐标均为窗口像素，与 MAA 运行时一致。")
        ttk.Label(parent, text=tip, wraplength=290, justify="left").pack(anchor="w")

    # ---------------- 窗口 / 截图 ----------------
    def _refresh_windows(self):
        wins = adapter.locate_all_windows(adapter._GAME_TITLE_SUBSTR)
        self._windows = []
        labels = []
        for i, h in enumerate(wins):
            w = adapter.GameWindow(h, adapter._GAME_TITLE_SUBSTR)
            r = w.rect()
            size = f"{r[2]}x{r[3]}" if r else "?"
            labels.append(f"#{i} hwnd={h} {size} {w.title[:24]}")
            self._windows.append((h, w.title))
        self.win_cb["values"] = labels
        if labels and not self.win_var.get():
            self.win_var.set(labels[0])

    def _selected_hwnd(self):
        idx = self.win_cb.current()
        if 0 <= idx < len(self._windows):
            return self._windows[idx][0]
        return 0

    def _on_capture(self):
        self.engine = self.eng_var.get()
        hwnd = self._selected_hwnd()
        if not hwnd:
            messagebox.showwarning("未找到窗口", "请先启动《梦幻西游：时空》客户端，或点「打开图片」离线标定。")
            return
        try:
            img = capture.capture_window(hwnd, self.engine)
        except Exception as e:
            messagebox.showerror("截图失败", f"{e}\n\n可改用「打开图片」加载客户端截图。")
            return
        self._set_image(img)
        self._status(f"已截图 hwnd={hwnd}（{img.width}x{img.height}），引擎={self.engine}")

    def _on_open_image(self):
        path = filedialog.askopenfilename(title="选择客户端截图",
                                          filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp")])
        if path:
            try:
                self.load_image_file(path)
            except Exception as e:
                messagebox.showerror("打开失败", str(e))

    def load_image_file(self, path):
        img = capture.load_image_file(path)
        self._set_image(img)
        self._status(f"已加载图片: {os.path.basename(path)}（{img.width}x{img.height}）")

    # ---------------- 图像显示 / 坐标 ----------------
    def _set_image(self, img):
        self.img = img
        self.sel = None
        self.swipe_begin = None
        self.swipe_end = None
        self._clear_rect()
        self._update_sel_label()
        iw, ih = img.size
        self.scale = min(CANVAS_W / iw, CANVAS_H / ih, MAX_SCALE)
        disp = img.resize((max(1, int(iw * self.scale)), max(1, int(ih * self.scale))))
        self.tkimg = ImageTk.PhotoImage(disp)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.tkimg, anchor="nw")

    def _canvas_to_img(self, cx, cy):
        return int(round(cx / self.scale)), int(round(cy / self.scale))

    def _norm_img(self, p0, p1):
        """两个画布坐标点 → 归一化图像坐标 [x, y, w, h]，并夹在图像范围内。"""
        x0, y0 = self._canvas_to_img(*p0)
        x1, y1 = self._canvas_to_img(*p1)
        x, y = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        iw, ih = self.img.size
        x = max(0, min(x, iw - 1))
        y = max(0, min(y, ih - 1))
        w = max(0, min(w, iw - x))
        h = max(0, min(h, ih - y))
        return [x, y, w, h]

    def _clear_rect(self):
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            self.rect_id = None

    # ---------------- 拖框 ----------------
    def _on_press(self, event):
        if self.img is None:
            return
        self.drag_start = (event.x, event.y)
        self._clear_rect()

    def _on_motion(self, event):
        if self.drag_start is None:
            return
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.drag_start[0], self.drag_start[1], event.x, event.y,
            outline="#ffeb3b", width=2, dash=(4, 3))

    def _on_release(self, event):
        if self.drag_start is None or self.img is None:
            return
        box = self._norm_img(self.drag_start, (event.x, event.y))
        self.drag_start = None
        if self.mode_var.get() == "swipe":
            if self.swipe_begin is None:
                self.swipe_begin = box
                self._status("滑动 begin 已记录，请再拖一次设定 end")
            else:
                self.swipe_end = box
                self.sel = self.swipe_begin
        else:
            self.sel = box
        self._update_sel_label()

    # ---------------- 面板交互 ----------------
    def _on_task_change(self):
        task = self.task_var.get().strip()
        if task:
            self.node_cb["values"] = export.list_nodes(task)

    def _on_mode_change(self):
        self.mode = self.mode_var.get()
        # 切换模式重置滑动的两次选择
        self.swipe_begin = None
        self.swipe_end = None
        self._update_sel_label()

    def _on_clear(self):
        self.sel = None
        self.swipe_begin = None
        self.swipe_end = None
        self._clear_rect()
        self._update_sel_label()
        self._status("已清除选区")

    def _update_sel_label(self):
        if self.mode_var.get() == "swipe":
            b = self.swipe_begin
            e = self.swipe_end
            txt = f"begin: {b}\nend:   {e}" if (b or e) else "（未选择，先拖 begin）"
        else:
            txt = f"{self.sel}" if self.sel else "（未选择）"
        self.sel_var.set(txt)

    def _build_fields(self):
        mode = self.mode_var.get()
        if mode in ("template", "roi"):
            if not self.sel:
                return None, "请先在截图上拖出区域"
            return {"roi": list(self.sel)}, None
        if mode == "click":
            if not self.sel:
                return None, "请先拖出点击位置（区域中心作为点击点）"
            return {"target": list(self.sel)}, None
        if mode == "swipe":
            if not self.swipe_begin or not self.swipe_end:
                return None, "滑动模式需拖两次：第一次 begin，第二次 end"
            return {"begin": list(self.swipe_begin), "end": list(self.swipe_end)}, None
        return None, "未知标定类型"

    # ---------------- 落盘 ----------------
    def _on_apply(self):
        task = self.task_var.get().strip()
        node = self.node_var.get().strip()
        if not task or not node:
            messagebox.showerror("缺少参数", "请选择「任务名」与「节点名」")
            return
        fields, err = self._build_fields()
        if err:
            messagebox.showwarning("无法应用", err)
            return
        tpl_img = None
        tpl_name = None
        if self.mode_var.get() == "template":
            tpl_name = self.tpl_var.get().strip() or "tpl"
            x, y, w, h = self.sel
            tpl_img = self.img.crop((x, y, x + w, y + h))
        try:
            path = export.apply_calibration(task, node, fields,
                                             template_img=tpl_img, template_name=tpl_name)
        except Exception as e:
            messagebox.showerror("写入失败", str(e))
            return
        self._status(f"已写入覆盖层: {os.path.relpath(path, export.ROOT)}")

    def _on_copy(self):
        task = self.task_var.get().strip()
        node = self.node_var.get().strip()
        if not node:
            messagebox.showerror("缺少参数", "请选择「节点名」")
            return
        fields, err = self._build_fields()
        if err:
            messagebox.showwarning("无法复制", err)
            return
        if self.mode_var.get() == "template":
            tpl_name = self.tpl_var.get().strip() or "tpl"
            fields = dict(fields)
            fields["template"] = f"{task}/{tpl_name}.png"
            fields.setdefault("recognition", "TemplateMatch")
        snippet = {node: fields}
        text = json.dumps(snippet, indent=4, ensure_ascii=False)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._status("已复制 JSON 片段到剪贴板")

    def _status(self, msg):
        self.status_var.set(msg)
