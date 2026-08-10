# AI Gmail Agent — Powered by Gemini

A production-style AI Gmail agent that understands natural language and controls your Gmail inbox using Google Gemini as the LLM and the Gmail API for all email operations.

---

## Features

| Capability | Command Example |
|------------|-----------------|
| **Search Gmail** | `Find emails from Indeed` |
| **Read email** | `Read the Adobe hackathon email` |
| **Semantic search** | `Find emails related to machine learning` |
| **Mark as read** | `Mark the testing email as read` |
| **Mark as unread** | `Mark the Indeed email as unread` |
| **Star / Unstar** | `Star the Slack email` |
| **Archive** | `Archive the Groww digest` |
| **Safe delete** | `Delete the testing email` *(asks for confirmation)* |
| **Inbox overview** | `Give me an inbox overview` |
| **Categorize** | `Categorize my emails` |
| **Summarize** | `Summarize my job emails` |
| **Web UI Dashboard** | Interactive Web UI at `http://127.0.0.1:8000` |

---

## Architecture

```
USER
  |
  v
GEMINI (gemini-flash-latest with tool calling)
  |
  | decides which tool to use
  v
TOOL CONTROLLER (Python — controlled loop, dedup detection)
  |
  +------------------+-------------------+
  |                  |                   |
  v                  v                   v
search_gmail    read_gmail_email    search_emails_semantically
mark_as_read    mark_as_unread      (Gemini text-embedding-004)
star/archive    delete (safe)
get_overview
  |
  v
GMAIL API (OAuth2, gmail.modify scope)
  |
  v
GEMINI (generates final answer)
  |
  v
USER
```

---

## Setup

### 1. Clone and create virtual environment

```bash
git clone <your-repo>
cd AIGmailAgent
python -m venv avkve
source avkve/bin/activate
pip install -r requirements.txt
```

### 2. Set up Gmail OAuth

Go to [Google Cloud Console](https://console.cloud.google.com):
1. Create a project → Enable **Gmail API**
2. Create OAuth 2.0 credentials → Download as `credentials.json`
3. Place `credentials.json` in the project root
4. Run:

```bash
python gmail_auth.py
```

This opens a browser for authorization and creates `token.json`.

### 3. Set up Gemini API keys

Get keys at [Google AI Studio](https://aistudio.google.com/app/apikey).

Copy `.env.example` to `.env` and fill in your key(s):

```bash
cp .env.example .env
```

```env
GEMINI_API_KEY_1=your_key_here
GEMINI_API_KEY_2=optional_second_key
GEMINI_API_KEY_3=optional_third_key
```

> **Note:** If all keys are from the same Google Cloud project, quota is shared at the project level. Keys from different projects give independent quotas.

### 4. Build email index (for semantic search)

```bash
python email_indexer.py
```

This fetches your 50 most recent inbox emails and embeds them using Gemini `text-embedding-004` (768-dim). Only new emails are embedded on subsequent runs.

### 5. Run the Web UI Dashboard (Recommended)

```bash
python web_server.py
```
Open your browser at **`http://127.0.0.1:8000`**.

Features available in the Web UI:
- 💬 **AI Agent Chat & Tool Tracing**: Real-time tool execution logs with arguments and in-chat safety confirmation cards.
- 📥 **Smart Inbox & Reader Drawer**: Filter unread, starred, today's emails, and view complete email content with quick actions.
- 🏷️ **Gemini Categorizer & Bulk Cleaner**: Group today's emails (Jobs, Finance, Promotions, Social, etc.) and bulk trash unwanted newsletters.
- 🔍 **Semantic Vector Search Studio**: Concept-based search with cosine similarity match percentage meters.

### 6. Run via CLI (Optional)

```bash
python gmail_agent.py
```

---

## Usage Examples

```
Ask your Gmail agent: Find emails from Indeed
Ask your Gmail agent: Show unread emails
Ask your Gmail agent: Read the Adobe hackathon email
Ask your Gmail agent: Mark the testing with vijay email as read
Ask your Gmail agent: Find emails related to AI internships
Ask your Gmail agent: Give me an inbox overview
Ask your Gmail agent: Summarize my job emails
Ask your Gmail agent: Delete the testing email
```

> For deletion, the agent will show you the email details and ask for confirmation before deleting. Type `yes` to confirm or `no` to cancel.

---

## Testing

Run tests in this order:

```bash
# 1. Test Gmail connection
python gmail_service.py

# 2. Test Gmail search
python test_tool.py
python test_search.py

# 3. Test read and mark-read
python test_read_tool.py
python test_mark_read.py

# 4. Test Gemini connection
python test_gemini_chat.py

# 5. Test Gemini tool calling
python test_gemini_tools.py

# 6. Test semantic search (after indexing)
python test_semantic_tool.py

# 7. Run full agent
python gmail_agent.py
```

---

## Project Structure

```
AIGmailAgent/
│
├── gmail_agent.py          # Main agent (Gemini + controlled tool loop)
├── gemini_client.py        # Gemini LLM/embedding factory + key fallback
│
├── gmail_auth.py           # OAuth authentication (run once)
├── gmail_service.py        # Gmail API service factory
├── gmail_tools.py          # All Gmail LangChain tools
├── read_emails.py          # Gmail email reading/parsing utilities
│
├── email_indexer.py        # Build/update semantic search index
├── semantic_search_tool.py # Semantic email search (Gemini embeddings)
│
├── email_ai.py             # Single-email AI analysis
├── ai_email_agent.py       # Simple batch email analyzer
│
├── test_gemini_chat.py     # Test Gemini API connection
├── test_gemini_tools.py    # Test Gemini tool calling
├── test_tool.py            # Test search_gmail tool
├── test_search.py          # Test Gmail search
├── test_read_tool.py       # Test read_gmail_email tool
├── test_mark_read.py       # Test mark_email_as_read tool
├── test_semantic_tool.py   # Test semantic search
│
├── .env.example            # Environment variable template
├── .gitignore              # Excludes credentials, .env, embeddings
│
└── avkve/                  # Python virtual environment
```

---

## Key Safety Features

| Feature | Description |
|---------|-------------|
| **Duplicate detection** | Stops if Gemini calls the same tool with same args twice |
| **Message ID validation** | Rejects non-hex strings as message IDs (prevents hallucinated IDs) |
| **Delete confirmation** | Always asks user to confirm before any deletion |
| **Max iterations** | Hard cap of 5 tool calls per request |
| **Key + model fallback** | On quota errors, tries next model then next key |
| **No hardcoded secrets** | All keys in `.env`, never in source code |

---

## Gemini Models Used

| Purpose | Model |
|---------|-------|
| LLM / Agent | `gemini-flash-latest` (primary) with fallbacks |
| Embeddings | `text-embedding-004` (768-dim) |

**Model fallback chain:**
`gemini-flash-latest` → `gemini-3.5-flash` → `gemini-3.5-flash-lite` → `gemini-flash-lite-latest`

---

## Security

- `credentials.json` and `token.json` are **never committed** (in `.gitignore`)
- `.env` is **never committed** (in `.gitignore`)
- `email_embeddings.json` is **never committed** (contains personal email data)
- API keys are only loaded from environment variables via `python-dotenv`

---

## Gmail Scope

The agent uses `https://www.googleapis.com/auth/gmail.modify` which allows:
- Reading and searching emails
- Marking read/unread, starring, archiving
- Moving to Trash (delete)

It does **not** request `gmail.readonly` (too restrictive) or `gmail.full` (unnecessary).
