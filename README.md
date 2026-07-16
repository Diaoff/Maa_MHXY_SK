<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img alt="LOGO" src="./docs/img/logo.png" width="220" />
</p>

<div align="center">

# MAA_MHXY_SK

![GitHub stars](https://img.shields.io/github/stars/Diaoff/Maa_MHXY_SK?style=flat-square)
![GitHub release](https://img.shields.io/github/v/release/Diaoff/Maa_MHXY_SK?style=flat-square)
![License](https://img.shields.io/github/license/Diaoff/Maa_MHXY_SK?style=flat-square)

基于 MaaFramework 的"梦手"自动化助手，结合图像识别与模拟控制，帮助完成高频日常与部分周常任务。

</div>

## 目录
- [项目简介](#项目简介)
- [项目结构](#项目结构)
- [功能列表](#功能列表)
- [教程文档](#教程文档)
- [鸣谢](#鸣谢)
- [免责声明](#免责声明)
- [沟通交流](#沟通交流)
- [赞助](#赞助)

## 项目简介

`MAA_MHXY_SK` 是从 [Maa_MHXY_MG](https://github.com/gitlihang/Maa_MHXY_MG) Fork 而来，针对**梦幻西游时空版**进行适配迁移的自动化项目。

与原版 Maa_MHXY_MG 的主要区别：

| 项目 | 目标版本 | 控制方式 |
|------|----------|----------|
| Maa_MHXY_MG | 梦幻西游（手游） | ADB 控制（模拟器） |
| **MAA_MHXY_SK** | **梦幻西游时空版** | **Win32 控制（PC 客户端）** |

本项目使用 Win32 控制器直接操作 PC 客户端窗口，不依赖 ADB 模拟器，适用于时空版玩家。

> 重点说明：由于 69 级以下账号操作逻辑不同，部分功能对低等级小号的适配仍存在限制。

## 项目结构

```
Maa_MHXY_SK/
├── assets/                          # 资源文件（MaaFramework Bundle）
│   ├── interface.json               # ProjectInterface 配置（通用 UI 入口）
│   ├── logo.png                     # 项目 Logo
│   ├── MaaCommonAssets/             # Git 子模块：OCR 模型等通用资源
│   └── resource/                    # MaaFramework 资源包
│       ├── base/                    # 基础资源
│       │   ├── pipeline/            #   基础 Pipeline JSON
│       │   ├── image/               #   模板匹配图片
│       │   ├── model/               #   OCR 模型文件
│       │   └── default_pipeline.json
│       ├── tasks/                   # 任务 Pipeline
│       │   ├── preset/              #   预设任务
│       │   └── tuichuduiwu.json     #   退出队伍任务
│       ├── 9game/pipeline/          # 九游服务器专用 Pipeline
│       ├── NeteaseServer/pipeline/  # 网易服务器专用 Pipeline
│       └── mac/pipeline/            # Mac 平台专用 Pipeline
│
├── agent/                           # Python Agent 代码（自定义识别/动作）
│   ├── main.py                      # Agent 入口
│   ├── custom/                      # 自定义扩展
│   │   ├── recognition/             #   自定义识别器
│   │   ├── action/                  #   自定义动作
│   │   └── sink/                    #   事件监听器
│   ├── calibrator/                  # 动态标定工具
│   │   ├── gui.py                   #   标定 GUI
│   │   ├── capture.py               #   截图捕获
│   │   └── export.py                #   导出标定数据
│   ├── gui/                         # 控制台 GUI
│   ├── safety/                      # 安全机制
│   │   └── emergency_stop.py        #   紧急停止
│   ├── multi_instance/              # 多实例支持
│   │   ├── rotation.py              #   轮换调度
│   │   ├── teaming.py               #   组队逻辑
│   │   └── leader_history.py        #   队长历史
│   ├── win32/                       # Win32 适配器
│   │   └── adapter.py
│   ├── data/                        # 运行时数据
│   │   └── mnma_storage.json
│   └── utils/                       # 工具函数
│       ├── logger.py
│       ├── utils.py
│       └── humanize.py
│
├── config/                          # 配置文件
│   ├── controller_config.json       # 控制器配置
│   └── multi_instance.json          # 多实例配置
│
├── tools/                           # 开发与辅助工具
│   ├── gui.py                       # GUI 启动器
│   ├── calibrate.py                 # 标定工具
│   ├── configure.py                 # 配置工具
│   ├── install.py                   # 安装脚本
│   ├── install_mxu.py               # MXU 安装
│   ├── emergency_stop.py            # 紧急停止脚本
│   ├── run_multi_instance.py        # 多实例运行
│   ├── gen_user_override.py         # 生成用户覆盖配置
│   ├── team.py                      # 组队工具
│   ├── leader_id.py                 # 队长 ID 工具
│   ├── win32_probe.py               # Win32 窗口探测
│   └── ci/                          # CI 脚本
│       ├── check_resource.py
│       ├── download_deps.py
│       ├── setup_embed_python.py
│       └── setup_pip.py
│
├── docs/                            # 文档
│   ├── 窗口运行教程.md
│   ├── CMD运行教程.md
│   ├── mac窗口运行教程.md
│   ├── 功能列表.md
│   ├── 二次开发.md
│   └── img/                         # 文档图片
│
├── runtime/                         # 运行时数据
│   ├── team/                        # 组队运行数据
│   └── team_test/                   # 组队测试数据
│
├── skills/                          # Agent 开发技能
│   ├── maafw-dev/                   # MaaFramework 开发技能
│   └── KhazixW2/                    # 特定角色技能
│
├── start.bat                        # 启动脚本（Windows）
├── gui.bat                          # GUI 启动脚本（Windows）
├── multi.bat                        # 多实例启动脚本（Windows）
├── calibrate.bat                    # 标定启动脚本（Windows）
├── requirements.txt                 # Python 依赖
├── LICENSE                          # 许可证
└── README.md                        # 本文件
```

### 核心目录说明

| 目录 | 说明 |
|------|------|
| `assets/resource/` | MaaFramework 资源包，包含 Pipeline JSON、模板图片、OCR 模型 |
| `assets/interface.json` | ProjectInterface 配置，定义任务列表和控制器选项 |
| `agent/custom/` | 自定义识别器和动作，实现复杂业务逻辑 |
| `agent/calibrator/` | 动态标定工具，用于校准识别区域坐标 |
| `config/` | 运行时配置，包括控制器参数和多实例设置 |
| `tools/` | 开发辅助工具，包括安装、配置、CI 脚本 |

### Pipeline 资源组织

Pipeline 按服务器类型和功能模块组织：

- `base/pipeline/` - 基础通用 Pipeline
- `tasks/` - 独立任务 Pipeline（可单独调用）
- `9game/pipeline/` - 九游服务器特有逻辑
- `NeteaseServer/pipeline/` - 网易服务器特有逻辑
- `mac/pipeline/` - Mac 平台适配

### Agent 扩展机制

本项目使用 MaaFramework 的 Agent 系统（方案二：JSON + Agent 扩展），在 `agent/custom/` 中实现：

- **自定义识别** (`recognition/`)：扩展 OCR、模板匹配等识别能力
- **自定义动作** (`action/`)：实现复杂点击、滑动、多步骤操作
- **事件监听** (`sink/`)：监控任务执行状态，记录日志

## 功能列表

已完成的代表性功能包括：
- 签到、师门、秘境等日常任务
- 周长任务中的多项内容

完整功能明细请查看：[功能列表](./docs/功能列表.md)

## 教程文档

- [窗口运行教程](./docs/窗口运行教程.md)
- [CMD 运行教程](./docs/CMD运行教程.md)
- [Mac 窗口运行教程](./docs/mac窗口运行教程.md)
- [二次开发指南](./docs/二次开发.md)
- [功能列表](./docs/功能列表.md)

## 鸣谢

本项目由 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 提供强力支持，感谢所有参与和支持项目开发的贡献者！

- [Maa_MHXY_MG](https://github.com/gitlihang/Maa_MHXY_MG) - 原版项目（梦幻西游手游）
- [MaaFramework](https://github.com/MaaXYZ/MaaFramework) - 自动化框架
- [MFAAvalonia](https://github.com/SweetSmellFox/MFAAvalonia) - 通用 GUI
- [MXU](https://github.com/MistEO/MXU) - 通用 GUI

## 免责声明

本项目仅供学习与交流参考。
