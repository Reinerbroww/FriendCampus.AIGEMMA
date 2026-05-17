function toggleModal() {
    const overlay = document.getElementById('modalOverlay');
    if (!overlay) return;
    overlay.classList.toggle('show');
    if (overlay.classList.contains('show')) {
        setTimeout(() => {
            const input = overlay.querySelector('input');
            if (input) input.focus();
        }, 100);
    }
}

function showTab(tabName, btn) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('tab-' + tabName).classList.add('active');
    btn.classList.add('active');

    if (tabName === 'check') {
        showCheckState('intro');
        loadCheckTopics();
    }
    if (tabName === 'roadmap') loadRoadmap();
    if (tabName === 'weakness') {
        weaknessLoaded = false;
        loadWeakness();
    }
    if (tabName === 'references') loadSavedReferences();
}

// ===== CHAT =====
function formatMessage(text) {
    if (!text) return '';

    // Escape HTML
    let html = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Numbered list
    html = html.replace(/^(\d+)\.\s+(.+)$/gm,
        '<div class="msg-list-item"><span class="msg-num">$1.</span> $2</div>');

    // Lettered sub-list
    html = html.replace(/^([a-z])\.\s+(.+)$/gm,
        '<div class="msg-sub-item"><span class="msg-letter">$1.</span> $2</div>');

    // Superscript untuk pangkat
    html = html.replace(/(\w+)\^(\w+)/g, '$1<sup>$2</sup>');

    // Line breaks
    html = html.replace(/\n\n/g, '<br><br>');
    html = html.replace(/\n/g, '<br>');

    return html;
}

async function sendMessage() {
    const input   = document.getElementById('userInput');
    const message = input.value.trim();

    if (!message && !selectedImage) return;

    if (selectedImage) {
        await sendImageMessage(message || "Please analyze this image.");
        return;
    }

    appendMessage('user', message);
    input.value = '';
    input.style.height = 'auto';

    document.getElementById('loading').style.display = 'flex';
    document.getElementById('sendBtn').disabled = true;

    // Bikin bubble kosong buat streaming
    const chatBox = document.getElementById('chatBox');
    const empty   = chatBox.querySelector('.empty-chat');
    if (empty) empty.remove();

    const bubble = document.createElement('div');
    bubble.className = 'message assistant';
    bubble.innerHTML = '<div class="bubble" id="streamBubble"></div>';
    chatBox.appendChild(bubble);

    const streamEl = document.getElementById('streamBubble');
    let fullText   = '';

    try {
        const response = await fetch(`/chat/${SUBJECT_ID}`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ message })
        });

        const reader  = response.body.getReader();
        const decoder = new TextDecoder();

        document.getElementById('loading').style.display = 'none';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const text  = decoder.decode(value);
            const lines = text.split('\n');

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;

                try {
                    const data = JSON.parse(line.slice(6));

                    if (data.chunk) {
                        fullText += data.chunk;
                        streamEl.innerHTML = formatMessage(fullText);
                        chatBox.scrollTop  = chatBox.scrollHeight;
                    }

                    if (data.done) break;

                    if (data.error) {
                        streamEl.textContent = 'Error: ' + data.error;
                        break;
                    }
                } catch (e) {
                    // Skip invalid JSON
                }
            }
        }

    } catch (err) {
        if (streamEl) streamEl.textContent = 'Connection error. Try again!';
    } finally {
        document.getElementById('loading').style.display = 'none';
        document.getElementById('sendBtn').disabled      = false;
    }
}

function appendMessage(role, message) {
    const chatBox = document.getElementById('chatBox');
    const empty   = chatBox.querySelector('.empty-chat');
    if (empty) empty.remove();

    const div = document.createElement('div');
    div.className = `message ${role}`;

    const formatted = role === 'assistant' ? formatMessage(message) :
        message.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

    div.innerHTML = `<div class="bubble">${formatted}</div>`;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function clearChat() {
    if (!confirm('Delete all chat history?')) return;
    await fetch(`/clear-chat/${SUBJECT_ID}`, { method: 'POST' });
    const chatBox = document.getElementById('chatBox');
    chatBox.innerHTML = `
        <div class="empty-chat">
            <div class="empty-icon">💬</div>
            <p style="color:#555;font-size:14px;">Chat deleted. Start a new conversation!</p>
            <p class="empty-hint">Press Enter to send</p>
        </div>`;
}

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('userInput');
    if (input) {
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }

    const chatBox = document.getElementById('chatBox');
    if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;
});

// ===== CHECK UNDERSTANDING =====
let currentQuestion = "";
let currentTopic = "";
let checkTopicsLoaded = false;

function showCheckState(state) {
    document.getElementById('checkIntro').style.display    = 'none';
    document.getElementById('checkQuestion').style.display = 'none';
    document.getElementById('checkResult').style.display   = 'none';

    if (state === 'intro')    document.getElementById('checkIntro').style.display    = 'block';
    if (state === 'question') document.getElementById('checkQuestion').style.display = 'block';
    if (state === 'result')   document.getElementById('checkResult').style.display   = 'block';
}

async function loadCheckTopics() {
    const loading  = document.getElementById('checkTopicsLoading');
    const list     = document.getElementById('checkTopicsList');
    const noTopics = document.getElementById('checkNoTopics');

    loading.style.display  = 'flex';
    list.style.display     = 'none';
    noTopics.style.display = 'none';

    try {
        const res = await fetch(`/topics-for-check/${SUBJECT_ID}`);
        const data = await res.json();
        const topics = data.topics;

        loading.style.display = 'none';

        if (!topics || topics.length === 0) {
            noTopics.style.display = 'block';
            return;
        }

        list.style.display = 'flex';
        list.innerHTML = topics.map((topic, i) => `
            <div class="check-topic-item ${topic.level === 1 ? 'sub-topic' : 'parent-topic'}"
                 onclick="selectTopic('${topic.topic_name.replace(/'/g, "\\'")}')">
                <div class="check-topic-left">
                    <div class="check-topic-num">${topic.level === 0 ? (i + 1) : '↳'}</div>
                    <div class="check-topic-name">${topic.topic_name}</div>
                </div>
                <div class="check-topic-status ${topic.is_completed ? 'done' : ''}">
                    ${topic.is_completed ? '✓ Studied' : 'Not yet'}
                </div>
                <div class="check-topic-arrow">→</div>
            </div>
        `).join('');

        checkTopicsLoaded = true;

    } catch (err) {
        loading.style.display  = 'none';
        noTopics.style.display = 'block';
    }
}

async function selectTopic(topicName) {
    currentTopic = topicName;

    // Tampilin state pertanyaan
    showCheckState('question');
    document.getElementById('checkTopicTag').textContent  = topicName;
    document.getElementById('checkQuestionText').textContent = 'Gemma is generating a question...';
    document.getElementById('checkAnswer').value = '';

    try {
        const res  = await fetch(`/understanding-check/${SUBJECT_ID}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic_name: topicName })
        });
        const data = await res.json();

        if (data.error) {
            document.getElementById('checkQuestionText').textContent = 'Failed to load question. Try again.';
            return;
        }

        currentQuestion = data.question;
        document.getElementById('checkQuestionText').textContent = data.question;

    } catch (err) {
        document.getElementById('checkQuestionText').textContent = 'Failed to load question. Try again.';
    }
}

async function submitAnswer() {
    const answer = document.getElementById('checkAnswer').value.trim();
    if (!answer) { alert('Write your answer first!'); return; }

    const btn = document.getElementById('submitAnswerBtn');
    btn.textContent = 'Evaluating...';
    btn.disabled = true;

    try {
        const res  = await fetch(`/evaluate/${SUBJECT_ID}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: currentQuestion,
                answer: answer,
                topic: currentTopic
            })
        });
        const data = await res.json();

        // Update result panel
        const scoreEl    = document.getElementById('resultScore');
        const resultPanel = document.getElementById('resultPanel');
        const topicTag   = document.getElementById('resultTopicTag');

        topicTag.textContent = currentTopic;
        document.getElementById('resultFeedback').textContent = data.feedback;
        scoreEl.textContent = data.score;

        // Warna berdasarkan skor
        if (data.score >= 75) {
            scoreEl.style.color        = '#ffffff';
            resultPanel.style.background   = '#0a140a';
            resultPanel.style.borderColor  = '#1a2a1a';
        } else if (data.score >= 50) {
            scoreEl.style.color        = '#ffffff';
            resultPanel.style.background   = '#14110a';
            resultPanel.style.borderColor  = '#2a200a';
        } else {
            scoreEl.style.color        = '#ffffff';
            resultPanel.style.background   = '#140a0a';
            resultPanel.style.borderColor  = '#2a1010';
        }

        showCheckState('result');
        weaknessLoaded = false;

    } catch (err) {
        alert('Failed to evaluate. Try again.');
    } finally {
        btn.textContent = 'Submit Answer';
        btn.disabled    = false;
    }
}

function cancelCheck() {
    showCheckState('intro');
    loadCheckTopics();
}

function tryAgain() {
    selectTopic(currentTopic);
}

// ===== ROADMAP =====
let roadmapLoaded  = false;
const pendingToggles = new Map();

async function loadRoadmap() {
    if (roadmapLoaded) return;

    const list = document.getElementById('topicsList');
    if (!list) return;

    // Tampilkan pesan yang lebih informatif
    const messages = [
        "Gemma is analyzing the subject...",
        "Building your learning path...",
        "Organizing topics by difficulty...",
        "Almost ready..."
    ];

    let msgIndex = 0;
    list.innerHTML = `
        <div class="roadmap-loading">
            <div class="loading-dots"><span></span><span></span><span></span></div>
            <span id="roadmapLoadingMsg">${messages[0]}</span>
        </div>`;

    // Rotate pesan tiap 3 detik biar keliatan progress
    const msgTimer = setInterval(() => {
        msgIndex = (msgIndex + 1) % messages.length;
        const el = document.getElementById('roadmapLoadingMsg');
        if (el) el.textContent = messages[msgIndex];
    }, 3000);

    try {
        const res  = await fetch(`/roadmap/${SUBJECT_ID}`);
        const data = await res.json();

        clearInterval(msgTimer);

        if (data.error) {
            list.innerHTML = `
                <div style="text-align:center;padding:2rem;">
                    <p style="color:var(--text-4);margin-bottom:1rem;">
                        Failed to load roadmap.
                    </p>
                    <button onclick="resetRoadmap()" class="reset-btn">
                        🔄 Try Again
                    </button>
                </div>`;
            return;
        }

        renderRoadmap(data.topics);
        roadmapLoaded = true;

    } catch (err) {
        clearInterval(msgTimer);
        list.innerHTML = `
            <div style="text-align:center;padding:2rem;">
                <p style="color:var(--text-4);margin-bottom:1rem;">
                    Connection timeout. Please try again.
                </p>
                <button onclick="loadRoadmap(); roadmapLoaded=false;" class="reset-btn">
                    🔄 Retry
                </button>
            </div>`;
    }
}

function renderRoadmap(topics) {
    const list = document.getElementById('topicsList');
    if (!topics || topics.length === 0) {
        list.innerHTML = `<div class="roadmap-empty">
            <div class="empty-icon">🗺️</div>
            <p>No topics yet. Click Regenerate to create your roadmap.</p>
        </div>`;
        updateOverallProgress(0, 0);
        return;
    }

    // Hitung total progress
    let totalSubs     = 0;
    let completedSubs = 0;

    topics.forEach(topic => {
        const subs = topic.subtopics || [];
        if (subs.length > 0) {
            totalSubs     += subs.length;
            completedSubs += subs.filter(s => s.is_completed).length;
        } else {
            totalSubs++;
            if (topic.is_completed) completedSubs++;
        }
    });

    updateOverallProgress(completedSubs, totalSubs);

    // Render topics
    list.innerHTML = topics.map((topic, i) => {
        const subs         = topic.subtopics || [];
        const subTotal     = subs.length;
        const subCompleted = subs.filter(s => s.is_completed).length;
        const subPercent   = subTotal > 0
            ? Math.round((subCompleted / subTotal) * 100)
            : (topic.is_completed ? 100 : 0);
        const allDone      = subTotal > 0
            ? subCompleted === subTotal
            : topic.is_completed;

        const subsHtml = subs.length > 0 ? `
            <div class="topic-subtopics">
                ${subs.map(sub => `
                    <div class="topic-sub-item ${sub.is_completed ? 'completed' : ''}"
                         id="sub-${sub.id}"
                         onclick="toggleSubTopic(${sub.id}, ${sub.is_completed ? 1 : 0}, ${topic.id})">
                        <div class="sub-checkbox">${sub.is_completed ? '✓' : ''}</div>
                        <div class="sub-name">${sub.topic_name}</div>
                    </div>
                `).join('')}
            </div>` : '';

        return `
            <div class="topic-parent ${allDone ? 'all-done' : ''}"
                 id="parent-${topic.id}"
                 data-topic-number="${i + 1}">
                <div class="topic-parent-header"
                     onclick="toggleParentExpand(${topic.id}, ${subs.length})">
                    <div class="topic-parent-num">${allDone ? '✓' : (i + 1)}</div>
                    <div class="topic-parent-info">
                        <div class="topic-parent-name">${topic.topic_name}</div>
                        <div class="topic-parent-progress">
                            ${subTotal > 0 ? `
                                <div class="topic-mini-bar">
                                    <div class="topic-mini-fill" style="width:${subPercent}%"></div>
                                </div>
                                <div class="topic-mini-label">${subCompleted}/${subTotal} done</div>
                            ` : `
                                <div class="topic-mini-label">${topic.is_completed ? '✓ Completed' : 'Not started'}</div>
                            `}
                        </div>
                    </div>
                    ${subs.length > 0 ? '<div class="topic-expand-icon">›</div>' : ''}
                </div>
                ${subsHtml}
            </div>`;
    }).join('');
}

function toggleParentExpand(parentId, hasSubtopics) {
    if (!hasSubtopics) return;
    const el = document.getElementById(`parent-${parentId}`);
    if (el) el.classList.toggle('expanded');
}

function updateOverallProgress(completed, total) {
    const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
    const fill    = document.getElementById('roadmapOverallFill');
    const label   = document.getElementById('roadmapProgress');
    if (fill)  fill.style.width  = percent + '%';
    if (label) label.textContent = `${completed} of ${total} subtopics done — ${percent}%`;
}

async function toggleSubTopic(topicId, currentState, parentId) {
    // Cegah double click
    if (pendingToggles.get(topicId)) return;
    pendingToggles.set(topicId, true);

    const el       = document.getElementById(`sub-${topicId}`);
    const checkbox = el ? el.querySelector('.sub-checkbox') : null;
    if (!el) { pendingToggles.delete(topicId); return; }

    // Optimistic update
    const newCompleted = currentState === 0;
    el.classList.toggle('completed', newCompleted);
    if (checkbox) checkbox.textContent = newCompleted ? '✓' : '';
    el.setAttribute('onclick',
        `toggleSubTopic(${topicId}, ${newCompleted ? 1 : 0}, ${parentId})`);

    // Update parent progress langsung
    updateParentProgress(parentId);
    updateOverallProgressFromDOM();

    try {
        const res = await fetch(`/toggle-topic/${topicId}`, { method: 'POST' });
        if (!res.ok) throw new Error('Server error');
    } catch (err) {
        // Revert
        el.classList.toggle('completed', !newCompleted);
        if (checkbox) checkbox.textContent = !newCompleted ? '✓' : '';
        el.setAttribute('onclick',
            `toggleSubTopic(${topicId}, ${currentState}, ${parentId})`);
        updateParentProgress(parentId);
        updateOverallProgressFromDOM();
    } finally {
        pendingToggles.delete(topicId);
    }
}

function updateParentProgress(parentId) {

    const parentEl = document.getElementById(`parent-${parentId}`);
    if (!parentEl) return;

    const subs = parentEl.querySelectorAll('.topic-sub-item');
    const completed = parentEl.querySelectorAll('.topic-sub-item.completed');

    const total = subs.length;
    const done = completed.length;

    const percent = total > 0
        ? Math.round((done / total) * 100)
        : 0;

    const miniBar   = parentEl.querySelector('.topic-mini-fill');
    const miniLabel = parentEl.querySelector('.topic-mini-label');
    const numEl     = parentEl.querySelector('.topic-parent-num');

    const allDone = total > 0 && done === total;

    // update progress bar
    if (miniBar) {
        miniBar.style.width = percent + '%';
    }

    // update label
    if (miniLabel) {
        miniLabel.textContent = `${done}/${total} done`;
    }

    // FIX BUG CHECKLIST PARENT
    if (numEl) {

        if (allDone) {
            numEl.textContent = '✓';
        } else {
            numEl.textContent = parentEl.dataset.topicNumber;
        }

    }

    // update class
    parentEl.classList.toggle('all-done', allDone);
}

function updateOverallProgressFromDOM() {
    const allSubs   = document.querySelectorAll('.topic-sub-item');
    const doneSubs  = document.querySelectorAll('.topic-sub-item.completed');
    updateOverallProgress(doneSubs.length, allSubs.length);
}

async function resetRoadmap() {
    if (!confirm('Regenerate roadmap? All progress will be lost.')) return;

    await fetch(`/reset-roadmap/${SUBJECT_ID}`, { method: 'POST' });
    roadmapLoaded = false;

    const list = document.getElementById('topicsList');
    list.innerHTML = `
        <div class="roadmap-loading">
            <div class="loading-dots"><span></span><span></span><span></span></div>
            Gemma is rebuilding your roadmap...
        </div>`;

    updateOverallProgress(0, 0);
    loadRoadmap();
}

// ===== WEAKNESS =====
let weaknessLoaded = false;

async function loadWeakness() {
    if (weaknessLoaded) return;
    const list = document.getElementById('weaknessList');
    if (!list) return;

    try {
        const res = await fetch(`/weakness-report/${SUBJECT_ID}`);
        const data = await res.json();

        if (!data.report || data.report.length === 0) {
            list.innerHTML = `
                <div class="weakness-empty">
                    <div class="empty-icon">📊</div>
                    <p>No data yet. Try the Understanding Check feature first!</p>
                </div>`;
            weaknessLoaded = true;
            return;
        }

        list.innerHTML = data.report.map(item => {
            const score = item.avg_score;
            const cls = score >= 75 ? 'score-high' : score >= 50 ? 'score-mid' : 'score-low';
            return `
                <div class="weakness-item">
                    <div class="weakness-score-circle ${cls}">${score}</div>
                    <div class="weakness-info">
                        <div class="weakness-topic">${item.topic_name}</div>
                        <div class="weakness-bar">
                            <div class="weakness-bar-fill" style="width:${score}%"></div>
                        </div>
                        <div class="weakness-meta">${item.attempt_count}x checked</div>
                    </div>
                </div>`;
        }).join('');

        weaknessLoaded = true;
    } catch (err) {
        list.innerHTML = `<p style="color:#cc4444;font-size:13px;padding:1rem;">Failed to load report.</p>`;
    }
}

// ===== REFERENCES =====
let allReferences = [];
let currentRefFilter = 'all';
let savedRefs = [];

async function searchReferences(useSubjectName = false) {
    const input = document.getElementById('refSearchInput');
    const query = useSubjectName
        ? SUBJECT_NAME
        : input.value.trim();

    if (!query) return;
    if (useSubjectName) input.value = query;

    const btn      = document.getElementById('refSearchBtn');
    const loading  = document.getElementById('refLoading');
    const empty    = document.getElementById('refEmpty');
    const filters  = document.getElementById('refFilters');
    const subtabs  = document.getElementById('refSubtabs');

    btn.disabled      = true;
    btn.textContent   = 'Searching...';
    loading.style.display = 'flex';
    empty.style.display   = 'none';
    document.getElementById('refResults').innerHTML = '';

    // Update loading message
    const refMessages = [
        "Searching the web...",
        "Finding academic papers...",
        "Collecting references...",
        "Almost done..."
    ];
    let refMsgIndex = 0;
    const refMsgTimer = setInterval(() => {
        refMsgIndex = (refMsgIndex + 1) % refMessages.length;
        const loadingEl = loading.querySelector('span');
        if (loadingEl) loadingEl.textContent = refMessages[refMsgIndex];
    }, 4000);

    try {
        // Pake AbortController buat timeout 90 detik
        const controller = new AbortController();
        const timeout    = setTimeout(() => controller.abort(), 90000);

        const res  = await fetch(`/references/${SUBJECT_ID}`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ query }),
            signal:  controller.signal
        });

        clearTimeout(timeout);
        clearInterval(refMsgTimer);

        const data = await res.json();

        if (data.error) {
            document.getElementById('refResults').innerHTML = `
                <div class="ref-empty">
                    <div class="ref-empty-title">Search Failed</div>
                    <div class="ref-empty-sub">${data.error}</div>
                </div>`;
            return;
        }

        allReferences = data.references || [];
        document.getElementById('resultsCount').textContent = allReferences.length;

        filters.style.display  = 'flex';
        subtabs.style.display  = 'flex';

        renderReferences(allReferences);
        loadSavedReferences();

    } catch (err) {
        clearInterval(refMsgTimer);

        const isTimeout = err.name === 'AbortError';
        document.getElementById('refResults').innerHTML = `
            <div class="ref-empty">
                <div class="ref-empty-title">
                    ${isTimeout ? 'Search Timed Out' : 'Search Failed'}
                </div>
                <div class="ref-empty-sub">
                    ${isTimeout
                        ? 'The search took too long. Try a more specific query.'
                        : 'Connection error. Please try again.'
                    }
                </div>
                <button onclick="searchReferences()" class="start-check-btn"
                        style="margin-top:1rem;">
                    🔄 Try Again
                </button>
            </div>`;
    } finally {
        btn.disabled    = false;
        btn.textContent = 'Search';
        loading.style.display = 'none';
    }
}

function renderReferences(refs) {
    const container = document.getElementById('refResults');

    if (!refs || refs.length === 0) {
        container.innerHTML = `
            <div class="ref-empty">
                <div class="empty-icon" style="opacity:.3;">🔍</div>
                <div class="ref-empty-title">No references found</div>
                <div class="ref-empty-sub">Try a different search term</div>
            </div>`;
        return;
    }

    container.innerHTML = refs.map((ref, i) => `
        <div class="ref-card" style="animation-delay:${i * 0.05}s">
            <div class="ref-top">
                <div class="ref-title">${ref.title}</div>
                <div class="ref-type-badge">${ref.type}</div>
            </div>
            <div class="ref-meta">${ref.author || ''} ${ref.year ? '· ' + ref.year : ''}</div>
            <div class="ref-summary">${ref.summary}</div>
            <div class="ref-tags">
                ${(ref.tags || []).map(t => `<span class="ref-tag">${t}</span>`).join('')}
            </div>
            <div class="ref-actions">
                ${ref.url
                    ? `<a href="${ref.url}" target="_blank" class="ref-btn ref-btn-primary">Open Reference ↗</a>`
                    : `<button class="ref-btn ref-btn-primary" disabled style="opacity:.3;">No URL Available</button>`
                }
                <button class="ref-btn ref-btn-secondary"
                        onclick='saveReference(${JSON.stringify(ref).replace(/'/g, "&#39;")})'>
                    ☆ Save
                </button>
                <button class="ref-btn ref-btn-secondary"
                        onclick='askGemmaAbout(${JSON.stringify(ref.title).replace(/'/g, "&#39;")})'>
                    Ask Gemma
                </button>
            </div>
        </div>
    `).join('');
}

function filterRefs(type, btn) {
    currentRefFilter = type;

    document.querySelectorAll('.ref-chip').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');

    const filtered = type === 'all'
        ? allReferences
        : allReferences.filter(r => r.type === type);

    renderReferences(filtered);
}

function showRefTab(tab, btn) {
    document.querySelectorAll('.ref-subtab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    document.getElementById('refResults').style.display = tab === 'results' ? 'flex' : 'none';
    document.getElementById('refSaved').style.display   = tab === 'saved'   ? 'flex' : 'none';

    if (tab === 'saved') loadSavedReferences();
}

async function saveReference(ref) {
    try {
        await fetch(`/save-reference/${SUBJECT_ID}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(ref)
        });
        loadSavedReferences();
    } catch (err) {
        alert('Failed to save reference.');
    }
}

async function loadSavedReferences() {
    try {
        const res = await fetch(`/saved-references/${SUBJECT_ID}`);
        const data = await res.json();
        savedRefs = data.references || [];

        document.getElementById('savedCount').textContent = savedRefs.length;

        const container = document.getElementById('refSaved');

        if (savedRefs.length === 0) {
            container.innerHTML = `
                <div class="ref-empty">
                    <div class="empty-icon" style="opacity:.3;">☆</div>
                    <div class="ref-empty-title">No saved references yet</div>
                    <div class="ref-empty-sub">Save references from your search results</div>
                </div>`;
            return;
        }

        container.innerHTML = savedRefs.map(ref => `
            <div class="ref-card">
                <div class="ref-top">
                    <div class="ref-title">${ref.title}</div>
                    <div class="ref-type-badge">${ref.type}</div>
                </div>
                <div class="ref-meta">${ref.author || ''} ${ref.year ? '· ' + ref.year : ''}</div>
                <div class="ref-summary">${ref.summary}</div>
                <div class="ref-tags">
                    ${(ref.tags || []).map(t => `<span class="ref-tag">${t}</span>`).join('')}
                </div>
                <div class="ref-actions">
                    ${ref.url
                        ? `<a href="${ref.url}" target="_blank" class="ref-btn ref-btn-primary">Open ↗</a>`
                        : ''
                    }
                    <button class="ref-btn ref-btn-secondary"
                            onclick='askGemmaAbout(${JSON.stringify(ref.title).replace(/'/g, "&#39;")})'>
                        Ask Gemma
                    </button>
                    <button class="ref-btn ref-btn-secondary"
                            onclick="deleteRef(${ref.id})" style="color:#553333;border-color:#2a1a1a;">
                        Remove
                    </button>
                </div>
            </div>
        `).join('');

    } catch (err) {
        console.error('Failed to load saved references:', err);
    }
}

async function deleteRef(refId) {
    if (!confirm('Remove this reference?')) return;
    await fetch(`/delete-reference/${refId}`, { method: 'POST' });
    loadSavedReferences();
}

function askGemmaAbout(title) {
    // Switch ke tab chat dan pre-fill input
    const chatTab = document.querySelector('.tab-btn');
    showTab('chat', chatTab);

    const input = document.getElementById('userInput');
    if (input) {
        input.value = `Can you explain more about "${title}"? How is it relevant to what I'm studying?`;
        input.focus();
        input.style.height = 'auto';
        input.style.height = input.scrollHeight + 'px';
    }
}

// Enter key buat search references
document.addEventListener('DOMContentLoaded', () => {
    const refInput = document.getElementById('refSearchInput');
    if (refInput) {
        refInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') searchReferences();
        });
    }
});

// ===== IMAGE UPLOAD =====
let selectedImage = null;

function previewImage(input) {
    if (!input.files || !input.files[0]) return;

    const file = input.files[0];

    // Cek ukuran
    if (file.size > 5 * 1024 * 1024) {
        alert('Image too large. Max 5MB.');
        input.value = '';
        return;
    }

    selectedImage = file;

    const reader = new FileReader();
    reader.onload = (e) => {
        const preview = document.getElementById('imagePreview');
        const img = document.getElementById('previewImg');
        img.src = e.target.result;
        preview.style.display = 'block';
    };
    reader.readAsDataURL(file);
}

function removeImage() {
    selectedImage = null;
    document.getElementById('imageUpload').value = '';
    document.getElementById('imagePreview').style.display = 'none';
    document.getElementById('previewImg').src = '';
}

async function sendImageMessage(message) {
    const input = document.getElementById('userInput');

    // Tampilin preview di chat
    const reader = new FileReader();
    reader.onload = (e) => {
        const chatBox = document.getElementById('chatBox');
        const empty = chatBox.querySelector('.empty-chat');
        if (empty) empty.remove();

        const div = document.createElement('div');
        div.className = 'message user';
        div.innerHTML = `
            <div class="bubble">
                <div class="image-message-label">📷 Image</div>
                <img src="${e.target.result}" alt="Uploaded image" style="max-width:100%;border-radius:8px;">
                ${message ? `<div style="margin-top:6px;">${message}</div>` : ''}
            </div>`;
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
    };
    reader.readAsDataURL(selectedImage);

    // Reset input
    const imageFile = selectedImage;
    input.value = '';
    input.style.height = 'auto';
    removeImage();

    document.getElementById('loading').style.display = 'flex';
    document.getElementById('sendBtn').disabled = true;

    try {
        const formData = new FormData();
        formData.append('image', imageFile);
        formData.append('message', message);

        const res = await fetch(`/analyze-image/${SUBJECT_ID}`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (data.error) {
            appendMessage('assistant', `Error: ${data.error}`);
        } else {
            appendMessage('assistant', data.response);
        }
    } catch (err) {
        appendMessage('assistant', 'Failed to analyze image. Try again!');
    } finally {
        document.getElementById('loading').style.display = 'none';
        document.getElementById('sendBtn').disabled = false;
    }
}

// Prefetch data waktu halaman subject load
document.addEventListener('DOMContentLoaded', () => {
    if (typeof SUBJECT_ID !== 'undefined') {
        loadCheckTopics();
    }
});
