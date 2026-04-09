import ollama
import json
from mnemosyne.config import get_settings
from mnemosyne.agent.tools import TOOLS, dispatch
from mnemosyne.agent.schemas import AgentResponse, WritePlan

SYSTEM_PROMPT = """You are a helpful assistant for an Obsidian markdown vault.\nYou have tools to search notes, read note contents, find related notes,\nand propose write actions for the user to approve.\n\nRules:\n- Always search before answering questions about note contents.\n- For write operations, use propose_* tools. Never claim to have written something without proposing first.\n- Cite specific note paths when referencing content.\n- If you cannot find relevant notes, say so clearly rather than guessing.\n- Keep responses focused and direct."""

def run(message: str, history: list[dict]) -> AgentResponse:
    settings = get_settings()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": message}
    ]
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
            return AgentResponse(
                text=response.message.content or "",
                messages=messages,
                write_plans=write_plans,
                tool_calls_made=tool_calls_made,
            )

        for tc in response.message.tool_calls:
            name = tc.function.name
            args = tc.function.arguments
            tool_calls_made.append(name)
            result = dispatch(name, args)
            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": str(result),
            })

    # Loop cap hit — force a final response
    messages.append({"role": "user", "content": "Please summarize what you found so far."})
    final = ollama.chat(model=settings.chat_model, messages=messages)
    return AgentResponse(
        text=final.message.content or "Reached iteration limit. Please refine your query.",
        messages=messages,
        write_plans=write_plans,
        tool_calls_made=tool_calls_made,
    )
