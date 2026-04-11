import ollama

from mnemosyne.agent.schemas import AgentResponse, WritePlan
from mnemosyne.agent.tools import TOOLS, dispatch
from mnemosyne.config import get_settings

SYSTEM_PROMPT = """You are a helpful assistant for an Obsidian markdown vault.\nYou have tools to search notes, read note contents, find related notes,\nand propose write actions for the user to approve.\n\nRules:\n- Always search before answering questions about note contents.\n- For write operations, use propose_* tools. Never claim to have written something without proposing first.\n- Cite specific note paths when referencing content.\n- If you cannot find relevant notes, say so clearly rather than guessing.\n- Keep responses focused and direct."""


def run(message: str, history: list[dict]) -> AgentResponse:
    """Synchronous agent loop (non-streaming)."""
    settings = get_settings()
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": message}]
    )
    tool_calls_made = []
    write_plans = []
    max_iters = settings.agent_max_iterations

    for iteration in range(max_iters):
        response = ollama.chat(
            model=settings.chat_model,
            messages=messages,
            tools=TOOLS,
        )
        messages.append(response.message)

        if not response.message.tool_calls:
            # Extract any WritePlan objects from tool results in this turn
            for msg in messages:
                if msg.get("role") == "tool":
                    try:
                        plan = WritePlan.model_validate_json(msg["content"])
                        write_plans.append(plan)
                    except Exception:
                        pass
            # Convert all messages to dicts for Pydantic compatibility
            msg_dicts = [m if isinstance(m, dict) else m.__dict__ for m in messages]
            return AgentResponse(
                text=response.message.content or "",
                messages=msg_dicts,
                write_plans=write_plans,
                tool_calls_made=tool_calls_made,
            )

        for tc in response.message.tool_calls:
            name = tc.function.name
            args = tc.function.arguments
            tool_calls_made.append(name)
            result = dispatch(name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_name": name,
                    "content": str(result),
                }
            )

    # Loop cap hit — force a final response
    messages.append(
        {"role": "user", "content": "Please summarize what you found so far."}
    )
    final = ollama.chat(model=settings.chat_model, messages=messages)
    return AgentResponse(
        text=final.message.content
        or "Reached iteration limit. Please refine your query.",
        messages=messages,
        write_plans=write_plans,
        tool_calls_made=tool_calls_made,
    )


import asyncio


def _run_stream_sync(message: str, history: list[dict]):
    """Streaming agent loop: yields partial content as it arrives from Ollama."""
    settings = get_settings()
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": message}]
    )
    partial_content = ""

    for chunk in ollama.chat(
        model=settings.chat_model,
        messages=messages,
        tools=TOOLS,
        stream=True,
    ):
        if chunk.get("content"):
            partial_content += chunk["content"]
            yield {"type": "content", "content": partial_content}
        if chunk.get("tool_calls"):
            yield {"type": "tool_call", "tool_calls": chunk["tool_calls"]}
    yield {"type": "done", "content": partial_content}


async def run_stream(message: str, history: list[dict]):
    """Async generator for streaming agent loop."""
    loop = asyncio.get_event_loop()
    queue = asyncio.Queue()

    def produce():
        try:
            for chunk in _run_stream_sync(message, history):
                asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    import threading

    threading.Thread(target=produce, daemon=True).start()

    while True:
        chunk = await queue.get()
        if chunk is None:
            break
        yield chunk
    settings = get_settings()
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": message}]
    )
    tool_calls_made = []
    write_plans = []
    max_iters = settings.agent_max_iterations

    for iteration in range(max_iters):
        response = ollama.chat(
            model=settings.chat_model,
            messages=messages,
            tools=TOOLS,
        )
        messages.append(response.message)

        if not response.message.tool_calls:
            # Extract any WritePlan objects from tool results in this turn
            for msg in messages:
                if msg.get("role") == "tool":
                    try:
                        plan = WritePlan.model_validate_json(msg["content"])
                        write_plans.append(plan)
                    except Exception:
                        pass
            # Convert all messages to dicts for Pydantic compatibility
            msg_dicts = [m if isinstance(m, dict) else m.__dict__ for m in messages]
            yield {
                "type": "done",
                "content": response.message.content or "",
                "messages": msg_dicts,
                "write_plans": write_plans,
                "tool_calls_made": tool_calls_made,
            }
            return

        for tc in response.message.tool_calls:
            name = tc.function.name
            args = tc.function.arguments
            tool_calls_made.append(name)
            result = dispatch(name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_name": name,
                    "content": str(result),
                }
            )

    # Loop cap hit — force a final response
    messages.append(
        {"role": "user", "content": "Please summarize what you found so far."}
    )
    final = ollama.chat(model=settings.chat_model, messages=messages)
    yield {
        "type": "done",
        "content": final.message.content
        or "Reached iteration limit. Please refine your query.",
        "messages": messages,
        "write_plans": write_plans,
        "tool_calls_made": tool_calls_made,
    }
    return
