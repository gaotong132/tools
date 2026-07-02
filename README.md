# LLM Trace Analyzer

分析 LLM_IO_TRACE 日志，重建完整请求/响应链路并生成可视化 HTML 报告。

## 安装

```bash
uv venv && uv pip install -e .[dev]
```

或使用 pip：

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows
pip install -e .[dev]
```

## 使用

```bash
lt                              # 自动分析最新日志
lt -O                           # 分析后自动在浏览器打开
lt <log_file> -o report_dir     # 分析指定日志文件
lt --session <session_id>       # 筛选特定 session（含所有 subagent）
lt -v                           # 显示详细摘要
```

## 前置要求

OfficeClaw 需要开启 DEBUG 级别日志才能记录 `LLM_IO_TRACE`。修改配置文件：

```yaml
# 配置文件路径：<用户目录>/.office-claw/.jiuwenclaw/config/config.yaml
logging:
  level: DEBUG
  full: DEBUG
```

## 特性

- 解析 `full.json`（JSON Lines）或 `full.log`（纯文本），自动检测格式
- 合并分片请求体（body_part 1/N → N/N）
- 关联请求（messages+tools）与响应（content+tool_calls）
- 支持 `_subagent_` 和 `_fork_agent_` 嵌套关系识别
- Timing Overview 面板：按迭代展示 LLM/Tool/Total 耗时，支持排序
- 自动转换 tools 格式为标准 OpenAI 格式

## 报告内容

- **index.html**：Session 列表索引页
- **session_*.html**：
  - Timing Overview：迭代耗时列表，支持排序和点击跳转
  - 按 iteration 展示请求→响应链路
  - 完整 JSON 展开：messages、tools、response
  - reasoning_content（推理过程）
  - tool_calls 详情及工具名称摘要
  - Tool Call Results：工具调用结果
  - Copy Body 按钮：一键复制请求体
  - Subagents 树状展示：调用链和嵌套深度

## 默认日志路径

- `~/.office-claw/.jiuwenclaw/service_default/.logs/full.json`（优先）
- `~/.office-claw/.jiuwenclaw/service_default/.logs/full.log`（回退）
