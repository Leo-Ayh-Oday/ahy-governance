# Ahy Governance MCP 配置指南

## 5 分钟接入 Ahy 治理

### Step 1: 安装

```bash
pip install ahy-governance
```

### Step 2: 配置 Claude Desktop

打开 Claude Desktop 配置文件：
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

添加 Ahy MCP Server：

```json
{
  "mcpServers": {
    "ahy-governance": {
      "command": "ahy-governance-mcp",
      "env": {
        "AHY_DB_PATH": "~/.ahy/ahy_governance.db"
      }
    }
  }
}
```

### Step 3: 配置 Cursor

打开 Cursor 设置 → MCP Servers，添加：

```json
{
  "ahy-governance": {
    "command": "ahy-governance-mcp",
    "env": {
      "AHY_DB_PATH": "~/.ahy/ahy_governance.db"
    }
  }
}
```

### Step 4: 重启 Claude Desktop / Cursor

重启后，你的 AI 助手就自动具备 Ahy 治理能力了。

## 有什么用？

配置完成后，你的 Claude/Cursor 在工作时会自动：

| 功能 | 说明 |
|------|------|
| 成本追踪 | 每次调用自动记录 token 消耗 |
| 冲突检测 | 多 Agent 输出自动检测矛盾 |
| 异常检测 | Token 暴涨、重复调用自动告警 |
| Prompt 防注入 | 输入自动扫描注入风险 |
| 审计日志 | 所有操作自动记录，可追溯 |

## 验证安装

在 Claude 里问：

> "帮我检查一下 Ahy 治理系统的健康状态"

Claude 会自动调用 `ahy_check_health` 工具，返回系统状态。

## 生成治理报告

在 Claude 里说：

> "生成一份合规报告"

Claude 会调用 `ahy_generate_compliance_report`，自动输出算法备案、安全评估或数据出境报告。

## 管理员工具

如需使用管理员工具（工作区管理、用户管理、告警配置等），设置环境变量：

```json
{
  "mcpServers": {
    "ahy-governance": {
      "command": "ahy-governance-mcp",
      "env": {
        "AHY_DB_PATH": "~/.ahy/ahy_governance.db",
        "AHY_MCP_ADMIN": "1"
      }
    }
  }
}
```

## 故障排查

**Q: Claude 看不到 ahy_* 工具？**
A: 检查 `ahy-governance-mcp` 命令是否可用：`which ahy-governance-mcp`

**Q: 数据库报错？**
A: 确保 `AHY_DB_PATH` 指向的目录存在，或删除旧数据库重新开始

**Q: 权限错误？**
A: 管理员工具需要 `AHY_MCP_ADMIN=1`
