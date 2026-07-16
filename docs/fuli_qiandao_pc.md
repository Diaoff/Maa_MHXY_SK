# 福利签到（fuli_qiandao）PC 版迁移说明

覆盖层文件：`assets/resource/NeteasePc/pipeline/fuli_qiandao.json`
（节点名与 base 同名 → 自动覆盖 base 版；base 其余节点/选项接线不变）

## 已完成的改造（零成本、无需截图即可跑的部分）
- 所有 `roi` 改为全屏 `[0,0,500,900]`，绕开手游坐标全错问题。
- 文字类节点保留 OCR，点击落在识别文字中心：
  - `fuli_qiandao-ocr`：OCR「福利」→ 点击福利图标（去掉了手游的 ClickKey 热键，PC 用点击更稳）
  - `dakaiguaguale`：OCR「打开刮刮乐」→ 点击
  - `click_fuli_leiji{1,2,3}_lingqu`：OCR「领取」→ 点击（原为写死坐标 `target:[800,564,...]`，已重构）
- 节点名 / `next` 链路完全保留，与 base 其它任务（如 `panduan_zhujiemian`）的接线不受影响。

## ⚠️ 必须在 Windows 实机补的 PC 模板图
把下面 3 张图在**时空版 PC 客户端（500×900 竖屏）**实截，存到
`assets/resource/NeteasePc/image/qiandao/`（文件名与 base 保持一致，直接覆盖同名文件）：

| 文件名 | 内容 | base 原图 |
|---|---|---|
| `leiji2.png` | 第 1 个「累计」奖励图标 | base/image/qiandao/leiji2.png（手游图，需替换） |
| `leiji5.png` | 第 2 个「累计」奖励图标 | base/image/qiandao/leiji5.png |
| `leiji7.png` | 第 3 个「累计」奖励图标 | base/image/qiandao/leiji7.png |

> 这三个节点用 `TemplateMatch` + 全屏 roi 找图标；没放 PC 图前会回退到 base 的手游图，PC 下匹配不到 → 节点不命中。

## ⚠️ 必须在 Windows 验证 / 可能要改的部分
1. **滑动轮播（qiandaohuadong 1-6）**
   - 当前给的是占位坐标（水平滑动，y≈430-460，x 70→430）。
   - **先看 PC 上 3 个「累计」图标是不是一次全可见**：若是，直接删掉 `qiandaohuadong`~`qiandaohuadong6` 这 6 个节点，把 `dakaiguaguale` 的 `next` 改成 `["click_fuli_leiji1"]` 即可，不用滑。
   - 若需滑动：确认方向（竖屏可能是横向轮播）和 y 位置，改 begin/end。
2. **「领取」OCR 歧义**
   - `click_fuli_leiji{1,2,3}_lingqu` 用 OCR「领取」全屏找。若 福利界面同时存在多个「领取」文字导致点错，改为 TemplateMatch：
     截一张 PC 的「领取」按钮图存 `NeteasePc/image/qiandao/lingqu.png`，把对应节点改成
     `{"recognition":"TemplateMatch","template":"qiandao/lingqu.png","roi":[0,0,500,900],"action":"Click"}`。
3. **「福利」入口歧义**
   - 若主界面有多个「福利」文字，OCR 可能点错。可改用模板：截 PC 福利图标存 `NeteasePc/image/qiandao/fuli.png`，节点改 TemplateMatch。

## 运行前提
- 必须在 **Windows** 实机跑（`seize` 后台注入 + Win32 控制器，mac 跑不了）。
- v1 走串行架构（`config/multi_instance.json` 默认 `strategy:"sequential"` + `activate_before_run:true`）。
- 资源选「时空版-官方重标定」（interface.json 已绑定 base + NeteasePc）。
- 验证顺序建议：先把 3 张 leiji PC 图放进去，跑一次看 OCR 部分（福利/刮刮乐/领取）能否命中、图标能否点中；滑动部分按上面第 1 条判断。
