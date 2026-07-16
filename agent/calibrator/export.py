# -*- coding: utf-8 -*-
"""
把标定结果落盘为 MAA 覆盖资源（pipeline override JSON + template PNG）。

覆盖语义（与 tools/gen_user_override.py 对齐）：MAA 按「节点名」整节点覆盖 base 层，
因此 override 文件里的节点必须是【完整定义】。本模块写入时：
  - 优先以已存在的 user override 节点为基底（保留已标定过的其它字段）；
  - 否则以 base/pipeline/<task>.json 中的完整节点为基底；
  - 再合并本次标定的字段，整体写回 user/pipeline/<task>.override.json。

模板图写入 user/image/<task>/<name>.png，pipeline 中以 "<task>/<name>.png" 引用
（与 base/image 下 "shimen/shimenwancheng2.png" 的引用方式一致）。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE_PIPELINE_DIR = os.path.join(ROOT, "assets", "resource", "base", "pipeline")
USER_PIPELINE_DIR = os.path.join(ROOT, "assets", "resource", "user", "pipeline")
USER_IMAGE_DIR = os.path.join(ROOT, "assets", "resource", "user", "image")


def _read_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_tasks():
    """返回 base/pipeline 下所有任务名（去 .json 后缀）。"""
    if not os.path.isdir(BASE_PIPELINE_DIR):
        return []
    return sorted(os.path.splitext(n)[0] for n in os.listdir(BASE_PIPELINE_DIR) if n.endswith(".json"))


def list_nodes(task):
    """返回某任务流水线里的所有节点名。"""
    data = _read_json(os.path.join(BASE_PIPELINE_DIR, f"{task}.json"))
    return sorted(data.keys())


def node_base(task, node):
    """取节点当前生效的完整定义：优先 user override，其次 base。找不到返回 {}。"""
    ov = _read_json(os.path.join(USER_PIPELINE_DIR, f"{task}.override.json"))
    if node in ov:
        return ov[node]
    base = _read_json(os.path.join(BASE_PIPELINE_DIR, f"{task}.json"))
    return base.get(node, {})


def save_template(pil_img, task, name):
    """把截取的模板区域存为 user/image/<task>/<name>.png，返回 pipeline 引用路径 <task>/<name>.png。"""
    name = (name or "tpl").strip()
    if not name.lower().endswith(".png"):
        name += ".png"
    d = os.path.join(USER_IMAGE_DIR, task)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    pil_img.save(path, "PNG")
    return f"{task}/{name}"


def apply_calibration(task, node, fields, template_img=None, template_name=None):
    """把标定字段合并进 user override 文件的节点（整节点覆盖语义）。返回写出路径。

    fields: 本次标定的 pipeline 字段，如 {"roi":[x,y,w,h]} / {"target":[...]} / {"begin":..,"end":..}
    template_img / template_name: 模板图模式时提供，裁图存盘并写入 "template" 字段。
    """
    ov_path = os.path.join(USER_PIPELINE_DIR, f"{task}.override.json")
    ov = _read_json(ov_path)
    base = node_base(task, node)
    merged = dict(base)
    merged.update({k: v for k, v in fields.items() if v is not None})

    if template_img is not None and template_name:
        rel = save_template(template_img, task, template_name)
        merged["template"] = rel
        # 模板节点默认用 TemplateMatch 识别（除非已经是带缓存的模板识别）
        if merged.get("recognition") not in ("TemplateMatch", "TemplateMatchWithCache"):
            merged["recognition"] = "TemplateMatch"

    ov[node] = merged
    os.makedirs(USER_PIPELINE_DIR, exist_ok=True)
    with open(ov_path, "w", encoding="utf-8") as f:
        json.dump(ov, f, indent=4, ensure_ascii=False)
    return ov_path
