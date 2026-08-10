import os
import requests
import numpy as np


API_KEY = os.getenv("OPENROUTER_API_KEY")

if not API_KEY:
    raise ValueError("OPENROUTER_API_KEY is not set")


URL = "https://openrouter.ai/api/v1/embeddings"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def get_embedding(text):
    data = {
        "model": "nvidia/nemotron-3-embed-1b:free",
        "input": text,
        "encoding_format": "float",
    }

    response = requests.post(
        URL,
        headers=HEADERS,
        json=data,
        timeout=60,
    )

    response.raise_for_status()

    return response.json()["data"][0]["embedding"]


def cosine_similarity(vector_a, vector_b):
    a = np.array(vector_a)
    b = np.array(vector_b)

    return np.dot(a, b) / (
        np.linalg.norm(a) * np.linalg.norm(b)
    )


text1 = "Python developer internship opportunity"
text2 = "Machine learning internship for students"
text3 = "Python developer job opening"


print("Generating embeddings...\n")

embedding1 = get_embedding(text1)
embedding2 = get_embedding(text2)
embedding3 = get_embedding(text3)


similarity_1_2 = cosine_similarity(
    embedding1,
    embedding2
)

similarity_1_3 = cosine_similarity(
    embedding1,
    embedding3
)


print("Text 1:", text1)
print("Text 2:", text2)
print("Text 3:", text3)

print("\nCosine similarities:")

print(
    "Text 1 ↔ Text 2:",
    round(similarity_1_2, 4)
)

print(
    "Text 1 ↔ Text 3:",
    round(similarity_1_3, 4)
)