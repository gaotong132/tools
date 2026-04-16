"""JSON加载模块"""

import json
from pathlib import Path
from typing import Any, Dict, List


class JSONLoader:
    """JSON文件加载器"""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def load(self) -> List[Dict[str, Any]]:
        """加载JSON文件，支持JSON数组和JSONL两种格式"""
        try:
            with open(self.file_path, encoding="utf-8") as f:
                first_char = f.read(1)
                if not first_char:
                    return []

                if first_char == "[":
                    f.seek(0)
                    return self._load_json_array(f)
                else:
                    return self._load_jsonl(f, first_char)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"文件不存在: {self.file_path}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON格式错误: {e}") from e

    def _load_json_array(self, f) -> List[Dict[str, Any]]:
        """加载JSON数组格式（旧格式）"""
        data: List[Dict[str, Any]] = json.load(f)
        return data

    def _load_jsonl(self, f, first_char: str) -> List[Dict[str, Any]]:
        """加载JSONL格式（新格式：每行一个JSON对象）"""
        data: List[Dict[str, Any]] = []
        first_line = first_char + f.readline()
        first_line = first_line.strip()
        if first_line:
            try:
                data.append(json.loads(first_line))
            except json.JSONDecodeError:
                pass

        for line in f:
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return data
