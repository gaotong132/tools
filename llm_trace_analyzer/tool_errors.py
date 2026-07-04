"""工具执行失败检测模块

通过匹配 tool result 消息的内容模式来判断工具是否执行失败。

设计说明
--------
- 检测基于内容模式匹配（启发式），并非所有失败都能被准确识别
- 新增错误模式只需在 ERROR_DETECTORS 列表中追加 ErrorDetector 即可
- 每条检测器有唯一 category，便于后续分类统计

当前支持的错误类型:
- framework_error: 框架级错误，格式 "<type> operation execution error, execution: <op>, reason: ..."
  适用于所有工具（read_file、bash、edit_file 等）
- fetch_error: fetch_webpage 工具的网络错误，格式 "[ERROR]: fetch failed (...)"

可扩展方向（示例）:
- web_search 返回空结果或异常状态
- web_fetch 超时或 HTTP 错误码
- bash 非零退出码
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class ErrorDetector:
    """工具错误检测器

    Attributes:
        category: 错误分类标识（如 'framework_error', 'fetch_error'）
        pattern: 编译后的正则表达式，用于匹配 tool result 内容
    """

    category: str
    pattern: re.Pattern

    def match(self, content: str) -> bool:
        return bool(self.pattern.search(content))


# ── 错误检测器注册表 ──────────────────────────────────────────────
# 新增错误模式只需在此列表追加 ErrorDetector 实例。
# 匹配按顺序进行，第一个命中的检测器生效。
# ──────────────────────────────────────────────────────────────────
ERROR_DETECTORS: List[ErrorDetector] = [
    # 框架级错误: "<type> operation execution error, execution: <op>, reason: ..."
    # 覆盖: read_file (Access denied / File not found), bash (timeout), edit_file 等
    ErrorDetector("framework_error", re.compile(r"operation execution error")),
    # fetch_webpage 网络错误: "[ERROR]: fetch failed (...)"
    ErrorDetector("fetch_error", re.compile(r"\[ERROR\]:")),
]


def detect_tool_failure(content: str) -> Tuple[bool, Optional[str]]:
    """检测工具执行结果是否表示失败。

    Args:
        content: tool result 消息的文本内容

    Returns:
        (is_failure, category): 是否失败及错误分类。
        category 为 None 时表示未检测到失败。
    """
    if not content:
        return False, None
    for detector in ERROR_DETECTORS:
        if detector.match(content):
            return True, detector.category
    return False, None
