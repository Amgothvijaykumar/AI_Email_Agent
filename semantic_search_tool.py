import os
import json
import numpy as np
from dotenv import load_dotenv
from langchain_core.tools import tool
from gemini_client import embed_text

load_dotenv()

STORAGE_FILE = "email_embeddings.json"
EXPECTED_MODEL = "models/gemini-embedding-001"


def load_embeddings() -> list[dict]:
    """Load cached email embeddings from JSON index."""
    if not os.path.exists(STORAGE_FILE):
        raise FileNotFoundError(f"{STORAGE_FILE} not found. Run 'python email_indexer.py' first.")

    with open(STORAGE_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, dict):
        return data.get("emails", [])
    return data


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity score between two vectors."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0


def semantic_search(query: str, records: list[dict], top_k: int = 5) -> list[dict]:
    """Find the top-k most semantically relevant emails for a query."""
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


@tool
def search_emails_semantically(query: str) -> str:
    """
    Search indexed emails by concept, meaning, or topic using vector similarity.
    Use this for conceptual queries like 'machine learning internships' or 'hackathon events'.
    """
    try:
        records = load_embeddings()
    except FileNotFoundError as e:
        return str(e)

    if not records:
        return "Email index is empty. Run 'python email_indexer.py' first."

    results = semantic_search(query, records, top_k=5)
    if not results:
        return "No matching emails found."

    output = [f"Semantic search results for '{query}':\n"]
    for i, result in enumerate(results, start=1):
        email = result["record"]
        score = result["score"]
        preview = " ".join(email.get("body", "").split())[:200]
        output.append(
            f"{i}. [{score:.3f}] {email.get('subject', 'No Subject')}\n"
            f"   Message ID: {email.get('id', 'N/A')}\n"
            f"   Sender: {email.get('sender', 'N/A')}\n"
            f"   Date: {email.get('date', 'N/A')}\n"
            f"   Preview: {preview}..."
        )

    return "\n\n".join(output)


if __name__ == "__main__":
    print(search_emails_semantically.invoke({"query": "Python developer jobs"}))