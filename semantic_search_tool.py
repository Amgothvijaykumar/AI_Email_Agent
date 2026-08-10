"""
semantic_search_tool.py
=======================
Semantic email search using Gemini text-embedding-004.

Loads pre-built email index from email_embeddings.json,
generates a query embedding using Gemini, and returns
the top-K most similar emails by cosine similarity.

Run email_indexer.py first to build the index.
"""

import os
import json

import numpy as np
from dotenv import load_dotenv
from langchain_core.tools import tool

from gemini_client import embed_text

# Load .env if present
load_dotenv()

# ============================================================
# Configuration
# ============================================================

STORAGE_FILE = "email_embeddings.json"

# Must match the model used in email_indexer.py
EXPECTED_MODEL = "models/gemini-embedding-001"


# ============================================================
# Load saved email embeddings
# ============================================================

def load_embeddings() -> list[dict]:
    """
    Load email embeddings from local JSON index.

    Returns:
        List of email records, each containing:
        id, sender, subject, date, body, embedding

    Raises:
        FileNotFoundError: If the index file doesn't exist.
        ValueError: If the index was built with a different model.
    """
    if not os.path.exists(STORAGE_FILE):
        raise FileNotFoundError(
            f"{STORAGE_FILE} not found.\n"
            "Run: python email_indexer.py\n"
            "to build the email index first."
        )

    with open(STORAGE_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    # Handle both old format (list) and new format (dict with metadata)
    if isinstance(data, dict):
        model_used = data.get("embedding_model", "unknown")
        records = data.get("emails", [])

        if model_used != EXPECTED_MODEL:
            print(
                f"⚠️  Warning: Index was built with '{model_used}', "
                f"but query uses '{EXPECTED_MODEL}'.\n"
                "Run: python email_indexer.py  to rebuild the index."
            )
    else:
        # Old format: plain list of records
        records = data

    return records


# ============================================================
# Cosine similarity
# ============================================================

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)

    denom = np.linalg.norm(a) * np.linalg.norm(b)

    if denom == 0:
        return 0.0

    return float(np.dot(a, b) / denom)


# ============================================================
# Semantic search
# ============================================================

def semantic_search(
    query: str,
    records: list[dict],
    top_k: int = 5,
) -> list[dict]:
    """
    Find the most semantically similar emails to a query.

    Args:
        query: Natural language search query
        records: List of email records with embeddings
        top_k: Number of top results to return

    Returns:
        List of dicts: {"record": {...}, "score": float}
    """
    query_embedding = embed_text(query)

    scored = []

    for record in records:
        emb = record.get("embedding")

        if not emb:
            continue

        score = cosine_similarity(query_embedding, emb)
        scored.append({"record": record, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)

    return scored[:top_k]


# ============================================================
# LangChain Tool
# ============================================================

@tool
def search_emails_semantically(query: str) -> str:
    """
    Search Gmail emails semantically using saved email embeddings
    and Gemini text embeddings.

    Use this tool ONLY when the user is searching by MEANING or TOPIC,
    not by exact sender/subject/date.

    Good for:
    - "emails related to machine learning"
    - "emails about internship opportunities"
    - "emails about AI hackathons"
    - "emails concerning Python development"

    NOT for:
    - "emails from Indeed" (use search_gmail with from:Indeed)
    - "unread emails" (use search_gmail with is:unread)
    - "emails with attachments" (use search_gmail with has:attachment)
    - modifying a specific email

    Returns:
        Top matching emails with Message IDs for further actions.
    """
    try:
        records = load_embeddings()
    except FileNotFoundError as e:
        return str(e)

    if not records:
        return (
            "Email index is empty. "
            "Run: python email_indexer.py  to build the index."
        )

    results = semantic_search(query, records, top_k=5)

    if not results:
        return "No matching emails found."

    output_lines = [
        f"Semantic search results for: '{query}'\n"
    ]

    for i, result in enumerate(results, start=1):
        email = result["record"]
        score = result["score"]

        preview = " ".join(email.get("body", "").split())[:250]
        if len(email.get("body", "")) > 250:
            preview += "..."

        output_lines.append(
            f"{i}. [{score:.3f}] {email.get('subject', 'No Subject')}\n"
            f"   Message ID: {email.get('id', 'N/A')}\n"
            f"   Sender: {email.get('sender', 'N/A')}\n"
            f"   Date: {email.get('date', 'N/A')}\n"
            f"   Preview: {preview}"
        )

    return "\n\n".join(output_lines)


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    query = input("Semantic search query: ").strip()

    if not query:
        query = "Python developer jobs"

    print(f"\nSearching for: '{query}'\n")

    result = search_emails_semantically.invoke({"query": query})
    print(result)