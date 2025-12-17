/**
 * SAIGBOX Sales Dashboard Module
 * Focused on actionable sales tools for email-based communication
 */

(function(app) {
    'use strict';

    const state = app.state;

    // ===========================================
    // Sales State
    // ===========================================

    state.opportunities = state.opportunities || [];
    state.currentOpportunityFilter = 'all';
    state.currentOpportunityEmails = [];
    state.salesPipeline = [];
    state.salesAnalytics = {};
    state.leadScores = {};
    state.objections = {};
    state.sequences = {};
    state.followupQueue = [];
    state.proposals = [];
    state.currentSalesTab = 'action-center';
    state.selectedProspectForCompose = null;

    // CTA Analysis State
    state.currentCtaStrength = null;
    state.ctaAnalysisTimer = null;
    state.subjectSuggestions = [];
    state.currentTone = 'professional';

    // ===========================================
    // Dashboard Loading
    // ===========================================

    /**
     * Load sales dashboard data
     */
    window.loadSalesDashboard = async function() {
        const container = document.getElementById('sales-dashboard-content');
        if (container) {
            container.innerHTML = '<div class="p-4 text-center"><i class="fas fa-spinner fa-spin mr-2"></i>Loading dashboard...</div>';
        }

        try {
            // Load multiple endpoints in parallel
            const [overviewRes, opportunitiesRes, recommendationsRes, proposalsRes, sequencesRes] = await Promise.all([
                app.apiRequest('/api/sales-dashboard/overview'),
                app.apiRequest('/api/sales-dashboard/opportunities'),
                app.apiRequest('/api/sales-dashboard/recommendations'),
                app.apiRequest('/api/sales-dashboard/proposals'),
                app.apiRequest('/api/sales-dashboard/followup-sequences')
            ]);

            const overview = overviewRes.ok ? await overviewRes.json() : {};
            const opportunities = opportunitiesRes.ok ? await opportunitiesRes.json() : [];
            const recommendations = recommendationsRes.ok ? await recommendationsRes.json() : {};
            const proposals = proposalsRes.ok ? await proposalsRes.json() : [];
            const sequences = sequencesRes.ok ? await sequencesRes.json() : {};

            state.opportunities = opportunities.opportunities || opportunities || [];
            state.salesAnalytics = overview;
            state.recommendations = recommendations;
            state.proposals = proposals.proposals || proposals || [];
            state.followupQueue = sequences.sequences || [];

            renderSalesDashboard(overview);

        } catch (error) {
            console.error('Error loading sales dashboard:', error);
            if (container) {
                container.innerHTML = '<div class="p-4 text-center text-red-500">Error loading dashboard</div>';
            }
        }
    };

    /**
     * Render main sales dashboard
     */
    function renderSalesDashboard(overview) {
        const container = document.getElementById('sales-dashboard-content');
        if (!container) return;

        const stats = overview.stats || {};

        container.innerHTML = `
            <!-- Quick Stats -->
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                <div class="bg-white p-4 rounded-lg shadow">
                    <div class="text-sm text-gray-500">Hot Leads</div>
                    <div class="text-2xl font-bold text-red-500">${stats.hot_leads || 0}</div>
                    <div class="text-xs text-gray-400">Needs immediate action</div>
                </div>
                <div class="bg-white p-4 rounded-lg shadow">
                    <div class="text-sm text-gray-500">Pending Follow-ups</div>
                    <div class="text-2xl font-bold text-yellow-500">${state.followupQueue.length || 0}</div>
                    <div class="text-xs text-gray-400">Due for outreach</div>
                </div>
                <div class="bg-white p-4 rounded-lg shadow">
                    <div class="text-sm text-gray-500">Active Proposals</div>
                    <div class="text-2xl font-bold text-blue-500">${state.proposals.length || 0}</div>
                    <div class="text-xs text-gray-400">Ready to send</div>
                </div>
                <div class="bg-white p-4 rounded-lg shadow">
                    <div class="text-sm text-gray-500">Response Rate</div>
                    <div class="text-2xl font-bold text-green-500">${stats.response_rate || '0%'}</div>
                    <div class="text-xs text-gray-400">This month</div>
                </div>
            </div>

            <!-- Main Tabs Navigation -->
            <div class="bg-white rounded-lg shadow mb-6">
                <div class="border-b">
                    <nav class="flex -mb-px overflow-x-auto">
                        <button onclick="switchSalesTab('action-center')" id="tab-action-center" class="sales-tab px-6 py-3 text-sm font-medium border-b-2 whitespace-nowrap ${state.currentSalesTab === 'action-center' ? 'border-green-500 text-green-600' : 'border-transparent text-gray-500 hover:text-gray-700'}">
                            <i class="fas fa-bolt mr-2"></i>Action Center
                        </button>
                        <button onclick="switchSalesTab('compose')" id="tab-compose" class="sales-tab px-6 py-3 text-sm font-medium border-b-2 whitespace-nowrap ${state.currentSalesTab === 'compose' ? 'border-green-500 text-green-600' : 'border-transparent text-gray-500 hover:text-gray-700'}">
                            <i class="fas fa-magic mr-2"></i>Smart Compose
                        </button>
                        <button onclick="switchSalesTab('followups')" id="tab-followups" class="sales-tab px-6 py-3 text-sm font-medium border-b-2 whitespace-nowrap ${state.currentSalesTab === 'followups' ? 'border-green-500 text-green-600' : 'border-transparent text-gray-500 hover:text-gray-700'}">
                            <i class="fas fa-clock mr-2"></i>Follow-up Queue
                        </button>
                        <button onclick="switchSalesTab('proposals')" id="tab-proposals" class="sales-tab px-6 py-3 text-sm font-medium border-b-2 whitespace-nowrap ${state.currentSalesTab === 'proposals' ? 'border-green-500 text-green-600' : 'border-transparent text-gray-500 hover:text-gray-700'}">
                            <i class="fas fa-file-invoice mr-2"></i>Proposals
                        </button>
                    </nav>
                </div>

                <!-- Tab Content -->
                <div id="sales-tab-content" class="p-4">
                    ${renderSalesTabContent()}
                </div>
            </div>

            <!-- Opportunities Section -->
            <div class="bg-white rounded-lg shadow">
                <div class="p-4 border-b flex justify-between items-center">
                    <h3 class="text-lg font-semibold">Opportunities</h3>
                    <div class="flex gap-2">
                        <button onclick="filterOpportunities('all')" class="px-3 py-1 rounded text-sm ${state.currentOpportunityFilter === 'all' ? 'bg-green-100 text-green-700' : 'bg-gray-100'}">All</button>
                        <button onclick="filterOpportunities('hot')" class="px-3 py-1 rounded text-sm ${state.currentOpportunityFilter === 'hot' ? 'bg-red-100 text-red-700' : 'bg-gray-100'}">Hot</button>
                        <button onclick="filterOpportunities('warm')" class="px-3 py-1 rounded text-sm ${state.currentOpportunityFilter === 'warm' ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100'}">Warm</button>
                        <button onclick="filterOpportunities('cold')" class="px-3 py-1 rounded text-sm ${state.currentOpportunityFilter === 'cold' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100'}">Cold</button>
                    </div>
                </div>
                <div id="opportunities-list" class="divide-y"></div>
            </div>
        `;

        renderOpportunities();
    }

    /**
     * Switch sales dashboard tab
     */
    window.switchSalesTab = function(tabName) {
        state.currentSalesTab = tabName;

        // Update tab styling
        document.querySelectorAll('.sales-tab').forEach(tab => {
            tab.classList.remove('border-green-500', 'text-green-600');
            tab.classList.add('border-transparent', 'text-gray-500');
        });
        const activeTab = document.getElementById(`tab-${tabName}`);
        if (activeTab) {
            activeTab.classList.remove('border-transparent', 'text-gray-500');
            activeTab.classList.add('border-green-500', 'text-green-600');
        }

        // Render tab content
        const contentDiv = document.getElementById('sales-tab-content');
        if (contentDiv) {
            contentDiv.innerHTML = renderSalesTabContent();
        }
    };

    /**
     * Render content for the current sales tab
     */
    function renderSalesTabContent() {
        switch (state.currentSalesTab) {
            case 'compose':
                return renderComposeTab();
            case 'followups':
                return renderFollowupsTab();
            case 'proposals':
                return renderProposalsTab();
            default:
                return renderActionCenterTab();
        }
    }

    // ===========================================
    // ACTION CENTER TAB
    // ===========================================

    /**
     * Render action center tab - prioritized queue of what needs attention
     */
    function renderActionCenterTab() {
        const recommendations = state.recommendations || {};
        const actions = recommendations.actions || [];
        const hotLeads = state.opportunities.filter(o => o.temperature === 'hot');

        return `
            <div class="space-y-6">
                <!-- Urgent Actions -->
                <div>
                    <h4 class="font-semibold mb-3 flex items-center">
                        <span class="w-2 h-2 bg-red-500 rounded-full mr-2 animate-pulse"></span>
                        Priority Actions
                    </h4>
                    <div class="space-y-2">
                        ${hotLeads.length === 0 && actions.length === 0 ?
                            '<div class="text-gray-500 text-center py-6">No urgent actions. Great job staying on top of things!</div>' :
                            hotLeads.slice(0, 3).map(lead => renderActionCard(lead, 'hot')).join('') +
                            actions.slice(0, 3).map(action => renderRecommendationCard(action)).join('')
                        }
                    </div>
                </div>

                <!-- Quick Reply Suggestions -->
                <div>
                    <h4 class="font-semibold mb-3">
                        <i class="fas fa-reply text-blue-500 mr-2"></i>Suggested Replies
                    </h4>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                        ${state.opportunities.slice(0, 4).map(opp => renderQuickReplyCard(opp)).join('') ||
                          '<div class="text-gray-500 col-span-2 text-center py-6">No pending replies needed</div>'}
                    </div>
                </div>

                <!-- Objection Alerts -->
                ${renderObjectionAlerts()}
            </div>
        `;
    }

    /**
     * Render an action card for hot leads
     */
    function renderActionCard(lead, priority) {
        const colors = {
            hot: 'border-red-200 bg-red-50',
            warm: 'border-yellow-200 bg-yellow-50',
            cold: 'border-blue-200 bg-blue-50'
        };

        return `
            <div class="p-4 rounded-lg border ${colors[priority] || 'border-gray-200 bg-gray-50'}">
                <div class="flex items-center justify-between">
                    <div>
                        <div class="font-medium">${app.escapeHtml(lead.sender_name || lead.sender)}</div>
                        <div class="text-sm text-gray-600">${app.escapeHtml(lead.company || lead.sender?.split('@')[1] || '')}</div>
                        <div class="text-xs text-gray-500 mt-1">${lead.email_count || 0} emails &bull; Score: ${lead.score || 0}</div>
                    </div>
                    <div class="flex gap-2">
                        <button onclick="openSmartCompose('${app.escapeHtml(lead.sender)}', '${app.escapeHtml(lead.sender_name || '')}')"
                                class="px-3 py-2 bg-green-500 text-white rounded-lg text-sm hover:bg-green-600">
                            <i class="fas fa-pen mr-1"></i>Compose
                        </button>
                        <button onclick="viewOpportunityEmails('${app.escapeHtml(lead.sender)}')"
                                class="px-3 py-2 bg-gray-100 rounded-lg text-sm hover:bg-gray-200">
                            <i class="fas fa-envelope mr-1"></i>View
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Render recommendation card
     */
    function renderRecommendationCard(action) {
        return `
            <div class="p-4 rounded-lg border border-blue-200 bg-blue-50">
                <div class="flex items-center justify-between">
                    <div>
                        <div class="font-medium">${app.escapeHtml(action.title || action.type || 'Action Required')}</div>
                        <div class="text-sm text-gray-600">${app.escapeHtml(action.description || '')}</div>
                    </div>
                    ${action.prospect ? `
                        <button onclick="openSmartCompose('${app.escapeHtml(action.prospect)}', '')"
                                class="px-3 py-2 bg-blue-500 text-white rounded-lg text-sm hover:bg-blue-600">
                            <i class="fas fa-arrow-right mr-1"></i>Act
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    }

    /**
     * Render quick reply card
     */
    function renderQuickReplyCard(opp) {
        return `
            <div class="p-3 rounded-lg border border-gray-200 hover:border-green-300 cursor-pointer transition-colors"
                 onclick="openSmartCompose('${app.escapeHtml(opp.sender)}', '${app.escapeHtml(opp.sender_name || '')}')">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center text-gray-600 font-medium">
                        ${(opp.sender_name || opp.sender || '?')[0].toUpperCase()}
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="font-medium truncate">${app.escapeHtml(opp.sender_name || opp.sender)}</div>
                        <div class="text-xs text-gray-500">Click to compose reply</div>
                    </div>
                    <i class="fas fa-chevron-right text-gray-400"></i>
                </div>
            </div>
        `;
    }

    /**
     * Render objection alerts section
     */
    function renderObjectionAlerts() {
        const objections = state.objections?.active_objections || [];
        if (objections.length === 0) return '';

        return `
            <div>
                <h4 class="font-semibold mb-3">
                    <i class="fas fa-exclamation-triangle text-orange-500 mr-2"></i>Objections Detected
                </h4>
                <div class="space-y-2">
                    ${objections.slice(0, 3).map(obj => `
                        <div class="p-3 rounded-lg border border-orange-200 bg-orange-50">
                            <div class="flex items-start justify-between">
                                <div>
                                    <span class="text-xs px-2 py-0.5 rounded bg-orange-200 capitalize">${obj.type || 'objection'}</span>
                                    <div class="mt-2 text-sm">"${app.escapeHtml(obj.quote || obj.text || '')}"</div>
                                    <div class="text-xs text-gray-500 mt-1">From: ${app.escapeHtml(obj.sender_name || obj.sender || 'Unknown')}</div>
                                </div>
                                <button onclick="handleObjection('${obj.type}', '${app.escapeHtml(obj.sender || '')}')"
                                        class="px-3 py-1 bg-orange-500 text-white rounded text-sm hover:bg-orange-600">
                                    Respond
                                </button>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    // ===========================================
    // SMART COMPOSE TAB
    // ===========================================

    /**
     * Render smart compose tab
     */
    function renderComposeTab() {
        const selectedProspect = state.selectedProspectForCompose;

        return `
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <!-- Left: Compose Area -->
                <div class="lg:col-span-2 space-y-4">
                    <!-- Recipient Selection -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">To:</label>
                        <div class="flex gap-2">
                            <input type="email" id="compose-to" placeholder="recipient@example.com"
                                   value="${selectedProspect ? app.escapeHtml(selectedProspect) : ''}"
                                   class="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500">
                            <button onclick="selectFromOpportunities()" class="px-3 py-2 bg-gray-100 rounded-lg hover:bg-gray-200 text-sm">
                                <i class="fas fa-address-book mr-1"></i>Contacts
                            </button>
                        </div>
                    </div>

                    <!-- Subject with AI -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Subject:</label>
                        <div class="relative">
                            <input type="text" id="compose-subject" placeholder="Email subject"
                                   class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500 pr-24"
                                   oninput="analyzeCtaStrength()">
                            <button onclick="generateSubjectLines()"
                                    class="absolute right-2 top-1/2 -translate-y-1/2 px-2 py-1 text-xs bg-purple-100 text-purple-700 rounded hover:bg-purple-200"
                                    title="Get AI subject line suggestions">
                                <i class="fas fa-magic mr-1"></i>Suggest
                            </button>
                        </div>
                        <div id="subject-suggestions" class="hidden mt-2 border rounded-lg bg-white shadow-lg max-h-48 overflow-y-auto"></div>
                    </div>

                    <!-- Email Body with CTA Strength -->
                    <div>
                        <div class="flex items-center justify-between mb-1">
                            <label class="block text-sm font-medium text-gray-700">Message:</label>
                            <div id="cta-strength-indicator" class="hidden flex items-center gap-2 text-xs">
                                <span class="text-gray-500">CTA Strength:</span>
                                <span id="cta-strength-badge" class="px-2 py-0.5 rounded font-medium"></span>
                            </div>
                        </div>
                        <textarea id="compose-body" rows="10" placeholder="Write your email here..."
                                  class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500 resize-none"
                                  oninput="analyzeCtaStrength()"></textarea>

                        <!-- CTA Suggestions Panel -->
                        <div id="cta-suggestions" class="hidden mt-2 p-3 bg-blue-50 rounded-lg border border-blue-200">
                            <div class="flex items-center justify-between mb-2">
                                <span class="text-sm font-medium text-blue-700"><i class="fas fa-bullhorn mr-1"></i>CTA Suggestions</span>
                                <button onclick="hideCTASuggestions()" class="text-blue-500 hover:text-blue-700"><i class="fas fa-times"></i></button>
                            </div>
                            <div id="cta-suggestions-list" class="space-y-1"></div>
                        </div>
                    </div>

                    <!-- Action Buttons -->
                    <div class="flex items-center justify-between">
                        <div class="flex gap-2">
                            <button onclick="askSaigToHelp()" class="px-4 py-2 text-green-600 hover:bg-green-50 rounded-lg" title="Get AI help">
                                <i class="fas fa-robot mr-2"></i>AI Help
                            </button>
                            <button onclick="showCTASuggestions()" class="px-4 py-2 text-blue-600 hover:bg-blue-50 rounded-lg" title="Get CTA suggestions">
                                <i class="fas fa-bullhorn mr-2"></i>CTA Tips
                            </button>
                        </div>
                        <div class="flex gap-2">
                            <button onclick="clearCompose()" class="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg">
                                <i class="fas fa-eraser mr-1"></i>Clear
                            </button>
                            <button onclick="sendComposedEmail()" class="px-6 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600">
                                <i class="fas fa-paper-plane mr-2"></i>Send
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Right: Templates & Tools -->
                <div class="space-y-4">
                    <!-- Smart Response Suggestions -->
                    <div class="bg-gray-50 rounded-lg p-4">
                        <div class="flex items-center justify-between mb-3">
                            <h5 class="font-medium">
                                <i class="fas fa-lightbulb text-yellow-500 mr-2"></i>Smart Responses
                            </h5>
                            <button onclick="generateContextTemplates()" class="text-xs text-blue-600 hover:text-blue-700">
                                <i class="fas fa-sync-alt mr-1"></i>Refresh
                            </button>
                        </div>
                        <div id="smart-templates-container" class="space-y-2">
                            <p class="text-xs text-gray-500 text-center py-2">
                                Enter a recipient to get AI-powered response suggestions based on your conversation history
                            </p>
                        </div>
                    </div>

                    <!-- Tone Selector -->
                    <div class="bg-gray-50 rounded-lg p-4">
                        <h5 class="font-medium mb-3">
                            <i class="fas fa-sliders-h text-gray-500 mr-2"></i>Email Tone
                        </h5>
                        <div class="flex flex-wrap gap-2">
                            <button onclick="setTone('professional')" class="tone-btn px-3 py-1 rounded ${state.currentTone === 'professional' ? 'bg-green-100 text-green-700' : 'bg-gray-100'} text-sm">Professional</button>
                            <button onclick="setTone('friendly')" class="tone-btn px-3 py-1 rounded ${state.currentTone === 'friendly' ? 'bg-green-100 text-green-700' : 'bg-gray-100'} text-sm">Friendly</button>
                            <button onclick="setTone('urgent')" class="tone-btn px-3 py-1 rounded ${state.currentTone === 'urgent' ? 'bg-green-100 text-green-700' : 'bg-gray-100'} text-sm">Urgent</button>
                            <button onclick="setTone('casual')" class="tone-btn px-3 py-1 rounded ${state.currentTone === 'casual' ? 'bg-green-100 text-green-700' : 'bg-gray-100'} text-sm">Casual</button>
                        </div>
                    </div>

                    <!-- AI Writing Assistant -->
                    <div class="bg-purple-50 rounded-lg p-4">
                        <h5 class="font-medium mb-3 text-purple-800">
                            <i class="fas fa-robot mr-2"></i>AI Assistant
                        </h5>
                        <div class="space-y-2">
                            <button onclick="improveEmail()" class="w-full px-3 py-2 bg-white border rounded-lg text-sm hover:bg-gray-50 text-left">
                                <i class="fas fa-wand-magic-sparkles text-purple-500 mr-2"></i>Improve Writing
                            </button>
                            <button onclick="shortenEmail()" class="w-full px-3 py-2 bg-white border rounded-lg text-sm hover:bg-gray-50 text-left">
                                <i class="fas fa-compress text-purple-500 mr-2"></i>Make Concise
                            </button>
                            <button onclick="expandEmail()" class="w-full px-3 py-2 bg-white border rounded-lg text-sm hover:bg-gray-50 text-left">
                                <i class="fas fa-expand text-purple-500 mr-2"></i>Expand Details
                            </button>
                        </div>
                    </div>

                    <!-- CTA Strength Legend -->
                    <div class="bg-gray-50 rounded-lg p-4">
                        <h5 class="font-medium mb-3">
                            <i class="fas fa-chart-bar text-gray-500 mr-2"></i>CTA Strength Guide
                        </h5>
                        <div class="space-y-2 text-xs">
                            <div class="flex items-center gap-2">
                                <span class="px-2 py-0.5 rounded bg-green-100 text-green-700 font-medium">Strong</span>
                                <span class="text-gray-600">"Schedule a call", "Book now"</span>
                            </div>
                            <div class="flex items-center gap-2">
                                <span class="px-2 py-0.5 rounded bg-yellow-100 text-yellow-700 font-medium">Medium</span>
                                <span class="text-gray-600">"Let me know", "Learn more"</span>
                            </div>
                            <div class="flex items-center gap-2">
                                <span class="px-2 py-0.5 rounded bg-blue-100 text-blue-700 font-medium">Soft</span>
                                <span class="text-gray-600">"Feel free to", "Thoughts?"</span>
                            </div>
                            <div class="flex items-center gap-2">
                                <span class="px-2 py-0.5 rounded bg-red-100 text-red-700 font-medium">Missing</span>
                                <span class="text-gray-600">No clear call-to-action</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Generate context-aware templates based on conversation history
     */
    window.generateContextTemplates = async function() {
        const recipient = document.getElementById('compose-to')?.value;
        const container = document.getElementById('smart-templates-container');

        if (!container) return;

        if (!recipient || !recipient.includes('@')) {
            container.innerHTML = `
                <p class="text-xs text-gray-500 text-center py-2">
                    Enter a recipient email to get AI-powered response suggestions
                </p>
            `;
            return;
        }

        container.innerHTML = `
            <div class="text-center py-3">
                <i class="fas fa-spinner fa-spin text-blue-500 mr-2"></i>
                <span class="text-sm text-gray-500">Analyzing conversation history...</span>
            </div>
        `;

        try {
            const response = await app.apiJson('/api/sales-dashboard/smart-templates', {
                method: 'POST',
                body: JSON.stringify({
                    recipient_email: recipient,
                    tone: state.currentTone
                })
            });

            if (response.ok) {
                const data = await response.json();
                renderSmartTemplates(data.templates || [], data.context || {});
            } else {
                // Fallback to generic templates
                renderFallbackTemplates();
            }
        } catch (error) {
            console.error('Error generating templates:', error);
            renderFallbackTemplates();
        }
    };

    /**
     * Render AI-generated smart templates
     */
    function renderSmartTemplates(templates, context) {
        const container = document.getElementById('smart-templates-container');
        if (!container) return;

        if (templates.length === 0) {
            renderFallbackTemplates();
            return;
        }

        // Store templates in state for use
        state.smartTemplates = templates;

        const contextHtml = context.last_topic ? `
            <div class="mb-3 p-2 bg-blue-50 rounded text-xs">
                <div class="font-medium text-blue-700 mb-1">
                    <i class="fas fa-history mr-1"></i>Last discussed:
                </div>
                <div class="text-blue-600">${app.escapeHtml(context.last_topic)}</div>
                ${context.days_since_contact ? `<div class="text-blue-500 mt-1">${context.days_since_contact} days since last contact</div>` : ''}
            </div>
        ` : '';

        const templatesHtml = templates.map((t, i) => `
            <button onclick="useSmartTemplate(${i})"
                    class="w-full px-3 py-2 bg-white border rounded-lg text-sm hover:bg-gray-50 text-left group">
                <div class="flex items-start gap-2">
                    <i class="fas ${t.icon || 'fa-envelope'} text-green-500 mt-0.5"></i>
                    <div class="flex-1 min-w-0">
                        <div class="font-medium text-gray-700">${app.escapeHtml(t.name)}</div>
                        <div class="text-xs text-gray-500 truncate">${app.escapeHtml(t.preview || '')}</div>
                    </div>
                </div>
            </button>
        `).join('');

        container.innerHTML = contextHtml + templatesHtml;
    }

    /**
     * Render fallback generic templates
     */
    function renderFallbackTemplates() {
        const container = document.getElementById('smart-templates-container');
        if (!container) return;

        const templates = [
            { id: 'follow_up', name: 'Follow-up', icon: 'fa-redo', preview: 'Check in on previous discussion' },
            { id: 'intro', name: 'Introduction', icon: 'fa-handshake', preview: 'Introduce yourself and company' },
            { id: 'proposal', name: 'Send Proposal', icon: 'fa-file-invoice', preview: 'Offer a solution' },
            { id: 'meeting', name: 'Schedule Meeting', icon: 'fa-calendar', preview: 'Request a call or meeting' }
        ];

        container.innerHTML = templates.map(t => `
            <button onclick="useTemplate('${t.id}')"
                    class="w-full px-3 py-2 bg-white border rounded-lg text-sm hover:bg-gray-50 text-left">
                <div class="flex items-start gap-2">
                    <i class="fas ${t.icon} text-gray-400 mt-0.5"></i>
                    <div class="flex-1 min-w-0">
                        <div class="font-medium text-gray-700">${t.name}</div>
                        <div class="text-xs text-gray-500">${t.preview}</div>
                    </div>
                </div>
            </button>
        `).join('');
    }

    /**
     * Use an AI-generated smart template
     */
    window.useSmartTemplate = function(index) {
        const template = state.smartTemplates?.[index];
        if (!template) return;

        const bodyField = document.getElementById('compose-body');
        const subjectField = document.getElementById('compose-subject');

        if (bodyField && template.body) {
            bodyField.value = template.body;
        }
        if (subjectField && template.subject && !subjectField.value) {
            subjectField.value = template.subject;
        }

        analyzeCtaStrength();
        app.showNotification(`Applied "${template.name}" template`, 'success');
    };

    /**
     * Open smart compose with a specific recipient
     */
    window.openSmartCompose = function(email, name) {
        state.selectedProspectForCompose = email;
        switchSalesTab('compose');

        setTimeout(() => {
            const toField = document.getElementById('compose-to');
            if (toField) toField.value = email;
        }, 50);
    };

    /**
     * Generate AI subject lines with categories and open rate estimates
     */
    window.generateSubjectLines = async function() {
        const recipient = document.getElementById('compose-to')?.value;
        const subject = document.getElementById('compose-subject')?.value;
        const body = document.getElementById('compose-body')?.value;
        const container = document.getElementById('subject-suggestions');

        if (!container) return;

        container.classList.remove('hidden');
        container.innerHTML = '<div class="p-3 text-sm text-gray-500"><i class="fas fa-spinner fa-spin mr-2"></i>Generating suggestions...</div>';

        try {
            const response = await app.apiJson('/api/sales-dashboard/generate-subject-lines', {
                method: 'POST',
                body: JSON.stringify({
                    recipient_email: recipient,
                    recipient_name: recipient ? recipient.split('@')[0] : '',
                    purpose: subject || 'professional email',
                    previous_context: body,
                    categories: ['curiosity', 'value', 'personalized', 'urgency']
                })
            });

            if (response.ok) {
                const data = await response.json();
                renderSubjectSuggestions(data.suggestions || data.subject_lines || []);
            } else {
                container.innerHTML = '<div class="p-3 text-sm text-red-500">Failed to get suggestions</div>';
            }
        } catch (error) {
            console.error('Error generating subject lines:', error);
            container.innerHTML = '<div class="p-3 text-sm text-red-500">Error generating suggestions</div>';
        }
    };

    /**
     * Render subject line suggestions with categories
     */
    function renderSubjectSuggestions(suggestions) {
        const container = document.getElementById('subject-suggestions');
        if (!container) return;

        // Handle both array of strings and array of objects
        const formattedSuggestions = suggestions.map((s, i) => {
            if (typeof s === 'string') {
                const categories = ['curiosity', 'value', 'personalized', 'urgency'];
                return {
                    text: s,
                    category: categories[i % categories.length],
                    estimated_open_rate: 0.25 + (Math.random() * 0.15)
                };
            }
            return s;
        });

        if (formattedSuggestions.length === 0) {
            container.innerHTML = '<div class="p-3 text-sm text-gray-500">No suggestions available</div>';
            return;
        }

        const categoryColors = {
            curiosity: 'bg-purple-100 text-purple-700',
            value: 'bg-green-100 text-green-700',
            social_proof: 'bg-blue-100 text-blue-700',
            personalized: 'bg-yellow-100 text-yellow-700',
            urgency: 'bg-red-100 text-red-700'
        };

        container.innerHTML = formattedSuggestions.map(s => `
            <div class="p-3 hover:bg-gray-50 cursor-pointer border-b last:border-b-0 flex items-center justify-between"
                 onclick="useSubjectLine('${app.escapeHtml((s.text || s).replace(/'/g, "\\'"))}')">
                <div class="flex-1">
                    <div class="font-medium text-sm">${app.escapeHtml(s.text || s)}</div>
                    <div class="flex items-center gap-2 mt-1">
                        <span class="px-2 py-0.5 rounded text-xs ${categoryColors[s.category] || 'bg-gray-100'}">${s.category || 'general'}</span>
                        ${s.estimated_open_rate ? `<span class="text-xs text-gray-500">${Math.round(s.estimated_open_rate * 100)}% est. open rate</span>` : ''}
                    </div>
                </div>
                <i class="fas fa-check text-green-500 opacity-0 hover:opacity-100 ml-2"></i>
            </div>
        `).join('');
    }

    /**
     * Use a suggested subject line
     */
    window.useSubjectLine = function(subject) {
        const field = document.getElementById('compose-subject');
        if (field) {
            field.value = subject;
            document.getElementById('subject-suggestions')?.classList.add('hidden');
        }
        analyzeCtaStrength();
    };

    // ===========================================
    // CTA ANALYSIS & SUGGESTIONS
    // ===========================================

    /**
     * Analyze CTA strength in the email body (debounced)
     */
    window.analyzeCtaStrength = function() {
        if (state.ctaAnalysisTimer) {
            clearTimeout(state.ctaAnalysisTimer);
        }
        state.ctaAnalysisTimer = setTimeout(() => {
            performCtaAnalysis();
        }, 500);
    };

    /**
     * Perform actual CTA analysis
     */
    function performCtaAnalysis() {
        const body = document.getElementById('compose-body')?.value || '';
        const indicator = document.getElementById('cta-strength-indicator');
        const badge = document.getElementById('cta-strength-badge');

        if (!body.trim() || body.length < 50) {
            if (indicator) indicator.classList.add('hidden');
            return;
        }

        // CTA detection patterns
        const ctaPatterns = {
            strong: [
                /book a (call|demo|meeting)/i,
                /schedule a/i,
                /sign up/i,
                /get started/i,
                /buy now/i,
                /order today/i,
                /claim your/i,
                /start your (trial|free)/i,
                /let's set up/i,
                /when (can|are) you available/i
            ],
            medium: [
                /let me know/i,
                /reply to this/i,
                /click here/i,
                /learn more/i,
                /check out/i,
                /visit our/i,
                /see how/i,
                /find out/i,
                /send over/i,
                /interested in/i
            ],
            soft: [
                /let's (connect|chat|talk)/i,
                /would love to/i,
                /happy to discuss/i,
                /feel free to/i,
                /reach out/i,
                /questions\?/i,
                /thoughts\?/i,
                /any questions/i
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
     * Show CTA suggestions panel with AI-generated suggestions
     */
    window.showCTASuggestions = async function() {
        const suggestionsDiv = document.getElementById('cta-suggestions');
        const listDiv = document.getElementById('cta-suggestions-list');

        if (!suggestionsDiv || !listDiv) return;

        suggestionsDiv.classList.remove('hidden');
        listDiv.innerHTML = '<div class="text-sm text-gray-500"><i class="fas fa-spinner fa-spin mr-2"></i>Loading suggestions...</div>';

        try {
            const body = document.getElementById('compose-body')?.value || '';
            const to = document.getElementById('compose-to')?.value || '';

            const response = await app.apiJson('/api/sales-dashboard/suggest-cta', {
                method: 'POST',
                body: JSON.stringify({
                    email_content: body,
                    recipient_email: to,
                    stage: 'engaged',
                    tone: state.currentTone
                })
            });

            if (response.ok) {
                const data = await response.json();
                renderCtaSuggestions(data.suggestions || data.cta_suggestions || []);
            } else {
                listDiv.innerHTML = '<div class="text-sm text-red-500">Failed to load suggestions</div>';
            }
        } catch (error) {
            console.error('Error fetching CTA suggestions:', error);
            // Provide fallback suggestions
            renderCtaSuggestions([
                { text: "Would you be available for a quick 15-minute call this week?", strength: "strong", context: "Meeting request" },
                { text: "Let me know if you'd like me to send over more details.", strength: "medium", context: "Follow-up" },
                { text: "I'd be happy to answer any questions you might have.", strength: "soft", context: "Open-ended" }
            ]);
        }
    };

    /**
     * Render CTA suggestions
     */
    function renderCtaSuggestions(suggestions) {
        const listDiv = document.getElementById('cta-suggestions-list');
        if (!listDiv) return;

        // Handle string or object format
        const formattedSuggestions = suggestions.map((s, i) => {
            if (typeof s === 'string') {
                const strengths = ['strong', 'medium', 'soft'];
                return { text: s, strength: strengths[i % 3], context: '' };
            }
            return s;
        });

        if (formattedSuggestions.length === 0) {
            listDiv.innerHTML = '<div class="text-sm text-gray-500">No suggestions available</div>';
            return;
        }

        const strengthColors = {
            strong: 'border-green-300 bg-green-50',
            medium: 'border-yellow-300 bg-yellow-50',
            soft: 'border-blue-300 bg-blue-50'
        };

        listDiv.innerHTML = formattedSuggestions.map(s => `
            <div class="p-2 border rounded cursor-pointer hover:bg-white ${strengthColors[s.strength] || 'border-gray-200'}"
                 onclick="insertCta('${app.escapeHtml((s.text || s).replace(/'/g, "\\'"))}')">
                <div class="text-sm font-medium">"${app.escapeHtml(s.text || s)}"</div>
                <div class="text-xs text-gray-600 mt-1">${s.strength || ''} CTA ${s.context ? '- ' + s.context : ''}</div>
            </div>
        `).join('');
    }

    /**
     * Insert CTA into email body
     */
    window.insertCta = function(cta) {
        const bodyField = document.getElementById('compose-body');
        if (bodyField) {
            const currentValue = bodyField.value.trim();
            bodyField.value = currentValue + (currentValue ? '\n\n' : '') + cta;
            bodyField.focus();
            analyzeCtaStrength();
        }
        hideCTASuggestions();
    };

    /**
     * Hide CTA suggestions panel
     */
    window.hideCTASuggestions = function() {
        const suggestionsDiv = document.getElementById('cta-suggestions');
        if (suggestionsDiv) {
            suggestionsDiv.classList.add('hidden');
        }
    };

    /**
     * Ask SAIG AI for help with the email
     */
    window.askSaigToHelp = async function() {
        const to = document.getElementById('compose-to')?.value || '';
        const subject = document.getElementById('compose-subject')?.value || '';
        const body = document.getElementById('compose-body')?.value || '';

        if (!to) {
            app.showNotification('Please enter a recipient first', 'warning');
            return;
        }

        app.showNotification('Generating AI-powered email...', 'info');

        try {
            const response = await app.apiJson('/api/sales-dashboard/compose-sequence-email', {
                method: 'POST',
                body: JSON.stringify({
                    prospect_email: to,
                    stage: 1,
                    context: body || subject || 'initial outreach',
                    tone: state.currentTone
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.email_content || data.body) {
                    const bodyField = document.getElementById('compose-body');
                    if (bodyField) {
                        bodyField.value = data.email_content || data.body;
                    }
                    if (data.subject_line && !subject) {
                        const subjectField = document.getElementById('compose-subject');
                        if (subjectField) subjectField.value = data.subject_line;
                    }
                    analyzeCtaStrength();
                    app.showNotification('Email generated!', 'success');
                }
            } else {
                app.showNotification('Failed to generate email', 'error');
            }
        } catch (error) {
            console.error('Error with AI help:', error);
            app.showNotification('Error generating email', 'error');
        }
    };

    /**
     * Improve email writing with AI
     */
    window.improveEmail = async function() {
        const body = document.getElementById('compose-body')?.value;
        if (!body || body.length < 20) {
            app.showNotification('Write some content first', 'warning');
            return;
        }
        app.showNotification('Improving email...', 'info');
        // TODO: Call AI endpoint to improve writing
        app.showNotification('AI improvement feature coming soon', 'info');
    };

    /**
     * Make email more concise
     */
    window.shortenEmail = async function() {
        const body = document.getElementById('compose-body')?.value;
        if (!body || body.length < 50) {
            app.showNotification('Write more content first', 'warning');
            return;
        }
        app.showNotification('Shortening feature coming soon', 'info');
    };

    /**
     * Expand email with more details
     */
    window.expandEmail = async function() {
        const body = document.getElementById('compose-body')?.value;
        if (!body) {
            app.showNotification('Write some content first', 'warning');
            return;
        }
        app.showNotification('Expand feature coming soon', 'info');
    };

    /**
     * Use a template
     */
    window.useTemplate = async function(templateId) {
        const templates = {
            follow_up: `Hi [Name],

I wanted to follow up on our recent conversation about [topic].

Do you have any updates or questions I can help with?

Looking forward to hearing from you.

Best regards`,
            intro: `Hi [Name],

I'm reaching out because I noticed [observation about their company/role].

At Major Manufacturers, we help companies like yours [key value proposition].

Would you be open to a brief conversation to explore if we might be a good fit?

Best regards`,
            proposal: `Hi [Name],

Thank you for taking the time to discuss your needs. Based on our conversation, I've put together a proposal that addresses:

- [Key need 1]
- [Key need 2]
- [Key need 3]

I'd love to walk you through the details at your convenience.

Best regards`,
            meeting: `Hi [Name],

I'd like to schedule a brief call to discuss how we can help with [topic].

Would any of these times work for you?
- [Option 1]
- [Option 2]
- [Option 3]

Looking forward to connecting.

Best regards`,
            thank_you: `Hi [Name],

Thank you for taking the time to speak with me today. I really appreciated learning more about [topic discussed].

As discussed, I'll [next steps].

Please don't hesitate to reach out if you have any questions.

Best regards`,
            check_in: `Hi [Name],

I hope this message finds you well. I wanted to check in and see how things are progressing with [project/topic].

Is there anything I can help with?

Best regards`
        };

        const template = templates[templateId] || '';
        const bodyField = document.getElementById('compose-body');
        if (bodyField) {
            bodyField.value = template;
        }
    };

    /**
     * Set email tone
     */
    window.setTone = function(tone) {
        state.currentTone = tone;

        // Update all tone buttons
        document.querySelectorAll('.tone-btn').forEach(btn => {
            btn.classList.remove('bg-green-100', 'text-green-700');
            btn.classList.add('bg-gray-100');
        });

        // Find and highlight the active button
        if (event && event.target) {
            event.target.classList.remove('bg-gray-100');
            event.target.classList.add('bg-green-100', 'text-green-700');
        }

        app.showNotification(`Tone set to ${tone}`, 'success');
    };

    /**
     * Clear compose form
     */
    window.clearCompose = function() {
        const toField = document.getElementById('compose-to');
        const subjectField = document.getElementById('compose-subject');
        const bodyField = document.getElementById('compose-body');

        if (toField) toField.value = '';
        if (subjectField) subjectField.value = '';
        if (bodyField) bodyField.value = '';

        document.getElementById('subject-suggestions')?.classList.add('hidden');
        document.getElementById('cta-suggestions')?.classList.add('hidden');
        document.getElementById('cta-strength-indicator')?.classList.add('hidden');

        state.selectedProspectForCompose = null;
        state.currentCtaStrength = null;

        app.showNotification('Form cleared', 'success');
    };

    /**
     * Send composed email
     */
    window.sendComposedEmail = async function() {
        const to = document.getElementById('compose-to')?.value;
        const subject = document.getElementById('compose-subject')?.value;
        const body = document.getElementById('compose-body')?.value;

        if (!to || !subject || !body) {
            app.showNotification('Please fill in all fields', 'warning');
            return;
        }

        // Use the existing compose modal send functionality
        if (typeof window.showComposeModal === 'function') {
            showComposeModal();
            setTimeout(() => {
                const toField = document.getElementById('composeTo');
                const subjectField = document.getElementById('composeSubject');
                const bodyField = document.getElementById('composeBody');
                if (toField) toField.value = to;
                if (subjectField) subjectField.value = subject;
                if (bodyField) bodyField.value = body;
            }, 100);
        } else {
            app.showNotification('Compose modal not available', 'error');
        }
    };

    // ===========================================
    // FOLLOW-UP QUEUE TAB
    // ===========================================

    /**
     * Render follow-ups tab
     */
    function renderFollowupsTab() {
        const queue = state.followupQueue || [];
        const opportunities = state.opportunities || [];

        // Create a prioritized queue from opportunities
        const prioritizedQueue = opportunities
            .filter(o => o.temperature === 'hot' || o.temperature === 'warm')
            .sort((a, b) => {
                // Hot first, then by score
                if (a.temperature === 'hot' && b.temperature !== 'hot') return -1;
                if (a.temperature !== 'hot' && b.temperature === 'hot') return 1;
                return (b.score || 0) - (a.score || 0);
            });

        return `
            <div class="space-y-4">
                <!-- Priority Legend -->
                <div class="flex items-center gap-4 text-sm">
                    <span><span class="inline-block w-3 h-3 rounded-full bg-red-500 mr-1"></span>Hot - Contact Today</span>
                    <span><span class="inline-block w-3 h-3 rounded-full bg-yellow-500 mr-1"></span>Warm - Contact This Week</span>
                    <span><span class="inline-block w-3 h-3 rounded-full bg-blue-500 mr-1"></span>Cold - Nurture</span>
                </div>

                <!-- Queue List -->
                <div class="space-y-3">
                    ${prioritizedQueue.length === 0 ?
                        '<div class="text-center py-8 text-gray-500">No follow-ups needed right now</div>' :
                        prioritizedQueue.map((item, index) => renderFollowupCard(item, index + 1)).join('')
                    }
                </div>

                <!-- Sequence Suggestions -->
                ${queue.length > 0 ? `
                    <div class="mt-6 pt-6 border-t">
                        <h5 class="font-medium mb-3">Active Email Sequences</h5>
                        <div class="space-y-2">
                            ${queue.map(seq => renderSequenceProgress(seq)).join('')}
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }

    /**
     * Render a follow-up card
     */
    function renderFollowupCard(item, priority) {
        const colors = {
            hot: 'border-l-red-500',
            warm: 'border-l-yellow-500',
            cold: 'border-l-blue-500'
        };

        return `
            <div class="bg-white border rounded-lg p-4 border-l-4 ${colors[item.temperature] || 'border-l-gray-300'}">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-4">
                        <span class="text-2xl font-bold text-gray-300">#${priority}</span>
                        <div>
                            <div class="font-medium">${app.escapeHtml(item.sender_name || item.sender)}</div>
                            <div class="text-sm text-gray-500">${app.escapeHtml(item.company || '')} &bull; ${item.email_count || 0} emails</div>
                        </div>
                    </div>
                    <div class="flex items-center gap-3">
                        <div class="text-right">
                            <div class="text-sm font-medium">Score: ${item.score || 0}</div>
                            <div class="text-xs text-gray-500 capitalize">${item.temperature || 'unknown'} lead</div>
                        </div>
                        <button onclick="openSmartCompose('${app.escapeHtml(item.sender)}', '${app.escapeHtml(item.sender_name || '')}')"
                                class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600">
                            <i class="fas fa-reply mr-1"></i>Follow Up
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Render sequence progress
     */
    function renderSequenceProgress(seq) {
        const stages = 6;
        const currentStage = seq.current_stage || 1;

        return `
            <div class="bg-gray-50 rounded-lg p-3">
                <div class="flex items-center justify-between mb-2">
                    <span class="font-medium text-sm">${app.escapeHtml(seq.prospect || seq.prospect_email || 'Unknown')}</span>
                    <span class="text-xs text-gray-500">Stage ${currentStage}/${stages}</span>
                </div>
                <div class="flex gap-1">
                    ${Array.from({length: stages}, (_, i) => `
                        <div class="flex-1 h-2 rounded ${i < currentStage ? 'bg-green-500' : 'bg-gray-200'}"></div>
                    `).join('')}
                </div>
                ${seq.next_action ? `
                    <div class="mt-2 text-xs text-gray-600">
                        <i class="fas fa-lightbulb text-yellow-500 mr-1"></i>Next: ${app.escapeHtml(seq.next_action)}
                    </div>
                ` : ''}
            </div>
        `;
    }

    // ===========================================
    // PROPOSALS TAB
    // ===========================================

    /**
     * Render proposals tab
     */
    function renderProposalsTab() {
        const proposals = state.proposals || [];

        return `
            <div class="space-y-4">
                <!-- Generate New Proposal -->
                <div class="bg-gradient-to-r from-green-50 to-blue-50 rounded-lg p-6 border border-green-200">
                    <h5 class="font-semibold mb-2">
                        <i class="fas fa-file-invoice text-green-600 mr-2"></i>Generate New Proposal
                    </h5>
                    <p class="text-sm text-gray-600 mb-4">Create a customized proposal based on your conversation history with a prospect.</p>

                    <div class="flex gap-3">
                        <select id="proposal-prospect" class="flex-1 px-3 py-2 border rounded-lg">
                            <option value="">Select a prospect...</option>
                            ${state.opportunities.map(opp => `
                                <option value="${app.escapeHtml(opp.sender)}">${app.escapeHtml(opp.sender_name || opp.sender)}</option>
                            `).join('')}
                        </select>
                        <button onclick="generateProposal()" class="px-6 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600">
                            <i class="fas fa-magic mr-2"></i>Generate
                        </button>
                    </div>
                </div>

                <!-- Existing Proposals -->
                <div>
                    <h5 class="font-semibold mb-3">Your Proposals</h5>
                    ${proposals.length === 0 ?
                        '<div class="text-center py-8 text-gray-500 bg-gray-50 rounded-lg">No proposals yet. Generate one above!</div>' :
                        `<div class="space-y-3">${proposals.map(p => renderProposalCard(p)).join('')}</div>`
                    }
                </div>
            </div>
        `;
    }

    /**
     * Render a proposal card with comprehensive BANT and pricing display
     */
    function renderProposalCard(proposal) {
        // Get BANT score color
        const bantScore = proposal.bant_score || 0;
        const bantBg = bantScore >= 70 ? 'bg-green-100 text-green-700' : bantScore >= 40 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700';

        // Get conversation stage badge
        const stage = proposal.conversation_stage || 'discovery';
        const stageBadges = {
            'cold_outreach': 'bg-gray-100 text-gray-700',
            'engaged': 'bg-blue-100 text-blue-700',
            'discovery': 'bg-purple-100 text-purple-700',
            'evaluation': 'bg-indigo-100 text-indigo-700',
            'proposal': 'bg-orange-100 text-orange-700',
            'negotiation': 'bg-yellow-100 text-yellow-700',
            'closing': 'bg-green-100 text-green-700'
        };
        const stageBadge = stageBadges[stage] || 'bg-gray-100 text-gray-700';

        // Format objections
        const objections = proposal.objections_detected || [];
        const objectionCount = objections.length;

        // Get client name and email
        const clientName = proposal.client || proposal.prospect_name || proposal.prospect || 'Unknown';
        const clientEmail = proposal.client_email || proposal.prospect || '';

        return `
            <div class="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 bg-white">
                <div class="flex justify-between items-start mb-3">
                    <div>
                        <h5 class="font-semibold">${app.escapeHtml(clientName)}</h5>
                        <p class="text-sm text-gray-600">${app.escapeHtml(clientEmail)}</p>
                    </div>
                    <div class="flex flex-col items-end gap-1">
                        <span class="px-2 py-1 text-xs rounded-full bg-green-100 text-green-700">
                            Score: ${((proposal.opportunity_score || 0) * 100).toFixed(0)}%
                        </span>
                        <span class="px-2 py-1 text-xs rounded-full ${bantBg}">
                            BANT: ${bantScore}%
                        </span>
                    </div>
                </div>

                <!-- Conversation Stage & Objections -->
                <div class="flex flex-wrap gap-2 mb-3">
                    <span class="px-2 py-1 text-xs rounded-full ${stageBadge}">
                        <i class="fas fa-comments mr-1"></i> ${stage.replace('_', ' ')}
                    </span>
                    ${objectionCount > 0 ? `
                        <span class="px-2 py-1 text-xs rounded-full bg-red-100 text-red-700">
                            <i class="fas fa-exclamation-triangle mr-1"></i> ${objectionCount} objection${objectionCount > 1 ? 's' : ''}
                        </span>
                    ` : ''}
                </div>

                <!-- BANT Details -->
                ${proposal.bant_details ? `
                <div class="bg-gray-50 rounded p-2 mb-3">
                    <h6 class="text-xs font-semibold text-gray-600 mb-1">Lead Qualification</h6>
                    <div class="grid grid-cols-4 gap-1 text-xs">
                        <div class="text-center">
                            <span class="${proposal.bant_details.budget ? 'text-green-600' : 'text-gray-400'}">
                                <i class="fas fa-dollar-sign"></i> Budget
                            </span>
                        </div>
                        <div class="text-center">
                            <span class="${proposal.bant_details.authority ? 'text-green-600' : 'text-gray-400'}">
                                <i class="fas fa-user-tie"></i> Authority
                            </span>
                        </div>
                        <div class="text-center">
                            <span class="${proposal.bant_details.need ? 'text-green-600' : 'text-gray-400'}">
                                <i class="fas fa-check-circle"></i> Need
                            </span>
                        </div>
                        <div class="text-center">
                            <span class="${proposal.bant_details.timeline ? 'text-green-600' : 'text-gray-400'}">
                                <i class="fas fa-calendar"></i> Timeline
                            </span>
                        </div>
                    </div>
                </div>
                ` : ''}

                <div class="mb-3">
                    <p class="text-sm text-gray-700">
                        <strong>Industry:</strong> ${proposal.client_info?.industry || 'Unknown'}<br>
                        <strong>Budget:</strong> ${proposal.client_info?.budget_range || 'TBD'}<br>
                        <strong>Requirements:</strong> ${proposal.requirements?.length || 0} identified
                    </p>
                </div>

                <!-- Pricing Options -->
                ${(proposal.pricing?.options || []).length > 0 ? `
                <div class="bg-gray-50 rounded p-3 mb-3">
                    <h6 class="text-xs font-semibold text-gray-600 mb-1">Pricing Options</h6>
                    ${(proposal.pricing?.options || []).map(opt => `
                        <div class="flex justify-between text-xs ${opt.recommended ? 'font-semibold text-blue-600' : 'text-gray-600'}">
                            <span>${opt.name}${opt.recommended ? ' ★' : ''}</span>
                            <span>$${opt.price?.toLocaleString() || '0'}</span>
                        </div>
                    `).join('')}
                </div>
                ` : ''}

                <div class="flex space-x-2">
                    <button onclick="viewProposal('${proposal.id}')"
                            class="flex-1 text-xs bg-gray-600 text-white px-3 py-1 rounded hover:bg-gray-700">
                        <i class="fas fa-eye mr-1"></i> Preview
                    </button>
                    <button onclick="exportProposal('${proposal.id}', 'pdf')"
                            class="flex-1 text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700">
                        <i class="fas fa-download mr-1"></i> Export PDF
                    </button>
                    <button onclick="sendProposal('${proposal.id}', '${app.escapeHtml(clientEmail)}')"
                            class="flex-1 text-xs bg-green-600 text-white px-3 py-1 rounded hover:bg-green-700">
                        <i class="fas fa-paper-plane mr-1"></i> Send
                    </button>
                </div>
            </div>
        `;
    }

    /**
     * Generate a proposal for selected prospect
     */
    window.generateProposal = async function() {
        const select = document.getElementById('proposal-prospect');
        const prospect = select?.value;

        if (!prospect) {
            app.showNotification('Please select a prospect', 'warning');
            return;
        }

        app.showNotification('Generating proposal...', 'info');

        try {
            const response = await app.apiRequest('/api/sales-dashboard/proposals');
            if (response.ok) {
                const data = await response.json();
                state.proposals = data.proposals || [];
                switchSalesTab('proposals');
                app.showNotification('Proposals loaded', 'success');
            }
        } catch (error) {
            console.error('Error generating proposal:', error);
            app.showNotification('Error generating proposal', 'error');
        }
    };

    /**
     * View a proposal with full modal preview
     */
    window.viewProposal = async function(proposalId) {
        // Find the proposal in state
        const proposal = state.proposals.find(p => p.id === proposalId);
        if (!proposal) {
            app.showNotification('Proposal not found', 'error');
            return;
        }

        // Get client info
        const clientName = proposal.client || proposal.prospect_name || proposal.prospect || 'Unknown';
        const clientEmail = proposal.client_email || proposal.prospect || '';

        // Create modal
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4';
        modal.id = 'proposal-preview-modal';
        modal.onclick = (e) => { if (e.target === modal) closeProposalModal(); };

        // Check if we have full HTML proposal
        if (proposal.proposal_html || proposal.html_preview) {
            modal.innerHTML = `
                <div class="bg-white rounded-xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col">
                    <!-- Modal Header -->
                    <div class="flex justify-between items-center p-4 border-b">
                        <div>
                            <h3 class="text-xl font-bold text-gray-800">Proposal Preview</h3>
                            <p class="text-sm text-gray-500">${app.escapeHtml(clientName)} - ${app.escapeHtml(clientEmail)}</p>
                        </div>
                        <div class="flex items-center gap-2">
                            <button onclick="printProposal()" class="px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 text-sm">
                                <i class="fas fa-print mr-1"></i> Print
                            </button>
                            <button onclick="exportProposal('${proposalId}', 'pdf')" class="px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm">
                                <i class="fas fa-download mr-1"></i> Export PDF
                            </button>
                            <button onclick="closeProposalModal()" class="text-gray-400 hover:text-gray-600 p-2">
                                <i class="fas fa-times text-xl"></i>
                            </button>
                        </div>
                    </div>

                    <!-- Modal Body - Scrollable iframe for HTML proposal -->
                    <div class="flex-1 overflow-hidden p-4">
                        <iframe id="proposal-iframe" class="w-full h-full border rounded-lg" style="min-height: 600px;"></iframe>
                    </div>

                    <!-- Modal Footer -->
                    <div class="flex justify-between items-center p-4 border-t bg-gray-50">
                        <div class="text-sm text-gray-600">
                            <span class="mr-4"><i class="fas fa-chart-line mr-1"></i> BANT Score: ${proposal.bant_score || 0}%</span>
                            <span><i class="fas fa-comments mr-1"></i> Stage: ${(proposal.conversation_stage || 'discovery').replace('_', ' ')}</span>
                        </div>
                        <div class="flex gap-2">
                            <button onclick="closeProposalModal()" class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-100">
                                Close
                            </button>
                            <button onclick="sendProposal('${proposalId}', '${app.escapeHtml(clientEmail)}'); closeProposalModal();"
                                    class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700">
                                <i class="fas fa-paper-plane mr-1"></i> Send to Client
                            </button>
                        </div>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);

            // Write HTML to iframe
            const iframe = document.getElementById('proposal-iframe');
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            iframeDoc.open();
            iframeDoc.write(proposal.proposal_html || proposal.html_preview);
            iframeDoc.close();

        } else {
            // Fallback to structured view if no HTML
            modal.innerHTML = `
                <div class="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto">
                    <!-- Modal Header -->
                    <div class="sticky top-0 bg-white flex justify-between items-center p-4 border-b z-10">
                        <div>
                            <h3 class="text-xl font-bold text-gray-800">Proposal: ${app.escapeHtml(clientName)}</h3>
                            <p class="text-sm text-gray-500">${app.escapeHtml(clientEmail)}</p>
                        </div>
                        <button onclick="closeProposalModal()" class="text-gray-400 hover:text-gray-600 p-2">
                            <i class="fas fa-times text-xl"></i>
                        </button>
                    </div>

                    <!-- Modal Body -->
                    <div class="p-6 space-y-6">
                        <!-- Score Cards -->
                        <div class="grid grid-cols-3 gap-4">
                            <div class="bg-green-50 rounded-lg p-4 text-center">
                                <div class="text-2xl font-bold text-green-600">${((proposal.opportunity_score || 0) * 100).toFixed(0)}%</div>
                                <div class="text-sm text-green-700">Opportunity Score</div>
                            </div>
                            <div class="bg-blue-50 rounded-lg p-4 text-center">
                                <div class="text-2xl font-bold text-blue-600">${proposal.bant_score || 0}%</div>
                                <div class="text-sm text-blue-700">BANT Score</div>
                            </div>
                            <div class="bg-purple-50 rounded-lg p-4 text-center">
                                <div class="text-2xl font-bold text-purple-600">${(proposal.conversation_stage || 'discovery').replace('_', ' ')}</div>
                                <div class="text-sm text-purple-700">Sales Stage</div>
                            </div>
                        </div>

                        <!-- Client Info -->
                        <div class="bg-gray-50 rounded-lg p-4">
                            <h4 class="font-semibold text-gray-800 mb-3"><i class="fas fa-building mr-2"></i>Client Information</h4>
                            <div class="grid grid-cols-2 gap-4 text-sm">
                                <div><strong>Company:</strong> ${proposal.client_info?.company || clientName}</div>
                                <div><strong>Industry:</strong> ${proposal.client_info?.industry || 'Unknown'}</div>
                                <div><strong>Budget Range:</strong> ${proposal.client_info?.budget_range || 'TBD'}</div>
                                <div><strong>Requirements:</strong> ${proposal.requirements?.length || 0} identified</div>
                            </div>
                        </div>

                        <!-- Pricing -->
                        ${(proposal.pricing?.options || []).length > 0 ? `
                        <div class="bg-gray-50 rounded-lg p-4">
                            <h4 class="font-semibold text-gray-800 mb-3"><i class="fas fa-tags mr-2"></i>Pricing Options</h4>
                            <div class="space-y-2">
                                ${(proposal.pricing?.options || []).map(opt => `
                                    <div class="flex justify-between items-center p-2 ${opt.recommended ? 'bg-blue-50 border border-blue-200 rounded' : ''}">
                                        <span class="${opt.recommended ? 'font-semibold text-blue-700' : 'text-gray-700'}">${opt.name}${opt.recommended ? ' (Recommended)' : ''}</span>
                                        <span class="font-semibold">$${opt.price?.toLocaleString() || '0'}</span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                        ` : ''}

                        <!-- Requirements -->
                        ${(proposal.requirements || []).length > 0 ? `
                        <div class="bg-gray-50 rounded-lg p-4">
                            <h4 class="font-semibold text-gray-800 mb-3"><i class="fas fa-list-check mr-2"></i>Identified Requirements</h4>
                            <ul class="list-disc list-inside text-sm text-gray-700 space-y-1">
                                ${(proposal.requirements || []).map(req => `<li>${app.escapeHtml(req)}</li>`).join('')}
                            </ul>
                        </div>
                        ` : ''}
                    </div>

                    <!-- Modal Footer -->
                    <div class="sticky bottom-0 bg-gray-50 flex justify-between items-center p-4 border-t">
                        <button onclick="closeProposalModal()" class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-100">
                            Close
                        </button>
                        <div class="flex gap-2">
                            <button onclick="exportProposal('${proposalId}', 'pdf')" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                                <i class="fas fa-download mr-1"></i> Export PDF
                            </button>
                            <button onclick="sendProposal('${proposalId}', '${app.escapeHtml(clientEmail)}'); closeProposalModal();"
                                    class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700">
                                <i class="fas fa-paper-plane mr-1"></i> Send to Client
                            </button>
                        </div>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);
        }
    };

    /**
     * Close proposal preview modal
     */
    window.closeProposalModal = function() {
        const modal = document.getElementById('proposal-preview-modal');
        if (modal) modal.remove();
    };

    /**
     * Print proposal from iframe
     */
    window.printProposal = function() {
        const iframe = document.getElementById('proposal-iframe');
        if (iframe) {
            iframe.contentWindow.print();
        }
    };

    /**
     * Export proposal to PDF
     */
    window.exportProposal = async function(proposalId, format) {
        try {
            app.showNotification('Exporting proposal...', 'info');
            const response = await app.apiJson(`/api/sales-dashboard/proposals/${proposalId}/export`, {
                method: 'POST',
                body: JSON.stringify({ format: format })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.download_url) {
                    app.showNotification('Proposal exported! Download starting...', 'success');
                    window.open(data.download_url, '_blank');
                } else {
                    app.showNotification('Proposal exported successfully', 'success');
                }
            } else {
                const error = await response.json();
                app.showNotification(error.detail || 'Failed to export proposal', 'error');
            }
        } catch (error) {
            console.error('Error exporting proposal:', error);
            app.showNotification('Error exporting proposal', 'error');
        }
    };

    /**
     * Send a proposal
     */
    window.sendProposal = async function(proposalId, prospect) {
        try {
            const response = await app.apiJson(`/api/sales-dashboard/proposals/${proposalId}/send`, {
                method: 'POST',
                body: JSON.stringify({ recipient: prospect })
            });

            if (response.ok) {
                app.showNotification('Proposal sent!', 'success');
                loadSalesDashboard();
            } else {
                const error = await response.json();
                app.showNotification(error.detail || 'Failed to send proposal', 'error');
            }
        } catch (error) {
            console.error('Error sending proposal:', error);
            app.showNotification('Error sending proposal', 'error');
        }
    };

    // ===========================================
    // HELPER FUNCTIONS
    // ===========================================

    /**
     * Handle objection with suggested response
     */
    window.handleObjection = function(type, sender) {
        openSmartCompose(sender, '');

        // Pre-fill with objection handling template
        setTimeout(() => {
            const templates = {
                price: `I understand budget is a key consideration. Let me share how our solution provides value that typically exceeds the investment...`,
                timing: `I appreciate you sharing your timeline concerns. Let me show you how we can work with your schedule...`,
                authority: `I'd be happy to provide materials you can share with your team. Would it help if I prepared a summary for the decision makers?`,
                need: `I hear you. Let me better understand your current situation to see if we're truly a fit...`,
                competition: `That's a fair point. Let me highlight what makes our approach unique...`
            };

            const bodyField = document.getElementById('compose-body');
            if (bodyField) {
                bodyField.value = templates[type] || 'Thank you for your feedback. Let me address your concerns...';
            }
        }, 100);
    };

    /**
     * Select from opportunities for compose
     */
    window.selectFromOpportunities = function() {
        const opportunities = state.opportunities || [];
        if (opportunities.length === 0) {
            app.showNotification('No contacts available', 'info');
            return;
        }

        // Create a simple selection modal
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
        modal.innerHTML = `
            <div class="bg-white rounded-lg shadow-xl max-w-md w-full m-4 max-h-96 overflow-hidden">
                <div class="p-4 border-b flex items-center justify-between">
                    <h3 class="font-semibold">Select Contact</h3>
                    <button onclick="this.closest('.fixed').remove()" class="text-gray-400 hover:text-gray-600">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="overflow-y-auto max-h-72">
                    ${opportunities.map(opp => `
                        <div onclick="selectContact('${app.escapeHtml(opp.sender)}'); this.closest('.fixed').remove();"
                             class="p-3 hover:bg-gray-50 cursor-pointer border-b">
                            <div class="font-medium">${app.escapeHtml(opp.sender_name || opp.sender)}</div>
                            <div class="text-sm text-gray-500">${app.escapeHtml(opp.sender)}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    };

    /**
     * Select a contact for compose
     */
    window.selectContact = function(email) {
        const field = document.getElementById('compose-to');
        if (field) field.value = email;
    };

    /**
     * Copy text to clipboard
     */
    window.copyToClipboard = function(text) {
        navigator.clipboard.writeText(text).then(() => {
            app.showNotification('Copied to clipboard', 'success');
        }).catch(err => {
            console.error('Failed to copy:', err);
        });
    };

    // ===========================================
    // Opportunities Section (kept from original)
    // ===========================================

    window.filterOpportunities = function(filter) {
        state.currentOpportunityFilter = filter;

        document.querySelectorAll('[onclick^="filterOpportunities"]').forEach(btn => {
            btn.className = 'px-3 py-1 rounded text-sm bg-gray-100';
        });
        const activeBtn = document.querySelector(`[onclick="filterOpportunities('${filter}')"]`);
        if (activeBtn) {
            const colorMap = { all: 'green', hot: 'red', warm: 'yellow', cold: 'blue' };
            activeBtn.className = `px-3 py-1 rounded text-sm bg-${colorMap[filter]}-100 text-${colorMap[filter]}-700`;
        }

        renderOpportunities();
    };

    window.renderOpportunities = function() {
        const container = document.getElementById('opportunities-list');
        if (!container) return;

        let filtered = state.opportunities;
        if (state.currentOpportunityFilter !== 'all') {
            filtered = filtered.filter(o => o.temperature === state.currentOpportunityFilter);
        }

        if (filtered.length === 0) {
            container.innerHTML = '<div class="p-8 text-center text-gray-500">No opportunities found</div>';
            return;
        }

        container.innerHTML = filtered.map(opp => {
            const tempColors = {
                hot: 'bg-red-100 text-red-700',
                warm: 'bg-yellow-100 text-yellow-700',
                cold: 'bg-blue-100 text-blue-700'
            };

            return `
                <div class="p-4 hover:bg-gray-50">
                    <div class="flex items-center justify-between">
                        <div class="flex-1">
                            <div class="flex items-center gap-2">
                                <span class="font-medium">${app.escapeHtml(opp.sender_name || opp.sender)}</span>
                                <span class="px-2 py-0.5 rounded text-xs ${tempColors[opp.temperature] || 'bg-gray-100'}">${opp.temperature || 'unknown'}</span>
                            </div>
                            <div class="text-sm text-gray-600">${app.escapeHtml(opp.company || '')}</div>
                            <div class="text-sm text-gray-500">${opp.email_count || 0} emails | Score: ${opp.score || 0}</div>
                        </div>
                        <div class="flex gap-2">
                            <button onclick="viewOpportunityEmails('${app.escapeHtml(opp.sender)}')" class="px-3 py-1 bg-gray-100 rounded text-sm hover:bg-gray-200">
                                <i class="fas fa-envelope mr-1"></i>View
                            </button>
                            <button onclick="openSmartCompose('${app.escapeHtml(opp.sender)}', '${app.escapeHtml(opp.sender_name || '')}')" class="px-3 py-1 bg-green-500 text-white rounded text-sm hover:bg-green-600">
                                <i class="fas fa-reply mr-1"></i>Reply
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    };

    window.viewOpportunityEmails = async function(sender) {
        try {
            const response = await app.apiRequest(`/api/emails?sender=${encodeURIComponent(sender)}`);

            if (response.ok) {
                const data = await response.json();
                state.currentOpportunityEmails = data.emails || [];
                showOpportunityEmailModal(sender);
            }
        } catch (error) {
            console.error('Error loading opportunity emails:', error);
            app.showNotification('Error loading emails', 'error');
        }
    };

    function showOpportunityEmailModal(sender) {
        const modal = document.getElementById('opportunity-email-modal');
        if (!modal) return;

        const title = document.getElementById('opp-email-modal-title');
        const subtitle = document.getElementById('opp-email-modal-subtitle');
        const container = document.getElementById('opp-email-list-container');

        if (title) title.textContent = `Emails from ${sender}`;
        if (subtitle) subtitle.textContent = `${state.currentOpportunityEmails.length} emails`;

        if (container) {
            renderOpportunityEmailList();
        }

        modal.classList.remove('hidden');
    }

    window.renderOpportunityEmailList = function() {
        const container = document.getElementById('opp-email-list-container');
        if (!container) return;

        if (state.currentOpportunityEmails.length === 0) {
            container.innerHTML = '<div class="p-6 text-center text-gray-500">No emails found</div>';
            return;
        }

        const sortedEmails = [...state.currentOpportunityEmails].sort((a, b) =>
            new Date(b.received_at) - new Date(a.received_at)
        );

        container.innerHTML = sortedEmails.map((email, index) => {
            const dateStr = app.formatDate(email.received_at);
            const body = formatEmailBody(email);

            return `
                <div class="p-5 ${index > 0 ? 'border-t-2 border-gray-200' : ''}">
                    <div class="flex items-start justify-between mb-3">
                        <div>
                            <h4 class="font-bold text-lg text-gray-900">${app.escapeHtml(email.subject || '(No subject)')}</h4>
                            <p class="text-sm text-gray-600"><strong>${app.escapeHtml(email.sender_name || email.sender)}</strong> &bull; ${dateStr}</p>
                        </div>
                        ${email.is_urgent ? '<span class="px-2 py-1 bg-red-100 text-red-700 rounded text-xs"><i class="fas fa-exclamation-circle mr-1"></i>Urgent</span>' : ''}
                    </div>
                    <div class="text-gray-800 leading-relaxed">
                        ${body}
                    </div>
                </div>
            `;
        }).join('');
    };

    function formatEmailBody(email) {
        if (email.body_text && email.body_text.trim()) {
            return app.escapeHtml(email.body_text).replace(/\n/g, '<br>');
        }
        if (email.body_html && email.body_html.trim()) {
            let sanitized = email.body_html
                .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
                .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
                .replace(/<link[^>]*>/gi, '')
                .replace(/style\s*=\s*["'][^"']*font[^"']*["']/gi, '')
                .replace(/@import[^;]+;/gi, '');
            return `<div class="email-body-content" style="font-family: inherit !important;">${sanitized}</div>`;
        }
        return '<span class="text-gray-400 italic">No content</span>';
    }

    window.closeOpportunityEmailModal = function() {
        const modal = document.getElementById('opportunity-email-modal');
        if (modal) modal.classList.add('hidden');
    };

    // ===========================================
    // Business Profile (kept from original)
    // ===========================================

    window.checkBusinessProfile = async function() {
        try {
            const response = await app.apiRequest('/api/sales-dashboard/business-profile');
            if (response.ok) {
                const data = await response.json();
                return data.profile && data.profile.company_name;
            }
        } catch (error) {
            console.error('Error checking business profile:', error);
        }
        return false;
    };

    window.showBusinessProfileModal = async function() {
        const modal = document.getElementById('business-profile-modal');
        if (!modal) return;

        try {
            const response = await app.apiRequest('/api/sales-dashboard/business-profile');
            if (response.ok) {
                const data = await response.json();
                if (data.profile) {
                    populateBusinessProfileForm(data.profile);
                }
            }
        } catch (error) {
            console.error('Error loading business profile:', error);
        }

        modal.classList.remove('hidden');
    };

    function populateBusinessProfileForm(profile) {
        const fields = ['company_name', 'company_website', 'industry', 'company_size',
                       'value_proposition', 'elevator_pitch', 'target_market'];

        fields.forEach(field => {
            const input = document.getElementById(`bp-${field.replace(/_/g, '-')}`);
            if (input && profile[field]) {
                input.value = profile[field];
            }
        });
    }

    window.saveBusinessProfile = async function(event) {
        if (event) event.preventDefault();

        const formData = {
            company_name: document.getElementById('bp-company-name')?.value,
            company_website: document.getElementById('bp-company-website')?.value,
            industry: document.getElementById('bp-industry')?.value,
            company_size: document.getElementById('bp-company-size')?.value,
            value_proposition: document.getElementById('bp-value-proposition')?.value,
            elevator_pitch: document.getElementById('bp-elevator-pitch')?.value,
            target_market: document.getElementById('bp-target-market')?.value
        };

        try {
            const response = await app.apiJson('/api/sales-dashboard/business-profile', {
                method: 'POST',
                body: JSON.stringify(formData)
            });

            if (response.ok) {
                app.showNotification('Business profile saved', 'success');
                closeBusinessProfileModal();
            } else {
                app.showNotification('Failed to save profile', 'error');
            }
        } catch (error) {
            console.error('Error saving business profile:', error);
            app.showNotification('Error saving profile', 'error');
        }
    };

    window.closeBusinessProfileModal = function() {
        const modal = document.getElementById('business-profile-modal');
        if (modal) modal.classList.add('hidden');
    };

})(window.SAIGBOX);
