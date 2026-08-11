"""
gmail_agent.py
==============
AI Gmail Agent — Gemini-powered, tool-controlled.

Architecture:
    USER → Gemini → Tool Controller → Gmail API → Gemini → Answer

Key safety features:
    - MAX 5 tool iterations per request
    - Duplicate tool-call detection (same tool + same args = stop)
    - Delete confirmation: Python asks user before executing
    - Message ID validation: never allow non-ID strings as message_id
    - No infinite search loops

Usage:
    python gmail_agent.py

Requires:
    - .env file with GEMINI_API_KEY_1
    - token.json (run gmail_auth.py first)
    - email_embeddings.json (run email_indexer.py for semantic search)
"""

import json
import os

from dotenv import load_dotenv

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

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

# Load .env
load_dotenv()


# ============================================================
# Configuration
# ============================================================

MAX_TOOL_ITERATIONS = 5


# ============================================================
# Tool registry
# (delete_email & batch_delete_emails return confirmation requests)
# ============================================================

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


# ============================================================
# System prompt (Gemini-specific, concise and clear)
# ============================================================

SYSTEM_PROMPT = """
You are a smart Gmail assistant with access to Gmail tools.

============================================================
SEARCH RULES
============================================================

Use search_gmail for:
- Specific senders:     from:indeed
- Unread emails:        is:unread
- Subject keywords:     subject:"job offer"
- Date filters:         after:2024/01/01 before:2024/12/31
- Starred:              is:starred
- Attachments:          has:attachment
- Combined:             from:indeed is:unread

Make ONE well-formed search query. Do NOT call search_gmail
multiple times with slightly different queries.

Use search_emails_semantically ONLY when the user is searching
by concept or topic (not sender/date/status):
- "emails related to machine learning"
- "emails about internship opportunities"
- "emails about AI hackathons"

Do NOT use semantic search for:
- specific senders, dates, read/unread status, or starred

============================================================
MODIFICATION RULES
============================================================

To mark/star/archive/delete an email:
1. Use search_gmail to find the email(s)
2. Use the EXACT Message IDs from the results
3. Call the modification tool with that ID

NEVER invent a Message ID. Never use subject, sender name,
or any text as a message_id. Only IDs like "19fe5f834c141592".

============================================================
DELETE RULES
============================================================

- For a SINGLE email:
  1. Search for it with search_gmail
  2. Call delete_email(message_id=<exact_id>)

- For MULTIPLE / BATCH emails (e.g. promotional emails, newsletters, all emails from a sender):
  1. Search for the matching emails with search_gmail (e.g. category:promotions, from:newsletter, etc.)
  2. Collect all matching Message IDs
  3. Call batch_delete_emails(message_ids=[id1, id2, id3, ...])

Python/UI will always ask the user for confirmation before moving emails to Trash.
Do NOT attempt to delete without searching first.

============================================================
READING RULE
============================================================

Only use read_gmail_email when user explicitly asks to read
the content. For listing/finding emails, use search_gmail
which already shows a preview.

============================================================
TOOL LOOP RULE
============================================================

- One search is usually enough. If found, proceed to action.
- If search returns no results, make at most ONE alternative.
- Do NOT loop with the same or similar queries.
- After the action is done, give a clear final answer.

============================================================
ANSWER STYLE
============================================================

- Be concise and helpful
- Show sender, subject, date for email results
- Always confirm completed actions clearly
- Do not invent information
"""


# ============================================================
# Helper: build a tool-call signature for dedup detection
# ============================================================

def _call_signature(tool_name: str, tool_args: dict) -> str:
    """Create a unique string for a tool call to detect duplicates."""
    try:
        sorted_args = json.dumps(tool_args, sort_keys=True)
    except Exception:
        sorted_args = str(tool_args)
    return f"{tool_name}::{sorted_args}"


# ============================================================
# Helper: check if a message_id looks like a real Gmail ID
# ============================================================

def _is_valid_message_id(message_id: str) -> bool:
    """
    Gmail message IDs are hex strings, typically 16 characters.
    Reject anything that looks like natural language.
    """
    if not message_id:
        return False

    stripped = message_id.strip()

    # Gmail IDs are hex, 10-20 chars, no spaces
    if " " in stripped:
        return False

    if len(stripped) < 8 or len(stripped) > 32:
        return False

    # Allow hex chars plus some variation
    allowed = set("0123456789abcdefABCDEF")
    if all(c in allowed for c in stripped):
        return True

    # Some IDs contain letters beyond hex — allow alphanumeric
    if stripped.isalnum():
        return True

    return False


# ============================================================
# Main conversation loop
# ============================================================

def run_agent():
    """Run the interactive Gmail agent."""

    print()
    print("=" * 60)
    print("  AI Gmail Agent  |  Powered by Gemini")
    print("=" * 60)
    print("Type 'exit' or 'quit' to stop.")
    print()

    # Persistent conversation history
    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    while True:

        # ----------------------------------------------------------
        # Get user input
        # ----------------------------------------------------------
        try:
            question = input("Ask your Gmail agent: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nGmail agent stopped.")
            break

        if not question:
            continue

        if question.lower() in ["exit", "quit", "bye", "q"]:
            print("\nGmail agent stopped. Goodbye!")
            break

        # Add user message
        messages.append(HumanMessage(content=question))

        # ----------------------------------------------------------
        # Agent tool-calling loop
        # ----------------------------------------------------------

        executed_calls: set[str] = set()
        pending_delete: dict | None = None  # track delete confirmations

        for iteration in range(MAX_TOOL_ITERATIONS):

            print(f"\n🤖 Agent iteration {iteration + 1}/{MAX_TOOL_ITERATIONS}")

            # Invoke Gemini (with model + key fallback on 429)
            try:
                response = invoke_with_fallback(messages, tools=TOOLS)
            except Exception as e:
                print(f"\n❌ Gemini error: {e}")
                break

            messages.append(response)

            # ----------------------------------------------------------
            # No tool calls → final answer
            # ----------------------------------------------------------

            if not response.tool_calls:
                text = extract_text(response)
                print(f"\n💬 Agent: {text}")
                break

            # ----------------------------------------------------------
            # Execute tool calls
            # ----------------------------------------------------------

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                print(f"\n🔧 Tool: {tool_name}")
                print(f"   Args: {tool_args}")

                # ---- Duplicate detection ----
                signature = _call_signature(tool_name, tool_args)

                if signature in executed_calls:
                    print(
                        f"   ⚠️  Duplicate tool call detected. "
                        f"Stopping loop."
                    )
                    tool_result = (
                        "ERROR: This exact tool call was already executed. "
                        "Do not repeat it. Provide your final answer based "
                        "on what you already know."
                    )
                    messages.append(
                        ToolMessage(
                            content=tool_result,
                            tool_call_id=tool_id,
                        )
                    )
                    continue

                executed_calls.add(signature)

                # ---- Message ID validation ----
                id_requiring_tools = {
                    "read_gmail_email",
                    "mark_email_as_read",
                    "mark_email_as_unread",
                    "star_email",
                    "unstar_email",
                    "archive_email",
                    "delete_email",
                }

                if tool_name in id_requiring_tools:
                    msg_id = tool_args.get("message_id", "")
                    if not _is_valid_message_id(msg_id):
                        print(
                            f"   ❌ Invalid message_id: '{msg_id}'\n"
                            f"   Use search_gmail first to get a real ID."
                        )
                        tool_result = (
                            f"ERROR: '{msg_id}' is not a valid Gmail message ID. "
                            "You must call search_gmail first and use the exact "
                            "Message ID returned (a hex string like '19fe5f834c141592'). "
                            "Never use subject, sender name, or keywords as message_id."
                        )
                        messages.append(
                            ToolMessage(
                                content=tool_result,
                                tool_call_id=tool_id,
                            )
                        )
                        continue

                # ---- Execute the tool ----
                tool_fn = TOOL_MAP.get(tool_name)

                if tool_fn is None:
                    tool_result = f"Unknown tool: {tool_name}"
                else:
                    try:
                        tool_result = tool_fn.invoke(tool_args)
                    except Exception as e:
                        tool_result = f"Tool error: {e}"

                # ---- Handle delete confirmation (single or batch) ----
                if (
                    (tool_name == "delete_email" or tool_name == "batch_delete_emails")
                    and isinstance(tool_result, str)
                    and ("DELETE_CONFIRMATION_REQUIRED" in tool_result or "BATCH_DELETE_CONFIRMATION_REQUIRED" in tool_result)
                ):
                    print(f"\n⚠️  {tool_result}")

                    confirm = input(
                        "\nType 'yes' to move to Trash, 'no' to cancel: "
                    ).strip().lower()

                    if confirm == "yes":
                        service = create_gmail_service()
                        if tool_name == "batch_delete_emails":
                            mids = tool_args.get("message_ids", [])
                            delete_result = execute_batch_delete_emails(service, mids)
                        else:
                            delete_result = execute_delete_email(
                                service,
                                tool_args.get("message_id"),
                            )
                        tool_result = delete_result
                        print(f"   {delete_result}")
                    else:
                        tool_result = "Deletion was cancelled by the user."
                        print("   Deletion cancelled.")

                print(f"   ✓ Result: {str(tool_result)[:200]}")

                messages.append(
                    ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tool_id,
                    )
                )

        else:
            # Reached max iterations
            print(
                f"\n⚠️  Reached maximum {MAX_TOOL_ITERATIONS} tool iterations.\n"
                "Please try a more specific request."
            )

        print()


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    run_agent()