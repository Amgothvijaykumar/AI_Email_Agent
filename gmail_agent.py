import json
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from gemini_client import invoke_with_fallback, extract_text
from gmail_tools import (
    search_gmail,
    read_gmail_email,
    mark_email_as_read,
    mark_email_as_unread,
    star_email,
    unstar_email,
    archive_email,
    delete_email,
    batch_delete_emails,
    get_inbox_overview,
    execute_delete_email,
    execute_batch_delete_emails,
)
from gmail_service import create_gmail_service
from semantic_search_tool import search_emails_semantically

load_dotenv()

MAX_TOOL_ITERATIONS = 5

TOOLS = [
    search_gmail,
    read_gmail_email,
    mark_email_as_read,
    mark_email_as_unread,
    star_email,
    unstar_email,
    archive_email,
    delete_email,
    batch_delete_emails,
    get_inbox_overview,
    search_emails_semantically,
]
TOOL_MAP = {tool.name: tool for tool in TOOLS}

SYSTEM_PROMPT = """You are an AI assistant managing Gmail.
- For specific senders, dates, read status, or subjects: use search_gmail.
- For concept/topic searches: use search_emails_semantically.
- To read or modify emails: search first, then use the exact hex Message ID.
- For single delete: call delete_email(message_id=...).
- For multiple/promotional deletes: call batch_delete_emails(message_ids=[...]).
Always provide concise, clear answers."""


def _call_signature(tool_name: str, tool_args: dict) -> str:
    """Generate unique call signature for duplicate detection."""
    try:
        sorted_args = json.dumps(tool_args, sort_keys=True)
    except Exception:
        sorted_args = str(tool_args)
    return f"{tool_name}::{sorted_args}"


def _is_valid_message_id(message_id: str) -> bool:
    """Verify that string matches Gmail hexadecimal Message ID format."""
    if not message_id or " " in message_id.strip():
        return False
    stripped = message_id.strip()
    return 8 <= len(stripped) <= 32 and stripped.isalnum()


def run_agent():
    """Run interactive CLI agent loop."""
    print("AI Gmail Agent initialized. Type 'exit' to quit.\n")
    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    while True:
        try:
            question = input("Ask your Gmail agent: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAgent stopped.")
            break

        if not question:
            continue
        if question.lower() in ["exit", "quit", "bye", "q"]:
            break

        messages.append(HumanMessage(content=question))
        executed_calls = set()

        for iteration in range(MAX_TOOL_ITERATIONS):
            try:
                response = invoke_with_fallback(messages, tools=TOOLS)
            except Exception as e:
                print(f"Error: {e}")
                break

            messages.append(response)

            if not response.tool_calls:
                print(f"\nAgent: {extract_text(response)}\n")
                break

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                signature = _call_signature(tool_name, tool_args)
                if signature in executed_calls:
                    messages.append(ToolMessage(
                        content="ERROR: Duplicate call detected. Proceed to final answer.",
                        tool_call_id=tool_id
                    ))
                    continue
                executed_calls.add(signature)

                id_requiring = {
                    "read_gmail_email", "mark_email_as_read", "mark_email_as_unread",
                    "star_email", "unstar_email", "archive_email", "delete_email"
                }
                if tool_name in id_requiring:
                    msg_id = tool_args.get("message_id", "")
                    if not _is_valid_message_id(msg_id):
                        messages.append(ToolMessage(
                            content=f"ERROR: '{msg_id}' is not a valid hex Message ID. Call search_gmail first.",
                            tool_call_id=tool_id
                        ))
                        continue

                tool_fn = TOOL_MAP.get(tool_name)
                try:
                    tool_result = tool_fn.invoke(tool_args) if tool_fn else f"Unknown tool: {tool_name}"
                except Exception as e:
                    tool_result = f"Tool execution failed: {e}"

                if (
                    (tool_name == "delete_email" or tool_name == "batch_delete_emails")
                    and isinstance(tool_result, str)
                    and ("DELETE_CONFIRMATION_REQUIRED" in tool_result or "BATCH_DELETE_CONFIRMATION_REQUIRED" in tool_result)
                ):
                    print(f"\n{tool_result}")
                    confirm = input("\nType 'yes' to move to Trash, 'no' to cancel: ").strip().lower()
                    if confirm == "yes":
                        service = create_gmail_service()
                        if tool_name == "batch_delete_emails":
                            tool_result = execute_batch_delete_emails(service, tool_args.get("message_ids", []))
                        else:
                            tool_result = execute_delete_email(service, tool_args.get("message_id"))
                    else:
                        tool_result = "Deletion was cancelled by user."

                messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_id))


if __name__ == "__main__":
    run_agent()