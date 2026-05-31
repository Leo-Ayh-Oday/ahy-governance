"""
SDK Decorator — 一行集成装饰器

用法:
    from ahy_governance import track

    @track(agent="Planner", model="claude-sonnet-4-6")
    def plan(prompt: str) -> str:
        return llm.call(prompt)

    @track(agent="Executor", model="gpt-4o")
    async def execute(task: str) -> str:
        return await llm.acall(task)

设计:
    - 薄封装: 内部用 GovernancePipeline 记录事件
    - sync/async 双模式
    - 输出截断 500 字符避免存储爆炸
    - 自动推断 tokens (粗估: len/4)
    - 失败不抛: 装饰器不改变原函数行为
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import time
from typing import Callable

from .events import AgentStartEvent, AgentEndEvent
from .collector import GovernancePipeline
from .cost_tracker import get_tracker


OUTPUT_MAX_LEN = 500
_TOKEN_RATIO = 4  # 粗估: 1 token ≈ 4 chars


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _TOKEN_RATIO)


def track(
    agent: str,
    model: str = "unknown",
    session_id: str = "",
    capture_output: bool = True,
    output_max_len: int = OUTPUT_MAX_LEN,
) -> Callable:
    """装饰器: 自动追踪 Agent 调用。

    Args:
        agent: Agent 名称
        model: 使用的模型 ID
        session_id: 会话 ID (可选)
        capture_output: 是否捕获输出 (默认 True)
        output_max_len: 输出截断长度 (默认 500)
    """

    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                pipeline = GovernancePipeline()
                start = time.monotonic()
                pipeline.on_agent_start(AgentStartEvent(
                    agent_name=agent, model=model, session_id=session_id,
                ))
                error = None
                result = None
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    error = e
                    raise
                finally:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    output_str = ""
                    if capture_output and result is not None:
                        output_str = str(result)[:output_max_len]

                    prompt_str = str(args[0]) if args else ""
                    tokens_in = _estimate_tokens(prompt_str)
                    tokens_out = _estimate_tokens(output_str) if output_str else 0
                    try:
                        get_tracker().track(agent, model, tokens_in, tokens_out, session_id)
                    except Exception:
                        pass

                    pipeline.on_agent_end(AgentEndEvent(
                        agent_name=agent,
                        output={"result": output_str} if output_str else None,
                        success=error is None,
                        total_latency_ms=elapsed_ms,
                        session_id=session_id,
                    ))

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                pipeline = GovernancePipeline()
                start = time.monotonic()
                pipeline.on_agent_start(AgentStartEvent(
                    agent_name=agent, model=model, session_id=session_id,
                ))
                error = None
                result = None
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    error = e
                    raise
                finally:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    output_str = ""
                    if capture_output and result is not None:
                        output_str = str(result)[:output_max_len]

                    prompt_str = str(args[0]) if args else ""
                    tokens_in = _estimate_tokens(prompt_str)
                    tokens_out = _estimate_tokens(output_str) if output_str else 0
                    try:
                        get_tracker().track(agent, model, tokens_in, tokens_out, session_id)
                    except Exception:
                        pass

                    pipeline.on_agent_end(AgentEndEvent(
                        agent_name=agent,
                        output={"result": output_str} if output_str else None,
                        success=error is None,
                        total_latency_ms=elapsed_ms,
                        session_id=session_id,
                    ))

            return sync_wrapper

    return decorator
