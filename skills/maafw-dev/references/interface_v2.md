# interface.json V2 协议（完整字段）

> ProjectInterface 协议，让通用 UI（MFAAvalonia）/ MaaPiCli 能加载并运行项目。
> 协议版本 v2.3.0+。JSON5 允许注释（实际运行时 MaaFramework 解析为 JSON）。

## 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `interface_version` | `2` | ✅ | 协议版本，必须为 2 |
| `name` | string | ✅ | 项目内部标识 |
| `label` | string | ❌ | 显示名（默认 name） |
| `title` | string | ❌ | 窗口标题（默认 `{label} {version}`） |
| `version` | string | ❌ | 显示版本 |
| `icon` | string | ❌ | 图标相对路径 |
| `description` | string | ❌ | 项目描述 |
| `url` | string | ❌ | 仓库地址 |
| `contact` | string | ❌ | 联系方式 |
| `license` | string | ❌ | 许可证标识 |
| `mirrorchyan_rid` | string | ❌ | Mirror 酱更新 ID |
| `mirrorchyan_multiplatform` | bool | ❌ | 是否多平台下载 |
| `languages` | dict | ❌ | 语言→翻译文件映射，如 `{"en":"i18n/en.json"}` |
| `controller` | Controller[] | ✅ | 控制器声明 |
| `resource` | Resource[] | ✅ | 资源包声明 |
| `task` | Task[] | ❌ | 可执行任务声明 |
| `option` | dict[str,Option] | ❌ | 选项定义（按名 key） |
| `global_option` | string[] | ❌ | 全局选项（参与所有任务 override） |
| `agent` | Agent \| Agent[] | ❌ | MaaFramework Agent 配置 |
| `preset` | Preset[] | ❌ | 预置 任务+选项 组合 |
| `import` | string[] | ❌ | 相对路径的 interface 片段文件（拆分大文件） |

## Controller

```jsonc
{
  "name": "win32_pc",          // 唯一 ID，作控制器标识
  "label": "时空版PC",          // 显示名，支持 $ 国际化
  "description": "Windows PC 客户端",
  "type": "Win32",             // Adb | Win32 | PlayCover | MacOS | Gamepad
  "class_regex": ".*",         // Win32/Gamepad：窗口类名正则
  "window_regex": "梦幻西游.*", // Win32/Gamepad：窗口标题正则（多语言匹配）
  "screencap": "dxgi_desktopduplication", // Win32 截图后端
  "mouse": "Seize",            // Win32 鼠标后端
  "keyboard": "Seize",         // Win32 键盘后端
  "macos": { "title_regex": "...", "input": "GlobalEvent", "screencap": "..." }, // MacOS 专用
  "playcover": { "uuid": "..." }, // PlayCover 专用
  "adb": {},                   // AdbController 透传额外字段
  "permission_required": true, // Win32 常需管理员运行
  "display_short_side": 720,   // 默认缩放短边；与 display_long_side/display_raw 互斥
  "attach_resource_path": ["extra_pipeline.json"],
  "option": ["server_region"]  // 绑定到本控制器的选项
}
```

- 公共字段：`name`/`label`/`description`/`icon`/`option`。
- `display_short_side`/`display_long_side`/`display_raw` 三者互斥，多设非默认值会校验报错。

## Resource

```jsonc
{
  "name": "时空版-用户标定覆盖",
  "label": "用户标定覆盖",
  "path": ["./resource/base", "./resource/user"], // 靠后覆盖靠前的同名任务/字段
  "controller": ["Win32"],   // 仅对这些控制器的任务可用
  "option": ["server_region"]
}
```

- `path` 数组决定资源加载顺序与覆盖优先级。
- `controller`/`option`：限制资源仅在特定控制器/选项下可见。

## Task

```jsonc
{
  "name": "福利签到",
  "label": "福利签到",
  "entry": "fuli_qiandao",     // 指向 pipeline 入口节点名（全局唯一）
  "default_check": true,
  "description": "自动福利签到",
  "doc": ["步骤1...", "步骤2..."],
  "icon": "icons/qiandao.svg",
  "group": ["daily_tasks"],
  "resource": ["base_resource"],
  "controller": ["win32_pc"],  // 仅这些控制器可跑
  "option": ["关卡选择", "作战次数"],  // 必须注册，否则 UI 不显示
  "pipeline_override": { "NodeA": { "enabled": true } },
  "repeatable": true,
  "repeat_count": 1
}
```

- 校验：task 引用的 resource/controller 必须存在于顶层声明。

## Option（详见 pipeline-option/references/protocol.md）

```jsonc
{
  "关卡类型": {
    "type": "select",                 // select | checkbox | input | switch
    "controller": ["Win32"],          // 限控制器（v2.3.0）
    "resource": ["官服"],              // 限资源（v2.3.0）
    "label": "关卡类型",
    "default_case": "主线",
    "cases": [
      { "name": "主线", "label": "主线关卡",
        "pipeline_override": { "SomeNode": { "expected": ["主线"] } } }
    ],
    "inputs": [ { "name": "章节号", "label": "章节号", "default": "2",
                  "pipeline_type": "string", "verify": "^(\\d+)$", "pattern_msg": "请输入数字" } ],
    "pipeline_override": { "SelectStage": { "expected": ["{章节号}"] } }
  }
}
```

- `switch` 仅支持 `Yes`/`No`（大小写敏感）。
- `cases[].pipeline_override` 深度合并，后者覆盖前者；同名顶层 key 跨文件冲突会被 `check_resource.py` 拒绝。
- `input` 用 `{name}` 占位符注入 `pipeline_override`（识别/动作参数均可）。
- `global_option` 不依赖资源/控制器选择，参与所有任务 override。
