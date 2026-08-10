import os
import json
import requests
import numpy as np


# ==========================================
# Configuration
# ==========================================

API_KEY = os.getenv("OPENROUTER_API_KEY")

if not API_KEY:
    raise ValueError("OPENROUTER_API_KEY is not set")

EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"

MODEL = "nvidia/nemotron-3-embed-1b:free"

STORAGE_FILE = "email_embeddings.json"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


# ==========================================
# Generate query embedding
# ==========================================

def get_embedding(text):

    data = {
        "model": MODEL,
        "input": text,
        "encoding_format": "float",
    }

    response = requests.post(
        EMBEDDING_URL,
        headers=HEADERS,
        json=data,
        timeout=60,
    )

    response.raise_for_status()

    return response.json()["data"][0]["embedding"]


# ==========================================
# Load stored embeddings
# ==========================================

def load_embeddings():

    if not os.path.exists(STORAGE_FILE):
        raise FileNotFoundError(
            f"{STORAGE_FILE} not found. "
            "Run test_embedding_storage.py first."
        )

    with open(
        STORAGE_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ==========================================
# Cosine similarity
# ==========================================

def cosine_similarity(a, b):

    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)

    denominator = (
        np.linalg.norm(a) *
        np.linalg.norm(b)
    )

    if denominator == 0:
        return 0.0

    return float(
        np.dot(a, b) / denominator
    )


# ==========================================
# Semantic search
# ==========================================

def semantic_search(
    query,
    records,
    top_k=5
):

    print("Generating query embedding...")

    query_embedding = get_embedding(query)

    results = []

    for record in records:

        score = cosine_similarity(
            query_embedding,
            record["embedding"]
        )

        results.append({
            "record": record,
            "score": score
        })

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return results[:top_k]


# ==========================================
# Main
# ==========================================

print("Loading saved embeddings...")

records = load_embeddings()

print(
    f"Loaded {len(records)} email embeddings"
)

print(
    f"Vector dimensions: "
    f"{len(records[0]['embedding'])}"
)

print(
    "\nNo Gmail API call is being made."
)

print(
    "Only the query will be sent to OpenRouter."
)


# ==========================================
# User query
# ==========================================

query = input(
    "\nWhat emails are you looking for?\n> "
)

print(
    "\nSearching saved embeddings...\n"
)

results = semantic_search(
    query,
    records,
    top_k=5
)


# ==========================================
# Display results
# ==========================================

print("=" * 70)
print("SEMANTIC SEARCH RESULTS")
print("=" * 70)

for i, result in enumerate(
    results,
    start=1
):

    email = result["record"]

    print(
        f"\n{i}. {email['subject']}"
    )

    print(
        f"   Sender: {email['sender']}"
    )

    print(
        f"   Date: {email['date']}"
    )

    print(
        f"   Similarity: "
        f"{result['score']:.4f}"
    )

    body = email["body"].strip()

    if body:

        preview = " ".join(
            body.split()
        )[:200]

        print(
            f"   Preview: {preview}..."
        )