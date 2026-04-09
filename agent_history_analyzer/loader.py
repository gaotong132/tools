"""JSON加载模块"""

import json
from pathlib import Path
from typing import Any, Dict, List


class JSONLoader:
    """JSON文件加载器"""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def load(self) -> List[Dict[str, Any]]:
        """加载JSON文件"""
        try:
            with open(self.file_path, encoding="utf-8") as f:
                data: List[Dict[str, Any]] = json.load(f)
                return data
        except FileNotFoundError as e:
            raise FileNotFoundError(f"文件不存在: {self.file_path}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON格式错误: {e}") from e
