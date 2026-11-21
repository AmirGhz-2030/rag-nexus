const API_BASE = 'http://localhost:8000/api/v1';

// DOM Elements
const fileInput = document.getElementById('fileInput');
const dropZone = document.getElementById('dropZone');
const uploadStatus = document.getElementById('uploadStatus');
const queryInput = document.getElementById('queryInput');
const sendBtn = document.getElementById('sendBtn');
const chatMessages = document.getElementById('chatMessages');
const chunksList = document.getElementById('chunksList');
const chunksCount = document.getElementById('chunksCount');
const retrievedCount = document.getElementById('retrievedCount');
const latencyBadge = document.getElementById('latencyBadge');

const topKInput = document.getElementById('topK');
const topKVal = document.getElementById('topKVal');
const alphaSlider = document.getElementById('alphaSlider');
const alphaVal = document.getElementById('alphaVal');

const indexedFilesSection = document.getElementById('indexedFilesSection');
const indexedFilesList = document.getElementById('indexedFilesList');
const clearIndexBtn = document.getElementById('clearIndexBtn');
const exportChatBtn = document.getElementById('exportChatBtn');
const clearChatBtn = document.getElementById('clearChatBtn');

// Chat Memory & LocalStorage
let chatHistory = JSON.parse(localStorage.getItem('rag_nexus_chat_history') || '[]');

// Event Listeners for Sliders
topKInput.addEventListener('input', (e) => topKVal.textContent = e.target.value);
alphaSlider.addEventListener('input', (e) => alphaVal.textContent = e.target.value);

// Check Health & Document Stats on startup
async function fetchHealth() {
    try {
        const res = await fetch(`${API_BASE}/health`);
        const data = await res.json();
        chunksCount.textContent = data.indexed_chunks_count || 0;
        document.getElementById('providerName').textContent = (data.llm_provider || 'gemini').toUpperCase();
        if (data.indexed_files) {
            renderIndexedFiles(data.indexed_files);
        }
    } catch (err) {
        console.warn('Backend not running yet or connection failed:', err);
    }
}

// Fetch currently indexed documents
async function fetchDocuments() {
    try {
        const res = await fetch(`${API_BASE}/documents`);
        const data = await res.json();
        chunksCount.textContent = data.total_chunks || 0;
        renderIndexedFiles(data.files || []);
    } catch (err) {
        console.warn('Could not fetch documents:', err);
    }
}

function renderIndexedFiles(files) {
    indexedFilesList.innerHTML = '';
    if (!files || files.length === 0) {
        indexedFilesSection.style.display = 'none';
        return;
    }
    indexedFilesSection.style.display = 'block';
    files.forEach(f => {
        const li = document.createElement('li');
        li.innerHTML = `
            <span class="file-name" title="${f.filename}">📄 ${f.filename}</span>
            <span class="chunk-count">${f.chunks} chunks</span>
        `;
        indexedFilesList.appendChild(li);
    });
}

// Clear Index Handler
clearIndexBtn.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to clear all indexed documents?')) return;
    try {
        const res = await fetch(`${API_BASE}/clear-index`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            uploadStatus.style.color = '#10b981';
            uploadStatus.textContent = '🗑️ Index cleared successfully.';
            chunksCount.textContent = 0;
            renderIndexedFiles([]);
            chunksList.innerHTML = '<div class="empty-state"><p>Index cleared. Upload new documents to start.</p></div>';
            retrievedCount.textContent = '0 Chunks';
        }
    } catch (err) {
        alert('Failed to clear index. Make sure backend is running.');
    }
});

fetchHealth();

// Restore Chat History on Page Load
function restoreChatHistory() {
    if (chatHistory.length > 0) {
        chatHistory.forEach(msg => {
            appendMessageUI(msg.role, msg.content, false);
        });
    }
}
restoreChatHistory();

// File Upload Handler (Supports Multiple Files)
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        uploadFiles(e.target.files);
    }
});

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        uploadFiles(e.dataTransfer.files);
    }
});

async function uploadFiles(files) {
    const fileArray = Array.from(files);
    uploadStatus.textContent = `Uploading ${fileArray.length} file(s)...`;
    uploadStatus.style.color = '#f59e0b';

    const formData = new FormData();
    fileArray.forEach(file => {
        formData.append('files', file);
    });

    try {
        const res = await fetch(`${API_BASE}/ingest`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (res.ok) {
            uploadStatus.style.color = '#10b981';
            uploadStatus.textContent = `✅ Indexed ${data.total_files} file(s) (${data.total_indexed_chunks} total chunks)`;
            chunksCount.textContent = data.total_indexed_chunks;
            fetchDocuments();

            // Auto-adjust retrieval controls based on file type
            if (data.recommended_top_k !== undefined) {
                topKInput.value = data.recommended_top_k;
                topKVal.textContent = data.recommended_top_k;
            }
            if (data.recommended_alpha !== undefined) {
                alphaSlider.value = data.recommended_alpha;
                alphaVal.textContent = data.recommended_alpha;
            }

            // Flash the auto badge
            const autoBadge = document.getElementById('autoBadge');
            autoBadge.textContent = `🤖 ${data.file_type.toUpperCase()} Optimized`;
            setTimeout(() => { autoBadge.textContent = '🤖 Auto'; }, 3000);
        } else {
            uploadStatus.style.color = '#ef4444';
            uploadStatus.textContent = data.detail || 'Upload failed.';
        }
    } catch (err) {
        uploadStatus.style.color = '#ef4444';
        uploadStatus.textContent = 'Backend server unavailable.';
    }
}

// Query Handler
sendBtn.addEventListener('click', handleQuery);
queryInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleQuery();
});

async function handleQuery() {
    const query = queryInput.value.trim();
    if (!query) return;

    // Append User Message
    appendMessage('user', query);
    queryInput.value = '';

    // Show loading state
    latencyBadge.innerHTML = `<span class="dot" style="background:#f59e0b"></span> Querying...`;
    
    try {
        const res = await fetch(`${API_BASE}/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                top_k: parseInt(topKInput.value),
                alpha: parseFloat(alphaSlider.value),
                chat_history: chatHistory.slice(-6)  // send last 6 turns
            })
        });

        const data = await res.json();

        if (res.ok) {
            appendMessage('assistant', data.answer);
            renderChunks(data.chunks);
            latencyBadge.innerHTML = `<span class="dot"></span> ${data.latency_seconds}s Latency`;
        } else {
            appendMessage('assistant', `Error: ${data.detail || 'Query failed.'}`);
            latencyBadge.innerHTML = `<span class="dot" style="background:#ef4444"></span> Error`;
        }
    } catch (err) {
        appendMessage('assistant', 'Backend server unavailable. Please make sure FastAPI backend is running.');
        latencyBadge.innerHTML = `<span class="dot" style="background:#ef4444"></span> Error`;
    }
}

function appendMessage(role, text) {
    // Save to chatHistory array & LocalStorage
    chatHistory.push({ role, content: text });
    localStorage.setItem('rag_nexus_chat_history', JSON.stringify(chatHistory));

    appendMessageUI(role, text, true);
}

function appendMessageUI(role, text, scroll = true) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role === 'user' ? 'user-msg' : 'system-msg'}`;
    
    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = role === 'user' ? '👤' : '🤖';

    const content = document.createElement('div');
    content.className = 'msg-content';
    content.innerHTML = text.replace(/\n/g, '<br>');

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(content);
    chatMessages.appendChild(msgDiv);
    if (scroll) {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

function renderChunks(chunks) {
    chunksList.innerHTML = '';
    retrievedCount.textContent = `${chunks ? chunks.length : 0} Chunks`;

    if (!chunks || chunks.length === 0) {
        chunksList.innerHTML = '<div class="empty-state"><p>No relevant context chunks found.</p></div>';
        return;
    }

    chunks.forEach((c, idx) => {
        const card = document.createElement('div');
        card.className = 'chunk-card';

        card.innerHTML = `
            <div class="chunk-meta">
                <span>#${idx + 1} ${c.metadata.source || 'Doc'} (Chunk #${c.metadata.chunk_index})</span>
                <span class="score-tag">Rerank: ${c.rerank_score ? c.rerank_score.toFixed(4) : 'N/A'}</span>
            </div>
            <div class="chunk-text">${c.content}</div>
        `;
        chunksList.appendChild(card);
    });
}

// Clear Chat History
clearChatBtn.addEventListener('click', () => {
    if (chatHistory.length === 0) return;
    if (!confirm('Clear chat history?')) return;
    
    chatHistory = [];
    localStorage.removeItem('rag_nexus_chat_history');
    chatMessages.innerHTML = `
        <div class="message system-msg">
            <div class="avatar">🤖</div>
            <div class="msg-content">
                Chat history cleared. Ask any question about your documents!
            </div>
        </div>
    `;
});

// Export Chat History as Markdown
exportChatBtn.addEventListener('click', () => {
    if (chatHistory.length === 0) {
        alert('No chat history to export.');
        return;
    }
    
    let markdown = `# RAG Nexus Conversation History\n\n`;
    markdown += `*Exported on ${new Date().toLocaleString()}*\n\n---\n\n`;
    
    chatHistory.forEach(msg => {
        const roleName = msg.role === 'user' ? '👤 **User**' : '🤖 **RAG Nexus**';
        markdown += `${roleName}:\n${msg.content}\n\n---\n\n`;
    });

    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `rag_nexus_chat_${new Date().toISOString().slice(0,10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
});

// ==================== API Settings Management ====================

const providerSelect = document.getElementById('providerSelect');
const googleField = document.getElementById('googleField');
const lmstudioField = document.getElementById('lmstudioField');
const ninerouterField = document.getElementById('ninerouterField');
const saveSettingsBtn = document.getElementById('saveSettingsBtn');
const settingsStatus = document.getElementById('settingsStatus');

function updateProviderFieldsVisibility() {
    const provider = providerSelect.value;
    googleField.style.display = provider === 'google' ? 'block' : 'none';
    lmstudioField.style.display = provider === 'lmstudio' ? 'block' : 'none';
    ninerouterField.style.display = provider === '9router' ? 'block' : 'none';
}

// Toggle fields based on provider
providerSelect.addEventListener('change', updateProviderFieldsVisibility);
providerSelect.addEventListener('input', updateProviderFieldsVisibility);

// Toggle password visibility
document.querySelectorAll('.toggle-eye').forEach(btn => {
    btn.addEventListener('click', () => {
        const input = document.getElementById(btn.dataset.target);
        if (input.type === 'password') {
            input.type = 'text';
            btn.textContent = '🙈';
        } else {
            input.type = 'password';
            btn.textContent = '👁';
        }
    });
});

// Load current settings from backend
async function loadSettings() {
    try {
        const res = await fetch(`${API_BASE}/settings`);
        const data = await res.json();

        providerSelect.value = data.llm_provider || 'google';
        updateProviderFieldsVisibility();

        // Google AI Studio
        if (data.google_api_key) {
            document.getElementById('googleKeyInput').placeholder = data.google_api_key;
        }
        if (data.google_model) {
            document.getElementById('googleModelInput').value = data.google_model;
        }

        // LM Studio
        if (data.lmstudio_base_url) {
            document.getElementById('lmstudioUrlInput').value = data.lmstudio_base_url;
        }
        if (data.lmstudio_model) {
            document.getElementById('lmstudioModelInput').value = data.lmstudio_model;
        }

        // 9Router
        if (data.ninerouter_base_url) {
            document.getElementById('ninerouterUrlInput').value = data.ninerouter_base_url;
        }
        if (data.ninerouter_api_key) {
            document.getElementById('ninerouterKeyInput').placeholder = data.ninerouter_api_key;
        }
        if (data.ninerouter_model) {
            document.getElementById('ninerouterModelInput').value = data.ninerouter_model;
        }
    } catch (err) {
        console.warn('Could not load settings:', err);
    }
}
loadSettings();

// Save settings to backend
saveSettingsBtn.addEventListener('click', async () => {
    saveSettingsBtn.classList.add('saving');
    saveSettingsBtn.textContent = '⏳ Saving...';
    settingsStatus.textContent = '';

    const selectedProvider = providerSelect.value;
    const payload = {
        llm_provider: selectedProvider
    };

    if (selectedProvider === 'google') {
        const googleKey = document.getElementById('googleKeyInput').value.trim();
        const googleModel = document.getElementById('googleModelInput').value.trim();
        if (googleKey) payload.google_api_key = googleKey;
        if (googleModel) payload.google_model = googleModel;
    } else if (selectedProvider === 'lmstudio') {
        const lmstudioUrl = document.getElementById('lmstudioUrlInput').value.trim();
        const lmstudioModel = document.getElementById('lmstudioModelInput').value.trim();
        if (lmstudioUrl) payload.lmstudio_base_url = lmstudioUrl;
        if (lmstudioModel) payload.lmstudio_model = lmstudioModel;
    } else if (selectedProvider === '9router') {
        const ninerouterUrl = document.getElementById('ninerouterUrlInput').value.trim();
        const ninerouterKey = document.getElementById('ninerouterKeyInput').value.trim();
        const ninerouterModel = document.getElementById('ninerouterModelInput').value.trim();
        if (ninerouterUrl) payload.ninerouter_base_url = ninerouterUrl;
        if (ninerouterKey) payload.ninerouter_api_key = ninerouterKey;
        if (ninerouterModel) payload.ninerouter_model = ninerouterModel;
    }

    try {
        const res = await fetch(`${API_BASE}/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (res.ok) {
            settingsStatus.style.color = '#10b981';
            const providerLabels = { google: 'GOOGLE AI STUDIO', lmstudio: 'LM STUDIO', '9router': '9ROUTER' };
            settingsStatus.textContent = `✅ Saved! Provider: ${providerLabels[data.active_provider] || data.active_provider.toUpperCase()}`;
            document.getElementById('providerName').textContent = providerLabels[data.active_provider] || data.active_provider.toUpperCase();
            // Clear key inputs after saving (security)
            document.getElementById('googleKeyInput').value = '';
            document.getElementById('ninerouterKeyInput').value = '';
            // Refresh masked placeholders
            loadSettings();
        } else {
            settingsStatus.style.color = '#ef4444';
            settingsStatus.textContent = `❌ ${data.detail || 'Save failed'}`;
        }
    } catch (err) {
        settingsStatus.style.color = '#ef4444';
        settingsStatus.textContent = '❌ Backend unavailable';
    }

    saveSettingsBtn.classList.remove('saving');
    saveSettingsBtn.textContent = '💾 Save';
});

// ==================== Test Connection ====================

const testConnectionBtn = document.getElementById('testConnectionBtn');

testConnectionBtn.addEventListener('click', async () => {
    testConnectionBtn.classList.add('testing');
    testConnectionBtn.textContent = '⏳ Testing...';
    settingsStatus.textContent = '';
    settingsStatus.style.color = '#f59e0b';
    settingsStatus.textContent = '🔄 Testing connection...';

    try {
        const res = await fetch(`${API_BASE}/test-connection`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();

        if (data.status === 'ok') {
            settingsStatus.style.color = '#10b981';
            settingsStatus.textContent = `${data.message} (${data.latency}s)`;
        } else {
            settingsStatus.style.color = '#ef4444';
            settingsStatus.textContent = data.message;
        }
    } catch (err) {
        settingsStatus.style.color = '#ef4444';
        settingsStatus.textContent = '❌ Backend server is not running';
    }

    testConnectionBtn.classList.remove('testing');
    testConnectionBtn.textContent = '🔌 Test';
});
