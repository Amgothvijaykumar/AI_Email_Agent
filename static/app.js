/**
 * app.js
 * ======
 * Frontend application logic for AI Gmail Agent Web UI.
 */

// State
const state = {
    sessionId: null,
    currentTab: 'chat',
    activeEmail: null,
    selectedCategoryEmailIds: new Set(),
    categorizedData: null,
    isAgentThinking: false,
};

// DOM Elements
const elements = {
    navTabs: document.querySelectorAll('.nav-tab'),
    tabPanels: document.querySelectorAll('.tab-panel'),
    accountEmail: document.getElementById('accountEmail'),
    headerUnreadBadge: document.getElementById('headerUnreadBadge'),
    statUnreadCount: document.getElementById('statUnreadCount'),
    statIndexedCount: document.getElementById('statIndexedCount'),
    btnRefreshStatus: document.getElementById('btnRefreshStatus'),

    // Chat
    chatMessages: document.getElementById('chatMessages'),
    chatInput: document.getElementById('chatInput'),
    btnSend: document.getElementById('btnSend'),

    // Inbox
    filterBtns: document.querySelectorAll('.filter-btn'),
    inboxSearchInput: document.getElementById('inboxSearchInput'),
    btnRefreshInbox: document.getElementById('btnRefreshInbox'),
    emailListContainer: document.getElementById('emailListContainer'),

    // Categorizer
    btnRunCategorizer: document.getElementById('btnRunCategorizer'),
    categoryGridContainer: document.getElementById('categoryGridContainer'),
    bulkActionBar: document.getElementById('bulkActionBar'),
    bulkSelectedCount: document.getElementById('bulkSelectedCount'),
    btnBulkDeselect: document.getElementById('btnBulkDeselect'),
    btnBulkTrash: document.getElementById('btnBulkTrash'),

    // Semantic
    semanticSearchInput: document.getElementById('semanticSearchInput'),
    btnRunSemanticSearch: document.getElementById('btnRunSemanticSearch'),
    semanticResultsContainer: document.getElementById('semanticResultsContainer'),
    semanticIndexCount: document.getElementById('semanticIndexCount'),
    btnReindex: document.getElementById('btnReindex'),

    // Drawer
    readerDrawer: document.getElementById('readerDrawer'),
    readerDrawerOverlay: document.getElementById('readerDrawerOverlay'),
    drawerContent: document.getElementById('drawerContent'),
    btnCloseDrawer: document.getElementById('btnCloseDrawer'),
    drawerStarBtn: document.getElementById('drawerStarBtn'),
    drawerReadBtn: document.getElementById('drawerReadBtn'),
    drawerArchiveBtn: document.getElementById('drawerArchiveBtn'),
    drawerTrashBtn: document.getElementById('drawerTrashBtn'),

    // Toast
    toastContainer: document.getElementById('toastContainer'),
};


// ============================================================
// Initialization & Navigation
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    // Generate session ID
    state.sessionId = 'sess_' + Math.random().toString(36).substring(2, 12);

    setupNavigation();
    setupChat();
    setupInbox();
    setupCategorizer();
    setupSemanticSearch();
    setupDrawer();

    // Initial data fetch
    fetchStatus();
    loadInboxEmails('label:INBOX');
});

function setupNavigation() {
    elements.navTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.tab;
            switchTab(target);
        });
    });
}

function switchTab(tabId) {
    state.currentTab = tabId;

    elements.navTabs.forEach(t => t.classList.toggle('active', t.dataset.tab === tabId));
    elements.tabPanels.forEach(p => p.classList.toggle('active', p.id === `panel-${tabId}`));

    // Auto-fetch tab data if needed
    if (tabId === 'inbox' && !state.inboxLoaded) {
        loadInboxEmails('label:INBOX');
    }
}


// ============================================================
// Account Status & Sync
// ============================================================

async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();

        if (data.status === 'connected') {
            elements.accountEmail.textContent = data.account;
            elements.headerUnreadBadge.textContent = `${data.unread_count} unread`;
            elements.statUnreadCount.textContent = data.unread_count;
            elements.statIndexedCount.textContent = `${data.index_stats.total} emails`;
            elements.semanticIndexCount.textContent = data.index_stats.total;
        } else {
            elements.accountEmail.textContent = 'Auth Error';
        }
    } catch (e) {
        elements.accountEmail.textContent = 'Offline';
    }
}

if (elements.btnRefreshStatus) {
    elements.btnRefreshStatus.addEventListener('click', () => {
        fetchStatus();
        showToast('Account status updated', 'success');
    });
}


// ============================================================
// Markdown Parser Utility
// ============================================================

function parseMarkdown(text) {
    if (!text) return '';
    let html = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Headings
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // Bold & Italic
    html = html.replace(/\*\*\*(.*?)\*\*\*/gim, '<b><i>$1</i></b>');
    html = html.replace(/\*\*(.*?)\*\*/gim, '<b>$1</b>');
    html = html.replace(/\*(.*?)\*/gim, '<i>$1</i>');

    // Code blocks & Inline code
    html = html.replace(/```([\s\S]*?)```/gim, '<pre><code>$1</code></pre>');
    html = html.replace(/`([^`]+)`/gim, '<code>$1</code>');

    // Bullet Lists
    html = html.replace(/^\s*[\-\*]\s+(.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    // Line breaks
    html = html.replace(/\n\n+/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');

    return `<p>${html}</p>`;
}


// ============================================================
// TAB 1: AI Agent Chat & Live Tool Execution
// ============================================================

function setupChat() {
    elements.btnSend.addEventListener('click', handleSendMessage);
    elements.chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    });
}

window.sendPrompt = function(promptText) {
    elements.chatInput.value = promptText;
    handleSendMessage();
};

async function handleSendMessage() {
    const text = elements.chatInput.value.trim();
    if (!text || state.isAgentThinking) return;

    elements.chatInput.value = '';
    state.isAgentThinking = true;

    // Append User Message
    appendChatMessage('user', text);

    // Append Thinking Indicator
    const thinkingRow = appendThinkingIndicator();
    scrollToChatBottom();

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: state.sessionId,
                message: text,
            }),
        });

        const data = await res.json();
        thinkingRow.remove();

        if (res.ok) {
            appendAgentMessage(data);
        } else {
            appendChatMessage('assistant', `❌ **Error**: ${data.detail || 'Failed to process request.'}`);
        }

    } catch (e) {
        thinkingRow.remove();
        appendChatMessage('assistant', `❌ **Network Error**: ${e.message}`);
    } finally {
        state.isAgentThinking = false;
        scrollToChatBottom();
    }
}

function appendChatMessage(role, content) {
    const row = document.createElement('div');
    row.className = `message-row ${role}`;

    const avatar = document.createElement('div');
    avatar.className = `${role}-avatar`;
    avatar.textContent = role === 'user' ? '👤' : '🤖';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = parseMarkdown(content);

    row.appendChild(avatar);
    row.appendChild(bubble);
    elements.chatMessages.appendChild(row);

    return row;
}

function appendThinkingIndicator() {
    const row = document.createElement('div');
    row.className = 'message-row assistant';

    const avatar = document.createElement('div');
    avatar.className = 'agent-avatar';
    avatar.textContent = '🤖';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = `
        <div style="display:flex; align-items:center; gap:10px; color:#94a3b8;">
            <div class="spinner" style="width:18px; height:18px; border-width:2px;"></div>
            <span>Analyzing request & selecting tools with Gemini...</span>
        </div>
    `;

    row.appendChild(avatar);
    row.appendChild(bubble);
    elements.chatMessages.appendChild(row);

    return row;
}

function appendAgentMessage(data) {
    const row = document.createElement('div');
    row.className = 'message-row assistant';

    const avatar = document.createElement('div');
    avatar.className = 'agent-avatar';
    avatar.textContent = '🤖';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    // 1. Tool execution steps accordion
    if (data.steps && data.steps.length > 0) {
        const stepsContainer = document.createElement('div');
        stepsContainer.className = 'tool-steps-container';

        data.steps.forEach(step => {
            const stepCard = document.createElement('div');
            stepCard.className = 'tool-step-card';

            const header = document.createElement('div');
            header.className = 'tool-step-header';
            header.innerHTML = `
                <div class="tool-badge-left">
                    <span class="tool-status-dot"></span>
                    <span>Iteration ${step.iteration}:</span>
                    <span class="tool-name-tag">${step.tool}</span>
                </div>
                <span style="font-size:0.75rem; color:#94a3b8;">▼ Click to inspect</span>
            `;

            const body = document.createElement('div');
            body.className = 'tool-step-body';
            body.style.display = 'none';
            body.textContent = `Args:\n${JSON.stringify(step.args, null, 2)}\n\nResult:\n${step.result || '(no output)'}`;

            header.addEventListener('click', () => {
                body.style.display = body.style.display === 'none' ? 'block' : 'none';
            });

            stepCard.appendChild(header);
            stepCard.appendChild(body);
            stepsContainer.appendChild(stepCard);
        });

        bubble.appendChild(stepsContainer);
    }

    // 2. Final response text
    const textDiv = document.createElement('div');
    textDiv.innerHTML = parseMarkdown(data.response);
    bubble.appendChild(textDiv);

    // 3. Pending Delete Confirmation Card (Single or Batch)
    if (data.pending_confirmation) {
        const confirmData = data.pending_confirmation;
        const confirmCard = document.createElement('div');
        confirmCard.className = 'safety-confirm-card';

        let detailsHtml = '';
        let titleText = '⚠️ Safety Check: Move to Trash';
        let btnText = '🗑️ Move to Trash';

        if (confirmData.is_batch && confirmData.items) {
            titleText = `⚠️ Safety Check: Move ${confirmData.count} Emails to Trash`;
            btnText = `🗑️ Move all ${confirmData.count} to Trash`;
            
            let listItems = confirmData.items.map(item => `
                <div style="margin-bottom:6px; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:4px;">
                    <div style="font-weight:600; color:#ffffff;">• ${item.subject}</div>
                    <div style="font-size:0.75rem; color:#94a3b8;">From: ${item.sender.split('<')[0]} • ${item.date}</div>
                </div>
            `).join('');

            detailsHtml = `
                <div style="max-height:180px; overflow-y:auto; padding-right:4px;">
                    ${listItems}
                </div>
            `;
        } else {
            detailsHtml = `
                <div><b>Subject:</b> ${confirmData.subject}</div>
                <div><b>Sender:</b> ${confirmData.sender}</div>
                <div><b>Date:</b> ${confirmData.date}</div>
                <div><b>Preview:</b> <i>${confirmData.snippet || ''}</i></div>
            `;
        }

        confirmCard.innerHTML = `
            <div class="safety-header">
                <span>${titleText}</span>
            </div>
            <div class="safety-details">
                ${detailsHtml}
            </div>
            <div class="safety-actions">
                <button class="btn-cancel-trash" id="btnCancel_${confirmData.confirmation_id}">Cancel</button>
                <button class="btn-confirm-trash" id="btnConfirm_${confirmData.confirmation_id}">${btnText}</button>
            </div>
        `;

        bubble.appendChild(confirmCard);

        setTimeout(() => {
            const btnConfirm = document.getElementById(`btnConfirm_${confirmData.confirmation_id}`);
            const btnCancel = document.getElementById(`btnCancel_${confirmData.confirmation_id}`);

            btnConfirm.addEventListener('click', () => handleInChatDeleteConfirm(confirmData, 'confirm', confirmCard));
            btnCancel.addEventListener('click', () => handleInChatDeleteConfirm(confirmData, 'cancel', confirmCard));
        }, 50);
    }

    row.appendChild(avatar);
    row.appendChild(bubble);
    elements.chatMessages.appendChild(row);
}

async function handleInChatDeleteConfirm(confirmData, action, confirmCard) {
    confirmCard.innerHTML = `
        <div style="display:flex; align-items:center; gap:8px; color:#94a3b8;">
            <div class="spinner" style="width:16px; height:16px; border-width:2px;"></div>
            <span>Executing ${action === 'confirm' ? 'trash' : 'cancel'} action...</span>
        </div>
    `;

    try {
        const res = await fetch('/api/chat/confirm_delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: confirmData.session_id,
                confirmation_id: confirmData.confirmation_id,
                action: action,
            }),
        });

        const data = await res.json();
        if (res.ok) {
            confirmCard.innerHTML = parseMarkdown(data.response);
            showToast(action === 'confirm' ? 'Email moved to Trash' : 'Action cancelled', 'success');
            fetchStatus();
        } else {
            confirmCard.innerHTML = `<span style="color:#f43f5e;">Error: ${data.detail}</span>`;
        }
    } catch (e) {
        confirmCard.innerHTML = `<span style="color:#f43f5e;">Network Error: ${e.message}</span>`;
    }
}

function scrollToChatBottom() {
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}


// ============================================================
// TAB 2: Smart Inbox & Email Reader
// ============================================================

function setupInbox() {
    elements.filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            elements.filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const q = btn.dataset.query;
            elements.inboxSearchInput.value = '';
            loadInboxEmails(q);
        });
    });

    elements.btnRefreshInbox.addEventListener('click', () => {
        const activeBtn = document.querySelector('.filter-btn.active');
        const q = elements.inboxSearchInput.value.trim() || (activeBtn ? activeBtn.dataset.query : 'label:INBOX');
        loadInboxEmails(q);
    });

    elements.inboxSearchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            loadInboxEmails(elements.inboxSearchInput.value.trim() || 'label:INBOX');
        }
    });
}

async function loadInboxEmails(query = 'label:INBOX') {
    elements.emailListContainer.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <p>Fetching emails matching "${query}"...</p>
        </div>
    `;

    try {
        const res = await fetch(`/api/emails?q=${encodeURIComponent(query)}&max_results=25`);
        const data = await res.json();

        state.inboxLoaded = true;

        if (!data.emails || data.emails.length === 0) {
            elements.emailListContainer.innerHTML = `
                <div class="empty-state-card">
                    <span class="empty-icon">📭</span>
                    <h3>No emails found</h3>
                    <p>No messages match your query "${query}".</p>
                </div>
            `;
            return;
        }

        renderEmailList(data.emails);

    } catch (e) {
        elements.emailListContainer.innerHTML = `
            <div class="empty-state-card">
                <span class="empty-icon">⚠️</span>
                <h3>Failed to load emails</h3>
                <p>${e.message}</p>
            </div>
        `;
    }
}

function renderEmailList(emails) {
    elements.emailListContainer.innerHTML = '';

    emails.forEach(email => {
        const card = document.createElement('div');
        const isUnread = email.body && !email.is_read; // heuristic or label
        card.className = `email-card ${isUnread ? 'unread' : ''}`;

        const senderInitial = (email.sender || 'U').charAt(0).toUpperCase();
        const cleanSender = (email.sender || 'Unknown').split('<')[0].replace(/"/g, '').trim();

        card.innerHTML = `
            <div class="email-avatar">${senderInitial}</div>
            <div class="email-info">
                <div class="email-top-row">
                    <span class="email-sender">${cleanSender}</span>
                    <span class="email-date">${email.date || ''}</span>
                </div>
                <div class="email-subject">${email.subject || '(No Subject)'}</div>
                <div class="email-snippet">${(email.body || '').substring(0, 120).replace(/\n/g, ' ')}...</div>
            </div>
        `;

        card.addEventListener('click', () => openEmailReader(email.id));
        elements.emailListContainer.appendChild(card);
    });
}


// ============================================================
// EMAIL READER DRAWER
// ============================================================

function setupDrawer() {
    elements.btnCloseDrawer.addEventListener('click', closeEmailReader);
    elements.readerDrawerOverlay.addEventListener('click', closeEmailReader);

    elements.drawerStarBtn.addEventListener('click', () => executeDrawerAction('star'));
    elements.drawerReadBtn.addEventListener('click', () => executeDrawerAction('mark_unread'));
    elements.drawerArchiveBtn.addEventListener('click', () => executeDrawerAction('archive'));
    elements.drawerTrashBtn.addEventListener('click', () => {
        if (confirm('Are you sure you want to move this email to Gmail Trash?')) {
            executeDrawerAction('trash');
        }
    });
}

async function openEmailReader(messageId) {
    state.activeEmail = null;
    elements.readerDrawerOverlay.classList.add('active');
    elements.readerDrawer.classList.add('active');

    elements.drawerContent.innerHTML = `
        <div class="drawer-loading">
            <div class="spinner"></div>
            <p>Loading email content...</p>
        </div>
    `;

    try {
        const res = await fetch(`/api/email/${messageId}`);
        const email = await res.json();

        state.activeEmail = email;

        elements.drawerContent.innerHTML = `
            <div class="drawer-email-subject">${email.subject || '(No Subject)'}</div>
            <div class="drawer-email-meta">
                <div class="meta-row"><span class="meta-key">From:</span> <span class="meta-val-text">${email.sender || ''}</span></div>
                <div class="meta-row"><span class="meta-key">Date:</span> <span class="meta-val-text">${email.date || ''}</span></div>
                <div class="meta-row"><span class="meta-key">ID:</span> <span class="meta-val-text"><code>${email.id}</code></span></div>
            </div>
            <div class="drawer-email-body">${email.body || '(No body content)'}</div>
        `;

    } catch (e) {
        elements.drawerContent.innerHTML = `<p style="color:#f43f5e;">Failed to load email: ${e.message}</p>`;
    }
}

function closeEmailReader() {
    elements.readerDrawerOverlay.classList.remove('active');
    elements.readerDrawer.classList.remove('active');
}

async function executeDrawerAction(action) {
    if (!state.activeEmail) return;

    try {
        const res = await fetch(`/api/email/${state.activeEmail.id}/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action }),
        });

        const data = await res.json();
        if (res.ok) {
            showToast(data.message || `Action ${action} successful`, 'success');
            if (action === 'trash') {
                closeEmailReader();
                fetchStatus();
                loadInboxEmails();
            }
        } else {
            showToast(data.detail || 'Action failed', 'error');
        }
    } catch (e) {
        showToast(e.message, 'error');
    }
}


// ============================================================
// TAB 3: Gemini Categorizer & Bulk Cleaner
// ============================================================

function setupCategorizer() {
    elements.btnRunCategorizer.addEventListener('click', runCategorizer);
    elements.btnBulkDeselect.addEventListener('click', () => {
        state.selectedCategoryEmailIds.clear();
        updateBulkBar();
        document.querySelectorAll('.cat-checkbox').forEach(cb => cb.checked = false);
    });

    elements.btnBulkTrash.addEventListener('click', handleBulkTrash);
}

async function runCategorizer() {
    elements.categoryGridContainer.innerHTML = `
        <div class="loading-state" style="grid-column: 1/-1;">
            <div class="spinner"></div>
            <p>Gemini is categorizing today's emails with structured intent analysis...</p>
        </div>
    `;

    try {
        const res = await fetch('/api/categorize?days=1&max_results=25');
        const data = await res.json();

        state.categorizedData = data;
        state.selectedCategoryEmailIds.clear();
        updateBulkBar();

        renderCategoryGrid(data);

    } catch (e) {
        elements.categoryGridContainer.innerHTML = `
            <div class="empty-state-card">
                <span class="empty-icon">⚠️</span>
                <h3>Categorization Error</h3>
                <p>${e.message}</p>
            </div>
        `;
    }
}

function renderCategoryGrid(data) {
    elements.categoryGridContainer.innerHTML = '';
    const categories = data.categories;
    const meta = data.category_meta;

    Object.keys(categories).forEach(catKey => {
        const emails = categories[catKey];
        if (!emails || emails.length === 0) return;

        const info = meta[catKey] || { icon: '📧', color: '#94a3b8' };
        const card = document.createElement('div');
        card.className = 'category-card';

        let emailsHtml = '';
        emails.forEach(em => {
            emailsHtml += `
                <div class="cat-email-row">
                    <input type="checkbox" class="cat-checkbox" data-id="${em.id}">
                    <div class="cat-email-details" onclick="openEmailReader('${em.id}')" style="cursor:pointer;">
                        <div class="cat-email-sub">${em.subject || '(No subject)'}</div>
                        <div class="cat-email-from">${(em.sender || '').split('<')[0].trim()}</div>
                        <div class="cat-email-reason">${em.reason || ''}</div>
                    </div>
                </div>
            `;
        });

        card.innerHTML = `
            <div class="category-card-header">
                <div class="cat-badge" style="color: ${info.color}">
                    <span>${info.icon}</span>
                    <span>${catKey}</span>
                    <span class="cat-count">${emails.length}</span>
                </div>
                <button class="cat-select-all" data-cat="${catKey}">Select All</button>
            </div>
            <div class="cat-emails">
                ${emailsHtml}
            </div>
        `;

        elements.categoryGridContainer.appendChild(card);
    });

    // Checkbox and Select-All handlers
    document.querySelectorAll('.cat-checkbox').forEach(cb => {
        cb.addEventListener('change', (e) => {
            const id = e.target.dataset.id;
            if (e.target.checked) state.selectedCategoryEmailIds.add(id);
            else state.selectedCategoryEmailIds.delete(id);
            updateBulkBar();
        });
    });

    document.querySelectorAll('.cat-select-all').forEach(btn => {
        btn.addEventListener('click', () => {
            const cat = btn.dataset.cat;
            const emails = data.categories[cat] || [];
            emails.forEach(em => {
                state.selectedCategoryEmailIds.add(em.id);
            });
            document.querySelectorAll('.cat-checkbox').forEach(cb => {
                if (state.selectedCategoryEmailIds.has(cb.dataset.id)) cb.checked = true;
            });
            updateBulkBar();
        });
    });
}

function updateBulkBar() {
    const count = state.selectedCategoryEmailIds.size;
    elements.bulkSelectedCount.textContent = count;
    elements.bulkActionBar.style.display = count > 0 ? 'flex' : 'none';
}

async function handleBulkTrash() {
    const count = state.selectedCategoryEmailIds.size;
    if (count === 0) return;

    if (!confirm(`Are you sure you want to move ${count} selected email(s) to Gmail Trash?`)) {
        return;
    }

    try {
        const res = await fetch('/api/bulk_trash', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message_ids: Array.from(state.selectedCategoryEmailIds) }),
        });

        const data = await res.json();
        showToast(data.message || 'Emails moved to Trash', 'success');
        state.selectedCategoryEmailIds.clear();
        updateBulkBar();
        runCategorizer();
        fetchStatus();

    } catch (e) {
        showToast(e.message, 'error');
    }
}


// ============================================================
// TAB 4: Semantic Vector Search Studio
// ============================================================

function setupSemanticSearch() {
    elements.btnRunSemanticSearch.addEventListener('click', handleSemanticSearch);
    elements.semanticSearchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleSemanticSearch();
    });

    elements.btnReindex.addEventListener('click', handleReindex);
}

window.runSemanticQuery = function(queryText) {
    elements.semanticSearchInput.value = queryText;
    handleSemanticSearch();
};

async function handleSemanticSearch() {
    const q = elements.semanticSearchInput.value.trim();
    if (!q) return;

    elements.semanticResultsContainer.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <p>Calculating 3072-dimensional vector cosine similarity for "${q}"...</p>
        </div>
    `;

    try {
        const res = await fetch('/api/semantic_search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: q, top_k: 6 }),
        });

        const data = await res.json();

        if (!data.results || data.results.length === 0) {
            elements.semanticResultsContainer.innerHTML = `
                <div class="empty-state-card">
                    <span class="empty-icon">🔍</span>
                    <h3>No matching vector results</h3>
                    <p>Try a different concept or sync your embeddings index.</p>
                </div>
            `;
            return;
        }

        renderSemanticResults(data.results);

    } catch (e) {
        elements.semanticResultsContainer.innerHTML = `
            <div class="empty-state-card">
                <span class="empty-icon">⚠️</span>
                <h3>Vector Search Error</h3>
                <p>${e.message}</p>
            </div>
        `;
    }
}

function renderSemanticResults(results) {
    elements.semanticResultsContainer.innerHTML = '';

    results.forEach(item => {
        const card = document.createElement('div');
        card.className = 'semantic-card';

        const isHigh = item.match_percentage >= 70;

        card.innerHTML = `
            <div class="semantic-card-top">
                <span class="semantic-card-subject">${item.subject || '(No Subject)'}</span>
                <span class="match-pill ${isHigh ? 'high' : ''}">${item.match_percentage}% Match (${item.similarity_score})</span>
            </div>
            <div class="semantic-card-meta">
                <span>From: ${(item.sender || '').split('<')[0]}</span> • <span>${item.date || ''}</span>
            </div>
            <div class="semantic-card-preview">${item.preview || ''}</div>
        `;

        card.addEventListener('click', () => openEmailReader(item.id));
        elements.semanticResultsContainer.appendChild(card);
    });
}

async function handleReindex() {
    elements.btnReindex.disabled = true;
    elements.btnReindex.innerHTML = '<span>⏳ Syncing...</span>';

    try {
        const res = await fetch('/api/reindex', { method: 'POST' });
        const data = await res.json();
        showToast(data.message || 'Indexing started', 'success');

        // Poll status after 5 seconds
        setTimeout(async () => {
            const stRes = await fetch('/api/reindex/status');
            const stData = await stRes.json();
            elements.semanticIndexCount.textContent = stData.total_indexed;
            elements.statIndexedCount.textContent = `${stData.total_indexed} emails`;
            elements.btnReindex.disabled = false;
            elements.btnReindex.innerHTML = '<span>🔄 Sync Index</span>';
            showToast(`Index updated: ${stData.total_indexed} emails`, 'success');
        }, 6000);

    } catch (e) {
        showToast(e.message, 'error');
        elements.btnReindex.disabled = false;
        elements.btnReindex.innerHTML = '<span>🔄 Sync Index</span>';
    }
}


// ============================================================
// Toast Notification Utility
// ============================================================

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        toast.style.transition = 'all 0.25s ease';
        setTimeout(() => toast.remove(), 250);
    }, 3500);
}
