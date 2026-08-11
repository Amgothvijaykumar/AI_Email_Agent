"""
web_server.py
=============
FastAPI backend server for the AI Gmail Agent Web UI.

Provides REST and execution endpoints for:
- Agent chat with step-by-step tool invocation tracking
- In-chat human-in-the-loop delete confirmation
- Inbox listing, filtering, and real-time email reader drawer
- Email actions (star, unstar, mark read, mark unread, archive, trash)
- Gemini email categorization and bulk cleaning
- Semantic vector search with match percentage scores
- Incremental vector re-indexing

Usage:
    source avkve/bin/activate
    python web_server.py
    # or: uvicorn web_server:app --host 127.0.0.1 --port 8000 --reload
"""

import os
import json
import uuid
import threading
from typing import Optional, List, Dict, Any
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage,
    AIMessage,
)

from gmail_service import create_gmail_service
from gemini_client import invoke_with_fallback, extract_text, LLM_MODELS, EMBEDDING_MODEL
from gmail_tools import (
    search_gmail,
    read_gmail_email,
    mark_email_as_read,
    mark_email_as_unread,
    star_email,
    unstar_email,
    archive_email,
    delete_email,
    get_inbox_overview,
    execute_delete_email,
)
from semantic_search_tool import search_emails_semantically
from read_emails import get_email_details, search_emails
from email_indexer import update_index

load_dotenv()

app = FastAPI(title="AI Gmail Agent API", version="1.0.0")

# Mount static folder
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ============================================================
# Models & In-Memory Sessions
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
    get_inbox_overview,
    search_emails_semantically,
]
TOOL_MAP = {tool.name: tool for tool in TOOLS}

SYSTEM_PROMPT = """
You are a smart, efficient AI Gmail assistant with access to Gmail tools.

SEARCH RULES:
- Use search_gmail for standard queries (senders: from:xxx, unread: is:unread, dates, subject keywords).
- Use search_emails_semantically ONLY for concept/topic-based searches (e.g. "internships in machine learning", "hackathons").
- Make ONE clean search query first.

MODIFICATION & ACTIONS:
- To read, mark, star, archive, or delete an email, you MUST use search_gmail first to get the real hex Message ID.
- NEVER invent or make up a Message ID.
- When asked to delete an email, call delete_email(message_id=<exact_id>). The system will safely ask the user for confirmation.

ANSWER STYLE:
- Format your answers cleanly with Markdown (bullet points, bold text, clear headings).
- Show sender, subject, and date for email listings.
- Confirm actions clearly once executed.
"""

# Active chat sessions: session_id -> list of LangChain messages
chat_sessions: Dict[str, List[Any]] = {}

# Pending delete confirmations: confirmation_id -> metadata
pending_confirmations: Dict[str, Dict[str, Any]] = {}

# Reindex task status
reindex_status = {
    "is_running": False,
    "last_run": None,
    "total_indexed": 0,
    "message": "Ready"
}


# ============================================================
# Pydantic Schemas
# ============================================================

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str

class DeleteConfirmRequest(BaseModel):
    session_id: str
    confirmation_id: str
    action: str  # "confirm" or "cancel"

class EmailActionRequest(BaseModel):
    action: str  # "mark_read", "mark_unread", "star", "unstar", "archive", "trash"

class BulkTrashRequest(BaseModel):
    message_ids: List[str]

class SemanticSearchRequest(BaseModel):
    query: str
    top_k: int = 5


# ============================================================
# Helper Functions
# ============================================================

def _is_valid_message_id(message_id: str) -> bool:
    if not message_id or " " in message_id.strip():
        return False
    stripped = message_id.strip()
    return 8 <= len(stripped) <= 32 and stripped.isalnum()


def _get_index_stats() -> dict:
    storage_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_embeddings.json")
    if os.path.exists(storage_path):
        try:
            with open(storage_path, "r") as f:
                data = json.load(f)
                return {
                    "total": data.get("total", len(data.get("emails", []))),
                    "model": data.get("embedding_model", "Unknown"),
                    "dimensions": data.get("dimensions", 3072)
                }
        except Exception:
            pass
    return {"total": 0, "model": "Not indexed", "dimensions": 0}


# ============================================================
# API Routes
# ============================================================

@app.get("/")
async def root():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"status": "AI Gmail Agent API is running. UI assets loading."}


@app.get("/api/status")
async def get_status():
    """Returns account status, unread count, active models, and index stats."""
    try:
        service = create_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        email_address = profile.get("emailAddress", "Connected")

        # Unread estimate
        unread_res = service.users().messages().list(
            userId="me", labelIds=["INBOX", "UNREAD"], maxResults=1
        ).execute()
        unread_count = unread_res.get("resultSizeEstimate", 0)

        index_stats = _get_index_stats()

        return {
            "status": "connected",
            "account": email_address,
            "unread_count": unread_count,
            "llm_model": LLM_MODELS[0],
            "fallback_models": LLM_MODELS,
            "embedding_model": EMBEDDING_MODEL,
            "index_stats": index_stats,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "llm_model": LLM_MODELS[0],
            "index_stats": _get_index_stats(),
        }


@app.get("/api/emails")
async def list_emails(
    q: str = "label:INBOX",
    max_results: int = 20,
    page_token: Optional[str] = None
):
    """Fetch emails using standard Gmail search query."""
    try:
        service = create_gmail_service()
        req = service.users().messages().list(
            userId="me",
            q=q,
            maxResults=min(max_results, 50),
            pageToken=page_token
        )
        res = req.execute()
        messages_meta = res.get("messages", [])
        next_page = res.get("nextPageToken")

        emails = []
        for m in messages_meta:
            detail = get_email_details(service, m["id"])
            emails.append(detail)

        return {
            "emails": emails,
            "next_page_token": next_page,
            "count": len(emails),
            "query": q
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch emails: {str(e)}")


@app.get("/api/email/{message_id}")
async def get_email(message_id: str):
    """Fetch full email content by ID."""
    try:
        service = create_gmail_service()
        detail = get_email_details(service, message_id)
        if not detail or not detail.get("subject"):
            raise HTTPException(status_code=404, detail="Email not found")
        return detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/email/{message_id}/action")
async def email_action(message_id: str, req: EmailActionRequest):
    """Execute a single email action (mark read, star, archive, trash, etc.)."""
    service = create_gmail_service()
    action = req.action.lower()

    try:
        if action == "mark_read":
            service.users().messages().modify(
                userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            return {"status": "ok", "message": f"Email marked as read"}

        elif action == "mark_unread":
            service.users().messages().modify(
                userId="me", id=message_id, body={"addLabelIds": ["UNREAD"]}
            ).execute()
            return {"status": "ok", "message": f"Email marked as unread"}

        elif action == "star":
            service.users().messages().modify(
                userId="me", id=message_id, body={"addLabelIds": ["STARRED"]}
            ).execute()
            return {"status": "ok", "message": f"Email starred"}

        elif action == "unstar":
            service.users().messages().modify(
                userId="me", id=message_id, body={"removeLabelIds": ["STARRED"]}
            ).execute()
            return {"status": "ok", "message": f"Star removed"}

        elif action == "archive":
            service.users().messages().modify(
                userId="me", id=message_id, body={"removeLabelIds": ["INBOX"]}
            ).execute()
            return {"status": "ok", "message": f"Email archived"}

        elif action == "trash":
            result = execute_delete_email(service, message_id)
            return {"status": "ok", "message": result}

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/bulk_trash")
async def bulk_trash(req: BulkTrashRequest):
    """Move multiple message IDs to Trash safely."""
    if not req.message_ids:
        return {"status": "ok", "deleted_count": 0, "messages": []}

    service = create_gmail_service()
    deleted = []
    failed = []

    for msg_id in req.message_ids:
        try:
            execute_delete_email(service, msg_id)
            deleted.append(msg_id)
        except Exception as e:
            failed.append({"id": msg_id, "error": str(e)})

    return {
        "status": "ok",
        "deleted_count": len(deleted),
        "deleted_ids": deleted,
        "failed": failed,
        "message": f"Moved {len(deleted)} email(s) to Trash."
    }


# ============================================================
# Gemini Categorizer Route
# ============================================================

CATEGORIES = ["Jobs", "Finance", "Promotions", "Social", "Security", "Personal", "Important", "Other"]
CATEGORY_META = {
    "Jobs": {"icon": "💼", "color": "#38bdf8", "desc": "Job offers, applications, recruiter emails"},
    "Finance": {"icon": "💰", "color": "#4ade80", "desc": "Banking, statements, crypto, market digests"},
    "Promotions": {"icon": "🛍️", "color": "#f472b6", "desc": "Deals, discounts, shopping newsletters"},
    "Social": {"icon": "👥", "color": "#a78bfa", "desc": "LinkedIn, Pinterest, community notifications"},
    "Security": {"icon": "🔒", "color": "#fb923c", "desc": "Password resets, 2FA, account alerts"},
    "Personal": {"icon": "💌", "color": "#f87171", "desc": "Direct 1-on-1 human correspondence"},
    "Important": {"icon": "⭐", "color": "#fbbf24", "desc": "Urgent deadlines, high-priority notices"},
    "Other": {"icon": "📧", "color": "#94a3b8", "desc": "General updates and newsletters"},
}

@app.get("/api/categorize")
async def categorize_todays_emails(days: int = 1, max_results: int = 25):
    """Fetch emails received today (since local midnight) and categorize them with Gemini."""
    service = create_gmail_service()
    from datetime import datetime
    today_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_ts = int(today_midnight.timestamp())
    query = f"after:{midnight_ts}"
    
    try:
        _, messages = search_emails(query, max_results=max_results)
        if not messages:
            # Fallback to general latest if no emails yet today
            _, messages = search_emails("label:INBOX", max_results=15)

        emails = []
        for m in messages:
            emails.append(get_email_details(service, m["id"]))

        # Structure container
        categorized: Dict[str, List[dict]] = {cat: [] for cat in CATEGORIES}

        # Prompt Gemini in batches or single multi-prompt to optimize latency
        batch_prompt = "Categorize each of these emails into EXACTLY ONE of: Jobs, Finance, Promotions, Social, Security, Personal, Important, Other.\n\n"
        for idx, em in enumerate(emails, 1):
            batch_prompt += f"[{idx}] ID: {em['id']}\nFrom: {em['sender']}\nSubject: {em['subject']}\nSnippet: {em.get('body', '')[:150].replace(chr(10), ' ')}\n\n"
        
        batch_prompt += "\nOutput EXACTLY in this format for each number:\n[1] Category: <Category> | Reason: <One short sentence>\n[2] Category: <Category> | Reason: <One short sentence>"

        response = invoke_with_fallback([
            SystemMessage(content="You are a precise email categorizer. Output only the requested numbered format."),
            HumanMessage(content=batch_prompt)
        ])
        
        resp_text = extract_text(response)
        
        # Parse lines
        cat_map = {}
        for line in resp_text.splitlines():
            line = line.strip()
            if line.startswith("[") and "]" in line:
                try:
                    num_part = line.split("]")[0].replace("[", "").strip()
                    idx = int(num_part) - 1
                    rest = line.split("]")[1].strip()
                    
                    cat = "Other"
                    reason = ""
                    if "Category:" in rest:
                        cat_raw = rest.split("Category:")[1].split("|")[0].strip()
                        for valid_cat in CATEGORIES:
                            if valid_cat.lower() in cat_raw.lower():
                                cat = valid_cat
                                break
                    if "Reason:" in rest:
                        reason = rest.split("Reason:")[1].strip()
                    
                    cat_map[idx] = (cat, reason)
                except Exception:
                    continue

        for idx, em in enumerate(emails):
            cat, reason = cat_map.get(idx, ("Other", "General update"))
            em["category"] = cat
            em["reason"] = reason
            categorized[cat].append(em)

        return {
            "total_emails": len(emails),
            "categories": categorized,
            "category_meta": CATEGORY_META,
            "query": query
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Categorization failed: {str(e)}")


# ============================================================
# Semantic Vector Search Route
# ============================================================

@app.post("/api/semantic_search")
async def semantic_search_api(req: SemanticSearchRequest):
    """Run vector search with cosine similarity against indexed emails."""
    try:
        from gemini_client import embed_text
        import numpy as np

        storage_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_embeddings.json")
        if not os.path.exists(storage_path):
            raise HTTPException(status_code=404, detail="Email vector index not found. Please run indexing first.")

        with open(storage_path, "r") as f:
            data = json.load(f)

        records = data.get("emails", [])
        if not records:
            return {"results": [], "query": req.query, "total_indexed": 0}

        query_vec = np.array(embed_text(req.query), dtype=float)
        query_norm = np.linalg.norm(query_vec)

        scored = []
        for r in records:
            emb = np.array(r.get("embedding", []), dtype=float)
            if len(emb) == 0:
                continue
            denom = query_norm * np.linalg.norm(emb)
            score = float(np.dot(query_vec, emb) / denom) if denom > 0 else 0.0
            
            scored.append({
                "id": r.get("id"),
                "subject": r.get("subject", "(No subject)"),
                "sender": r.get("sender", "Unknown"),
                "date": r.get("date", ""),
                "preview": r.get("body", "")[:280].replace("\n", " ").strip(),
                "similarity_score": round(score, 4),
                "match_percentage": max(0, min(100, int(score * 100)))
            })

        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        top_results = scored[:req.top_k]

        return {
            "query": req.query,
            "total_indexed": len(records),
            "results": top_results,
            "embedding_model": data.get("embedding_model", EMBEDDING_MODEL)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reindex")
async def trigger_reindex(background_tasks: BackgroundTasks):
    """Trigger background incremental vector index update."""
    global reindex_status
    if reindex_status["is_running"]:
        return {"status": "in_progress", "message": "Index update is already running."}

    def _run_indexer():
        global reindex_status
        reindex_status["is_running"] = True
        reindex_status["message"] = "Fetching new emails and generating Gemini embeddings..."
        try:
            service = create_gmail_service()
            records = update_index(service, max_results=50)
            reindex_status["total_indexed"] = len(records)
            reindex_status["last_run"] = datetime.now().isoformat()
            reindex_status["message"] = f"Successfully indexed {len(records)} emails."
        except Exception as e:
            reindex_status["message"] = f"Indexing error: {str(e)}"
        finally:
            reindex_status["is_running"] = False

    background_tasks.add_task(_run_indexer)
    return {"status": "started", "message": "Indexing started in the background."}


@app.get("/api/reindex/status")
async def get_reindex_status():
    global reindex_status
    stats = _get_index_stats()
    reindex_status["total_indexed"] = stats["total"]
    return reindex_status


# ============================================================
# Interactive Agent Chat Loop with Step Tracing & Delete Confirmation
# ============================================================

@app.post("/api/chat")
async def chat_with_agent(req: ChatRequest):
    """
    Runs the agent loop with real-time tool execution tracking.
    Returns:
    - steps: list of tool calls made, args, results
    - response: final AI assistant text
    - pending_confirmation: present if a destructive delete is requested
    """
    session_id = req.session_id or str(uuid.uuid4())
    
    if session_id not in chat_sessions:
        chat_sessions[session_id] = [SystemMessage(content=SYSTEM_PROMPT)]

    history = chat_sessions[session_id]
    history.append(HumanMessage(content=req.message))

    steps_log = []
    executed_calls = set()
    pending_confirmation = None
    final_text = ""

    MAX_TOOL_ITERATIONS = 5

    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            ai_resp = invoke_with_fallback(history, tools=TOOLS)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gemini LLM error: {str(e)}")

        history.append(ai_resp)

        # If no tool calls, we have our final text answer
        if not ai_resp.tool_calls:
            final_text = extract_text(ai_resp)
            break

        # Process tool calls
        for tool_call in ai_resp.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            step_entry = {
                "iteration": iteration + 1,
                "tool": tool_name,
                "args": tool_args,
                "status": "executing",
                "result": None,
            }

            # Duplicate call check
            signature = f"{tool_name}::{json.dumps(tool_args, sort_keys=True)}"
            if signature in executed_calls:
                step_entry["status"] = "duplicate_stopped"
                step_entry["result"] = "Duplicate call stopped to prevent loops."
                steps_log.append(step_entry)
                history.append(ToolMessage(
                    content="ERROR: Duplicate tool call. Provide final answer with existing knowledge.",
                    tool_call_id=tool_id
                ))
                continue

            executed_calls.add(signature)

            # Validate Message ID for action tools
            id_tools = {"read_gmail_email", "mark_email_as_read", "mark_email_as_unread", "star_email", "unstar_email", "archive_email", "delete_email"}
            if tool_name in id_tools:
                msg_id = str(tool_args.get("message_id", "")).strip()
                if not _is_valid_message_id(msg_id):
                    err_msg = f"ERROR: '{msg_id}' is not a valid 16-hex Gmail Message ID. Search with search_gmail first."
                    step_entry["status"] = "invalid_id"
                    step_entry["result"] = err_msg
                    steps_log.append(step_entry)
                    history.append(ToolMessage(content=err_msg, tool_call_id=tool_id))
                    continue

            # Execute tool
            tool_fn = TOOL_MAP.get(tool_name)
            if not tool_fn:
                tool_res = f"Unknown tool: {tool_name}"
            else:
                try:
                    tool_res = tool_fn.invoke(tool_args)
                except Exception as e:
                    tool_res = f"Tool execution failed: {str(e)}"

            # Handle Delete Confirmation Intercept
            if tool_name == "delete_email" and isinstance(tool_res, str) and "DELETE_CONFIRMATION_REQUIRED" in tool_res:
                confirm_id = str(uuid.uuid4())
                service = create_gmail_service()
                email_meta = get_email_details(service, tool_args.get("message_id"))

                pending_confirmation = {
                    "confirmation_id": confirm_id,
                    "session_id": session_id,
                    "tool_call_id": tool_id,
                    "message_id": tool_args.get("message_id"),
                    "subject": email_meta.get("subject", "No subject"),
                    "sender": email_meta.get("sender", "Unknown"),
                    "date": email_meta.get("date", ""),
                    "snippet": email_meta.get("body", "")[:200].strip(),
                    "prompt": "Are you sure you want to move this email to Gmail Trash?"
                }
                pending_confirmations[confirm_id] = pending_confirmation

                step_entry["status"] = "awaiting_confirmation"
                step_entry["result"] = "Safety check: Awaiting user confirmation to move email to Trash."
                steps_log.append(step_entry)

                # Return early with confirmation state
                return {
                    "session_id": session_id,
                    "steps": steps_log,
                    "response": "⚠️ **Confirmation Needed**: This action will move the following email to Gmail Trash (recoverable within 30 days). Please confirm below.",
                    "pending_confirmation": pending_confirmation
                }

            step_entry["status"] = "completed"
            step_entry["result"] = str(tool_res)
            steps_log.append(step_entry)

            history.append(ToolMessage(content=str(tool_res), tool_call_id=tool_id))

    if not final_text and not pending_confirmation:
        final_text = "Task completed with available tools."

    return {
        "session_id": session_id,
        "steps": steps_log,
        "response": final_text,
        "pending_confirmation": None
    }


@app.post("/api/chat/confirm_delete")
async def confirm_delete_action(req: DeleteConfirmRequest):
    """Handles the user's confirmation response for a pending deletion."""
    confirm_data = pending_confirmations.get(req.confirmation_id)
    if not confirm_data:
        raise HTTPException(status_code=404, detail="Pending confirmation expired or not found")

    session_id = req.session_id
    history = chat_sessions.get(session_id, [])
    tool_call_id = confirm_data["tool_call_id"]
    message_id = confirm_data["message_id"]

    del pending_confirmations[req.confirmation_id]

    if req.action == "confirm":
        service = create_gmail_service()
        delete_result = execute_delete_email(service, message_id)
        tool_response = delete_result
        final_text = f"✅ **Email Deleted**: The email `{confirm_data['subject']}` has been moved to Gmail Trash."
    else:
        tool_response = "Deletion was cancelled by the user."
        final_text = f"❌ **Cancelled**: Deletion was cancelled. The email was not modified."

    # Feed result back into history as ToolMessage
    history.append(ToolMessage(content=tool_response, tool_call_id=tool_call_id))

    return {
        "session_id": session_id,
        "status": "success",
        "action": req.action,
        "response": final_text,
        "message_id": message_id
    }


# ============================================================
# Entry Point
# ============================================================

def find_available_port(start_port: int = 8000, max_attempts: int = 10) -> int:
    import socket
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start_port

if __name__ == "__main__":
    import uvicorn
    port = find_available_port(8000)
    print("\n" + "=" * 60)
    print("  🚀 Starting AI Gmail Agent Web Server")
    print(f"  🌐 UI Dashboard: http://127.0.0.1:{port}")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")

