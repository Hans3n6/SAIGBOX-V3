/**
 * Company Intelligence Agent UI
 * Interface for teaching SAIG about your company
 * After learning, users interact with SAIG for queries
 */

class CompanyAgent {
    constructor() {
        this.apiBase = '/api/company-agent';
        this.status = null;
        this.chatHistory = [];
        this.isLoading = false;
        this.pollInterval = null;
    }

    /**
     * Initialize the Company Agent tab
     */
    async init() {
        await this.loadStatus();
        this.render();
        this.attachEventListeners();
    }

    /**
     * Load current agent status
     */
    async loadStatus() {
        try {
            const response = await fetch(`${this.apiBase}/status`, {
                credentials: 'include'
            });
            if (response.ok) {
                this.status = await response.json();
            }
        } catch (error) {
            console.error('Failed to load agent status:', error);
        }
    }

    /**
     * Render the Company Agent UI
     */
    render() {
        const container = document.getElementById('company-agent-content');
        if (!container) return;

        const hasKnowledge = this.status && this.status.total_chunks > 0;

        container.innerHTML = `
            <div class="company-agent-container">
                <!-- Header Section -->
                <div class="agent-header">
                    <div class="agent-title">
                        <svg class="agent-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 2a3 3 0 0 0-3 3v1H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-3V5a3 3 0 0 0-3-3z"/>
                            <circle cx="12" cy="13" r="2"/>
                            <path d="M10 13h.01M14 13h.01"/>
                        </svg>
                        <h2>Teach SAIG About Your Company</h2>
                    </div>
                    <p class="agent-subtitle">Enter your website and SAIG will learn everything about your company</p>
                </div>

                <!-- Setup Section -->
                <div class="agent-setup ${hasKnowledge ? 'has-knowledge' : ''}">
                    ${this.renderSetupSection(hasKnowledge)}
                </div>

                <!-- Knowledge Status -->
                ${hasKnowledge ? this.renderKnowledgeStatus() : ''}

                <!-- SAIG Integration Banner (when knowledge exists) -->
                ${hasKnowledge ? `
                    <div class="saig-integration-banner">
                        <div class="banner-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                            </svg>
                        </div>
                        <div class="banner-content">
                            <h3>SAIG is ready to help you sell!</h3>
                            <p>Go to the <strong>SAIG</strong> tab to ask questions about your company, get sales talking points, or competitive intel.</p>
                            <div class="banner-examples">
                                <span>"What are our main products?"</span>
                                <span>"Give me talking points for a healthcare CTO"</span>
                                <span>"How do we compare to [Competitor]?"</span>
                            </div>
                        </div>
                        <button id="go-to-saig-btn" class="btn-primary" onclick="window.switchView && window.switchView('saig')">
                            Go to SAIG
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px; margin-left: 6px;">
                                <path d="M5 12h14M12 5l7 7-7 7"/>
                            </svg>
                        </button>
                    </div>
                ` : ''}
            </div>
        `;
    }

    /**
     * Render setup section
     */
    renderSetupSection(hasKnowledge) {
        if (this.status?.crawl_progress?.in_progress) {
            return `
                <div class="setup-crawling">
                    <div class="crawl-spinner"></div>
                    <div class="crawl-status">
                        <h3>Learning your company...</h3>
                        <p class="crawl-progress">${this.status.crawl_progress.status}</p>
                        <div class="crawl-stats">
                            <span>${this.status.crawl_progress.pages || 0} pages crawled</span>
                            <span>${this.status.crawl_progress.chunks || 0} knowledge chunks</span>
                        </div>
                        <button id="refresh-status-btn" class="btn-secondary" style="margin-top: 12px;">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 14px; height: 14px;">
                                <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                            </svg>
                            Refresh Status
                        </button>
                    </div>
                </div>
            `;
        }

        if (hasKnowledge) {
            return `
                <div class="setup-complete">
                    <div class="setup-domain">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
                            <path d="M2 12h20M12 2c2.5 2.5 4 6 4 10s-1.5 7.5-4 10c-2.5-2.5-4-6-4-10s1.5-7.5 4-10z"/>
                        </svg>
                        <span>${this.status.domain || 'Your Company'}</span>
                    </div>
                    <div class="setup-actions">
                        <button id="generate-demo-emails-btn" class="btn-primary" style="margin-right: 8px;">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px;">
                                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                                <polyline points="22,6 12,13 2,6"/>
                            </svg>
                            Generate Demo Emails
                        </button>
                        <button id="relearn-btn" class="btn-secondary">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                            </svg>
                            Re-learn
                        </button>
                    </div>
                </div>
            `;
        }

        return `
            <div class="setup-new">
                <h3>Teach Me About Your Company</h3>
                <p>Enter your company website and I'll learn everything about your products, services, pricing, and more.</p>
                <div class="setup-input-container">
                    <input
                        type="url"
                        id="website-url"
                        class="website-input"
                        placeholder="https://yourcompany.com"
                    />
                    <button id="learn-btn" class="btn-primary">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 2a3 3 0 0 0-3 3v1H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-3V5a3 3 0 0 0-3-3z"/>
                        </svg>
                        Start Learning
                    </button>
                </div>
                <div class="demo-emails-section" style="margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--border-color, #e5e7eb);">
                    <p style="color: var(--text-muted, #6b7280); font-size: 14px; margin-bottom: 12px;">
                        Or try the demo with sample sales emails:
                    </p>
                    <button id="generate-demo-emails-btn" class="btn-secondary">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px;">
                            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                            <polyline points="22,6 12,13 2,6"/>
                        </svg>
                        Generate Demo Emails
                    </button>
                </div>
            </div>
        `;
    }

    /**
     * Render knowledge status cards
     */
    renderKnowledgeStatus() {
        const areas = this.status.knowledge_areas || {};
        const areaLabels = {
            'homepage': 'Homepage',
            'about': 'About',
            'product': 'Products',
            'pricing': 'Pricing',
            'case_study': 'Case Studies',
            'faq': 'FAQ',
            'blog': 'Blog',
            'team': 'Team',
            'contact': 'Contact',
            'comparison': 'Comparisons',
            'industries': 'Industries',
            'other': 'Other'
        };

        const knowledgeCards = Object.entries(areas)
            .filter(([_, count]) => count > 0)
            .map(([type, count]) => `
                <div class="knowledge-card">
                    <span class="card-count">${count}</span>
                    <span class="card-label">${areaLabels[type] || type}</span>
                </div>
            `).join('');

        return `
            <div class="knowledge-status">
                <div class="knowledge-summary">
                    <div class="summary-stat">
                        <span class="stat-value">${this.status.total_pages}</span>
                        <span class="stat-label">Pages Indexed</span>
                    </div>
                    <div class="summary-stat">
                        <span class="stat-value">${this.status.total_chunks}</span>
                        <span class="stat-label">Knowledge Chunks</span>
                    </div>
                    <div class="summary-stat">
                        <span class="stat-value">${Object.keys(areas).length}</span>
                        <span class="stat-label">Content Types</span>
                    </div>
                </div>
                <div class="knowledge-areas">
                    ${knowledgeCards}
                </div>
            </div>
        `;
    }

    /**
     * Render chat messages
     */
    renderChatMessages() {
        if (this.chatHistory.length === 0) {
            return `
                <div class="chat-empty">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    </svg>
                    <p>Ask me anything about your company!</p>
                </div>
            `;
        }

        return this.chatHistory.map(msg => `
            <div class="chat-message ${msg.role}">
                <div class="message-content">${this.formatMessage(msg.content)}</div>
                ${msg.sources && msg.sources.length > 0 ? `
                    <div class="message-sources">
                        <span class="sources-label">Sources:</span>
                        ${msg.sources.map(s => `<a href="${s.url}" target="_blank" class="source-link">${s.title}</a>`).join('')}
                    </div>
                ` : ''}
            </div>
        `).join('');
    }

    /**
     * Render suggested questions
     */
    renderSuggestions() {
        const suggestions = [
            "What are our main products?",
            "Who are our competitors?",
            "What's our pricing model?",
            "Tell me about our case studies",
            "What industries do we serve?"
        ];

        return `
            <div class="chat-suggestions">
                ${suggestions.map(s => `
                    <button class="suggestion-btn" data-question="${s}">${s}</button>
                `).join('')}
            </div>
        `;
    }

    /**
     * Render quick action buttons
     */
    renderQuickActions() {
        return `
            <div class="quick-actions">
                <h3>Quick Actions</h3>
                <div class="action-buttons">
                    <button class="action-btn" data-action="competitor-intel">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
                            <circle cx="9" cy="7" r="4"/>
                            <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
                        </svg>
                        <span>Competitor Intel</span>
                    </button>
                    <button class="action-btn" data-action="email-context">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                            <path d="M22 6l-10 7L2 6"/>
                        </svg>
                        <span>Email Help</span>
                    </button>
                    <button class="action-btn" data-action="search">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="11" cy="11" r="8"/>
                            <path d="M21 21l-4.35-4.35"/>
                        </svg>
                        <span>Search Knowledge</span>
                    </button>
                </div>
            </div>
        `;
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        // Learn button
        const learnBtn = document.getElementById('learn-btn');
        if (learnBtn) {
            learnBtn.addEventListener('click', () => this.startLearning());
        }

        // Re-learn button
        const relearnBtn = document.getElementById('relearn-btn');
        if (relearnBtn) {
            relearnBtn.addEventListener('click', () => this.showRelearnDialog());
        }

        // Generate demo emails button
        const generateDemoBtn = document.getElementById('generate-demo-emails-btn');
        if (generateDemoBtn) {
            generateDemoBtn.addEventListener('click', () => this.generateDemoEmails());
        }

        // Refresh status button (during crawl)
        const refreshBtn = document.getElementById('refresh-status-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', async () => {
                await this.loadStatus();
                this.render();
                this.attachEventListeners();
            });
        }

        // Chat input
        const chatInput = document.getElementById('chat-input');
        const sendBtn = document.getElementById('send-btn');

        if (chatInput) {
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        if (sendBtn) {
            sendBtn.addEventListener('click', () => this.sendMessage());
        }

        // Suggestion buttons
        document.querySelectorAll('.suggestion-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const question = btn.dataset.question;
                document.getElementById('chat-input').value = question;
                this.sendMessage();
            });
        });

        // Quick action buttons
        document.querySelectorAll('.action-btn').forEach(btn => {
            btn.addEventListener('click', () => this.handleQuickAction(btn.dataset.action));
        });
    }

    /**
     * Start learning a new company website
     */
    async startLearning() {
        const urlInput = document.getElementById('website-url');
        const url = urlInput?.value?.trim();

        if (!url) {
            this.showToast('Please enter a website URL', 'error');
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/learn`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ website_url: url, max_pages: 100 })
            });

            if (response.ok) {
                this.showToast('Learning started! This may take a few minutes.', 'success');
                this.startPolling();
            } else {
                const error = await response.json();
                this.showToast(error.detail || 'Failed to start learning', 'error');
            }
        } catch (error) {
            console.error('Learn error:', error);
            this.showToast('Failed to start learning', 'error');
        }
    }

    /**
     * Poll for crawl progress
     */
    startPolling() {
        if (this.pollInterval) clearInterval(this.pollInterval);

        this.pollInterval = setInterval(async () => {
            await this.loadStatus();
            console.log('Poll status:', this.status?.crawl_progress);
            this.render();
            this.attachEventListeners();

            // Explicit false check (not just falsy)
            const inProgress = this.status?.crawl_progress?.in_progress;
            if (inProgress === false) {
                clearInterval(this.pollInterval);
                this.pollInterval = null;
                if (this.status?.total_chunks > 0) {
                    this.showToast('Learning complete! Ask me anything.', 'success');
                }
            }
        }, 2000);
    }

    /**
     * Send a chat message
     */
    async sendMessage() {
        const input = document.getElementById('chat-input');
        const question = input?.value?.trim();

        if (!question || this.isLoading) return;

        // Add user message to history
        this.chatHistory.push({ role: 'user', content: question });
        input.value = '';
        this.renderChatArea();

        this.isLoading = true;

        try {
            const response = await fetch(`${this.apiBase}/ask`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ question })
            });

            if (response.ok) {
                const data = await response.json();
                this.chatHistory.push({
                    role: 'assistant',
                    content: data.answer,
                    sources: data.sources,
                    confidence: data.confidence
                });
            } else {
                this.chatHistory.push({
                    role: 'assistant',
                    content: 'Sorry, I encountered an error. Please try again.'
                });
            }
        } catch (error) {
            console.error('Chat error:', error);
            this.chatHistory.push({
                role: 'assistant',
                content: 'Sorry, I encountered an error. Please try again.'
            });
        }

        this.isLoading = false;
        this.renderChatArea();
    }

    /**
     * Render just the chat area (for updates)
     */
    renderChatArea() {
        const messagesContainer = document.getElementById('chat-messages');
        if (messagesContainer) {
            messagesContainer.innerHTML = this.renderChatMessages();
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    /**
     * Handle quick actions
     */
    async handleQuickAction(action) {
        switch (action) {
            case 'competitor-intel':
                this.showCompetitorDialog();
                break;
            case 'email-context':
                this.showEmailContextDialog();
                break;
            case 'search':
                this.showSearchDialog();
                break;
        }
    }

    /**
     * Show competitor intelligence dialog
     */
    showCompetitorDialog() {
        const competitor = prompt('Enter competitor name:');
        if (!competitor) return;

        this.chatHistory.push({
            role: 'user',
            content: `How do we compete against ${competitor}?`
        });
        this.renderChatArea();

        fetch(`${this.apiBase}/competitor-intel`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ competitor_name: competitor })
        })
        .then(r => r.json())
        .then(data => {
            let response = `**Competing against ${competitor}:**\n\n`;

            if (data.our_advantages?.length) {
                response += '**Our Advantages:**\n' + data.our_advantages.map(a => `- ${a}`).join('\n') + '\n\n';
            }
            if (data.talking_points?.length) {
                response += '**Key Talking Points:**\n' + data.talking_points.map(t => `- ${t}`).join('\n') + '\n\n';
            }
            if (data.objection_handlers?.length) {
                response += '**Handling Objections:**\n' + data.objection_handlers.map(o => `- "${o.objection}" → ${o.response}`).join('\n');
            }

            this.chatHistory.push({ role: 'assistant', content: response });
            this.renderChatArea();
        })
        .catch(e => {
            this.chatHistory.push({ role: 'assistant', content: 'Failed to get competitor intel.' });
            this.renderChatArea();
        });
    }

    /**
     * Show re-learn confirmation dialog
     */
    showRelearnDialog() {
        if (confirm('This will clear existing knowledge and re-crawl your website. Continue?')) {
            fetch(`${this.apiBase}/knowledge`, {
                method: 'DELETE',
                credentials: 'include'
            }).then(() => {
                this.status = null;
                this.chatHistory = [];
                this.render();
                this.attachEventListeners();
            });
        }
    }

    /**
     * Generate demo emails based on company knowledge
     */
    async generateDemoEmails() {
        const btn = document.getElementById('generate-demo-emails-btn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `
                <svg class="animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px;">
                    <circle cx="12" cy="12" r="10" stroke-opacity="0.25"/>
                    <path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"/>
                </svg>
                Generating...
            `;
        }

        try {
            const response = await fetch(`${this.apiBase}/generate-demo-emails`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ count: 15, clear_existing: true })
            });

            if (response.ok) {
                const data = await response.json();
                this.showToast(`Generated ${data.emails_generated} demo emails! Check your inbox.`, 'success');

                // Refresh inbox if function exists
                if (typeof window.refreshInbox === 'function') {
                    window.refreshInbox();
                }
            } else {
                const error = await response.json();
                this.showToast(error.detail || 'Failed to generate emails', 'error');
            }
        } catch (error) {
            console.error('Generate demo emails error:', error);
            this.showToast('Failed to generate demo emails', 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px;">
                        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                        <polyline points="22,6 12,13 2,6"/>
                    </svg>
                    Generate Demo Emails
                `;
            }
        }
    }

    /**
     * Format message content (basic markdown)
     */
    formatMessage(content) {
        if (!content) return '';
        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/\n/g, '<br>')
            .replace(/- (.*?)(<br>|$)/g, '<li>$1</li>');
    }

    /**
     * Show toast notification
     */
    showToast(message, type = 'info') {
        // Use existing toast system if available
        if (window.showToast) {
            window.showToast(message, type);
        } else {
            alert(message);
        }
    }

    /**
     * Show email context dialog
     */
    showEmailContextDialog() {
        const industry = prompt('Prospect industry (e.g., Healthcare, Manufacturing):');
        if (!industry) return;

        const role = prompt('Prospect role (e.g., CEO, VP Operations):');

        this.chatHistory.push({
            role: 'user',
            content: `Help me write an email to a ${role || 'decision maker'} in ${industry}`
        });
        this.renderChatArea();

        fetch(`${this.apiBase}/email-context`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                prospect_industry: industry,
                prospect_role: role || '',
                email_purpose: 'cold outreach'
            })
        })
        .then(r => r.json())
        .then(data => {
            let response = `**Email context for ${industry}${role ? ` (${role})` : ''}:**\n\n`;

            if (data.relevant_products?.length) {
                response += '**Products to highlight:**\n' + data.relevant_products.map(p => `- ${p}`).join('\n') + '\n\n';
            }
            if (data.key_benefits?.length) {
                response += '**Key benefits to emphasize:**\n' + data.key_benefits.map(b => `- ${b}`).join('\n') + '\n\n';
            }
            if (data.talking_points?.length) {
                response += '**Talking points:**\n' + data.talking_points.map(t => `- ${t}`).join('\n') + '\n\n';
            }
            if (data.case_study_mention) {
                response += `**Case study to mention:** ${data.case_study_mention}`;
            }

            this.chatHistory.push({ role: 'assistant', content: response });
            this.renderChatArea();
        })
        .catch(e => {
            this.chatHistory.push({ role: 'assistant', content: 'Failed to get email context.' });
            this.renderChatArea();
        });
    }

    /**
     * Show search dialog
     */
    showSearchDialog() {
        const query = prompt('Search your company knowledge:');
        if (!query) return;

        this.chatHistory.push({ role: 'user', content: `Search: ${query}` });
        this.renderChatArea();

        fetch(`${this.apiBase}/search?query=${encodeURIComponent(query)}&top_k=5`, {
            credentials: 'include'
        })
        .then(r => r.json())
        .then(data => {
            if (data.results?.length) {
                let response = `**Search results for "${query}":**\n\n`;
                data.results.forEach((r, i) => {
                    response += `**${i + 1}. ${r.title}** (${r.page_type})\n${r.content.substring(0, 200)}...\n\n`;
                });
                this.chatHistory.push({ role: 'assistant', content: response });
            } else {
                this.chatHistory.push({ role: 'assistant', content: 'No results found.' });
            }
            this.renderChatArea();
        })
        .catch(e => {
            this.chatHistory.push({ role: 'assistant', content: 'Search failed.' });
            this.renderChatArea();
        });
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('company-agent-content')) {
        window.companyAgent = new CompanyAgent();
        window.companyAgent.init();
    }
});

// Export for use in other modules
window.CompanyAgent = CompanyAgent;
