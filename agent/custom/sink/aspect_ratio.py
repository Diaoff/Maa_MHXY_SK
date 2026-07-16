"""
分辨率检查器

在任务开始时检查模拟器分辨率是否为 16:9（仅横屏），如果不是则停止任务并输出警告。
"""

from maa.agent.agent_server import AgentServer
from maa.tasker import Tasker, TaskerEventSink
from maa.event_sink import NotificationType

from utils.logger import logger

# 时空版为竖屏 PC 客户端：同时支持 横屏 16:9 与 竖屏 9:16
# （从 Maa_MHXY_MG 横屏手游模拟器 fork 而来，原仅允许 16:9 横屏）
TARGET_RATIOS = (16.0 / 9.0, 9.0 / 16.0)
# 容差范围（±2%）
TOLERANCE = 0.02


def is_supported_aspect_ratio(width: int, height: int) -> bool:
    """
    检查给定尺寸是否为受支持的宽高比（横屏 16:9 或 竖屏 9:16）。
    方向无关：竖屏 9:16（宽 < 高）也视为合法。
    """
    if width <= 0 or height <= 0:
        return False

    ratio = width / float(height)
    # 实际比例可能是某个目标比例本身（横屏）或其倒数（竖屏）
    for target in TARGET_RATIOS:
        if abs(ratio - target) <= target * TOLERANCE:
            return True
        inv = 1.0 / target
        if abs(ratio - inv) <= inv * TOLERANCE:
            return True
    return False


def calculate_aspect_ratio(width: int, height: int) -> float:
    """
    计算宽高比，返回宽度/高度（不进行方向归一化）
    用于日志输出实际比例
    """
    return width / float(height)


@AgentServer.tasker_sink()
class AspectRatioChecker(TaskerEventSink):
    """
    分辨率检查器
    在任务开始时检查设备分辨率是否为 16:9（横屏）
    """

    def __init__(self):
        self._checked = False

    def on_tasker_task(
        self,
        tasker: Tasker,
        noti_type: NotificationType,
        detail: TaskerEventSink.TaskerTaskDetail,
    ):
        # 只在任务开始时检查
        if noti_type != NotificationType.Starting:
            return

        # 忽略停止任务事件
        if detail.entry == "MaaTaskerPostStop":
            logger.debug("收到 PostStop 事件，跳过分辨率检查")
            return

        logger.debug(
            f"任务开始前检查分辨率 - task_id: {detail.task_id}, entry: {detail.entry}"
        )

        # 获取控制器
        controller = tasker.controller
        if controller is None:
            logger.error("无法获取控制器")
            return

        # 获取缓存的图像
        try:
            img = controller.cached_image
            if img is None:
                # 如果没有缓存图像，尝试截图
                img = controller.post_screencap().wait().get()
        except Exception as e:
            logger.error(f"无法获取截图: {e}")
            return

        if img is None:
            logger.error("无法获取截图")
            return

        # 获取图像尺寸
        height, width = img.shape[:2]

        logger.debug(f"截图尺寸: {width} x {height}")

        # 检查宽高比（横屏 16:9 或 竖屏 9:16 均可）
        if not is_supported_aspect_ratio(width, height):
            actual_ratio = calculate_aspect_ratio(width, height)
            logger.error(
                f"🚨 分辨率比例不匹配！任务已停止。"
                f"当前: {width}x{height} (比例: {actual_ratio:.4f})，"
                f"仅支持 16:9 横屏 或 9:16 竖屏，请调整分辨率。"
            )
            # 停止任务
            tasker.post_stop()
        else:
            orient = "竖屏 9:16" if width < height else "横屏 16:9"
            logger.debug(f"分辨率检查通过: {width}x{height} ({orient})")