/**
 * SAIGBOX Email Compose Module
 * Handles email composition, replies, and forwarding
 * Enhanced with sales intelligence features
 */

(function(app) {
    'use strict';

    const state = app.state;

    // Sales Intelligence State
    state.subjectSuggestions = [];
    state.ctaSuggestions = [];
    state.currentCtaStrength = null;
    state.composeContext = {};

    // ===========================================
    // Compose Modal
    // ===========================================

    /**
     * Show compose email modal
     */
    window.showComposeModal = function(prefill = {}) {
        let modal = document.getElementById('compose-modal');

        // Create modal if it doesn't exist
        if (!modal) {
            modal = createComposeModal();
            document.body.appendChild(modal);
        }

        // Clear or prefill form
        document.getElementById('composeTo').value = prefill.to || '';
        document.getElementById('composeSubject').value = prefill.subject || '';
        document.getElementById('composeBody').value = prefill.body || '';
        document.getElementById('composeCc').value = prefill.cc || '';

        modal.classList.remove('hidden');
        document.getElementById('composeTo').focus();
    };

    /**
     * Create compose modal HTML
     */
    function createComposeModal() {
        const modal = document.createElement('div');
        modal.id = 'compose-modal';
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        modal.innerHTML = `
            <div class="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
                <!-- Header -->
                <div class="flex items-center justify-between p-4 border-b">
                    <h3 class="text-lg font-semibold">New Message</h3>
                    <button onclick="closeComposeModal()" class="text-gray-400 hover:text-gray-600">
                        <i class="fas fa-times"></i>
                    </button>
                </div>

                <!-- Form -->
                <div class="flex-1 overflow-y-auto p-4">
                    <form id="compose-form" onsubmit="sendComposedEmail(event)">
                        <div class="space-y-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">To</label>
                                <input type="email" id="composeTo" required
                                       class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                       placeholder="recipient@example.com">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Cc</label>
                                <input type="text" id="composeCc"
                                       class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                       placeholder="cc@example.com (optional)">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Subject</label>
                                <div class="relative">
                                    <input type="text" id="composeSubject" required
                                           class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent pr-24"
                                           placeholder="Email subject"
                                           oninput="analyzeCtaStrength()">
                                    <button type="button" onclick="fetchSubjectSuggestions()"
                                            class="absolute right-2 top-1/2 -translate-y-1/2 px-2 py-1 text-xs bg-purple-100 text-purple-700 rounded hover:bg-purple-200"
                                            title="Get AI subject line suggestions">
                                        <i class="fas fa-magic mr-1"></i>Suggest
                                    </button>
                                </div>
                                <div id="subject-suggestions" class="hidden mt-2 border rounded-lg bg-white shadow-lg max-h-48 overflow-y-auto"></div>
                            </div>
                            <div>
                                <div class="flex items-center justify-between mb-1">
                                    <label class="block text-sm font-medium text-gray-700">Message</label>
                                    <div id="cta-strength-indicator" class="hidden flex items-center gap-2 text-xs">
                                        <span class="text-gray-500">CTA Strength:</span>
                                        <span id="cta-strength-badge" class="px-2 py-0.5 rounded font-medium"></span>
                                    </div>
                                </div>
                                <textarea id="composeBody" rows="10" required
                                          class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent resize-none"
                                          placeholder="Write your message..."
                                          oninput="analyzeCtaStrength()"></textarea>
                                <div id="cta-suggestions" class="hidden mt-2 p-3 bg-blue-50 rounded-lg border border-blue-200">
                                    <div class="flex items-center justify-between mb-2">
                                        <span class="text-sm font-medium text-blue-700"><i class="fas fa-bullhorn mr-1"></i>CTA Suggestions</span>
                                        <button onclick="hideCTASuggestions()" class="text-blue-500 hover:text-blue-700"><i class="fas fa-times"></i></button>
                                    </div>
                                    <div id="cta-suggestions-list" class="space-y-1"></div>
                                </div>
                            </div>
                        </div>
                    </form>
                </div>

                <!-- Footer -->
                <div class="flex items-center justify-between p-4 border-t bg-gray-50 rounded-b-lg">
                    <div class="flex gap-2">
                        <button onclick="askSaigToHelp()" class="px-4 py-2 text-green-600 hover:bg-green-50 rounded-lg" title="Get AI help">
                            <i class="fas fa-robot mr-2"></i>AI Help
                        </button>
                        <button onclick="showCTASuggestions()" class="px-4 py-2 text-blue-600 hover:bg-blue-50 rounded-lg" title="Get CTA suggestions">
                            <i class="fas fa-bullhorn mr-2"></i>CTA Tips
                        </button>
                    </div>
                    <div class="flex gap-2">
                        <button onclick="closeComposeModal()" class="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg">
                            Cancel
                        </button>
                        <button onclick="sendComposedEmail()" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600">
                            <i class="fas fa-paper-plane mr-2"></i>Send
                        </button>
                    </div>
                </div>
            </div>
        `;
        return modal;
    }

    /**
     * Close compose modal
     */
    window.closeComposeModal = function() {
        const modal = document.getElementById('compose-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
    };

    /**
     * Send composed email
     */
    window.sendComposedEmail = async function(event) {
        if (event) event.preventDefault();

        const to = document.getElementById('composeTo').value.trim();
        const cc = document.getElementById('composeCc').value.trim();
        const subject = document.getElementById('composeSubject').value.trim();
        const body = document.getElementById('composeBody').value.trim();

        if (!to || !subject || !body) {
            app.showNotification('Please fill in all required fields', 'warning');
            return;
        }

        // Show sending state
        const sendBtn = document.querySelector('#compose-modal button[onclick*="sendComposedEmail"]');
        if (sendBtn) {
            sendBtn.disabled = true;
            sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Sending...';
        }

        try {
            const recipients = to.split(',').map(e => e.trim()).filter(e => e);
            const ccRecipients = cc ? cc.split(',').map(e => e.trim()).filter(e => e) : [];

            const response = await app.apiJson('/api/emails/send', {
                method: 'POST',
                body: JSON.stringify({
                    to: recipients,
                    cc: ccRecipients,
                    subject: subject,
                    body: body
                })
            });

            if (response.ok) {
                app.showNotification('Email sent successfully!', 'success');
                closeComposeModal();
            } else {
                const error = await response.json();
                app.showNotification(error.detail || 'Failed to send email', 'error');
            }
        } catch (error) {
            console.error('Error sending email:', error);
            app.showNotification('Error sending email', 'error');
        } finally {
            if (sendBtn) {
                sendBtn.disabled = false;
                sendBtn.innerHTML = '<i class="fas fa-paper-plane mr-2"></i>Send';
            }
        }
    };

    // ===========================================
    // Reply & Forward
    // ===========================================

    /**
     * Reply to email
     */
    window.replyToEmail = function(emailId) {
        const email = state.allLoadedEmails.find(e => e.id === emailId);
        if (!email) return;

        const replySubject = email.subject?.startsWith('Re:') ? email.subject : `Re: ${email.subject || ''}`;
        const replyBody = `\n\n---\nOn ${new Date(email.received_at).toLocaleString()}, ${email.sender_name || email.sender} wrote:\n> ${(email.body_text || '').replace(/\n/g, '\n> ')}`;

        showComposeModal({
            to: email.sender,
            subject: replySubject,
            body: replyBody
        });
    };

    /**
     * Reply all to email
     */
    window.replyAllToEmail = function(emailId) {
        const email = state.allLoadedEmails.find(e => e.id === emailId);
        if (!email) return;

        const allRecipients = [email.sender];
        if (email.recipients) {
            const recipients = Array.isArray(email.recipients) ? email.recipients : [];
            recipients.forEach(r => {
                const addr = typeof r === 'object' ? r.email : r;
                if (addr && addr !== state.userEmail && !allRecipients.includes(addr)) {
                    allRecipients.push(addr);
                }
            });
        }

        const replySubject = email.subject?.startsWith('Re:') ? email.subject : `Re: ${email.subject || ''}`;
        const replyBody = `\n\n---\nOn ${new Date(email.received_at).toLocaleString()}, ${email.sender_name || email.sender} wrote:\n> ${(email.body_text || '').replace(/\n/g, '\n> ')}`;

        showComposeModal({
            to: allRecipients.join(', '),
            subject: replySubject,
            body: replyBody
        });
    };

    /**
     * Forward email
     */
    window.forwardEmail = function(emailId) {
        const email = state.allLoadedEmails.find(e => e.id === emailId);
        if (!email) return;

        const fwdSubject = email.subject?.startsWith('Fwd:') ? email.subject : `Fwd: ${email.subject || ''}`;
        const fwdBody = `\n\n---\nForwarded message:\nFrom: ${email.sender_name || email.sender}\nDate: ${new Date(email.received_at).toLocaleString()}\nSubject: ${email.subject || ''}\n\n${email.body_text || ''}`;

        showComposeModal({
            to: '',
            subject: fwdSubject,
            body: fwdBody
        });
    };

    // ===========================================
    // AI Help
    // ===========================================

    /**
     * Ask SAIG to help compose email
     */
    window.askSaigToHelp = function() {
        const body = document.getElementById('composeBody').value.trim();
        const subject = document.getElementById('composeSubject').value.trim();
        const to = document.getElementById('composeTo').value.trim();

        let prompt = 'Help me write an email';
        if (to) prompt += ` to ${to}`;
        if (subject) prompt += ` about "${subject}"`;
        if (body) prompt += `. Here's my draft: "${body}"`;

        // Switch to SAIG view and send message
        if (typeof window.switchView === 'function') {
            closeComposeModal();
            window.switchView('saig');
            setTimeout(() => {
                const input = document.getElementById('saig-input');
                if (input) {
                    input.value = prompt;
                    if (typeof window.sendMessage === 'function') {
                        window.sendMessage();
                    }
                }
            }, 100);
        }
    };

    /**
     * Insert AI-generated content into compose body
     */
    window.insertAiContent = function(content) {
        const bodyField = document.getElementById('composeBody');
        if (bodyField) {
            bodyField.value = content;
            bodyField.focus();
        }
    };

    // ===========================================
    // Subject Line Suggestions
    // ===========================================

    /**
     * Fetch subject line suggestions from API
     */
    window.fetchSubjectSuggestions = async function() {
        const to = document.getElementById('composeTo').value.trim();
        const subject = document.getElementById('composeSubject').value.trim();
        const body = document.getElementById('composeBody').value.trim();

        const suggestionsDiv = document.getElementById('subject-suggestions');
        if (!suggestionsDiv) return;

        // Show loading
        suggestionsDiv.innerHTML = '<div class="p-3 text-sm text-gray-500"><i class="fas fa-spinner fa-spin mr-2"></i>Generating suggestions...</div>';
        suggestionsDiv.classList.remove('hidden');

        try {
            const response = await app.apiJson('/api/sales-dashboard/generate-subject-lines', {
                method: 'POST',
                body: JSON.stringify({
                    recipient_email: to,
                    recipient_name: to.split('@')[0],
                    purpose: subject || 'professional email',
                    previous_context: body,
                    categories: ['curiosity', 'value', 'personalized']
                })
            });

            if (response.ok) {
                const data = await response.json();
                renderSubjectSuggestions(data.suggestions || []);
            } else {
                suggestionsDiv.innerHTML = '<div class="p-3 text-sm text-red-500">Failed to get suggestions</div>';
            }
        } catch (error) {
            console.error('Error fetching subject suggestions:', error);
            suggestionsDiv.innerHTML = '<div class="p-3 text-sm text-red-500">Error fetching suggestions</div>';
        }
    };

    /**
     * Render subject line suggestions
     */
    function renderSubjectSuggestions(suggestions) {
        const suggestionsDiv = document.getElementById('subject-suggestions');
        if (!suggestionsDiv) return;

        if (suggestions.length === 0) {
            suggestionsDiv.innerHTML = '<div class="p-3 text-sm text-gray-500">No suggestions available</div>';
            return;
        }

        const categoryColors = {
            curiosity: 'bg-purple-100 text-purple-700',
            value: 'bg-green-100 text-green-700',
            social_proof: 'bg-blue-100 text-blue-700',
            personalized: 'bg-yellow-100 text-yellow-700',
            urgency: 'bg-red-100 text-red-700'
        };

        suggestionsDiv.innerHTML = suggestions.map(s => `
            <div class="p-3 hover:bg-gray-50 cursor-pointer border-b last:border-b-0 flex items-center justify-between"
                 onclick="selectSubjectLine('${app.escapeHtml(s.text.replace(/'/g, "\\'"))}')">
                <div class="flex-1">
                    <div class="font-medium text-sm">${app.escapeHtml(s.text)}</div>
                    <div class="flex items-center gap-2 mt-1">
                        <span class="px-2 py-0.5 rounded text-xs ${categoryColors[s.category] || 'bg-gray-100'}">${s.category}</span>
                        ${s.estimated_open_rate ? `<span class="text-xs text-gray-500">${Math.round(s.estimated_open_rate * 100)}% est. open rate</span>` : ''}
                    </div>
                </div>
                <i class="fas fa-check text-green-500 opacity-0 hover:opacity-100 ml-2"></i>
            </div>
        `).join('');
    }

    /**
     * Select a subject line suggestion
     */
    window.selectSubjectLine = function(text) {
        const subjectField = document.getElementById('composeSubject');
        if (subjectField) {
            subjectField.value = text;
        }
        const suggestionsDiv = document.getElementById('subject-suggestions');
        if (suggestionsDiv) {
            suggestionsDiv.classList.add('hidden');
        }
        analyzeCtaStrength();
    };

    // ===========================================
    // CTA Analysis & Suggestions
    // ===========================================

    // Debounce timer for CTA analysis
    let ctaAnalysisTimer = null;

    /**
     * Analyze CTA strength in the email body
     */
    window.analyzeCtaStrength = function() {
        // Clear previous timer
        if (ctaAnalysisTimer) {
            clearTimeout(ctaAnalysisTimer);
        }

        // Debounce the analysis
        ctaAnalysisTimer = setTimeout(() => {
            performCtaAnalysis();
        }, 500);
    };

    /**
     * Perform the actual CTA analysis
     */
    function performCtaAnalysis() {
        const body = document.getElementById('composeBody')?.value || '';
        const indicator = document.getElementById('cta-strength-indicator');
        const badge = document.getElementById('cta-strength-badge');

        if (!body.trim() || body.length < 50) {
            if (indicator) indicator.classList.add('hidden');
            return;
        }

        // Simple client-side CTA detection
        const ctaPatterns = {
            strong: [
                /book a (call|demo|meeting)/i,
                /schedule a/i,
                /sign up/i,
                /get started/i,
                /buy now/i,
                /order today/i,
                /claim your/i,
                /start your (trial|free)/i
            ],
            medium: [
                /let me know/i,
                /reply to this/i,
                /click here/i,
                /learn more/i,
                /check out/i,
                /visit our/i,
                /see how/i,
                /find out/i
            ],
            soft: [
                /let's (connect|chat|talk)/i,
                /would love to/i,
                /happy to discuss/i,
                /feel free to/i,
                /reach out/i,
                /questions\?/i,
                /thoughts\?/i
            ]
        };

        let strength = 'none';
        for (const pattern of ctaPatterns.strong) {
            if (pattern.test(body)) {
                strength = 'strong';
                break;
            }
        }
        if (strength === 'none') {
            for (const pattern of ctaPatterns.medium) {
                if (pattern.test(body)) {
                    strength = 'medium';
                    break;
                }
            }
        }
        if (strength === 'none') {
            for (const pattern of ctaPatterns.soft) {
                if (pattern.test(body)) {
                    strength = 'soft';
                    break;
                }
            }
        }

        // Update indicator
        if (indicator && badge) {
            indicator.classList.remove('hidden');

            const strengthConfig = {
                strong: { text: 'Strong', class: 'bg-green-100 text-green-700' },
                medium: { text: 'Medium', class: 'bg-yellow-100 text-yellow-700' },
                soft: { text: 'Soft', class: 'bg-blue-100 text-blue-700' },
                none: { text: 'Missing', class: 'bg-red-100 text-red-700' }
            };

            const config = strengthConfig[strength];
            badge.textContent = config.text;
            badge.className = `px-2 py-0.5 rounded font-medium ${config.class}`;
        }

        state.currentCtaStrength = strength;
    }

    /**
     * Show CTA suggestions panel
     */
    window.showCTASuggestions = async function() {
        const suggestionsDiv = document.getElementById('cta-suggestions');
        const listDiv = document.getElementById('cta-suggestions-list');

        if (!suggestionsDiv || !listDiv) return;

        suggestionsDiv.classList.remove('hidden');
        listDiv.innerHTML = '<div class="text-sm text-gray-500"><i class="fas fa-spinner fa-spin mr-2"></i>Loading suggestions...</div>';

        try {
            const body = document.getElementById('composeBody')?.value || '';
            const to = document.getElementById('composeTo')?.value || '';

            const response = await app.apiJson('/api/sales-dashboard/suggest-cta', {
                method: 'POST',
                body: JSON.stringify({
                    email_content: body,
                    recipient_email: to,
                    stage: 'engaged' // Default stage
                })
            });

            if (response.ok) {
                const data = await response.json();
                renderCtaSuggestions(data.suggestions || []);
            } else {
                listDiv.innerHTML = '<div class="text-sm text-red-500">Failed to load suggestions</div>';
            }
        } catch (error) {
            console.error('Error fetching CTA suggestions:', error);
            listDiv.innerHTML = '<div class="text-sm text-red-500">Error loading suggestions</div>';
        }
    };

    /**
     * Render CTA suggestions
     */
    function renderCtaSuggestions(suggestions) {
        const listDiv = document.getElementById('cta-suggestions-list');
        if (!listDiv) return;

        if (suggestions.length === 0) {
            listDiv.innerHTML = '<div class="text-sm text-gray-500">No suggestions available</div>';
            return;
        }

        const strengthColors = {
            strong: 'border-green-300 bg-green-50',
            medium: 'border-yellow-300 bg-yellow-50',
            soft: 'border-blue-300 bg-blue-50'
        };

        listDiv.innerHTML = suggestions.map(s => `
            <div class="p-2 border rounded cursor-pointer hover:bg-white ${strengthColors[s.strength] || 'border-gray-200'}"
                 onclick="insertCta('${app.escapeHtml(s.text.replace(/'/g, "\\'"))}')">
                <div class="text-sm font-medium">"${app.escapeHtml(s.text)}"</div>
                <div class="text-xs text-gray-600 mt-1">${s.strength} CTA - ${s.context || ''}</div>
            </div>
        `).join('');
    }

    /**
     * Insert CTA into email body
     */
    window.insertCta = function(cta) {
        const bodyField = document.getElementById('composeBody');
        if (bodyField) {
            const currentValue = bodyField.value.trim();
            bodyField.value = currentValue + (currentValue ? '\n\n' : '') + cta;
            bodyField.focus();
            analyzeCtaStrength();
        }
    };

    /**
     * Hide CTA suggestions
     */
    window.hideCTASuggestions = function() {
        const suggestionsDiv = document.getElementById('cta-suggestions');
        if (suggestionsDiv) {
            suggestionsDiv.classList.add('hidden');
        }
    };

})(window.SAIGBOX);
