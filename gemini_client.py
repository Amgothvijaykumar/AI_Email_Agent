import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

load_dotenv()

LLM_MODELS = [
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
]

LLM_MODEL = LLM_MODELS[0]
EMBEDDING_MODEL = "models/gemini-embedding-001"


def _get_api_keys() -> list[str]:
    """Retrieve all available Gemini API keys from environment variables."""
    keys = []
    for i in range(1, 4):
        key = os.getenv(f"GEMINI_API_KEY_{i}", "").strip()
        if key:
            keys.append(key)

    plain_key = os.getenv("GEMINI_API_KEY", "").strip()
    if plain_key and plain_key not in keys:
        keys.append(plain_key)

    return keys


def get_gemini_llm(
    model: str = LLM_MODEL,
    temperature: float = 0,
) -> ChatGoogleGenerativeAI:
    """Initialize ChatGoogleGenerativeAI instance using the primary API key."""
    keys = _get_api_keys()
    if not keys:
        raise ValueError("No Gemini API key found. Set GEMINI_API_KEY_1 in .env.")

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
    """Invoke Gemini with automatic model and key rotation on rate limits."""
    keys = _get_api_keys()
    if not keys:
        raise ValueError("No Gemini API key found. Set GEMINI_API_KEY_1 in .env.")

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
                is_quota = any(w in error_str for w in ["429", "quota", "rate limit", "resource_exhausted", "limit: 0"])
                is_not_found = any(w in error_str for w in ["404", "not_found", "not supported", "no such model"])

                if is_quota or is_not_found:
                    last_error = e
                    continue
                raise

    raise RuntimeError(f"All Gemini models and keys exhausted. Last error: {last_error}")


def extract_text(response) -> str:
    """Extract plain text string from LangChain AIMessage response."""
    content = response.content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def get_gemini_embeddings(
    model: str = EMBEDDING_MODEL,
) -> GoogleGenerativeAIEmbeddings:
    """Initialize GoogleGenerativeAIEmbeddings client."""
    keys = _get_api_keys()
    if not keys:
        raise ValueError("No Gemini API key found for embeddings. Set GEMINI_API_KEY_1 in .env.")

    return GoogleGenerativeAIEmbeddings(
        model=model,
        google_api_key=keys[0],
    )


def embed_text(text: str) -> list[float]:
    """Generate a 3072-dimensional vector embedding for the input text."""
    embeddings = get_gemini_embeddings()
    return embeddings.embed_query(text)


if __name__ == "__main__":
    llm = get_gemini_llm()
    print("Gemini client initialized successfully.")
