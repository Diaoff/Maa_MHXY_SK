# -*- coding: utf-8 -*-
"""
时空版统一控制台 GUI（Tkinter，标准库自带，无额外依赖）。

整合能力：
  - 实例列表：探测本机《梦幻西游：时空》窗口（按进程名过滤），显示序号 / HWND / 标题 /
    角色（队长 / 队员）/ 状态。
  - 组队握手面板：设置队长、队长发信号、队员就位、一键模拟一次完整握手、复位；实时
    展示队长与各队员状态（轮询 runtime/team/ 文件，与引擎 / CLI 共享同一份状态）。
  - 三重急停：触发 / 解除（写入或删除 runtime/emergency_stop.flag 哨兵文件），并显示状态。
  - 启动多开：把 tools/run_multi_instance.py 作为子进程拉起（可选 --team），其日志流式进入
    下方日志区；可随时停止。

所有状态读取都走文件 IPC，因此控制台可独立运行，也能监控另一个进程里的多开引擎。
"""

import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

import agent.win32.adapter as adapter
from agent.multi_instance import teaming
from agent.safety.emergency_stop import EMERGENCY_STOP_DEFAULT

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (ROOT, os.path.join(ROOT, "agent")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

POLL_MS = 600
RUN_MULTI = os.path.join(ROOT, "tools", "run_multi_instance.py")
CALIBRATE = os.path.join(ROOT, "tools", "calibrate.py")


def _load_controller_config():
    cfg_path = os.path.join(ROOT, "config", "controller_config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f).get("win32", {})
    except Exception:
        return {}


def _sentinel_path():
    p = EMERGENCY_STOP_DEFAULT["sentinel_file"]["path"]
    return os.path.join(ROOT, p)


class ConsoleApp:
    def __init__(self, root):
        adapter.set_dpi_aware()
        self.root = root
        self.root.title("时空版统一控制台")
        self.root.geometry("980x720")

        self.win_config = _load_controller_config()
        adapter.set_game_process(self.win_config.get("window_process"))
        adapter.set_game_title_substr(
            self.win_config.get("window_title_substr", "梦幻西游"))
        self.title_substr = self.win_config.get("window_title_substr", "梦幻西游")

        self.coord = teaming.get_coordinator()
        self._windows = []        # [(idx, hwnd, title)]
        self._proc = None         # 多开子进程
        self._calib_proc = None   # 标定工具子进程
        self._stop = False

        self._build_ui()
        self._refresh_windows()
        self._poll()

    # ---------------- UI 构建 ----------------
    def _build_ui(self):
        # 顶部工具栏
        top = ttk.Frame(self.root)
        top.pack(side="top", fill="x", padx=6, pady=4)
        ttk.Button(top, text="刷新窗口", command=self._refresh_windows).pack(side="left")
        ttk.Button(top, text="启动多开", command=self._on_start).pack(side="left", padx=4)
        ttk.Button(top, text="停止多开", command=self._on_stop).pack(side="left")
        ttk.Button(top, text="标定工具", command=self._on_open_calib).pack(side="left", padx=4)
        ttk.Button(top, text="退出", command=self._on_quit).pack(side="right")

        body = ttk.PanedWindow(self.root, orient="horizontal")
        body.pack(side="top", fill="both", expand=True, padx=6, pady=4)

        # 左：实例列表
        left = ttk.Frame(body, width=420)
        body.add(left, weight=1)
        ttk.Label(left, text="实例（窗口）", font=("", 10, "bold")).pack(anchor="w")
        self.inst_tv = ttk.Treeview(
            left, columns=("idx", "hwnd", "title", "role", "status"),
            show="headings", height=10)
        for col, w in (("idx", 40), ("hwnd", 90), ("title", 180),
                       ("role", 60), ("status", 60)):
            self.inst_tv.heading(col, text=col)
            self.inst_tv.column(col, width=w, anchor="w")
        self.inst_tv.pack(fill="both", expand=True, pady=(2, 6))

        # 右：组队 + 急停
        right = ttk.Frame(body, width=520)
        body.add(right, weight=1)
        self._build_team_panel(right)
        self._build_estop_panel(right)

        # 底部日志
        self.log = scrolledtext.ScrolledText(self.root, height=12, state="disabled")
        self.log.pack(side="bottom", fill="both", expand=False, padx=6, pady=(0, 6))
        self._log("控制台就绪。")

    def _build_team_panel(self, parent):
        f = ttk.LabelFrame(parent, text="组队握手")
        f.pack(side="top", fill="x", pady=(2, 6))

        row1 = ttk.Frame(f)
        row1.pack(fill="x", padx=4, pady=2)
        ttk.Label(row1, text="队长序号").pack(side="left")
        self.leader_var = tk.StringVar(value="0")
        self.leader_cb = ttk.Combobox(row1, textvariable=self.leader_var,
                                      width=6, state="readonly")
        self.leader_cb.pack(side="left", padx=4)
        ttk.Button(row1, text="设为队长", command=self._on_set_leader).pack(side="left")

        row2 = ttk.Frame(f)
        row2.pack(fill="x", padx=4, pady=2)
        ttk.Label(row2, text="阶段").pack(side="left")
        self.phase_var = tk.StringVar(value="inviting")
        self.phase_cb = ttk.Combobox(row2, textvariable=self.phase_var,
                                     width=16, values=teaming.TEAM_PHASES)
        self.phase_cb.pack(side="left", padx=4)
        ttk.Button(row2, text="队长发信号", command=self._on_leader_signal).pack(side="left")

        row3 = ttk.Frame(f)
        row3.pack(fill="x", padx=4, pady=2)
        ttk.Label(row3, text="队员序号").pack(side="left")
        self.member_var = tk.StringVar(value="1")
        self.member_cb = ttk.Combobox(row3, textvariable=self.member_var,
                                      width=6, state="readonly")
        self.member_cb.pack(side="left", padx=4)
        ttk.Button(row3, text="队员就位", command=self._on_member_ready).pack(side="left")
        ttk.Button(row3, text="模拟握手", command=self._on_simulate).pack(side="left", padx=4)
        ttk.Button(row3, text="复位", command=self._on_team_reset).pack(side="left")

        # 实时状态
        ttk.Label(f, text="实时状态", font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(4, 0))
        self.leader_state_var = tk.StringVar(value="（无）")
        ttk.Label(f, textvariable=self.leader_state_var, relief="groove",
                  anchor="w").pack(fill="x", padx=4, pady=2)
        self.member_tv = ttk.Treeview(
            f, columns=("idx", "state"), show="headings", height=6)
        self.member_tv.heading("idx", text="队员")
        self.member_tv.heading("state", text="状态")
        self.member_tv.column("idx", width=60)
        self.member_tv.column("state", width=120)
        self.member_tv.pack(fill="x", padx=4, pady=2)

    def _build_estop_panel(self, parent):
        f = ttk.LabelFrame(parent, text="三重急停")
        f.pack(side="top", fill="x", pady=(2, 6))
        row = ttk.Frame(f)
        row.pack(fill="x", padx=4, pady=4)
        ttk.Button(row, text="触发急停", command=self._on_estop_trigger).pack(side="left")
        ttk.Button(row, text="解除急停", command=self._on_estop_reset).pack(side="left", padx=4)
        self.estop_var = tk.StringVar(value="未触发")
        ttk.Label(row, textvariable=self.estop_var, relief="sunken",
                  anchor="w", width=14).pack(side="left", padx=8)

    # ---------------- 实例 ----------------
    def _refresh_windows(self):
        try:
            hwnds = adapter.locate_all_windows(self.title_substr)
        except Exception as e:
            self._log(f"枚举窗口失败: {e}")
            hwnds = []
        self._windows = []
        self.inst_tv.delete(*self.inst_tv.get_children())
        for i, h in enumerate(hwnds):
            w = adapter.GameWindow(h, self.title_substr)
            self._windows.append((i, h, w.title))
            role = "队长" if i == self.coord.leader_index else "队员"
            self.inst_tv.insert("", "end", values=(i, h, w.title[:24], role, "在线"))
        # 更新下拉
        idxs = [str(i) for i, _, _ in self._windows]
        self.leader_cb["values"] = idxs or ["0"]
        self.member_cb["values"] = idxs or ["1"]
        if idxs and self.leader_var.get() not in idxs:
            self.leader_var.set(idxs[0])
        if idxs and self.member_var.get() not in idxs:
            self.member_var.set(idxs[-1] if len(idxs) > 1 else idxs[0])
        self._log(f"刷新窗口：发现 {len(hwnds)} 个")

    # ---------------- 组队操作 ----------------
    def _on_set_leader(self):
        try:
            leader = int(self.leader_var.get())
        except Exception:
            messagebox.showerror("错误", "请先刷新窗口并选择队长序号")
            return
        members = [i for i, _, _ in self._windows if i != leader]
        self.coord.set_roles(leader, members)
        self._refresh_windows()
        self._log(f"已设队长={leader}，队员={members}")

    def _on_leader_signal(self):
        self.coord.signal_leader(self.phase_var.get())
        self._log(f"队长发信号: {self.phase_var.get()}")

    def _on_member_ready(self):
        try:
            idx = int(self.member_var.get())
        except Exception:
            messagebox.showerror("错误", "请选择队员序号")
            return
        state = self.phase_var.get() or "accepted"
        self.coord.signal_member(idx, state)
        self._log(f"队员 {idx} 就位: {state}")

    def _on_team_reset(self):
        self.coord.reset()
        self._log("组队握手已复位")

    def _on_simulate(self):
        """后台线程模拟一次完整握手，验证协议闭环（不依赖游戏客户端）。"""
        def worker():
            members = self.coord.member_indices or [1, 2]
            leader = self.coord.leader_index
            self.coord.reset()
            self.coord.signal_leader("lobby")
            self._log("[模拟] 队长在 lobby，等待队员 accepted…")

            def member_job(mi):
                self.coord.wait_leader("inviting", timeout=10)
                self.coord.signal_member(mi, "accepted")
                self.coord.wait_leader("enter_dungeon", timeout=10)

            ts = [threading.Thread(target=member_job, args=(mi,), daemon=True)
                  for mi in members]
            for t in ts:
                t.start()
            time.sleep(0.3)
            self.coord.signal_leader("inviting")
            ok = self.coord.wait_all_members("accepted", timeout=10, indices=members)
            if ok:
                self.coord.signal_leader("enter_dungeon")
                self._log("[模拟] 全部就位，已进入 enter_dungeon ✅")
            else:
                self._log("[模拟] 等待队员超时 ❌")
            for t in ts:
                t.join(timeout=1)

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- 急停 ----------------
    def _on_estop_trigger(self):
        path = _sentinel_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w", encoding="utf-8").close()
            self._log(f"急停哨兵已写入: {path}")
        except Exception as e:
            self._log(f"写入急停哨兵失败: {e}")

    def _on_estop_reset(self):
        path = _sentinel_path()
        try:
            if os.path.exists(path):
                os.remove(path)
            self._log("急停已解除")
        except Exception as e:
            self._log(f"解除急停失败: {e}")

    # ---------------- 启动多开 ----------------
    def _on_start(self):
        if self._proc and self._proc.poll() is None:
            self._log("多开已在运行")
            return
        cmd = [sys.executable, RUN_MULTI]
        if self.coord.config.get("enabled"):
            cmd.append("--team")
        self._log(f"启动: {' '.join(cmd)}")
        try:
            self._proc = subprocess.Popen(
                cmd, cwd=ROOT, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            self._log(f"启动失败: {e}")
            return
        threading.Thread(target=self._pump, args=(self._proc,), daemon=True).start()

    def _pump(self, proc):
        try:
            for line in proc.stdout:
                self._log(line.rstrip("\n"), echo=False)
        except Exception:
            pass
        finally:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass

    def _on_stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._log("已发送终止信号")
        else:
            self._log("多开未运行")
    # ---------------- 标定工具 ----------------
    def _on_open_calib(self):
        """启动独立的动态标定工具 GUI（tools/calibrate.py）。"""
        if self._calib_proc and self._calib_proc.poll() is None:
            self._log("标定工具已在运行")
            return
        if not os.path.exists(CALIBRATE):
            self._log(f"未找到标定工具: {CALIBRATE}")
            return
        cmd = [sys.executable, CALIBRATE]
        self._log(f"启动标定工具: {' '.join(cmd)}")
        try:
            self._calib_proc = subprocess.Popen(
                cmd, cwd=ROOT, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            self._log(f"启动标定工具失败: {e}")
            return
        threading.Thread(target=self._pump_calib, args=(self._calib_proc,),
                        daemon=True).start()
    def _pump_calib(self, proc):
        try:
            for line in proc.stdout:
                self._log(line.rstrip("\n"), echo=False)
        except Exception:
            pass
        finally:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
            else:
                self._log("标定工具已退出")
    def _close_calib(self):
        if self._calib_proc and self._calib_proc.poll() is None:
            self._calib_proc.terminate()

    def _on_quit(self):
        self._stop = True
        self._on_stop()
        self._close_calib()
        self.root.destroy()

    # ---------------- 轮询 ----------------
    def _poll(self):
        if getattr(self, "_stop", False):
            return
        # 急停状态
        self.estop_var.set("已触发 ⚠" if os.path.exists(_sentinel_path()) else "未触发")
        # 队长状态
        self.leader_state_var.set(f"队长状态: {self.coord.leader_state() or '（无）'}")
        # 队员状态
        states = self.coord.members_state()
        self.member_tv.delete(*self.member_tv.get_children())
        for idx in sorted(states):
            self.member_tv.insert("", "end", values=(idx, states[idx] or "（无）"))
        self.root.after(POLL_MS, self._poll)

    # ---------------- 日志 ----------------
    def _log(self, msg, echo=True):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"

        def _append():
            self.log.configure(state="normal")
            self.log.insert("end", line + "\n")
            self.log.configure(state="disabled")
            self.log.see("end")

        if threading.current_thread() is threading.main_thread():
            _append()
        else:
            self.root.after(0, _append)


def main():
    root = tk.Tk()
    ConsoleApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
