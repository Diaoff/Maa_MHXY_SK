# Pipeline 执行模型深解

> 对应 maafw.com/docs/3.1-PipelineProtocol 与 deepwiki MaaFramework/3.x。

## 1. 节点 = 状态机的一步

每个节点（JSON 顶层 key）描述一次「识别 + 动作 + 后继」：
- `recognition`：本轮识别什么（在 `roi` 内）。
- `action`：识别命中后做什么。
- `next`：action 成功后要去的下一批候选节点。
- `on_error`：`next` 超时 或 本节点 action 失败 时去哪。

## 2. 主循环（一帧）

```
while (未命中 且 未超时):
    for node in current.next (顺序):
        识别 node
        if 命中: 立即中断后续探测; break
    if 命中: break
    sleep_until(rate_limit)
```

等价 v5.5 语义：`while(!hit && !timeout) { foreach(next); sleep_until(rate_limit); }`

## 3. 流转规则

| 情况 | 去向 |
|---|---|
| next 中某节点命中 且 action 成功 | 该节点的 `next` |
| next 中某节点命中 但 action 失败 | 该节点的 `on_error` |
| 本轮 next 全部未命中 且 超时 | 当前节点的 `on_error` |
| 当前节点 next 为空 | 终止（有 `[JumpBack]` 先回跳） |
| 外部 `post_stop` / `Stop` 动作 | 立即终止 |

- `next` 顺序识别，**命中即停**（短路），后面的兄弟节点不再识别。
- 相同任务去重：`next:["A","B","A","A"]` → 实际 `["A","B"]`（多次出现只认首次）。
- `JustReturn`(DirectHit 的等价：不识别直接 action) 型节点**不允许**出现在非末位（会干扰去重/识别）。

## 4. 节点生命周期（含等待）

```
pre_wait_freezes → pre_delay → action
  → [ repeat_wait_freezes → repeat_delay → action ] × (repeat-1)
  → post_wait_freezes → post_delay
  → 截图 → 识别 next
```

- `pre_delay`/`post_delay`：固定毫秒延迟（不管画面状态）。
- `*_wait_freezes`：等画面**视觉稳定**指定毫秒数再继续（阈值 `threshold` 默认 0.95，方法 5）。用于「点击开面板/滑动切屏」后画面还在动画时，避免 next 误识别过渡帧。
  - 经验值：点击开面板 `post_wait_freezes: 300~500`；滑动切屏 `500~1000`；战斗结算出现 `post_wait_freezes` 加到检测战斗结束的节点。

## 5. 控制流进阶

| 机制 | 写法 | 用途 |
|---|---|---|
| 分支 | `"next": ["A","B","C"]` | 顺序探测，命中第一个分支 |
| 子任务 | `"sub": ["S1","S2"]` | 当前节点完成后顺序跑子任务（可嵌套，勿写死循环）；`subErrorIgnored` 控制失败是否忽略 |
| 回跳 | `"next": ["[JumpBack]"]` 或 NodeAttr `{ "jump_back": true }` | 回跳到最近锚点（替代旧 `is_sub`/`interrupt`，v5.1+） |
| 锚点 | `"anchor": "myAnchor"` | 标记回跳目标；`roi`/`target` 可引用 `"[Anchor]myAnchor"`（v5.7 起支持对象格式指定目标节点/清除） |
| 计数上限 | `"maxTimes": 10, "exceededNext": ["End"]` | 达上限走 exceededNext |
| 命中上限 | `"max_hit": 3` | 节点最多命中次数 |
| 重复动作 | `"repeat": 3, "repeat_delay": 500, "repeat_wait_freezes": 200` | 同一动作连发 |
| 速率限制 | `"rate_limit": 1000` | 每轮识别最少消耗 ms（不足则 sleep） |
| 超时 | `"timeout": 20000`（默认），`-1` 永不超时 | 调的是**当前节点 next 的识别超时**；要改某节点识别等待，改的是**上一节点**的 timeout |

## 6. 特殊任务名

- `任务名@后缀`：特殊任务，字段默认值不同（如某些 `@` 型任务）；可用 `baseTask` 继承另一任务参数（未显式定义的字段直接沿用 baseTask）。
- `虚拟任务#`：`#` 后接 `self`/`back`/`next`/`sub`/`on_error_next`/`exceeded_next`/`reduce_other_times`。
  - `A#self` == `A`；`A@B#back` == `A@B`；`#next` 引用某任务 next 字段；单独 `#self`/`#back`/`#next` 直接跳过。

## 7. 节点属性 NodeAttr（v5.1+）

`next`/`on_error` 元素可是带属性的对象，与字符串混用：
```jsonc
"next": [
  "普通节点",
  { "name": "限时节点", "timeout": 5000, "rate_limit": 500 }
]
```

## 8. 版本变迁要点（写老项目时注意）

- v5.0：`attach` 字段；`TouchDown/Move/Up`、`KeyDown/Up`；`contact`/`pressure`；`target` 支持 `[x,y]`。
- v5.1：`anchor`/`max_hit`；`Scroll` 动作；节点属性（`jump_back`/`anchor`）；`is_sub`/`interrupt` **废弃**（用 `[JumpBack]` 替代）。
- v5.3：`repeat`/`repeat_delay`/`repeat_wait_freezes`；`And`/`Or`；`Shell`；TemplateMatch method `10001`；`default_pipeline.json` 默认属性。
- v5.5：`timeout: -1` 无限；`Scroll` 支持 `target`/`target_offset`。
- v5.6：`roi`/`target` 支持负值坐标与尺寸。
- v5.7：`anchor` 对象格式。
- v5.8：OCR `color_filter`；`Shell` timeout 改名 `shell_timeout`；新增 `Screencap` 动作。
- v5.9：`roi`/`target` 字符串形式支持 `[Anchor]锚点名` 引用。

## 9. 识别/动作的对象形式（v2）

字符串形式（旧）：`"recognition": "OCR"`、`"action": "Click"`。
对象形式（推荐，便于带参数）：
```jsonc
"recognition": { "type": "OCR", "param": { "expected": ["福利"], "roi": [0,0,500,900] } }
"action": { "type": "Click", "param": { "target": true, "target_offset": [0,0,0,0] } }
```
字段完整速查见 `../pipeline-guide/field_reference.md`。
