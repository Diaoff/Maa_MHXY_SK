<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img alt="LOGO" src="./docs/img/logo.png" width="220" />
</p>

<div align="center">

# MAA_MHXY_MG

![GitHub stars](https://img.shields.io/github/stars/gitlihang/Maa_MHXY_MG?style=flat-square)
![GitHub release](https://img.shields.io/github/v/release/gitlihang/Maa_MHXY_MG?style=flat-square)
![License](https://img.shields.io/github/license/gitlihang/Maa_MHXY_MG?style=flat-square)

基于 MaaFramework 的《梦幻西游手游》自动化助手，结合图像识别与模拟控制，帮助完成高频日常与部分周常任务。

</div>

## 目录
- [项目简介](#项目简介)
- [核心能力](#核心能力)
- [快速开始](#快速开始)
- [运行方式](#运行方式)
- [功能列表](#功能列表)
- [常见要求](#常见要求)
- [相关文档](#相关文档)
- [鸣谢](#鸣谢)
- [免责声明](#免责声明)
- [赞助与交流](#赞助与交流)

## 项目简介

`MAA_MHXY_MG` 是一个面向《梦幻西游手游》的自动化项目，依托 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 实现界面识别、流程编排与模拟操作。

项目适合已经在 PC 模拟器环境中游玩的用户，用来减少重复点击和日常任务的手动操作成本。

> 重点说明：由于 69 级以下账号操作逻辑不同，部分功能对低等级小号的适配仍存在限制。

## 核心能力

- 支持窗口界面运行，也支持命令行模式运行
- 覆盖签到、师门、秘境、宝图、运镖、抓鬼等高频任务
- 提供 AI 答题等扩展能力
- 基于发布产物即可使用，不必从源码手动搭建完整环境

## 快速开始

### 1. 下载发布版本

前往 [Releases](https://github.com/gitlihang/Maa_MHXY_MG/releases) 下载与你的系统和架构匹配的版本。

### 2. 准备模拟器环境

推荐使用 **MuMu 模拟器**，同时兼容雷电、蓝叠等主流模拟器。

建议参数：

- 分辨率：`1280 x 720`
- DPI：`240`
- 屏幕比例：`16:9`
- 渲染模式：`DirectX`

### 3. 完成系统依赖

Windows 用户通常还需要安装：

- [vc_redist](https://aka.ms/vs/17/release/vc_redist.x64.exe)
- [.NET 10](https://dotnet.microsoft.com/zh-cn/download/dotnet/10.0)

### 4. 启动并先做单任务测试

首次使用建议先单独运行“帮派签到”等简单任务，确认连接与识别链路正常后，再逐步增加任务组合。

## 运行方式

### 窗口运行（推荐）

推荐优先阅读：[窗口运行教程](./docs/窗口运行教程.md)

通常流程是：

1. 下载并解压发布包
2. 在 GUI 中选择触控模式为 **MaaTouch**
3. 连接模拟器
4. 选择任务并启动

### 命令行运行

参考文档：[CMD 运行教程](./docs/CMD运行教程.md)

命令行模式适合已经熟悉 ADB 地址、资源切换和任务编排的用户。

## 功能列表

已完成的代表性功能包括：

- 福利签到
- 帮派签到
- 师门任务
- 秘境任务
- 宝图任务（获得 / 挖取）
- 运镖任务
- 整理背包
- 三界奇缘
- 科举乡试（AI 答题）
- 抓鬼任务
- 家园整理
- 活力打工
- 周长任务中的多项内容

完整功能明细请查看：[功能列表](./docs/功能列表.md)

## 常见要求

- 电脑缩放建议保持 `100%`
- 首次运行期间，不要在初始化尚未完成时提前停止任务
- 如果是多开场景，可以通过创建实例的方式分别管理
- 遇到路径、ADB 或模拟器兼容问题，优先对照教程文档逐项检查

## 相关文档

- [窗口运行教程](./docs/窗口运行教程.md)
- [CMD 运行教程](./docs/CMD运行教程.md)
- [功能列表](./docs/功能列表.md)

## 鸣谢

本项目依赖以下相关项目：

- [MaaFramework](https://github.com/MaaXYZ/MaaFramework)
- [MFAAvalonia](https://github.com/SweetSmellFox/MFAAvalonia)

## 免责声明

本项目仅供学习与交流参考，请在理解风险与平台规则的前提下自行使用。

## 赞助与交流

- 爱发电：<https://afdian.com/a/gitlihang>
- QQ 群：`953819042`
