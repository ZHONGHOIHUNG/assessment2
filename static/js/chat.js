// AI Chat functionality

// Chat state
const chatState = {
    isOpen: false,
    history: [],
    isProcessing: false
};

// DOM elements
const chatToggleBtn = document.getElementById('chatToggleBtn');
const chatWindow = document.getElementById('chatWindow');
const closeChatBtn = document.getElementById('closeChatBtn');
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const sendChatBtn = document.getElementById('sendChatBtn');

// Initialize chat
document.addEventListener('DOMContentLoaded', () => {
    setupChatListeners();
});

function setupChatListeners() {
    chatToggleBtn.addEventListener('click', toggleChat);
    closeChatBtn.addEventListener('click', toggleChat);
    sendChatBtn.addEventListener('click', sendMessage);
    
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

function toggleChat() {
    chatState.isOpen = !chatState.isOpen;
    chatWindow.classList.toggle('active');
    
    if (chatState.isOpen) {
        chatInput.focus();
    }
}

async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message || chatState.isProcessing) return;

    // Add user message to UI
    addMessageToChat('user', message);
    chatInput.value = '';
    
    // Add to history
    chatState.history.push({
        role: 'user',
        content: message
    });

    // Show typing indicator
    const typingId = addTypingIndicator();
    chatState.isProcessing = true;
    sendChatBtn.disabled = true;
    chatInput.disabled = true;

    try {
        // Call chat API with streaming
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: message,
                history: chatState.history.slice(-6) // Last 3 exchanges
            })
        });

        if (!response.ok) {
            throw new Error('Chat request failed');
        }

        // Remove typing indicator
        removeTypingIndicator(typingId);

        // Create assistant message container
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message-assistant rounded-lg p-3 text-sm';
        chatMessages.appendChild(messageDiv);

        // Read streaming response
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let assistantMessage = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        if (data.type === 'content') {
                            assistantMessage += data.text;
                            messageDiv.textContent = assistantMessage;
                            chatMessages.scrollTop = chatMessages.scrollHeight;
                        } else if (data.type === 'error') {
                            throw new Error(data.message);
                        } else if (data.type === 'done') {
                            // Add to history
                            chatState.history.push({
                                role: 'assistant',
                                content: assistantMessage
                            });
                        }
                    } catch (e) {
                        console.error('Error parsing SSE data:', e);
                    }
                }
            }
        }

        // Format the message with markdown-like formatting
        messageDiv.innerHTML = formatChatMessage(assistantMessage);

    } catch (error) {
        console.error('Chat error:', error);
        removeTypingIndicator(typingId);
        addMessageToChat('assistant', `Sorry, I encountered an error: ${error.message}. Please try again.`);
    } finally {
        chatState.isProcessing = false;
        sendChatBtn.disabled = false;
        chatInput.disabled = false;
        chatInput.focus();
    }
}

function addMessageToChat(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message-${role} rounded-lg p-3 text-sm`;
    
    if (role === 'assistant') {
        messageDiv.innerHTML = formatChatMessage(content);
    } else {
        messageDiv.textContent = content;
    }
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function formatChatMessage(text) {
    // Simple markdown-like formatting
    let formatted = text;
    
    // Bold text: **text**
    formatted = formatted.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    
    // Bullet points
    formatted = formatted.replace(/^- (.+)$/gm, '• $1');
    formatted = formatted.replace(/^\* (.+)$/gm, '• $1');
    
    // Numbered lists
    formatted = formatted.replace(/^(\d+)\. /gm, '<strong>$1.</strong> ');
    
    // Line breaks
    formatted = formatted.replace(/\n/g, '<br>');
    
    // Product IDs (for linking)
    formatted = formatted.replace(/\(ID: (\d+)\)/g, '<span class="text-xs text-gray-500">(ID: $1)</span>');
    
    return formatted;
}

function addTypingIndicator() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message-assistant rounded-lg p-3 text-sm';
    typingDiv.id = `typing-${Date.now()}`;
    typingDiv.innerHTML = '<span class="loading-dots">Thinking</span>';
    chatMessages.appendChild(typingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return typingDiv.id;
}

function removeTypingIndicator(id) {
    const typingDiv = document.getElementById(id);
    if (typingDiv) {
        typingDiv.remove();
    }
}

// Suggested chat prompts
const suggestedPrompts = [
    "What sustainable flooring options do you have?",
    "Compare low carbon concrete products",
    "Show me timber cladding with certifications",
    "What are the most durable facade materials?"
];

// Optional: Add suggested prompts on first open
let firstOpen = true;
chatToggleBtn.addEventListener('click', () => {
    if (firstOpen && chatState.isOpen) {
        firstOpen = false;
        setTimeout(() => {
            const suggestionsDiv = document.createElement('div');
            suggestionsDiv.className = 'message-assistant rounded-lg p-3 text-sm';
            suggestionsDiv.innerHTML = `
                <p class="mb-2"><strong>Try asking:</strong></p>
                ${suggestedPrompts.map(prompt => 
                    `<button class="suggested-prompt block w-full text-left px-3 py-2 mb-1 bg-gray-100 hover:bg-gray-200 rounded text-xs transition-colors">
                        ${prompt}
                    </button>`
                ).join('')}
            `;
            chatMessages.appendChild(suggestionsDiv);
            
            // Add click handlers to suggested prompts
            suggestionsDiv.querySelectorAll('.suggested-prompt').forEach(btn => {
                btn.addEventListener('click', () => {
                    chatInput.value = btn.textContent.trim();
                    sendMessage();
                });
            });
            
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }, 500);
    }
});

