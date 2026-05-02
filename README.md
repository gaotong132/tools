# Python Tools Collection

Python工具集合项目

## 项目结构

```
tools/
├── agent_history_analyzer/    # Agent历史分析工具包
├── llm_trace_analyzer/        # LLM请求链路分析工具包
├── tests/                     # 测试目录
│   ├── fixtures/              # 测试数据
│   ├── test_loader.py
│   ├── test_parser.py
│   ├── test_analyzer.py
│   ├── test_reporter.py
│   ├── test_main.py
│   └── test_integration.py
├── .venv/                     # 虚拟环境
├── pyproject.toml             # 项目配置
└── README.md                  # 项目说明
```

## 快速开始

```bash
# 1. 创建虚拟环境（推荐使用 uv）
uv venv && uv pip install -e .[dev]

# 或使用 pip
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows
pip install -e .[dev]

# 2. 运行工具
ha                              # 分析Agent历史（自动查找最新）
ha <json_file> -o report.html   # 分析指定文件
lt                              # 分析LLM请求链路（自动查找）
lt <log_file> -o trace_report   # 分析指定日志
lt --session <session_id>       # 筛选特定 session
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
# 自动分析最新会话
ha

# 分析指定文件
ha <json_file_path> -o my_report.html -v
```

## LLM Trace Analyzer

分析LLM_IO_TRACE日志，重建完整请求/响应链路并生成可视化报告。

**前置要求：**

OfficeClaw 需要开启 DEBUG 级别日志才能记录 `LLM_IO_TRACE`。修改配置文件：

```yaml
# 配置文件路径：<用户目录>/.office-claw/.jiuwenclaw/config/config.yaml
logging:
  level: DEBUG
  full: DEBUG
```

**功能特性：**
- 解析 `full.log` 中的 `LLM_IO_TRACE` 日志
- 合并分片请求体（body_part 1/N → N/N）
- 关联请求（messages+tools）与响应（content+tool_calls）
- **支持新格式 session_id**：自动识别 `_subagent_` 和 `_fork_agent_` 嵌套关系
- **Timing Overview 面板**：按迭代展示 LLM 时间、Tool 时间、总时间，支持排序
- 自动转换 tools 格式为标准 OpenAI 格式

**使用方法：**

```bash
# 自动分析最新日志
lt

# 分析后自动在浏览器打开
lt -O

# 分析指定日志
lt <log_file_path> -o my_trace_report

# 筛选特定 session（含所有 subagent）
lt --session officeclaw_b2fbb87bbeebde489553cb50

# 显示详细摘要
lt -v
```

**报告内容：**
- **index.html**：Session 列表索引页
- **session_*.html**：
  - **Timing Overview**：迭代耗时列表，支持按 LLM/Tool/Total 排序，点击跳转
  - 按 iteration 展示请求→响应链路
  - 完整 JSON 展开：messages、tools、response
  - reasoning_content（推理过程）
  - tool_calls 详情及工具名称摘要
  - Tool Call Results：新增的工具调用结果
  - Copy Body 按钮：一键复制请求体
  - Subagents 树状展示：显示调用链和嵌套深度

**默认日志路径：**
- `~/.office-claw/.jiuwenclaw/service_default/.logs/full.log`

## 开发

```bash
# 安装开发依赖
uv pip install -e .[dev]

# 运行测试
pytest tests/ -v

# 代码检查
black . && ruff check . && mypy .

# 类型检查
mypy llm_trace_analyzer/ agent_history_analyzer/
```

## 测试

项目包含完整的单元测试和集成测试：

```
tests/
├── conftest.py          # 测试配置和 fixtures
├── fixtures/
│   └ llm_trace_b2fbb87bbeeb.log  # 测试日志（836行）
├── test_loader.py       # LogLoader 测试
├── test_parser.py       # TraceParser 测试
├── test_analyzer.py     # ChainAnalyzer 测试
├── test_reporter.py     # HTMLReporter 测试
├── test_main.py         # CLI 测试
└── test_integration.py  # 集成测试
```

运行测试：
```bash
pytest tests/ -v                    # 运行所有测试
pytest tests/test_analyzer.py -v    # 运行单个模块测试
```

## 添加新工具

1. 在项目根目录创建新的工具包
2. 更新 `pyproject.toml` 添加入口点

```toml
[project.scripts]
tool-name = "tool_package.main:main"
```

## 架构说明

**llm_trace_analyzer** 模块结构：

```
llm_trace_analyzer/
├── loader.py      # LogLoader - 解析日志行，提取 trace 数据
├── parser.py      # TraceParser - 合并分片，构建 Request/Response
├── analyzer.py    # ChainAnalyzer - 关联请求响应，识别 subagent
├── reporter.py    # HTMLReporter - 生成 HTML 报告
├── templates.py   # HTML 模板
├── models.py      # 数据模型
├── constants.py   # 常量定义
└── main.py        # CLI 入口
```

关键处理流程：
1. **Loader**：过滤 `[LLM_IO_TRACE]` 行，提取 event/session_id/request_id/iteration/body_part
2. **Parser**：按 timestamp 聚类合并分片，处理 reasoning_seq 重置分组
3. **Analyzer**：识别 `_subagent_` / `_fork_agent_` 新格式，计算嵌套深度和链路标签
4. **Reporter**：生成 index.html 和 session 详情页