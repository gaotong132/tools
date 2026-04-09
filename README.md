# Python Tools Collection

Python工具集合项目

## 项目结构

```
tools/
├── agent_history_analyzer/    # Agent历史分析工具包
│   ├── __init__.py            # 包入口
│   ├── main.py                # CLI入口
│   ├── analyzer.py            # 数据分析器
│   ├── reporter.py            # HTML报告生成器
│   ├── templates.py           # HTML模板
│   ├── constants.py           # 常量定义
│   └── models.py              # 数据类定义
├── util/                      # 通用工具模块
│   ├── __init__.py
│   └── loader.py              # JSON加载器
├── venv/                      # 虚拟环境
├── pyproject.toml             # 项目配置
└── README.md                  # 项目说明
```

## 快速开始

```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 激活虚拟环境
# Windows PowerShell
.\venv\Scripts\Activate.ps1

# Windows CMD
.\venv\Scripts\activate.bat

# Linux/macOS
source venv/bin/activate

# 3. 安装项目
pip install -e .

# 4. 运行工具
agent-history-analyzer <json_file_path>
```

## Agent History Analyzer

分析Agent会话历史并生成可视化HTML报告。

**功能特性：**
- 解析JSON格式的Agent会话历史文件
- 分析对话流程、工具调用、上下文压缩等事件
- 计算各阶段耗时和统计信息
- 生成可视化HTML报告

**使用方法：**

```bash
# 基本用法
agent-history-analyzer <json_file_path>

# 指定输出文件
agent-history-analyzer <json_file_path> --output my_report.html

# 显示详细信息
agent-history-analyzer <json_file_path> --verbose

# 或作为模块运行
python -m agent_history_analyzer <json_file_path>
```

**报告内容：**
- **统计概览**：总对话轮数、用户消息数、助手回复数、工具调用数、上下文压缩次数、总耗时
- **完整对话历史**：可折叠的对话时间线
  - 用户输入
  - 推理过程
  - 工具调用（参数和结果）
  - 上下文压缩事件
  - 助手回复
- **耗时排行榜**：Top 20 耗时操作

**作为库使用：**

```python
from agent_history_analyzer import AgentHistoryAnalyzer

analyzer = AgentHistoryAnalyzer("history.json")
analyzer.run(output_path="report.html", verbose=True)
```

## 添加新工具

在项目根目录创建新的工具包：

```
<tool_name>/
├── __init__.py
├── main.py         # CLI入口
├── ...             # 其他模块
```

更新 `pyproject.toml` 添加入口点：

```toml
[project.scripts]
tool-name = "tool_package.main:main"
```