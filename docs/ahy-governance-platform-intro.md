# Ahy Governance：让 Agent 敢上生产

82% 的企业有影子 Agent，85% 在跑，5% 敢上生产。这三个数字我反复看了很多次。

不是因为 Agent 不够聪明。是因为没人知道它们什么时候会出事，出事了谁负责。LangSmith 能告诉你 Agent 调了什么模型、花了多少 token。LangFuse 能追踪调用链。但它们止步于观测。观测完了，然后呢？

我写的 Ahy Governance 是做治理的。观测 + 防护 + 自愈 + 合规，四个东西串成一个闭环。

---

## 它到底做什么

把 Agent 放上来，五件事：

- **自动发现**。你项目里有几个 Agent、用什么框架写的、能力边界是什么，不用手动登记
- **实时监控**。每个 Agent 的健康状态、token 消耗、响应延迟，一分钟刷新一次
- **输入输出拦截**。提示注入、PII 泄露、越权工具调用，在进出两端卡住
- **挂了自愈**。Agent 崩溃、token 暴涨、无限循环，检测到自动拉回来
- **审计存证**。每一次调用都写进哈希链，事后能验证有没有被篡改

类比的话：Datadog 盯微服务，WAF 挡攻击，Ahy Governance 盯 Agent 的行为和边界。

---

## 为什么现在要做这个

7 月 15 日中国《生成式 AI 服务管理暂行办法》施行。企业用 Agent 的不少，但多数是员工自己偷偷用，IT 部门不清楚有多少 Agent、花多少钱、有没有合规风险。

Agent 的故障模式跟微服务不太一样。微服务挂了一般是超时、OOM、连接池耗尽。Agent 挂了可能是幻觉输出被当成真数据、提示注入绕过了权限、一个循环烧掉几百刀的 token。这些 LangSmith 看不到。

市场上观测工具一堆，治理工具基本没有。所以我做了这个。

---

## 具体有哪些东西

### 发现：AGP 自注册

每个 Agent 项目里放一个 `.ahy-agent.json`，长这样：

```json
{
  "agent_name": "订单Agent",
  "framework": "langgraph",
  "version": "1.0.0",
  "capabilities": { "can_read": true, "can_write_local": true },
  "governance": { "cost_budget_usd": 50, "max_tool_risk": "local_write" }
}
```

Agent 启动时自动注册，进程退出自动标记离线。支持 CrewAI、AutoGen、LangGraph、OpenAI Agents、Claude Code 等 10 种框架。不管用什么写的，扫到就能管。

### 输入输出防护

Prompt Guard 守在输入端。检测 "ignore previous instructions" 这类注入攻击，自动脱敏手机号、身份证号、API Key。调用前检查 Agent 是否在允许名单里。

Output Guard 守在输出端。三个时间点拦截：执行前（pre）、执行中（mid）、执行后（post）。系统提示词泄露、敏感数据外传、高风险工具调用，都能卡住。动作有四级：放行、警告、阻止、转人工审批。

内置 18 条策略，覆盖幻觉检测、越狱防护、数据泄露、成本超限、工具滥用。可以用 `ahy_update_policy` 按条开关。

### 自愈：三级恢复

Agent 出问题的时候：

第一级纯规则匹配。比如心跳超时三次就重启，token 用量超过预算就限流，响应延迟飙升就自动降级到更便宜的模型。

第二级加 LLM 诊断。DeepSeek 读错误日志和上下文，判断根因，匹配恢复策略。不是简单的 if-this-then-that。

第三级全自动闭环。检测到异常、LLM 诊断根因、执行恢复动作、记录恢复结果、从结果中学习新规则。做完一圈，下次同类问题能自己处理。

每次自愈后，Recovery Learner 会扫描恢复账本，自动提炼新的恢复规则。跑得越久，挂得越少。

### 成本控制

按 Agent、模型、会话三个维度追踪 token 消耗。设预算上限，超了告警。

CostAdvisor 分析用量模式后直接给建议。比如你某个 Agent 一直用 GPT-4 做简单分类，它会说"换成 GPT-4o-mini，每个月省 $120"。不是只报数字，是给可执行的动作。

### 审计和合规

审计日志用哈希链防篡改。每条记录里存了前一条的 SHA-256。Agent 启动、LLM 调用、工具调用、权限变更，全记下来。随时可以跑 `ahy_verify_audit_integrity` 验证整条链有没有被改过。

合规报告三合一。算法备案模板、OWASP Top 10 for LLM 安全自评、GDPR 数据可携带性导出，都是 `ahy_generate_compliance_report` 一个命令生成。

### 质量门

可以定义评估数据集和打分器，设阈值。比如"幻觉率低于 5% 且 schema 合规率高于 90% 才能上线"。不达标直接卡住。逻辑跟 CI/CD 的单元测试一样，但测的不是代码覆盖率，是 Agent 的行为质量。

---

## MCP 集成

Ahy Governance 把 18 个治理能力做成了 MCP 工具。Claude Code、Cursor、Windsurf，任何支持 MCP 的 AI 工具都能直接调。

```
ahygen mcp init > .mcp.json
```

配完就能用。你在 Claude Code 里写 Agent 代码，同一个终端里管理它。成本追踪、提示消毒、健康检查、自愈触发、审计验证，全都在对话里完成。

18 个工具按类别：

| 类别 | 工具 |
|------|------|
| 成本 | `ahy_track_cost` `ahy_analyze_costs` |
| 安全 | `ahy_sanitize_prompt` `ahy_check_policy` |
| 健康 | `ahy_check_health` `ahy_discover_agents` |
| 自愈 | `ahy_self_heal` `ahy_detect_anomalies` `ahy_auto_heal_check` |
| 审计 | `ahy_log_audit` `ahy_verify_audit_integrity` |
| 质量 | `ahy_run_eval` `ahy_run_quality_gate` `ahy_eval_report` |
| 管理 | `ahy_get_dashboard` `ahy_send_alert` `ahy_memory_write` `ahy_memory_read` |

---

## 一行代码接入

```python
from ahy_governance import track

@track(name="my-agent", framework="langgraph", version="1.0.0")
def my_agent(query: str) -> str:
    return response
```

成本追踪、健康监控、审计日志、自动注册，全在 `@track` 里。CrewAI 和 LangChain 有原生适配器，不需要改现有代码。

---

## 现在的状态

v0.9.1，916 个测试全过，PyPI 上 `pip install ahy-governance` 就能装。SQLite 做本地开发，PostgreSQL 上生产。Web Dashboard 是 FastAPI 加单文件前端，不依赖任何前端构建工具。

---

## 接下 43 天

7 月 15 日政策施行，倒计时中。手上的事情：

- Agent 分级标准（Level 0-5 自动评估+策略推荐）已做完
- AGP 自注册标准 已做完
- 找 3-5 个真实用户跑场景
- 算法备案报告模板完善

---

## 如果你在用 Agent

不管是在给客户部署、自己公司内部用、还是做 Agent 框架想加治理层，如果被合规或安全问题卡住了，可以聊聊。

GitHub: [github.com/zhazhanzhang/ahy-governance](https://github.com/zhazhanzhang/ahy-governance)

PyPI: `pip install ahy-governance`
