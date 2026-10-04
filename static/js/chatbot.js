/**
 * TravelAI Companion — AI Chatbot Controller (Gemini 3.8 Flash)
 */

document.addEventListener('DOMContentLoaded', function () {
    const toggleBtn = document.getElementById('chatbotToggleBtn');
    const chatWindow = document.getElementById('chatbotWindow');
    const closeBtn = document.getElementById('chatbotCloseBtn');
    const clearBtn = document.getElementById('chatbotClearBtn');
    const messagesContainer = document.getElementById('chatbotMessages');
    const typingIndicator = document.getElementById('chatbotTypingIndicator');
    const chatForm = document.getElementById('chatbotForm');
    const chatInput = document.getElementById('chatbotInput');
    const sendBtn = document.getElementById('chatbotSendBtn');

    if (!toggleBtn || !chatWindow || !chatForm) {
        return;
    }

    const iconOpen = toggleBtn.querySelector('.chatbot-icon-open');
    const iconClose = toggleBtn.querySelector('.chatbot-icon-close');
    const pulseBadge = toggleBtn.querySelector('.chatbot-badge-pulse');

    // Rolling conversation history sent with context: [{role: 'user'|'model', text: '...'}]
    let conversationHistory = [];
    let isRequestPending = false;

    // Toggle Chat Window
    function toggleChat(forceOpen = null) {
        const isCurrentlyOpen = !chatWindow.classList.contains('d-none');
        const shouldOpen = forceOpen !== null ? forceOpen : !isCurrentlyOpen;

        if (shouldOpen) {
            chatWindow.classList.remove('d-none');
            chatWindow.setAttribute('aria-hidden', 'false');
            if (iconOpen) iconOpen.classList.add('d-none');
            if (iconClose) iconClose.classList.remove('d-none');
            if (pulseBadge) pulseBadge.classList.add('d-none');
            scrollToBottom();
            setTimeout(() => chatInput.focus(), 150);
        } else {
            chatWindow.classList.add('d-none');
            chatWindow.setAttribute('aria-hidden', 'true');
            if (iconOpen) iconOpen.classList.remove('d-none');
            if (iconClose) iconClose.classList.add('d-none');
        }
    }

    toggleBtn.addEventListener('click', function () {
        toggleChat();
    });

    if (closeBtn) {
        closeBtn.addEventListener('click', function () {
            toggleChat(false);
        });
    }

    // Clear Conversation History
    if (clearBtn) {
        clearBtn.addEventListener('click', function () {
            conversationHistory = [];
            // Remove user and AI generated messages, keep only welcome bubble
            const allMessages = messagesContainer.querySelectorAll('.chat-msg');
            allMessages.forEach((msg, index) => {
                if (index > 0 && msg.id !== 'chatbotTypingIndicator') {
                    msg.remove();
                }
            });
            scrollToBottom();
            chatInput.focus();
        });
    }

    // Quick Suggestions Chip Handler
    function attachSuggestionListeners() {
        const chips = messagesContainer.querySelectorAll('.chat-suggestion-chip');
        chips.forEach(chip => {
            chip.removeEventListener('click', handleChipClick);
            chip.addEventListener('click', handleChipClick);
        });
    }

    function handleChipClick(e) {
        e.preventDefault();
        const prompt = this.getAttribute('data-prompt');
        if (prompt && !isRequestPending) {
            chatInput.value = prompt;
            submitMessage(prompt);
        }
    }

    attachSuggestionListeners();

    // Auto-scroll messages to bottom
    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // Escape HTML to prevent XSS
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Lightweight markdown formatter for safe AI output
    function formatMarkdown(text) {
        if (!text) return '';

        let safe = escapeHtml(text);

        // Convert blockquotes (> ...)
        safe = safe.replace(/^>\s*(.*?)$/gm, '<blockquote class="border-start border-3 border-info ps-2 my-2 text-muted">$1</blockquote>');

        // Headers (### ...)
        safe = safe.replace(/^###\s*(.*?)$/gm, '<h6 class="fw-bold text-dark mt-2 mb-1">$1</h6>');
        safe = safe.replace(/^##\s*(.*?)$/gm, '<h6 class="fw-bold text-dark mt-2 mb-1">$1</h6>');
        safe = safe.replace(/^#\s*(.*?)$/gm, '<h6 class="fw-bold text-dark mt-2 mb-1">$1</h6>');

        // Bold (**text**)
        safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // Italics (*text*)
        safe = safe.replace(/\*([^\*]+)\*/g, '<em>$1</em>');

        // Lists: Unordered (* or -)
        safe = safe.replace(/(?:^|\n)[*-]\s+(.+)/g, '<li class="small mb-1">$1</li>');
        safe = safe.replace(/(<li class="small mb-1">.*?<\/li>)+/gs, '<ul class="ps-3 my-1">$1</ul>');

        // Line breaks & Paragraphs
        safe = safe.replace(/\n\n+/g, '</p><p class="mb-2">');
        safe = safe.replace(/\n/g, '<br/>');

        return `<p class="mb-1">${safe}</p>`;
    }

    // Append Message to UI
    function appendMessage(role, text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `chat-msg chat-msg-${role} d-flex gap-2 mb-3`;

        if (role === 'user') {
            msgDiv.innerHTML = `
                <div class="chat-msg-bubble shadow-sm p-3 rounded-3">
                    <p class="mb-0 small">${escapeHtml(text)}</p>
                </div>
            `;
        } else {
            msgDiv.innerHTML = `
                <div class="chat-msg-avatar flex-shrink-0">
                    <div class="chatbot-mini-avatar bg-info text-dark">
                        <i class="bi bi-stars"></i>
                    </div>
                </div>
                <div class="chat-msg-bubble shadow-sm p-3 rounded-3">
                    ${formatMarkdown(text)}
                </div>
            `;
        }

        // Insert before typing indicator
        messagesContainer.insertBefore(msgDiv, typingIndicator);
        scrollToBottom();
    }

    // Submit Message to Backend
    function submitMessage(messageText) {
        const text = messageText.trim();
        if (!text || isRequestPending) return;

        // Render user message immediately
        appendMessage('user', text);
        chatInput.value = '';
        isRequestPending = true;

        // Update rolling history
        conversationHistory.push({ role: 'user', text: text });
        if (conversationHistory.length > 12) {
            conversationHistory = conversationHistory.slice(-12);
        }

        // Show typing indicator & disable send button
        typingIndicator.classList.remove('d-none');
        sendBtn.disabled = true;
        scrollToBottom();

        // Send POST request to Flask backend
        fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({
                message: text,
                history: conversationHistory.slice(0, -1) // prior history without current message
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Server returned status ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            typingIndicator.classList.add('d-none');
            isRequestPending = false;
            sendBtn.disabled = false;

            if (data.success && data.reply) {
                appendMessage('bot', data.reply);
                conversationHistory.push({ role: 'model', text: data.reply });
            } else {
                const errMsg = data.error || "I'm having trouble processing that travel request right now. Please try again in a moment!";
                appendMessage('bot', errMsg);
            }
            scrollToBottom();
            chatInput.focus();
        })
        .catch(err => {
            console.error('TravelAI Chat Error:', err);
            typingIndicator.classList.add('d-none');
            isRequestPending = false;
            sendBtn.disabled = false;

            appendMessage('bot', "⚠️ Unable to reach the travel assistant service. Please check your internet connection or try again.");
            scrollToBottom();
            chatInput.focus();
        });
    }

    // Form Submit Event
    chatForm.addEventListener('submit', function (e) {
        e.preventDefault();
        submitMessage(chatInput.value);
    });
});
