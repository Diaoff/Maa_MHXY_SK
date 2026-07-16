---
name: maafw-dev
description: MaaFramework 使用与开发全流程参考技能。当你需要编写/调试 pipeline JSON、配置 interface.json（ProjectInterface V2）、使用 ADB/Win32/PlayCover 控制器、编写 Python 自定义识别/动作（AgentServer）、理解任务流水线执行模型、定位识别失败、或用 MaaPiCli/MFAAvalonia 运行任务时，加载此技能。覆盖架构、三种开发方式、控制器、Pipeline 协议、自定义模块、Python API、调试与最佳实践。
---

# MaaFramework 开发技能

> 来源：deepwiki.com/MaaXYZ/MaaFramework 与 maafw.com/docs 全章节研读精编。
> 配套已装技能：`pipeline-generate`（自动算 ROI）、`pipeline-guide`（字段速查）、`pipeline-option`（option 协议）。
> 本项目落地背景：梦幻西游·时空版（Windows PC 客户端，Win32 控制器，`seize` 注入式输入，5 开竖屏 500×900，PC 适配走 `user/` 覆盖层）。

## 0. 何时用本技能

- 写/改 `assets/resource/**/pipeline/*.json`（任务流水线）
- 改 `assets/interface.json`（控制器/资源/任务/选项声明）
- 在 `agent/custom/{reco,action,sink}/` 写 Python 自定义识别/动作
- 排查「能截图、不点击 / 识别不到 / 任务卡住」类问题
- 用 `tools/win32_probe.py`、`MaaPiCli`、`MFAAvalonia` 跑任务
- 理解 `next / sub / on_error / [JumpBack] / 锚点 / 虚拟任务#` 等机制

---

## 1. 架构总览（四层）

```
Controller  ── 设备/窗口交互（截图 + 输入）
   │            ADB(安卓模拟器) / Win32(Windows PC) / PlayCover(macOS iOS) / MacOS / Gamepad
Resource   ── 资源包（pipeline JSON + image 模板 + model/ocr）
   │            interface.json 声明多个 resource，按 controller/option 选择性加载
Tasker     ── 把 Controller + Resource 绑定，post_task 驱动流水线执行
   │
Context    ── 仅在「自定义识别/动作回调」内可用，提供 override_next / run_recognition / 查询节点等
```

- **interface.json（ProjectInterface V2 协议）**：描述项目有哪些控制器、资源包、可执行任务、UI 选项，让通用 GUI（MFAAvalonia）或 MaaPiCli 能加载并运行。
- 纯 JSON 即可跑（MaaPiCli）；复杂逻辑用「JSON + Agent 自定义扩展」(推荐)；全代码 API 也可用但会失去可视化工具。

---

## 2. 三种开发方式

| 方案 | 适用 | 特点 |
|---|---|---|
| ① 纯 JSON 低代码 | 简单逻辑、快速入门 | 零编码，配 `pipeline/*.json`；配 MaaPipelineEditor 可视化拖拽 |
| ② JSON + 自定义逻辑（**推荐**） | 复杂逻辑 | JSON 管主干，注册 `custom_recognition`/`custom_action` 承载复杂算法；GUI 仍连 Agent 进程自动调用 |
| ③ 全代码 | 深度定制 | 直接用 Tasker/Controller API；失去可视化编辑器/调试器/通用 UI |

本项目用的是 ②：`agent/custom/` 下大量 Python 自定义模块 + `pipeline/*.json` 主干。

---

## 3. 资源目录结构

```
my_resource/
├── image/            # 模板匹配/特征检测图片（pipeline 中 template 字段引用）
│   └── my_xxx.png    # 基于「无损原图缩放到 720p 后裁剪」；勿直接用原图
├── model/ocr/        # PaddleOCR→ONNX：det.onnx / rec.onnx / keys.txt（用 MaaCommonAssets 预转换）
└── pipeline/         # 任务流水线（递归读取所有 .json；JSON 不支持注释）
```

- 以 `my_` 开头的文件/目录可改名；`image/ model/ocr/ pipeline/` 这些固定名不可改。
- 本项目分层：`base/`（手游版主干，勿改）、`user/`（PC 时空版覆盖层，放 500×900 重标定产物）。
- **覆盖层加载顺序**：interface.json 中 resource 的 `path` 数组靠后的覆盖靠前的同名任务/字段。

---

## 4. Pipeline 协议（核心）

### 4.1 基础格式

```jsonc
{
  "识别并点击开始": {
    "recognition": "OCR",
    "expected": "开始",
    "action": "Click",
    "next": ["识别并点击确认"]
  },
  "识别并点击确认": {
    "recognition": "TemplateMatch",
    "template": "确认.png",
    "action": "Click"
  }
}
```

### 4.2 执行逻辑

- 入口：Agent/Tasker `post_task(入口节点)` 或 `post_pipeline`。
- 对当前节点 `next` 列表**顺序识别**，命中第一个即中断后续探测、执行其 `action`。
- `action` 成功 → 进入该节点 `next`；`action` 失败 → 进入该节点 `on_error`；`next` 超时未命中 → 进入当前节点 `on_error`。
- **终止条件**：`next` 为空（有 `[JumpBack]` 先回跳）；`next` 超时；外部 `post_stop` 或 `Stop` 动作。
- 等价循环：`while(!hit && !timeout) { foreach(next); sleep_until(rate_limit); }`

### 4.3 节点生命周期

`pre_wait_freezes → pre_delay → action → [repeat_wait_freezes → repeat_delay → action]×(repeat-1) → post_wait_freezes → post_delay → 截图 → 识别 next`

### 4.4 recognition 类型

`DirectHit`(默认) / `TemplateMatch`(图) / `FeatureMatch`(SIFT特征) / `ColorMatch`(颜色) / `OCR`(文字) / `NeuralNetworkClassify` / `NeuralNetworkDetect` / `And` / `Or` / `Custom`。

v2 对象形式（推荐，便于带参数）：
```jsonc
"recognition": { "type": "OCR", "param": { "expected": ["福利"], "roi": [0,0,500,900] } }
```
字段详见 `../pipeline-guide/field_reference.md`（已装）。要点：
- `TemplateMatch.threshold` 默认 0.7；`method` 5=TM_CCOEFF_NORMED（推荐）。
- `OCR.expected` 写**完整中文**（`["福利"]` 对，`["fuli"]` 永远找不到）；`threshold` 默认 0.3。
- `ColorMatch.lower/upper` 必填（BGR 或 RGB，看 `method`）；`connected` 控制连通域。

### 4.5 action 类型

`DoNothing`(默认) / `Click` / `LongPress` / `Swipe` / `Scroll` / `ClickKey` / `LongPressKey` / `KeyDown`/`KeyUp` / `InputText` / `StartApp`/`StopApp` / `Shell` / `Command` / `Screencap` / `Custom`。

```jsonc
"action": { "type": "Click", "param": { "target": true, "target_offset": [0,0,0,0] } }
```
- `target: true` = 点识别到的 box；可改为固定点 `[x,y]`、固定区域 `[x,y,w,h]`、或引用其他节点名。
- `ClickKey`/`LongPressKey` 用 `key`（虚拟键码）；`StartApp`/`StopApp` 用 `package`。

### 4.6 特殊机制

| 机制 | 写法 | 说明 |
|---|---|---|
| 特殊任务 | `"任务名@xxx"` | 带 `@` 的任务字段默认值不同（如 `@` 型任务）；可用 `baseTask` 继承 |
| 虚拟任务# | `"A#self"` `"A@B#back"` `"#next"` | self=父任务名；back=去掉#前任务名；next=引用某任务 next 字段 |
| 节点属性 NodeAttr | `"next": [{"name":"X","timeout":5000}]` | next/on_error 元素可为带属性的对象（v5.1+） |
| 回跳 [JumpBack] | `"next": ["[JumpBack]"]` 或 `{ "jump_back": true }` | 回跳到最近设置锚点的地方（替代废弃的 is_sub/interrupt） |
| 锚点 anchor | `"anchor": "我的锚"` + `Context.set_anchor` | 标记回跳目标；roi/target 可引用 `"[Anchor]锚点名"` |
| maxTimes / exceededNext | `"maxTimes": 10, "exceededNext": ["结束"]` | 达上限走 exceededNext |
| max_hit | `"max_hit": 3` | 最大命中次数 |
| repeat | `"repeat": 3, "repeat_delay": 500` | 动作重复 |

### 4.7 roi / box / target 区别

- `roi`：识别区域（在 roi 内识别）；与 `roi_offset` 共同决定范围。
- `box`：识别成功返回的命中框（「识别到了哪」）。
- `target`：动作目标（「点哪」）；由 `target`+`target_offset` 决定；默认 true=用 box。
- 支持负值坐标与尺寸（v5.6）；字符串形式支持 `[Anchor]锚点名` 引用（v5.9）。

### 4.8 致命反模式（本项目实测踩坑）

- ❌ **死循环滑动**：在 `Click` 节点的 `next` 里放滑动节点 → 会无限滑动。可滚动 UI 用「共享大 ROI + 父级 orchestrator」或 `Scroll` 动作。
- ❌ **ROI 过大**：OCR 会把「福利」拆成「福」+「利」导致失败。`expand` 甜区 20–30。
- ❌ **expected 不配 recognition:OCR**：`expected` 只在识别为 OCR 时生效。
- ❌ **跨文件同名顶层 key**：`check_resource.py` 严格拒绝重复顶层 key，Python `json.load` 静默覆盖查不出。
- ❌ **option 漏注册到 task**：`task.option: ["xxx"]` 没写，UI 上看不到该选项。
- ❌ **手写坐标不匹配实际分辨率**：本项目 base 是手游 16:9 坐标，PC 500×900 必须重标定（已从实机验证：能截图不点击 = 识别全失败）。

---

## 5. 控制器（Controller）

| 类型 | 平台 | 关键点 |
|---|---|---|
| `Adb` | 安卓模拟器 | screencap/input 由框架自动选最优；需 adb 路径/地址 |
| `Win32` | Windows PC 客户端 | 绑定 HWND；`class_regex`+`window_regex` 匹配窗口；**常需管理员权限**；screencap/input 后端可配 |
| `PlayCover` | macOS (Apple Silicon) iOS | 仅 Apple Silicon；原生触控模拟，不需 ADB |
| `MacOS` | macOS | `title_regex` + `input`(GlobalEvent/PostToPid) + `screencap` |
| `Gamepad` | Windows 手柄 | `gamepad_type`: Xbox360/DualShock4/DS4 |

### 5.1 interface.json controller 字段

```jsonc
{
  "name": "win32_pc",           // 控制器唯一 ID
  "label": "时空版PC",
  "type": "Win32",
  "class_regex": ".*",           // 窗口类名（Unity 常为 UnityWndClass）
  "window_regex": "梦幻西游.*",  // 窗口标题正则（多语言匹配）
  "screencap": "dxgi_desktopduplication",  // 截图后端
  "mouse": "Seize",              // 输入后端：Seize=注入(后台可点) / SendInput=模拟(需前台)
  "keyboard": "Seize",
  "permission_required": true,   // 用 Win32 常需右键「以管理员身份运行」
  "display_short_side": 720      // 默认缩放短边；与 display_long_side/display_raw 互斥
}
```

- **本项目配置**：`config/controller_config.json` 的 `win32` 段（`input_backend: seize`、`window_process: MyGame_x64r.exe`、`window_title_substr: 梦幻西游`、实际窗口 500×900）。`seize` 向各自 HWND 注入点击 → 5 窗口并排互不抢前台，正是本项目需要的。
- **资源兼容性**：resource 的 `controller` 数组决定该资源能在哪些控制器跑；选错控制器任务直接报错。

---

## 6. 自定义识别 / 动作（Agent 进程）

> 本项目 `agent/custom/` 的全部自定义模块都走这套机制。

```python
from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.custom_action import CustomAction
from maa.context import Context

@AgentServer.custom_recognition("MyReco")
class MyReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        img = context.tasker.controller.cached_image   # numpy 截图
        # ... 自己的识别逻辑 ...
        return CustomRecognition.AnalyzeResult(box=[x, y, w, h], detail={})

@AgentServer.custom_action("MyAct")
class MyAct(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        context.controller.post_click(100, 10).wait()   # 执行点击
        context.override_next("当前节点", ["TaskA", "TaskB"])  # 动态改流程
        return True

# 启动 Agent 服务（由通用 UI / MaaPiCli 通过 sock_id 连接）
# AgentServer.start_up(sock_id)
```

pipeline 中引用：
```jsonc
"自定义处理模块": {
  "recognition": "Custom", "custom_recognition": "MyReco",
  "action": "Custom", "custom_action": "MyAct",
  "custom_recognition_param": { "...": "任意 JSON" },
  "custom_action_param": { "...": "任意 JSON" }
}
```

### Context 关键 API（回调内可用）

`context.controller` / `context.tasker` / `context.resource`
- `run_recognition(entry, image, override)` / `run_action(entry, box, reco_detail, override)` / `run_task(entry, override)` — 同步调用
- `override_pipeline(dict)` — 运行时改 pipeline
- `override_next(name, next_list)` — 改某节点 next
- `override_image(name, img)` — 换模板图
- `get_node_data(name)` — 查当前节点定义（含 option 注入的识别参数）
- `set_anchor(name, node)` / `get_anchor(name)` — 锚点
- `get_hit_count(name)` / `clear_hit_count(name)` — 计数

---

## 7. Python API 速查（全代码 / 集成用）

**Resource**：`post_bundle(path)` / `post_pipeline(path)` / `post_ocr_model(path)` / `post_image(path)` / `override_pipeline(dict)` / `register_custom_recognition(name, obj)` / `register_custom_action(name, obj)` / `loaded` / `node_list`。

**Controller**（基类方法，各平台同）：
- `post_connection()` / `connected` / `uuid`
- `post_click(x,y)` / `post_swipe(x1,y1,x2,y2,dur)` / `post_long_press` / `post_scroll(dx,dy)`(Win)
- `post_screencap()` → `JobWithResult`；`cached_image` 最近截图(numpy，按截图目标尺寸缩放)
- `post_input_text(text)` / `post_start_app(intent)` / `post_stop_app(intent)`
- `post_touch_down/move/up` / `post_key_down/up`
- `resolution` 原始分辨率（截图像素可能已缩放，二者可能不同）

**Tasker**：`bind(resource, controller)` / `post_task(entry, override)` / `post_pipeline(entry)` / `post_stop()` / `inited`/`running`/`stopping` / `resource` / `controller` / `set_log_dir` / `set_save_draw(bool)` / `set_debug_mode(bool)` / `set_stdout_level(level)`。

**Context**（见 §6）。

**Job 模式**：异步操作返回 `Job`/`JobWithResult`，用 `.wait().get()` 取结果。

---

## 8. interface.json V2 协议（顶层字段）

完整 schema 见 `references/interface_v2.md`。顶层：

```
interface_version: 2 (必填)
name / label / title / version / icon / description / url / contact / license
controller: [ {name,label,type,class_regex,window_regex,mouse,keyboard,screencap,permission_required,display_*,option,adb} ]  (必填)
resource: [ {name,label,path:[...],controller:[...],option:[...]} ]  (必填)
task:     [ {name,label,entry,default_check,description,doc,group,resource,controller,option,pipeline_override,repeatable,repeat_count} ]
option:   { "选项名": {type, controller, resource, label, default_case, cases, inputs, pipeline_override} }
global_option: [ "选项名", ... ]   # 参与所有任务 override
agent:    Agent | [Agent]          # MaaFramework agent 配置
preset:   [ Preset ]               # 预置 任务+选项 组合
import:   [ "相对路径片段文件" ]    # 拆分 interface.json
```

**option 协议要点**（详细见已装 `pipeline-option/references/protocol.md`）：
- `type`：`select`(单选)/`checkbox`(多选)/`input`(文本)/`switch`(Yes/No)。
- `cases[].pipeline_override`：选项激活时覆盖 pipeline（深度合并，后者覆盖前者）。
- `controller`/`resource`：限制选项仅对特定控制器/资源可见。
- `input`：`inputs[].verify` 正则校验，`{name}` 占位符注入 `pipeline_override`。
- `switch` 仅支持 `Yes`/`No`（大小写敏感）。
- **必须** `task.option: ["xxx"]` 注册，UI 才显示。

**task 关联**：`entry` 指向 pipeline 中的入口节点名（全局唯一）。

---

## 9. 调试

### 9.1 config/maa_option.json（MaaPiCli/工具自动生成于同目录）

```jsonc
{
  "logging": true,            // 生成 debug/maa.log
  "save_draw": true,          // 保存识别可视化图 → debug/vision/{节点}{识别ID}{时间戳}.jpg
  "stdout_level": 7,          // 0 关全部 / 2 Error(默认) / 7 全部
  "save_on_error": true,      // 任务失败存当前截图
  "recording": false,         // 存录像，可用 DbgController 复现
  "show_hit_draw": false      // 每次识别成功弹窗
}
```
开启 `save_draw` 后，draw 图在原图上标出 ROI、命中位置、匹配分数（模板匹配右侧显示模板图+分数）。

### 9.2 工具链

- **MaaPipelineEditor**：零代码可视化拖拽节点、导入导出 JSON、连后截图裁剪。
- **MaaDebugger**：官方调试器。
- **MaaLogAnalyzer**：导入 `debug/maa.log`，节点级可视化执行流，高亮报错/超时节点、命中计数。
- **手动看日志**：`debug/maa.log` 搜 `[ERR]`（崩溃）、`reco hit`（成功识别，查意外循环）。

### 9.3 识别失败诊断（本项目最高频问题）

现象「能截图、不点击」= 控制器/输入通道正常，识别全失败。定位：
1. 把疑似节点的 `roi` 临时改全屏（`[0,0,500,900]`）跑一下，若开始点击 → 确认是**坐标/分辨率不匹配**（本项目 base 是手游坐标，PC 500×900 必须重标定）。
2. 查 OCR 模型：`assets/MaaCommonAssets` 的 `.onnx` 是否齐全，否则 OCR 节点集体失败 → `git submodule update --init`。
3. 看 `debug/maa.log` 搜该节点 `recognition failed` / `node completed but not matched`。
4. 画面未稳定就截图：`post_wait_freezes: 300~1000`（点击开面板/滑动切屏后加；比 `post_delay` 智能，等画面稳定）。

---

## 10. 最佳实践清单

- 模板图：基于**无损原图缩放到 720p 后再裁剪**，避免缩放/编码导致识别异常（用 MaaPipelineEditor/MFAToolsPlus 截）。
- ROI：`expand` 甜区 20–30；`expected` 写完整中文并配 `recognition: OCR`。
- 可滚动 UI：共享大 ROI + 父级 orchestrator / `Scroll` 动作；**绝不在 Click 的 next 里放滑动**。
- 跨页面流程：`next` + `[JumpBack]` + 锚点；别用 Python 重写状态机（失去可视化）。
- 同名顶层 key 跨文件必冲突 → 用 `check_resource.py` 验证。
- option 必须在 `task.option` 注册；`switch` 用 `Yes`/`No`。
- 多开（本项目 5 开）：每个窗口一个 `Win32Controller(hwnd=...)` 绑一个 `Resource(base+user)`+`Tasker`；`user/` 适配层对全部实例共享复用（同分辨率同布局只需标定一次）。`seize` 注入式输入互不抢前台。
- Win32 连接：客户端若管理员运行，MFAAvalonia/MaaPiCli 也需**管理员身份运行**（否则输入被 UAC 拦截）。
- 优先「JSON + 自定义扩展」而非全代码，保留可视化/调试生态。

---

## 11. 本项目（Maa_MHXY_SK）落地提示

- **已实现**：Win32 控制器（interface.json）+ 多开轮转引擎（`agent/multi_instance/rotation.py`）+ 窗口适配层（`agent/win32/adapter.py`）+ 标定工具（`agent/calibrator/`，控制台「标定工具」按钮 / `calibrate.bat`）+ 三重急停 + 组队握手 + 拟人化输入 + 演练模式。
- **Phase 2 缺口（核心待办）**：`base/pipeline/*.json` 仍是手游 16:9 坐标/模板，PC 500×900 需重标定进 `user/` 覆盖层。逐个任务在 PC 客户端重截模板、改 ROI（用 `pipeline-generate` 的 `generate_node.py` 带 `--screen-width 500 --screen-height 900`，产物落 `user/pipeline/`）。
- **已装辅助技能**：`skills/KhazixW2/{pipeline-generate,pipeline-guide,pipeline-option}`。
- **macOS 限制**：Win32 控制器为 Windows 独占；mac 只能跑 ADB/PlayCover 手游路径，时空版 PC 自动化必须在 Windows。
