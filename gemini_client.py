"""
gemini_client.py
================
Gemini API key manager and LLM/embedding factory.

Loads GEMINI_API_KEY_1, GEMINI_API_KEY_2, GEMINI_API_KEY_3
from environment variables (via .env file or shell export).

Usage:
    from gemini_client import get_gemini_llm, get_gemini_embeddings

    llm = get_gemini_llm()
    embeddings = get_gemini_embeddings()
"""

import os
from dotenv import load_dotenv

from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings,
)

# Load .env file if present
load_dotenv()


# ============================================================
# Model configuration
# ============================================================

# Model fallback chain — confirmed working from live API test
# All support tool/function calling
LLM_MODELS = [
    "gemini-flash-latest",    # Primary: confirmed working ✓
    "gemini-3.5-flash",       # Fallback 1: confirmed working ✓
    "gemini-3.5-flash-lite",  # Fallback 2: confirmed working ✓
    "gemini-flash-lite-latest",# Fallback 3: confirmed working ✓
]

LLM_MODEL = LLM_MODELS[0]  # Default primary model

# gemini-embedding-001: confirmed working, 3072-dim vectors
EMBEDDING_MODEL = "models/gemini-embedding-001"



# ============================================================
# Collect available API keys
# ============================================================

def _get_api_keys() -> list[str]:
    """
    Collect all non-empty Gemini API keys from environment.
    Returns a list of available keys.
    """
    keys = []

    for i in range(1, 4):
        key = os.getenv(f"GEMINI_API_KEY_{i}", "").strip()
        if key:
            keys.append(key)

    # Also accept plain GEMINI_API_KEY as fallback
    plain_key = os.getenv("GEMINI_API_KEY", "").strip()
    if plain_key and plain_key not in keys:
        keys.append(plain_key)

    return keys


# ============================================================
# LLM factory with key fallback
# ============================================================

def get_gemini_llm(
    model: str = LLM_MODEL,
    temperature: float = 0,
) -> ChatGoogleGenerativeAI:
    """
    Return a ChatGoogleGenerativeAI instance using the first
    available Gemini API key.

    Args:
        model: Gemini model name. Default: gemini-2.0-flash
        temperature: 0 = deterministic. Default: 0

    Returns:
        ChatGoogleGenerativeAI instance

    Raises:
        ValueError: If no API key is found in the environment.
    """
    keys = _get_api_keys()

    if not keys:
        raise ValueError(
            "No Gemini API key found.\n"
            "Set GEMINI_API_KEY_1 (or GEMINI_API_KEY) in your .env file.\n"
            "See .env.example for the template."
        )

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=keys[0],
        temperature=temperature,
    )


def invoke_with_fallback(
    messages: list,
    tools: list = None,
    temperature: float = 0,
) -> object:
    """
    Invoke Gemini with automatic key + model fallback.

    Strategy:
        For each API key → for each model in LLM_MODELS:
            Try the request.
            On 429/quota error: try next model, then next key.
            On other errors: raise immediately.

    Args:
        messages: LangChain message list
        tools: Optional list of LangChain tools to bind
        temperature: LLM temperature (default 0)

    Returns:
        LangChain AI message response

    Raises:
        RuntimeError: If all keys and models are exhausted.
    """
    keys = _get_api_keys()

    if not keys:
        raise ValueError(
            "No Gemini API key found. "
            "Set GEMINI_API_KEY_1 in your .env file."
        )

    last_error = None

    for key in keys:
        for model in LLM_MODELS:
            try:
                llm = ChatGoogleGenerativeAI(
                    model=model,
                    google_api_key=key,
                    temperature=temperature,
                )

                if tools:
                    llm = llm.bind_tools(tools)

                return llm.invoke(messages)

            except Exception as e:
                error_str = str(e).lower()

                is_quota = any(word in error_str for word in [
                    "429", "quota", "rate limit",
                    "resource_exhausted", "limit: 0",
                ])
                is_not_found = any(word in error_str for word in [
                    "404", "not_found", "not found",
                    "not supported", "no such model",
                ])

                if is_quota:
                    print(
                        f"  ⚠️  Quota exceeded for {model} "
                        f"(key ...{key[-6:]}), trying next..."
                    )
                    last_error = e
                    continue  # try next model
                elif is_not_found:
                    # Model name not valid for this API version — skip silently
                    last_error = e
                    continue  # try next model
                else:
                    raise  # unexpected error: surface it immediately

    raise RuntimeError(
        f"All Gemini API keys and models exhausted.\n"
        f"Last error: {last_error}\n"
        "Options:\n"
        "  1. Wait for quota reset (usually resets per minute or per day)\n"
        "  2. Add API keys from different Google Cloud projects\n"
        "  3. Enable billing at https://console.cloud.google.com"
    )


def extract_text(response) -> str:
    """
    Extract plain text from a Gemini LangChain response.

    Newer Gemini models return content as a list of dicts:
        [{'type': 'text', 'text': '...', ...}]
    Older models return a plain string.
    This helper handles both formats uniformly.

    Args:
        response: LangChain AIMessage response object

    Returns:
        Plain text string
    """
    content = response.content

    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )

    return str(content)



# Embedding factory
# ============================================================

def get_gemini_embeddings(
    model: str = EMBEDDING_MODEL,
) -> GoogleGenerativeAIEmbeddings:
    """
    Return a GoogleGenerativeAIEmbeddings instance.

    Model: text-embedding-004 (768-dim vectors)

    Args:
        model: Embedding model name.

    Returns:
        GoogleGenerativeAIEmbeddings instance
    """
    keys = _get_api_keys()

    if not keys:
        raise ValueError(
            "No Gemini API key found for embeddings.\n"
            "Set GEMINI_API_KEY_1 in your .env file."
        )

    return GoogleGenerativeAIEmbeddings(
        model=model,
        google_api_key=keys[0],
    )


def embed_text(text: str) -> list[float]:
    """
    Generate an embedding vector for a single text string.

    Args:
        text: The text to embed.

    Returns:
        List of floats (3072-dimensional vector from gemini-embedding-001).
    """
    embeddings = get_gemini_embeddings()
    return embeddings.embed_query(text)


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    print("Testing Gemini client...")
    print()

    keys = _get_api_keys()
    print(f"Found {len(keys)} API key(s)")

    if not keys:
        print("❌ No keys found. Set GEMINI_API_KEY_1 in .env")
    else:
        print("✓ Keys loaded")
        print()

        # Test LLM
        print("Testing LLM (gemini-2.0-flash)...")
        llm = get_gemini_llm()
        from langchain_core.messages import HumanMessage
        response = llm.invoke([HumanMessage(content="Say: Gemini ready")])
        print("LLM response:", response.content)
        print()

        # Test embeddings
        print("Testing embeddings (text-embedding-004)...")
        vec = embed_text("Hello, Gmail agent")
        print(f"Embedding dimensions: {len(vec)}")
        print("✓ Gemini client working correctly")
