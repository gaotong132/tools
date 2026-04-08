# LSP 配置说明

本项目已配置 Python Language Server Protocol (LSP) 支持，可在编辑器中获得智能提示、代码补全、类型检查等功能。

## 支持的 LSP 服务器

### 1. Pyright (推荐)

**适用于：** VS Code + Pylance 扩展、其他支持 Pyright 的编辑器

**配置文件：** `pyproject.toml` 中的 `[tool.pyright]` 部分

**特点：**
- 微软官方开发，与 Pylance 扩展一致
- 快速、准确的类型检查
- 支持类型存根
- 自动检测虚拟环境

**VS Code 配置：**
```json
{
  "python.languageServer": "Pylance",
  "python.analysis.typeCheckingMode": "basic"
}
```

### 2. PyLSP (Python Language Server Protocol)

**适用于：** Vim/Neovim (with coc.nvim or nvim-lspconfig)、Emacs、Sublime Text 等

**配置文件：** `pyproject.toml` 中的 `[tool.pylsp]` 部分

**安装：**
```bash
# 在虚拟环境中安装
pip install python-lsp-server[all]

# 或只安装核心功能
pip install python-lsp-server
```

**Neovim 配置示例 (nvim-lspconfig)：**
```lua
local lspconfig = require('lspconfig')
lspconfig.pylsp.setup{
  settings = {
    pylsp = {
      plugins = {
        pyflakes = { enabled = true },
        mccabe = { enabled = true, threshold = 15 },
        pycodestyle = { enabled = true, ignore = {'E501', 'W503'} },
      }
    }
  }
}
```

**Vim/Neovim 配置示例 (coc.nvim)：**
```json
{
  "languageserver": {
    "python": {
      "command": "pylsp",
      "filetypes": ["python"],
      "settings": {
        "pylsp": {
          "plugins": {
            "pyflakes": { "enabled": true },
            "mccabe": { "enabled": true }
          }
        }
      }
    }
  }
}
```

## 编辑器配置

### VS Code

**推荐扩展：**
1. Python (Microsoft)
2. Pylance (Microsoft)

**settings.json：**
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/Scripts/python.exe",
  "python.languageServer": "Pylance",
  "python.analysis.typeCheckingMode": "basic",
  "python.analysis.autoImportCompletions": true,
  "editor.formatOnSave": true,
  "python.formatting.provider": "black",
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true
}
```

### PyCharm

PyCharm 使用自己的代码分析引擎，但可以配置使用项目中的工具：

1. **设置解释器：** File → Settings → Project → Python Interpreter → 选择 `venv/Scripts/python.exe`
2. **启用 Black：** File → Settings → Tools → Black → Configure
3. **启用 Ruff：** 安装 Ruff 插件

### Neovim

使用 nvim-lspconfig 和 mason.nvim：

```lua
-- 安装 LSP 服务器
require('mason').setup()
require('mason-lspconfig').setup{
  ensure_installed = { 'pyright', 'pylsp' }
}

-- 配置 Pyright
require('lspconfig').pyright.setup{}

-- 或配置 PyLSP
require('lspconfig').pylsp.setup{
  settings = {
    pylsp = {
      configurationSources = {"pyflakes", "mccabe", "pycodestyle"},
      plugins = {
        pyflakes = { enabled = true },
        mccabe = { enabled = true, threshold = 15 },
        pycodestyle = { enabled = true, maxLineLength = 100 }
      }
    }
  }
}
```

## 工具集成

项目已配置以下工具：

- **Black** - 代码格式化
- **Ruff** - 快速 linter
- **MyPy** - 静态类型检查
- **Pytest** - 测试框架

**运行命令：**

```bash
# 格式化代码
black tools/

# Lint 检查
ruff check tools/

# 类型检查
mypy tools/

# 运行测试
pytest
```

## 虚拟环境

项目使用 venv，LSP 会自动检测：

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境 (Windows)
.\venv\Scripts\Activate.ps1

# 安装依赖
pip install -e .[dev]
```

## 故障排查

### LSP 无法找到模块

**问题：** LSP 显示 "Import could not be resolved"

**解决方案：**
1. 确保虚拟环境已激活
2. 检查 `pyproject.toml` 中的 `venv` 配置
3. 在 VS Code 中选择正确的解释器：Ctrl+Shift+P → "Python: Select Interpreter"

### 类型提示不正确

**问题：** MyPy 或 Pyright 显示类型错误

**解决方案：**
1. 检查 `[tool.mypy]` 和 `[tool.pyright]` 配置
2. 添加 `# type: ignore` 注释临时忽略
3. 在 `pyproject.toml` 中配置 `[[tool.mypy.overrides]]`

### LSP 性能慢

**解决方案：**
1. 使用 Pyright（比 PyLSP 快）
2. 减少类型检查范围：`typeCheckingMode = "off"` 或 `"basic"`
3. 在 `exclude` 中排除不需要分析的目录

## 参考资源

- [Pyright Documentation](https://github.com/microsoft/pyright)
- [Python LSP Server](https://github.com/python-lsp/python-lsp-server)
- [Black Code Style](https://black.readthedocs.io/)
- [Ruff Linter](https://beta.ruff.rs/)
- [MyPy](https://mypy.readthedocs.io/)