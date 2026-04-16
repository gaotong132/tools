# Python Tools Collection

Python工具集合项目

## 项目结构

```
tools/
├── agent_history_analyzer/    # Agent历史分析工具包
├── llm_trace_analyzer/        # LLM请求链路分析工具包
├── .venv/                     # 虚拟环境
├── pyproject.toml             # 项目配置
└── README.md                  # 项目说明
```

## 快速开始

```bash
# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活虚拟环境
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows CMD
.\.venv\Scripts\activate.bat

# Linux/macOS
source .venv/bin/activate

# 3. 安装项目
pip install -e .

# 4. 运行工具
ha                                  # 分析Agent历史（自动查找）
ha <json_file> -o report.html       # 分析指定文件
lt                                  # 分析LLM请求链路（自动查找）
lt <log_file> -o trace_report.html  # 分析指定日志
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
# 自动分析最新会话（不带参数时，自动查找 ~/.office-claw/.jiuwenclaw/agent/sessions/ 下最新的 history.json）
ha

# 分析指定文件
ha <json_file_path>

# 指定输出文件
ha <json_file_path> -o my_report.html

# 显示详细信息
ha <json_file_path> -v

# 或作为模块运行
python -m agent_history_analyzer
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

## LLM Trace Analyzer

分析LLM_IO_TRACE日志，重建完整请求/响应链路并生成可视化报告。

**功能特性：**
- 解析 `app.log` 中的 `LLM_IO_TRACE` 日志
- 合并分片请求体（body_part 1/N → N/N）
- 关联请求（messages+tools）与响应（content+tool_calls）
- 支持按 session 筛选

**使用方法：**

```bash
# 自动分析最新日志
lt

# 分析指定日志文件
lt <log_file_path>

# 指定输出文件
lt <log_file_path> -o my_trace_report.html

# 筛选特定 session
lt <log_file_path> --session <session_id>

# 显示详细摘要
lt -v
```

**报告内容：**
- **按 Session 分开**：每个 session 生成独立 HTML 文件
- **index.html**：Session 列表索引页
- **session_*.html**：
  - 按 iteration 展示请求→响应链路
  - 完整 JSON 展开：messages、tools、response
  - reasoning_content（推理过程）
  - tool_calls 详情
  - 可滚动查看长内容

**作为库使用：**

```python
from llm_trace_analyzer import LLMTraceAnalyzer

analyzer = LLMTraceAnalyzer("app.log")
analyzer.run(output_path="trace_report", verbose=True)  # 生成 trace_report/ 目录
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