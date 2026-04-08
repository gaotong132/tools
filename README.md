# Python Tools Collection

Python工具集合项目

## 环境设置

### Windows激活虚拟环境
```powershell
.\venv\Scripts\Activate.ps1
```

或
```cmd
.\venv\Scripts\activate.bat
```

### 安装依赖
```bash
pip install -r requirements.txt
```

## 项目结构

```
tools/
├── venv/              # 虚拟环境
├── tools/             # 工具脚本目录
├── requirements.txt   # 依赖列表
└── README.md          # 项目说明
```

## 工具列表

### 1. Agent History Analyzer

分析Agent会话历史并生成可视化HTML报告。

**功能特性：**
- 解析JSON格式的Agent会话历史文件
- 分析对话流程、工具调用、上下文压缩等事件
- 计算各阶段耗时和统计信息
- 生成包含Chart.js图表的可视化HTML报告
- 支持折叠展开工具调用结果

**使用方法：**

```bash
# 基本使用
py -3 tools\analyze_agent_history.py <json_file_path>

# 指定输出文件名
py -3 tools\analyze_agent_history.py <json_file_path> --output my_report.html

# 显示详细信息
py -3 tools\analyze_agent_history.py <json_file_path> --verbose

# 示例
py -3 tools\analyze_agent_history.py "C:\Users\HW\.jiuwenclaw\agent\sessions\catcafe_634c1a138bbf0660f2038ca4\history.json" --verbose
```

**报告内容：**
- **统计概览**：总对话轮数、用户消息数、助手回复数、工具调用数、上下文压缩次数、平均耗时
- **完整对话历史**：可折叠的对话时间线，包含：
  - 用户输入
  - 推理过程
  - 工具调用（参数和结果可折叠）
  - 上下文压缩事件（穿插在对话中）
  - 助手回复
- **工具调用详情**：表格列出每个工具的调用次数、平均耗时、总耗时

**输出：**
- 默认生成 `report.html` 文件
- 可用浏览器打开查看完整的可视化报告

## 添加新工具

在 `tools/` 目录下创建新的Python脚本文件。