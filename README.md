# AI Gmail Agent & Copilot — Powered by Google Gemini

A production-ready, intelligent AI Gmail agent and web dashboard that understands natural language to search, categorize, read, star, archive, and safely trash emails using Google Gemini LLMs and official Gmail API.

---

## 🌟 Key Features

| Feature | Description | Example Request |
|---------|-------------|-----------------|
| 💬 **AI Agent Copilot** | Natural language tool-controlled assistant with step-by-step reasoning | *"Find my unread emails from Indeed"* |
| 🌐 **Modern Web UI Dashboard** | Interactive glassmorphic single-page dashboard at `http://127.0.0.1:8000` | Open browser for full UI |
| 🛡️ **Interactive Safety Checks** | In-chat and CLI confirmation cards before trashing single or batch emails | *"Delete the test email"* |
| 🗑️ **Batch & Bunch Trashing** | Safely bulk delete matching emails (promotions, newsletters, senders) | *"Delete all promotional emails from today"* |
| 🏷️ **Gemini Email Categorizer** | Groups emails into 8 intent categories (*Jobs, Finance, Promotions, Social, Security, Personal, Important, Other*) | *"Categorize today's emails"* |
| 🔍 **Semantic Vector Search** | Concept search using 3072-dimensional Gemini embeddings (`models/gemini-embedding-001`) | *"Find emails related to hackathons"* |
| 📥 **Smart Inbox & Drawer Reader** | Filter unread, starred, today's emails and read full bodies with one-click actions | Instant filter and sliding drawer reader |
| 🕒 **Local IST Time Normalization** | Converts raw international email timestamps to clean local Indian Standard Time | Automatic timezone formatting |
| 🔄 **Multi-Key & Model Fallback** | Resilient rotation across Gemini models and multiple API keys on rate limits | Auto-fallback on `429` quota limits |
| 🔐 **Permanent OAuth Auth** | Google Cloud Production configuration ensuring tokens never expire | One-time OAuth setup |

---

## 🏗️ Architecture

```
                                    +----------------------------------------------------+
                                    |                User Interfaces                     |
                                    |  • Modern Web UI Dashboard (FastAPI + SPA)        |
                                    |  • Interactive CLI Agent (gmail_agent.py)          |
                                    +----------------------------------------------------+
                                                             |
                                                             v
                                    +----------------------------------------------------+
                                    |             Gemini LLM Tool Controller             |
                                    |  (Model fallback chain + multi-key rotation)       |
                                    +----------------------------------------------------+
                                                             |
                                        Decides and executes tools autonomously:
                                                             |
                 +-------------------+-----------------------+-----------------------+-------------------+
                 |                   |                       |                       |                   |
                 v                   v                       v                       v                   v
          search_gmail        read_gmail_email        batch_delete_emails      get_inbox_overview  search_emails_semantically
          mark_email_read     star / unstar           delete_email (single)   (strict midnight)   (Gemini 3072-dim vectors)
          mark_email_unread   archive_email          (safety confirmation)
                 |                   |                       |                       |                   |
                 +-------------------+-----------------------+-----------------------+-------------------+
                                                             |
                                                             v
                                    +----------------------------------------------------+
                                    |            Official Gmail API (OAuth2)             |
                                    |         Scope: .../auth/gmail.modify               |
                                    +----------------------------------------------------+
                                                             |
                                                             v
                                    +----------------------------------------------------+
                                    |               Gemini Final Response                |
                                    |   Formatted Markdown + Step Tracing + Action Cards |
                                    +----------------------------------------------------+
```

---

## 🚀 Getting Started

### 1. Clone & Setup Virtual Environment

```bash
git clone https://github.com/Amgothvijaykumar/AI_Email_Agent.git
cd AI_Email_Agent
python -m venv avkve
source avkve/bin/activate
pip install -r requirements.txt
```

### 2. Configure Gemini API Keys

Get your free Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey).

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Add your keys to `.env`:
```env
GEMINI_API_KEY_1=AIzaSy...
GEMINI_API_KEY_2=AIzaSy... (optional backup key)
GEMINI_API_KEY_3=AIzaSy... (optional backup key)
```

### 3. Google Cloud OAuth Setup (Permanent Mode)

1. In [Google Cloud Console](https://console.cloud.google.com), create a project and enable **Gmail API**.
2. Go to **OAuth Consent Screen**:
   - Set User Type to **External**.
   - Click **"Publish App"** (moves publishing status from *Testing* to *In Production* so tokens never expire).
3. Create **OAuth 2.0 Client ID (Desktop Application)** → Download as `credentials.json` into project root.
4. Run one-time authentication:
   ```bash
   python gmail_auth.py
   ```
   *This saves your permanent production token in `token.json`.*

### 4. Build Semantic Vector Index

```bash
python email_indexer.py
```
*Embeds recent emails with 3072-dimensional Gemini vectors into `email_embeddings.json`. Subsequent runs are incremental and only index new emails.*

---

## 💻 Running the Application

### Option 1: Modern Web UI Dashboard (Recommended)

```bash
source avkve/bin/activate
python web_server.py
```
👉 Open **`http://127.0.0.1:8000`** in your browser.

#### Web Dashboard Panels:
1. 💬 **AI Agent Chat**: Real-time tool execution logs, quick prompt chips, and in-chat delete confirmation cards.
2. 📥 **Smart Inbox**: Search bar supporting Gmail queries (`is:unread`, `from:`, `subject:`), quick filters, and sliding Email Reader drawer.
3. 🏷️ **Gemini Categorizer**: Visual grid grouping today's emails with multi-select checkboxes to bulk clean clutter.
4. 🔍 **Semantic Search Studio**: Vector similarity search with percentage match meters and one-click index sync.

---

### Option 2: Command Line Interface (CLI)

```bash
source avkve/bin/activate
python gmail_agent.py
```

Example commands:
- `Show unread emails`
- `Find emails from Indeed`
- `Read the Adobe hackathon email`
- `Categorize today's emails`
- `Delete all promotional emails from today` *(prompts for confirmation)*
- `Find emails related to machine learning internships` *(uses semantic vector search)*

---

### Option 3: Bulk Categorize & Delete Script

```bash
python categorize_and_delete.py
```
*Fetches today's emails, categorizes them with Gemini, displays grouped numbered lists, and lets you select whole categories or individual emails to review and trash.*

---

## 📂 Project Structure

```
AIGmailAgent/
│
├── web_server.py             # FastAPI backend (REST API + static file server)
├── static/                   # Web UI Single Page Application
│   ├── index.html            # Dashboard layout (Chat, Inbox, Categorizer, Search)
│   ├── style.css             # Modern glassmorphic dark design system
│   └── app.js                # Frontend state, API integration & UI logic
│
├── gmail_agent.py            # CLI AI Agent with controlled tool execution loop
├── gemini_client.py          # Gemini LLM/Embedding client with model & key fallback
│
├── gmail_auth.py             # One-time OAuth credentials setup script
├── gmail_service.py          # Gmail API connection factory & token auto-refresher
├── gmail_tools.py            # LangChain Gmail Tools (search, read, star, delete, etc.)
├── read_emails.py            # Email parsing, HTML cleaner & local IST date formatter
│
├── email_indexer.py          # Incremental vector indexer (3072-dim embeddings)
├── semantic_search_tool.py   # Semantic search tool (cosine similarity)
│
├── categorize_and_delete.py  # Standalone CLI categorizer & bulk cleaner
├── email_ai.py               # Single email analysis helper
├── ai_email_agent.py         # Batch email analysis script
│
├── .env.example              # Template for API keys
├── .gitignore                # Protects credentials, tokens, .env, index
└── README.md                 # Project documentation
```

---

## 🛡️ Safety & Reliability Features

| Feature | Protection Mechanism |
|---------|----------------------|
| **Safe Deletions** | All delete operations move emails to **Gmail Trash** (recoverable within 30 days) rather than permanently purging. |
| **Human-in-the-Loop Confirmation** | Deletions (single or batch) ALWAYS pause and require explicit user confirmation via UI card or CLI prompt. |
| **Strict Midnight Filter** | "Today's" email queries filter strictly from `00:00:00` local time instead of rolling 24-hour windows. |
| **Duplicate Tool Detection** | Stops loops immediately if the LLM calls the same tool with identical arguments. |
| **Message ID Validation** | Rejects natural language or hallucinated IDs, enforcing valid 16-character hexadecimal Gmail IDs. |
| **Model Fallback Chain** | `gemini-flash-latest` → `gemini-3.5-flash` → `gemini-3.5-flash-lite` → `gemini-flash-lite-latest` on quota or 404 errors. |
| **Loop Limits** | Hard limit of 5 tool iterations per user query to prevent infinite execution. |

---

## 🧠 Gemini Models & Specifications

- **LLM / Agent**: `gemini-flash-latest` (Primary) with automated fallback chain.
- **Embedding Model**: `models/gemini-embedding-001` (3072-dimensional vector space).
- **Gmail Scope**: `https://www.googleapis.com/auth/gmail.modify` (Read, modify labels, move to trash).
