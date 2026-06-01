"""
LLM Diagnose — DeepSeek-powered failure diagnosis for SelfHealer.

提供 make_deepseek_diagnose_fn() 工厂函数，生成符合 LLMDoctor
set_diagnose_fn() 签名的诊断函数。

用法:
    from ahy_governance.self_healer import LLMDoctor
    from ahy_governance.llm_diagnose import make_deepseek_diagnose_fn

    doctor = LLMDoctor()
    doctor.set_diagnose_fn(make_deepseek_diagnose_fn(api_key="sk-..."))
    healer.set_llm_doctor(doctor)
"""

from __future__ import annotations

import json
import os
from typing import Callable

from .self_healer import RecoveryAction, RecoveryActionType

DIAGNOSE_PROMPT = """你是一个 AI Agent 故障诊断专家。你的任务是分析 Agent 崩溃/异常的原因，并给出具体的恢复方案。

## 故障信息
- Agent 名称: {agent_name}
- 故障类型: {incident_type}
- 错误消息: {error_message}
- 额外上下文: {context}

## 可用恢复策略
1. retry — 重试（适用于超时、瞬时错误）
2. circuit_break — 熔断+退避（适用于限流、过载）
3. rollback — 回滚（适用于依赖失败）
4. model_fallback — 模型降级（适用于幻觉、推理错误）
5. context_truncate — 上下文裁剪（适用于 token 超限）
6. output_validate — 输出校验（适用于格式错误）
7. restart_agent — 重启 Agent（适用于内存耗尽、死锁）
8. alert_human — 升级人工（适用于认证失败、未知故障）

## 要求
请用 JSON 格式回复，不要有任何其他文字：
```json
{{
  "action": "策略名",
  "description": "修复方案的中文描述，简洁具体（20字以内）",
  "confidence": 0.0-1.0,
  "params": {{}}
}}
```

如果完全无法判断原因，action 用 "alert_human"，confidence 设为 0.3。
"""


def make_deepseek_diagnose_fn(
    api_key: str | None = None,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-chat",
) -> Callable[[str, dict], RecoveryAction | None]:
    """Create a diagnose function backed by DeepSeek API.

    Returns a callable matching LLMDoctor.set_diagnose_fn() signature.
    """
    import urllib.request
    import urllib.error

    key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise ValueError("DeepSeek API key required — set DEEPSEEK_API_KEY or pass api_key=")

    def diagnose_fn(error_message: str, context: dict) -> RecoveryAction | None:
        agent_name = context.get("agent_name", "unknown")
        incident_type = context.get("incident_type", "unknown")
        ctx_str = json.dumps(
            {k: v for k, v in context.items() if k not in ("agent_name", "incident_type")},
            ensure_ascii=False, indent=2,
        )

        prompt = DIAGNOSE_PROMPT.format(
            agent_name=agent_name,
            incident_type=incident_type,
            error_message=error_message,
            context=ctx_str,
        )

        req_data = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一个精确的 JSON 输出机器人，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 256,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            data=req_data,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
            return None

        try:
            content = body["choices"][0]["message"]["content"]
            # Extract outermost JSON using bracket depth (handles nested objects)
            start = content.find("{")
            if start == -1:
                parsed = json.loads(content)
            else:
                depth = 0
                end = start
                for i in range(start, len(content)):
                    if content[i] == "{":
                        depth += 1
                    elif content[i] == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                parsed = json.loads(content[start:end])
        except (KeyError, IndexError, json.JSONDecodeError):
            return None

        action_str = parsed.get("action", "alert_human")
        try:
            action_type = RecoveryActionType(action_str)
        except ValueError:
            action_type = RecoveryActionType.ALERT_HUMAN

        return RecoveryAction(
            action_type=action_type,
            description=parsed.get("description", "LLM 诊断结果"),
            params=parsed.get("params", {}),
            confidence=float(parsed.get("confidence", 0.5)),
            source="llm",
        )

    return diagnose_fn
