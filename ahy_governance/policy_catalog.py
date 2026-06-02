"""
Policy Catalog — 20+ 内置治理策略

按 Waxell 26 类 + Galileo 31 指标对齐，覆盖 6 大类别。

用法:
  from .policy_catalog import default_policies
  guard = get_guard()
  guard.load_policies(default_policies())
"""

from __future__ import annotations

from .output_guard import GuardPolicy, GuardAction, GuardTiming


def default_policies() -> list[GuardPolicy]:
    return [
        # ── 数据安全 (4) ──
        GuardPolicy("pii_detect", "PII 检测", "data", "CRITICAL",
                    GuardTiming.MID, GuardAction.REDACT, True,
                    "检测并脱敏输出中的手机号、身份证、银行卡、邮箱"),
        GuardPolicy("data_retention", "数据留存", "data", "HIGH",
                    GuardTiming.POST, GuardAction.LOG, True,
                    "记录输出数据留存时间，超期自动清理"),
        GuardPolicy("output_filter", "输出过滤", "data", "HIGH",
                    GuardTiming.MID, GuardAction.REDACT, True,
                    "过滤输出中的敏感关键词和保密信息"),
        GuardPolicy("prompt_injection", "注入检测", "data", "CRITICAL",
                    GuardTiming.PRE, GuardAction.BLOCK, True,
                    "检测并阻止提示注入攻击（ignore instructions / act as 等）"),

        # ── 成本控制 (3) ──
        GuardPolicy("budget_enforce", "预算执行", "cost", "HIGH",
                    GuardTiming.PRE, GuardAction.BLOCK, True,
                    "当累计成本超过预算时阻止后续调用"),
        GuardPolicy("token_limit", "Token 上限", "cost", "MEDIUM",
                    GuardTiming.PRE, GuardAction.WARN, True,
                    "单次调用 Token 超过上限时告警"),
        GuardPolicy("model_tier", "模型层级", "cost", "LOW",
                    GuardTiming.PRE, GuardAction.LOG, True,
                    "记录使用的模型层级，低优先级 Agent 应使用经济模型"),

        # ── 工具访问 (5) ──
        GuardPolicy("tool_allowlist", "工具白名单", "tool", "CRITICAL",
                    GuardTiming.PRE, GuardAction.BLOCK, True,
                    "仅允许 Agent 使用白名单中的工具"),
        GuardPolicy("tool_denylist", "工具黑名单", "tool", "CRITICAL",
                    GuardTiming.PRE, GuardAction.BLOCK, True,
                    "禁止 Agent 使用黑名单中的高危工具"),
        GuardPolicy("tool_rate_limit", "工具频率限制", "tool", "HIGH",
                    GuardTiming.PRE, GuardAction.BLOCK, True,
                    "限制单个工具在时间窗口内的调用次数"),
        GuardPolicy("filesystem_scope", "文件系统范围", "tool", "CRITICAL",
                    GuardTiming.PRE, GuardAction.BLOCK, True,
                    "限制 Agent 可访问的文件系统路径"),
        GuardPolicy("network_scope", "网络访问范围", "tool", "CRITICAL",
                    GuardTiming.PRE, GuardAction.BLOCK, True,
                    "限制 Agent 可访问的网络域名和 IP 范围"),

        # ── 输出质量 (4) ──
        GuardPolicy("hallucination_guard", "幻觉拦截", "output", "HIGH",
                    GuardTiming.MID, GuardAction.WARN, True,
                    "检测输出中的虚构信息并告警"),
        GuardPolicy("toxicity_guard", "毒性检测", "output", "HIGH",
                    GuardTiming.MID, GuardAction.BLOCK, True,
                    "检测并拦截有害、偏见、歧视内容"),
        GuardPolicy("schema_validate", "Schema 校验", "output", "MEDIUM",
                    GuardTiming.MID, GuardAction.WARN, True,
                    "校验输出是否符合预期 JSON Schema"),
        GuardPolicy("factuality_check", "事实性检查", "output", "HIGH",
                    GuardTiming.POST, GuardAction.WARN, True,
                    "检查输出事实是否与输入一致"),

        # ── Agent 间通信 (2) ──
        GuardPolicy("inter_agent_auth", "Agent 间认证", "comm", "CRITICAL",
                    GuardTiming.PRE, GuardAction.BLOCK, True,
                    "验证 Agent 间通信的身份和权限"),
        GuardPolicy("cross_agent_scope", "跨 Agent 范围", "comm", "HIGH",
                    GuardTiming.PRE, GuardAction.BLOCK, True,
                    "限制 Agent 可调用的其他 Agent 范围"),

        # ── 身份与访问 (2) ──
        GuardPolicy("agent_identity", "Agent 身份验证", "identity", "CRITICAL",
                    GuardTiming.PRE, GuardAction.BLOCK, True,
                    "验证 Agent 身份令牌的有效性"),
        GuardPolicy("user_delegation", "用户委派", "identity", "HIGH",
                    GuardTiming.PRE, GuardAction.BLOCK, True,
                    "验证用户委派权限，防止越权操作"),
    ]
