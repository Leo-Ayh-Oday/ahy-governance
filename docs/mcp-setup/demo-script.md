# Ahy Governance MCP Demo 脚本

## 场景：客户 Agent 跑 10 分钟，自动出治理报告

### 前置条件
- 已安装 ahy-governance
- 已配置 Claude Desktop MCP
- 重启 Claude Desktop

---

## Demo 流程（5 分钟）

### 1. 评估 Agent 级别（30 秒）

在 Claude 里说：

> "我有一个数据分析 Agent，它能读取数据、搜索资料、生成报告，但不能写入外部系统。请评估它的治理级别。"

Claude 会调用 `ahy_evaluate_agent_level`，返回：
```json
{
  "level": 2,
  "level_label": "Read + Draft",
  "description": "可以读取和生成草稿，需要审批门控",
  "required_controls": ["审批流程", "成本追踪", "审计日志"]
}
```

### 2. 模拟 Agent 运行（2 分钟）

在 Claude 里说：

> "帮我模拟一个 Agent 运行场景：调用 GPT-4 分析数据，然后调用 Claude 生成报告。记录成本。"

Claude 会调用 `ahy_track_cost` 两次：
```json
{"agent": "data-analyst", "model": "gpt-4", "tokens_in": 5000, "tokens_out": 1200, "cost": "$0.08"}
{"agent": "report-writer", "model": "claude-3-opus", "tokens_in": 3000, "tokens_out": 800, "cost": "$0.05"}
```

### 3. 检测冲突（30 秒）

在 Claude 里说：

> "假设两个 Agent 给出了矛盾的结论：一个说'销量上升'，一个说'销量下降'。帮我检测冲突。"

Claude 会调用 `ahy_check_conflicts`，返回：
```json
{
  "conflicts": [
    {
      "type": "CONTRADICTION",
      "severity": "HIGH",
      "agents": ["data-analyst", "report-writer"],
      "description": "销量趋势判断矛盾"
    }
  ]
}
```

### 4. 自动修复（30 秒）

在 Claude 里说：

> "帮我自动解决这个冲突。"

Claude 会调用 `ahy_auto_resolve`，返回：
```json
{
  "resolution": "HIGH_CONFIDENCE_PICK",
  "chosen": "data-analyst",
  "reason": "数据分析师有原始数据支持",
  "confidence": 0.85
}
```

### 5. 生成合规报告（1 分钟）

在 Claude 里说：

> "帮我生成一份算法备案报告。"

Claude 会调用 `ahy_generate_compliance_report`，输出完整报告：

```
# 算法备案报告

## 1. 算法基本信息
- 算法名称：数据分析 Agent 系统
- 算法类型：机器学习算法
- 应用场景：销售数据分析与报告生成

## 2. 算法原理
[自动生成的技术说明]

## 3. 安全评估
- 风险等级：中等
- 已实施控制：审批流程、成本追踪、冲突检测

## 4. 数据合规
- 数据来源：内部数据库
- 数据出境：无
- 隐私保护：已实施

## 5. 审计链
[完整的操作日志]
```

### 6. 异常检测（30 秒）

在 Claude 里说：

> "扫描一下系统有没有异常。"

Claude 会调用 `ahy_detect_anomalies`，返回：
```json
{
  "anomalies": [
    {
      "type": "TOKEN_SPIKE",
      "agent": "data-analyst",
      "description": "Token 消耗突增 300%",
      "severity": "WARNING"
    }
  ]
}
```

---

## Demo 结束语

"以上演示展示了 Ahy Governance 的核心能力：
1. **Agent 分级评估** — 自动判断 Agent 需要什么级别的治理
2. **成本追踪** — 每次调用自动记账
3. **冲突检测** — 多 Agent 输出自动检测矛盾
4. **自动修复** — 高置信度冲突自动解决
5. **合规报告** — 一键生成算法备案报告
6. **异常检测** — Token 暴涨等异常自动告警

整个过程零代码，只需要配置一个 JSON 文件。"

---

## 录屏建议

1. 开头展示配置文件（30 秒）
2. 重启 Claude Desktop（10 秒）
3. 按上述流程操作（4 分钟）
4. 结尾展示生成的报告（30 秒）

总时长：约 5 分钟
