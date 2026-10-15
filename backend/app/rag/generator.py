"""DeepSeek 生成：调用大模型生成答案

非流式调用统一走 _create()，带指数退避重试（网络抖动 / 限流 / 5xx）；
流式调用不重试 —— 已经吐出部分内容再重试会导致答案重复，得不偿失。
"""
import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from openai import (  # noqa: E402
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings

# 模块级缓存客户端
_client = None

# 只对「可重试」的错误退避重试：连接失败、超时、限流、服务端 5xx
_RETRYABLE = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        # DeepSeek 兼容 OpenAI 接口
        _client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
    return _client


@retry(
    reraise=True,
    stop=stop_after_attempt(settings.llm_max_retries),
    wait=wait_exponential(multiplier=0.5, max=4),
    retry=retry_if_exception_type(_RETRYABLE),
)
def _create(**kwargs):
    """带重试的模型调用入口（非流式）"""
    return _get_client().chat.completions.create(**kwargs)


def generate(system_prompt: str, user_prompt: str) -> str:
    """调用 DeepSeek 生成回答文本"""
    resp = _create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,  # 低温度，减少幻觉、更稳定
    )
    return resp.choices[0].message.content


def generate_stream(system_prompt: str, user_prompt: str):
    """流式生成，逐段返回增量文本（用于 SSE 流式输出，不做重试）"""
    stream = _get_client().chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


# ===== 以下为 Agent（工具调用）相关 =====


def chat_with_tools(messages: list[dict], tools: list[dict]) -> dict:
    """带工具定义调用模型，返回可直接追加回 messages 的 assistant 消息。

    返回结构：{"role": "assistant", "content": "...", "tool_calls": [...]}
    模型若决定调用工具，tool_calls 非空；若决定直接回答，content 非空、tool_calls 缺省。
    """
    resp = _create(
        model=settings.deepseek_model,
        messages=messages,
        tools=tools,
        tool_choice="auto",  # 由模型自主决定调不调、调哪个工具
        temperature=0.3,
    )
    msg = resp.choices[0].message
    result: dict = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        # 转成普通 dict，方便后续原样回传给模型
        result["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return result


def stream_answer(messages: list[dict]):
    """流式生成最终答案（不带工具），逐段返回增量文本（不做重试）"""
    stream = _get_client().chat.completions.create(
        model=settings.deepseek_model,
        messages=messages,
        temperature=0.3,
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def generate_text(messages: list[dict]) -> str:
    """非流式生成完整答案，流式失败时兜底"""
    resp = _create(
        model=settings.deepseek_model,
        messages=messages,
        temperature=0.3,
    )
    return resp.choices[0].message.content or ""
