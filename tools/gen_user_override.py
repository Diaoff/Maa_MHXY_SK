# -*- coding: utf-8 -*-
"""
为某个任务生成「用户标定覆盖层」骨架（阶段0/阶段1 重标定工作流）。

重要约束（MAA 资源覆盖语义）：资源级同名节点是【整节点替换】，不是字段级合并。
因此覆盖层文件必须包含被覆盖节点的【完整定义】；否则该节点会丢失 recognition/action/next 等行为。
本工具复制 base/pipeline/<name>.json 为 user/pipeline/<name>.override.json（完整副本），
用户随后只需把其中的 roi / begin / end / target 坐标改成 PC 分辨率下的实测值即可。

用法：
    python tools/gen_user_override.py fuli_qiandao
    python tools/gen_user_override.py shimen_renwu baotu_renwu   # 可一次多个
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.join(ROOT, "assets", "resource", "base", "pipeline")
USER_DIR = os.path.join(ROOT, "assets", "resource", "user", "pipeline")


def gen_one(name):
    src = os.path.join(BASE_DIR, f"{name}.json")
    if not os.path.exists(src):
        print(f"[skip] 找不到 base 流水线: {src}")
        return False
    dst = os.path.join(USER_DIR, f"{name}.override.json")
    os.makedirs(USER_DIR, exist_ok=True)
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"[ok] 已生成覆盖骨架: {os.path.relpath(dst, ROOT)}")
    print(f"     请将其中的 roi/begin/end/target 坐标改为 PC 分辨率实测值（保留全部字段）。")
    return True


def main():
    names = sys.argv[1:]
    if not names:
        print("用法: python tools/gen_user_override.py <任务名> [任务名...]")
        print("示例: python tools/gen_user_override.py fuli_qiandao")
        return
    for n in names:
        gen_one(n)


if __name__ == "__main__":
    main()
