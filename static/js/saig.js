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
     * Set selected email for SAIG context (used by SAIG Reply feature)
     */
    window.setSelectedEmailForSAIG = function(email) {
        if (!email) return;

        // Store the selected email in SAIG context with full details
        state.saigContext = state.saigContext || {};
        state.saigContext.selected_email = {
            id: email.id,
            gmail_id: email.gmail_id,      // For Gmail API threading
            thread_id: email.thread_id,    // For conversation context
            subject: email.subject,
            sender: email.sender,
            sender_name: email.sender_name,
            recipients: email.recipients || [],
            body: email.body_text || email.body_html || email.snippet || '',
            received_at: email.received_at,
            is_urgent: email.is_urgent,
            labels: email.labels || []
        };
        state.selectedEmailId = email.id;

        // Persist to sessionStorage for cross-component access
        try {
            sessionStorage.setItem('saig_selected_email', JSON.stringify(state.saigContext.selected_email));
            sessionStorage.setItem('saig_selected_email_id', email.id);
        } catch (e) {
            console.warn('Could not persist email context to sessionStorage:', e);
        }

        console.log('SAIG context updated with selected email:', email.subject);

        // Update the context indicator in SAIG chat
        updateSaigContextIndicator();
    };

    // Update the SAIG context indicator UI
    function updateSaigContextIndicator() {
        const contextDiv = document.getElementById('saig-email-context');
        const subjectSpan = document.getElementById('saig-context-email-subject');

        if (!contextDiv || !subjectSpan) return;

        const selectedEmail = state.saigContext?.selected_email;

        if (selectedEmail && selectedEmail.subject) {
            subjectSpan.textContent = selectedEmail.subject;
            contextDiv.classList.remove('hidden');
        } else {
            contextDiv.classList.add('hidden');
        }
    }

    // Clear the SAIG email context
    window.clearSaigEmailContext = function() {
        state.saigContext = state.saigContext || {};
        delete state.saigContext.selected_email;
        state.selectedEmailId = null;

        // Clear from sessionStorage
        try {
            sessionStorage.removeItem('saig_selected_email');
            sessionStorage.removeItem('saig_selected_email_id');
        } catch (e) {
            console.warn('Could not clear sessionStorage:', e);
        }

        // Update UI
        updateSaigContextIndicator();
        app.showNotification('Email context cleared', 'info');
    };

    // Restore context from sessionStorage on load
    window.restoreSaigContext = function() {
        try {
            const savedEmail = sessionStorage.getItem('saig_selected_email');
            const savedEmailId = sessionStorage.getItem('saig_selected_email_id');
            if (savedEmail && savedEmailId) {
                state.saigContext = state.saigContext || {};
                state.saigContext.selected_email = JSON.parse(savedEmail);
                state.selectedEmailId = savedEmailId;
                console.log('SAIG context restored from sessionStorage');
                // Update UI after restore
                updateSaigContextIndicator();
            }
        } catch (e) {
            console.warn('Could not restore SAIG context:', e);
        }
    };

    // Auto-restore on module load
    window.restoreSaigContext();

    // Also update indicator when DOM is ready (in case SAIG chat wasn't in DOM yet)
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', updateSaigContextIndicator);
    } else {
        setTimeout(updateSaigContextIndicator, 100);
    }

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
            const response = await app.apiJson('/api/emails/reply', {
                method: 'POST',
                body: JSON.stringify({
                    email_id: emailId,
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
    // Email Reference Disambiguation
    // ===========================================

    /**
     * Select an email from disambiguation UI and continue with reply
     */
    window.selectEmailForReply = async function(emailId, subject) {
        console.log('selectEmailForReply called:', emailId, subject);

        // Show loading state
        app.showNotification('Loading email...', 'info');

        try {
            // Fetch full email details
            const response = await app.apiJson(`/api/emails/${emailId}`);

            if (response.ok) {
                const email = await response.json();

                // Set as selected email for SAIG
                window.setSelectedEmailForSAIG(email);

                // Notify user
                app.showNotification(`Selected: ${email.subject || subject}`, 'success');

                // Add message to chat showing selection
                addMessageToChat('assistant', `<div class="text-sm text-blue-600 mb-2"><i class="fas fa-check-circle mr-2"></i>Selected email: "${email.subject || subject}"</div>`);

                // Now automatically ask SAIG to generate a reply
                setTimeout(() => {
                    sendMessage('Please generate a reply to this email');
                }, 300);

            } else {
                app.showNotification('Failed to load email', 'error');
            }
        } catch (error) {
            console.error('Error selecting email:', error);
            app.showNotification('Error loading email', 'error');
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

    // ===========================================
    // Voice Commands
    // ===========================================

    let recognition = null;
    let isListening = false;

    /**
     * Initialize speech recognition
     */
    function initSpeechRecognition() {
        if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
            console.log('Speech recognition not supported');
            return null;
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const rec = new SpeechRecognition();
        rec.continuous = false;
        rec.interimResults = false;
        rec.lang = 'en-US';

        rec.onresult = function(event) {
            const transcript = event.results[0][0].transcript.toLowerCase().trim();
            console.log('Voice command recognized:', transcript);
            handleVoiceCommand(transcript);
        };

        rec.onerror = function(event) {
            console.error('Speech recognition error:', event.error);
            isListening = false;
            updateVoiceButton();
            if (event.error !== 'no-speech') {
                app.showNotification('Voice recognition error: ' + event.error, 'error');
            }
        };

        rec.onend = function() {
            isListening = false;
            updateVoiceButton();
        };

        return rec;
    }

    /**
     * Handle recognized voice commands
     */
    function handleVoiceCommand(command) {
        // Quick reply commands
        if (command.includes('reply yes') || command.includes('accept')) {
            if (state.selectedEmailId && typeof quickReply === 'function') {
                quickReply(state.selectedEmailId, 'accept');
                app.showNotification('Generating accept reply...', 'info');
            } else {
                app.showNotification('Please select an email first', 'warning');
            }
            return;
        }

        if (command.includes('reply no') || command.includes('decline')) {
            if (state.selectedEmailId && typeof quickReply === 'function') {
                quickReply(state.selectedEmailId, 'decline');
                app.showNotification('Generating decline reply...', 'info');
            } else {
                app.showNotification('Please select an email first', 'warning');
            }
            return;
        }

        if (command.includes('schedule') || command.includes('call')) {
            if (state.selectedEmailId && typeof quickReply === 'function') {
                quickReply(state.selectedEmailId, 'schedule_call');
                app.showNotification('Generating schedule reply...', 'info');
            } else {
                app.showNotification('Please select an email first', 'warning');
            }
            return;
        }

        if (command.includes('acknowledge') || command.includes('got it')) {
            if (state.selectedEmailId && typeof quickReply === 'function') {
                quickReply(state.selectedEmailId, 'acknowledge');
                app.showNotification('Generating acknowledgment...', 'info');
            } else {
                app.showNotification('Please select an email first', 'warning');
            }
            return;
        }

        if (command.includes('send it') || command.includes('send now')) {
            const sendBtn = document.getElementById('saig-modal-send-btn') || document.getElementById('quick-reply-send-btn');
            if (sendBtn) {
                sendBtn.click();
                app.showNotification('Sending...', 'info');
            } else {
                app.showNotification('No reply ready to send', 'warning');
            }
            return;
        }

        if (command.includes('cancel') || command.includes('go back')) {
            if (typeof cancelSaigReplyInModal === 'function') {
                cancelSaigReplyInModal();
                app.showNotification('Cancelled', 'info');
            }
            return;
        }

        // General commands - send to SAIG
        sendMessage(command);
        app.showNotification('Processing: "' + command + '"', 'info');
    }

    /**
     * Update voice button appearance
     */
    function updateVoiceButton() {
        const btn = document.getElementById('voice-command-btn');
        if (!btn) return;

        if (isListening) {
            btn.classList.add('listening');
            btn.innerHTML = '<i class="fas fa-microphone-slash"></i>';
            btn.title = 'Stop listening';
        } else {
            btn.classList.remove('listening');
            btn.innerHTML = '<i class="fas fa-microphone"></i>';
            btn.title = 'Start voice command';
        }
    }

    /**
     * Start/stop voice recognition
     */
    window.toggleVoiceCommand = function() {
        if (!recognition) {
            recognition = initSpeechRecognition();
        }

        if (!recognition) {
            app.showNotification('Voice commands not supported in this browser', 'warning');
            return;
        }

        if (isListening) {
            recognition.stop();
            isListening = false;
        } else {
            try {
                recognition.start();
                isListening = true;
                app.showNotification('Listening... Say a command like "reply yes" or "schedule call"', 'info');
            } catch (e) {
                console.error('Failed to start recognition:', e);
                app.showNotification('Failed to start voice recognition', 'error');
            }
        }

        updateVoiceButton();
    };

    /**
     * Check if voice commands are supported
     */
    window.isVoiceSupported = function() {
        return ('webkitSpeechRecognition' in window) || ('SpeechRecognition' in window);
    };

})(window.SAIGBOX);
