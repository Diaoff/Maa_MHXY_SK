# 自动发现并导入本目录下所有自定义 action 模块，确保 @AgentServer.custom_action 注册生效。
# 新增 action 只需在本目录放一个文件，无需手动维护导入列表。
import importlib
import pkgutil
import os

_this_dir = os.path.dirname(os.path.abspath(__file__))
for _m in pkgutil.iter_modules([_this_dir]):
    if _m.name in ("__init__",):
        continue
    try:
        importlib.import_module(f"{__name__}.{_m.name}")
    except Exception:
        # 单个 action 导入失败不应阻断其它 action 注册
        pass
