# app/agents/tool_agent.py
"""A tool-using agent: the LLM chooses which Antidote MCP tools to call.

The agent connects to the MCP server in-process (mcp.Client accepts an
MCPServer instance), turns the server's tool list into OpenAI-style tool
definitions, and loops: the model picks a tool, we call it through MCP and
hand back the result, until the model answers without a tool call.
"""
import json
import os

from mcp import Client

from app import llm

BUYER_TASK = """You are the Buyer agent of a procurement team, working only through the \
Antidote memory tools. Find out what our requirements are and which suppliers \
qualify, using supported memory only. Then propose exactly ONE purchase order for \
the servo actuators that follows the requirements, citing as premises the ids of \
all beliefs you rely on. You cannot approve orders; a human does. Finish with a \
short summary of what you proposed and why."""


def _tool_defs(tools) -> list[dict]:
    return [{"type": "function", "function": {
        "name": t.name, "description": t.description or "", "parameters": t.input_schema}}
        for t in tools]


async def run(server, task: str = BUYER_TASK, max_steps: int = 10) -> dict:
    """Run the agent against an MCPServer. Returns the transcript."""
    if not llm.configured():
        raise llm.LLMNotConfigured("set LLM_API_KEY and LLM_MODEL (see .env.example)")
    from openai import OpenAI

    model = OpenAI(api_key=os.environ["LLM_API_KEY"],
                   base_url=os.getenv("LLM_BASE_URL") or llm.GROQ_OPENAI_URL,
                   max_retries=4, timeout=90)
    transcript = {"model": llm.model_name(), "task": task, "steps": [], "final": None}
    async with Client(server) as client:
        tools = _tool_defs((await client.list_tools()).tools)
        messages = [{"role": "user", "content": task}]
        for _ in range(max_steps):
            reply = model.chat.completions.create(
                model=os.environ["LLM_MODEL"], messages=messages, tools=tools,
                temperature=0).choices[0].message
            messages.append(reply.model_dump(exclude_none=True))
            if not reply.tool_calls:
                transcript["final"] = reply.content
                break
            for call in reply.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                result = await client.call_tool(call.function.name, args)
                text = result.content[0].text if result.content else ""
                messages.append({"role": "tool", "tool_call_id": call.id, "content": text})
                try:
                    shown = json.loads(text)
                except json.JSONDecodeError:
                    shown = text
                transcript["steps"].append({"tool": call.function.name, "arguments": args,
                                            "result": shown})
    return transcript
