/**
 * SAIGBOX SAIG Assistant Module
 * Handles AI chat interactions and email assistance
 */

(function(app) {
    'use strict';

    const state = app.state;

    // ===========================================
    // Chat State
    // ===========================================

    state.saigContext = state.saigContext || {};
    state.chatHistory = state.chatHistory || [];

    // ===========================================
    // Chat Functions
    // ===========================================

    /**
     * Send message to SAIG assistant
     */
    window.sendMessage = async function(directMessage = null) {
        const inputField = document.getElementById('saig-input');
        const message = directMessage || (inputField ? inputField.value.trim() : '');

        if (!message) return;

        // Clear input
        if (inputField && !directMessage) {
            inputField.value = '';
        }

        // Add user message to chat
        addMessageToChat('user', message);

        // Build context
        const fullContext = {
            ...state.saigContext,
            selected_email_id: state.selectedEmailId,
            current_view: state.currentView,
            user_email: state.userEmail
        };

        try {
            const response = await app.apiJson('/api/saig/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: message,
                    context: fullContext
                })
            });

            if (response.ok) {
                const result = await response.json();

                // Add assistant response to chat
                addMessageToChat('assistant', result.response);

                // Update context if provided
                if (result.context) {
                    state.saigContext = { ...state.saigContext, ...result.context };
                }

                // Handle any actions
                if (result.actions_taken && result.actions_taken.length > 0) {
                    handleSaigActions(result.actions_taken);
                }
            } else {
                addMessageToChat('assistant', 'Sorry, I encountered an error. Please try again.');
            }
        } catch (error) {
            console.error('SAIG chat error:', error);
            addMessageToChat('assistant', 'Sorry, I encountered an error. Please try again.');
        }
    };

    /**
     * Add message to chat display
     */
    function addMessageToChat(role, content) {
        const chatContainer = document.getElementById('saig-chat');
        if (!chatContainer) return;

        const messageDiv = document.createElement('div');
        messageDiv.className = `p-4 ${role === 'user' ? 'bg-gray-100' : 'bg-white'} rounded-lg mb-2`;

        if (role === 'user') {
            messageDiv.innerHTML = `
                <div class="flex items-start gap-3">
                    <div class="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center text-white">
                        <i class="fas fa-user"></i>
                    </div>
                    <div class="flex-1">
                        <p class="text-sm text-gray-800">${app.escapeHtml(content)}</p>
                    </div>
                </div>
            `;
        } else {
            messageDiv.innerHTML = `
                <div class="flex items-start gap-3">
                    <div class="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center text-white">
                        <i class="fas fa-robot"></i>
                    </div>
                    <div class="flex-1">
                        <div class="text-sm text-gray-800 prose prose-sm max-w-none">${formatSaigResponse(content)}</div>
                    </div>
                </div>
            `;
        }

        chatContainer.appendChild(messageDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;

        // Add to history
        state.chatHistory.push({ role, content });
    }

    /**
     * Format SAIG response with markdown-like formatting
     */
    function formatSaigResponse(text) {
        if (!text) return '';

        // Convert markdown-style formatting
        let formatted = text
            // Bold
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            // Italic
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            // Code blocks
            .replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre class="bg-gray-100 p-2 rounded"><code>$2</code></pre>')
            // Inline code
            .replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1 rounded">$1</code>')
            // Line breaks
            .replace(/\n/g, '<br>');

        return formatted;
    }

    /**
     * Handle actions taken by SAIG
     */
    function handleSaigActions(actions) {
        for (const action of actions) {
            switch (action.type) {
                case 'email_sent':
                    app.showNotification('Email sent successfully', 'success');
                    break;
                case 'email_deleted':
                    app.showNotification('Email moved to trash', 'success');
                    if (typeof loadEmails === 'function') loadEmails();
                    break;
                case 'action_created':
                    app.showNotification('Action item created', 'success');
                    if (typeof loadActionItems === 'function') loadActionItems();
                    break;
                case 'compose_email':
                    if (typeof showComposeModal === 'function') {
                        showComposeModal();
                        // Pre-fill fields if provided
                        if (action.data) {
                            setTimeout(() => {
                                if (action.data.to) document.getElementById('composeTo').value = action.data.to;
                                if (action.data.subject) document.getElementById('composeSubject').value = action.data.subject;
                                if (action.data.body) document.getElementById('composeBody').value = action.data.body;
                            }, 100);
                        }
                    }
                    break;
            }
        }
    }

    // ===========================================
    // SAIG Reply Modal
    // ===========================================

    /**
     * Show SAIG reply modal for an email
     */
    window.showSAIGReplyModal = function(emailId) {
        const email = state.allLoadedEmails.find(e => e.id === emailId);
        if (!email) return;

        const modal = document.getElementById('saig-reply-modal');
        if (modal) {
            modal.classList.remove('hidden');
            // Generate reply
            generateSAIGReply(emailId);
        }
    };

    /**
     * Close SAIG reply modal
     */
    window.closeSAIGReplyModal = function() {
        const modal = document.getElementById('saig-reply-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
    };

    /**
     * Generate AI reply suggestion
     */
    window.generateSAIGReply = async function(emailId) {
        const email = state.allLoadedEmails.find(e => e.id === emailId);
        if (!email) return;

        const replyContent = document.getElementById('saig-reply-content');
        if (replyContent) {
            replyContent.innerHTML = '<div class="text-center py-4"><i class="fas fa-spinner fa-spin mr-2"></i>Generating reply...</div>';
        }

        try {
            const response = await app.apiJson('/api/saig/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: `Generate a professional reply to this email from ${email.sender_name || email.sender}. Subject: ${email.subject}. Content: ${email.body_text || email.snippet}`,
                    context: { selected_email: email }
                })
            });

            if (response.ok) {
                const result = await response.json();
                if (replyContent) {
                    replyContent.innerHTML = `<textarea class="w-full h-48 p-3 border rounded" id="saig-reply-text">${app.escapeHtml(result.response)}</textarea>`;
                }
            }
        } catch (error) {
            console.error('Error generating reply:', error);
            if (replyContent) {
                replyContent.innerHTML = '<div class="text-red-500">Error generating reply</div>';
            }
        }
    };

    /**
     * Send the SAIG-generated reply
     */
    window.sendSAIGReply = async function(emailId) {
        const email = state.allLoadedEmails.find(e => e.id === emailId);
        if (!email) return;

        const replyText = document.getElementById('saig-reply-text');
        if (!replyText || !replyText.value.trim()) {
            app.showNotification('Please enter a reply', 'warning');
            return;
        }

        try {
            const response = await app.apiJson(`/api/emails/${emailId}/reply`, {
                method: 'POST',
                body: JSON.stringify({
                    body: replyText.value,
                    reply_all: false
                })
            });

            if (response.ok) {
                app.showNotification('Reply sent!', 'success');
                closeSAIGReplyModal();
            } else {
                app.showNotification('Failed to send reply', 'error');
            }
        } catch (error) {
            console.error('Error sending reply:', error);
            app.showNotification('Error sending reply', 'error');
        }
    };

    // ===========================================
    // Quick Actions
    // ===========================================

    /**
     * Handle quick action clicks
     */
    window.saigQuickAction = function(action) {
        switch (action) {
            case 'summarize':
                sendMessage('Summarize my unread emails');
                break;
            case 'urgent':
                sendMessage('What are my most urgent emails?');
                break;
            case 'action-items':
                sendMessage('Extract action items from my recent emails');
                break;
            case 'compose':
                if (typeof showComposeModal === 'function') showComposeModal();
                break;
            default:
                sendMessage(action);
        }
    };

})(window.SAIGBOX);
