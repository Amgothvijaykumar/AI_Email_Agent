import os
import json
import uuid
import socket
from typing import Optional, List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
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
    batch_delete_emails,
    get_inbox_overview,
    execute_delete_email,
    execute_batch_delete_emails,
)
from semantic_search_tool import search_emails_semantically
from read_emails import get_email_details, search_emails
from email_indexer import update_index

load_dotenv()

app = FastAPI(title="AI Gmail Agent API", version="1.0.0")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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

SYSTEM_PROMPT = """You are an AI Gmail assistant.
- Use search_gmail for standard filters (senders, dates, read status, subjects).
- Use search_emails_semantically for topic or conceptual searches.
- Always retrieve the real Message ID before taking actions.
- Confirm completed actions cleanly with Markdown."""

chat_sessions: Dict[str, List[Any]] = {}
pending_confirmations: Dict[str, Dict[str, Any]] = {}
reindex_status = {
    "is_running": False,
    "last_run": None,
    "total_indexed": 0,
    "message": "Ready"
}

CATEGORIES = ["Jobs", "Finance", "Promotions", "Social", "Security", "Personal", "Important", "Other"]
CATEGORY_META = {
    "Jobs": {"icon": "💼", "color": "#38bdf8", "desc": "Job offers, applications, recruiter emails"},
    "Finance": {"icon": "💰", "color": "#4ade80", "desc": "Banking, statements, crypto, market digests"},
    "Promotions": {"icon": "🛍️", "color": "#f472b6", "desc": "Deals, discounts, shopping newsletters"},
    "Social": {"icon": "👥", "color": "#a78bfa", "desc": "LinkedIn, Pinterest, community notifications"},
    "Security": {"icon": "🔒", "color": "#fb923c", "desc": "Password resets, 2FA, account alerts"},
    "Personal": {"icon": "💌", "color": "#f87171", "desc": "Direct human correspondence"},
    "Important": {"icon": "⭐", "color": "#fbbf24", "desc": "Urgent deadlines, high-priority notices"},
    "Other": {"icon": "📧", "color": "#94a3b8", "desc": "General updates and newsletters"},
}


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


class DeleteConfirmRequest(BaseModel):
    session_id: str
    confirmation_id: str
    action: str


class EmailActionRequest(BaseModel):
    action: str


class BulkTrashRequest(BaseModel):
    message_ids: List[str]


class SemanticSearchRequest(BaseModel):
    query: str
    top_k: int = 5


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


@app.get("/")
async def root():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"status": "AI Gmail Agent API is running."}


@app.get("/api/status")
async def get_status():
    """Return account info, unread counter, active model names, and index stats."""
    try:
        service = create_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        email_address = profile.get("emailAddress", "Connected")

        unread_res = service.users().messages().list(
            userId="me", labelIds=["INBOX", "UNREAD"], maxResults=1
        ).execute()
        unread_count = unread_res.get("resultSizeEstimate", 0)

        return {
            "status": "connected",
            "account": email_address,
            "unread_count": unread_count,
            "llm_model": LLM_MODELS[0],
            "fallback_models": LLM_MODELS,
            "embedding_model": EMBEDDING_MODEL,
            "index_stats": _get_index_stats(),
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
async def list_emails(q: str = "label:INBOX", max_results: int = 20, page_token: Optional[str] = None):
    """Retrieve filtered email list."""
    try:
        service = create_gmail_service()
        res = service.users().messages().list(
            userId="me",
            q=q,
            maxResults=min(max_results, 50),
            pageToken=page_token
        ).execute()

        messages_meta = res.get("messages", [])
        next_page = res.get("nextPageToken")
        emails = [get_email_details(service, m["id"]) for m in messages_meta]

        return {
            "emails": emails,
            "next_page_token": next_page,
            "count": len(emails),
            "query": q
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/email/{message_id}")
async def get_email(message_id: str):
    """Retrieve full email content and metadata."""
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
    """Execute single email mutation (star, unread, archive, trash)."""
    service = create_gmail_service()
    action = req.action.lower()

    try:
        if action == "mark_read":
            service.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}).execute()
            return {"status": "ok", "message": "Email marked as read"}
        elif action == "mark_unread":
            service.users().messages().modify(userId="me", id=message_id, body={"addLabelIds": ["UNREAD"]}).execute()
            return {"status": "ok", "message": "Email marked as unread"}
        elif action == "star":
            service.users().messages().modify(userId="me", id=message_id, body={"addLabelIds": ["STARRED"]}).execute()
            return {"status": "ok", "message": "Email starred"}
        elif action == "unstar":
            service.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["STARRED"]}).execute()
            return {"status": "ok", "message": "Star removed"}
        elif action == "archive":
            service.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["INBOX"]}).execute()
            return {"status": "ok", "message": "Email archived"}
        elif action == "trash":
            res = execute_delete_email(service, message_id)
            return {"status": "ok", "message": res}
        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/bulk_trash")
async def bulk_trash(req: BulkTrashRequest):
    """Move list of email IDs to Trash."""
    if not req.message_ids:
        return {"status": "ok", "deleted_count": 0, "deleted_ids": []}

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


@app.get("/api/categorize")
async def categorize_todays_emails(days: int = 1, max_results: int = 25):
    """Group today's emails into categories using Gemini."""
    service = create_gmail_service()
    today_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    query = f"after:{int(today_midnight.timestamp())}"

    try:
        _, messages = search_emails(query, max_results=max_results)
        if not messages:
            _, messages = search_emails("label:INBOX", max_results=15)

        emails = [get_email_details(service, m["id"]) for m in messages]
        categorized: Dict[str, List[dict]] = {cat: [] for cat in CATEGORIES}

        batch_prompt = "Categorize each email into ONE of: Jobs, Finance, Promotions, Social, Security, Personal, Important, Other.\n\n"
        for idx, em in enumerate(emails, 1):
            batch_prompt += f"[{idx}] ID: {em['id']}\nFrom: {em['sender']}\nSubject: {em['subject']}\nSnippet: {em.get('body', '')[:140]}\n\n"
        batch_prompt += "\nOutput format:\n[1] Category: <Category> | Reason: <One sentence>"

        response = invoke_with_fallback([
            SystemMessage(content="You are an email categorizer. Output only the requested numbered format."),
            HumanMessage(content=batch_prompt)
        ])

        cat_map = {}
        for line in extract_text(response).splitlines():
            line = line.strip()
            if line.startswith("[") and "]" in line:
                try:
                    num = int(line.split("]")[0].replace("[", "").strip()) - 1
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
                    cat_map[num] = (cat, reason)
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/semantic_search")
async def semantic_search_api(req: SemanticSearchRequest):
    """Execute vector search with cosine similarity."""
    try:
        from gemini_client import embed_text
        import numpy as np

        storage_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_embeddings.json")
        if not os.path.exists(storage_path):
            raise HTTPException(status_code=404, detail="Email vector index not found. Run indexing first.")

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
        return {
            "query": req.query,
            "total_indexed": len(records),
            "results": scored[:req.top_k],
            "embedding_model": data.get("embedding_model", EMBEDDING_MODEL)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reindex")
async def trigger_reindex(background_tasks: BackgroundTasks):
    """Trigger background incremental vector index generation."""
    global reindex_status
    if reindex_status["is_running"]:
        return {"status": "in_progress", "message": "Indexing is already running."}

    def _run():
        global reindex_status
        reindex_status["is_running"] = True
        reindex_status["message"] = "Indexing emails..."
        try:
            service = create_gmail_service()
            records = update_index(service, max_results=50)
            reindex_status["total_indexed"] = len(records)
            reindex_status["last_run"] = datetime.now().isoformat()
            reindex_status["message"] = f"Indexed {len(records)} emails."
        except Exception as e:
            reindex_status["message"] = f"Indexing error: {e}"
        finally:
            reindex_status["is_running"] = False

    background_tasks.add_task(_run)
    return {"status": "started", "message": "Indexing started in background."}


@app.get("/api/reindex/status")
async def get_reindex_status():
    global reindex_status
    stats = _get_index_stats()
    reindex_status["total_indexed"] = stats["total"]
    return reindex_status


@app.post("/api/chat")
async def chat_with_agent(req: ChatRequest):
    """Execute interactive chat turn with tool tracing and safety confirmation."""
    session_id = req.session_id or str(uuid.uuid4())
    if session_id not in chat_sessions:
        chat_sessions[session_id] = [SystemMessage(content=SYSTEM_PROMPT)]

    history = chat_sessions[session_id]
    history.append(HumanMessage(content=req.message))

    steps_log = []
    executed_calls = set()
    pending_confirmation = None
    final_text = ""

    for iteration in range(5):
        try:
            ai_resp = invoke_with_fallback(history, tools=TOOLS)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gemini error: {e}")

        history.append(ai_resp)

        if not ai_resp.tool_calls:
            final_text = extract_text(ai_resp)
            break

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

            sig = f"{tool_name}::{json.dumps(tool_args, sort_keys=True)}"
            if sig in executed_calls:
                step_entry["status"] = "duplicate_stopped"
                step_entry["result"] = "Duplicate tool call stopped."
                steps_log.append(step_entry)
                history.append(ToolMessage(
                    content="ERROR: Duplicate call stopped. Provide final response.",
                    tool_call_id=tool_id
                ))
                continue
            executed_calls.add(sig)

            id_tools = {"read_gmail_email", "mark_email_as_read", "mark_email_as_unread", "star_email", "unstar_email", "archive_email", "delete_email"}
            if tool_name in id_tools:
                msg_id = str(tool_args.get("message_id", "")).strip()
                if not _is_valid_message_id(msg_id):
                    err = f"ERROR: '{msg_id}' is not a valid hex Message ID. Search first."
                    step_entry["status"] = "invalid_id"
                    step_entry["result"] = err
                    steps_log.append(step_entry)
                    history.append(ToolMessage(content=err, tool_call_id=tool_id))
                    continue

            tool_fn = TOOL_MAP.get(tool_name)
            tool_res = tool_fn.invoke(tool_args) if tool_fn else f"Unknown tool: {tool_name}"

            if (
                (tool_name == "delete_email" or tool_name == "batch_delete_emails")
                and isinstance(tool_res, str)
                and ("DELETE_CONFIRMATION_REQUIRED" in tool_res or "BATCH_DELETE_CONFIRMATION_REQUIRED" in tool_res)
            ):
                confirm_id = str(uuid.uuid4())
                service = create_gmail_service()

                if tool_name == "batch_delete_emails":
                    mids = tool_args.get("message_ids", [])
                    email_items = []
                    for mid in mids:
                        em = get_email_details(service, mid)
                        email_items.append({
                            "id": mid,
                            "subject": em.get("subject", "No subject"),
                            "sender": em.get("sender", "Unknown"),
                            "date": em.get("date", ""),
                        })

                    pending_confirmation = {
                        "confirmation_id": confirm_id,
                        "session_id": session_id,
                        "tool_call_id": tool_id,
                        "is_batch": True,
                        "message_ids": mids,
                        "count": len(mids),
                        "items": email_items,
                        "prompt": f"Confirm moving all {len(mids)} email(s) to Gmail Trash?"
                    }
                else:
                    mid = tool_args.get("message_id")
                    em = get_email_details(service, mid)
                    pending_confirmation = {
                        "confirmation_id": confirm_id,
                        "session_id": session_id,
                        "tool_call_id": tool_id,
                        "is_batch": False,
                        "message_id": mid,
                        "subject": em.get("subject", "No subject"),
                        "sender": em.get("sender", "Unknown"),
                        "date": em.get("date", ""),
                        "snippet": em.get("body", "")[:200].strip(),
                        "prompt": "Confirm moving this email to Gmail Trash?"
                    }

                pending_confirmations[confirm_id] = pending_confirmation
                step_entry["status"] = "awaiting_confirmation"
                step_entry["result"] = "Awaiting user confirmation to move email(s) to Trash."
                steps_log.append(step_entry)

                return {
                    "session_id": session_id,
                    "steps": steps_log,
                    "response": "⚠️ **Confirmation Needed**: Please review and confirm the email(s) to be moved to Gmail Trash (recoverable within 30 days).",
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
    """Execute confirmed single or batch deletion."""
    confirm_data = pending_confirmations.get(req.confirmation_id)
    if not confirm_data:
        raise HTTPException(status_code=404, detail="Confirmation request expired")

    session_id = req.session_id
    history = chat_sessions.get(session_id, [])
    tool_call_id = confirm_data["tool_call_id"]
    del pending_confirmations[req.confirmation_id]

    if req.action == "confirm":
        service = create_gmail_service()
        if confirm_data.get("is_batch"):
            mids = confirm_data.get("message_ids", [])
            tool_response = execute_batch_delete_emails(service, mids)
            final_text = f"✅ **Batch Deletion Complete**: {tool_response}"
        else:
            mid = confirm_data.get("message_id")
            tool_response = execute_delete_email(service, mid)
            final_text = f"✅ **Email Deleted**: The email `{confirm_data.get('subject', mid)}` has been moved to Gmail Trash."
    else:
        tool_response = "Deletion was cancelled by the user."
        final_text = "❌ **Cancelled**: Deletion was cancelled. No emails were modified."

    history.append(ToolMessage(content=tool_response, tool_call_id=tool_call_id))
    return {
        "session_id": session_id,
        "status": "success",
        "action": req.action,
        "response": final_text,
    }


def find_available_port(start_port: int = 8000, max_attempts: int = 10) -> int:
    """Find an available port starting from start_port."""
    for p in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    return start_port


if __name__ == "__main__":
    import uvicorn
    port = find_available_port(8000)
    print(f"Starting server on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
