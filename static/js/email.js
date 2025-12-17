/**
 * SAIGBOX Email Management Module
 * Handles email loading, filtering, rendering, and actions
 */

(function(app) {
    'use strict';

    const state = app.state;

    // ===========================================
    // Email Loading
    // ===========================================

    /**
     * Load emails from the server
     */
    window.loadEmails = async function(page = null, append = false) {
        if (state.isLoading) return;

        const targetPage = page !== null ? page : state.currentPage + 1;

        // Skip if page already loaded (unless explicitly requested)
        if (page === null && state.loadedPages.has(targetPage)) {
            return;
        }

        state.isLoading = true;
        const emailList = document.getElementById('email-list');

        if (!append && emailList) {
            emailList.innerHTML = '<div class="p-4 text-center text-gray-500"><i class="fas fa-spinner fa-spin mr-2"></i>Loading emails...</div>';
        }

        try {
            const params = new URLSearchParams({
                page: targetPage,
                limit: app.config.maxEmailsPerPage
            });

            if (state.currentSearchQuery) {
                params.append('search', state.currentSearchQuery);
            }

            const response = await app.apiRequest(`/api/emails?${params}`);

            if (response.ok) {
                const data = await response.json();
                const newEmails = data.emails || [];

                // Track loaded page
                state.loadedPages.add(targetPage);
                state.currentPage = targetPage;

                // Deduplicate and add new emails
                const existingIds = new Set(state.allLoadedEmails.map(e => e.id));
                const uniqueNewEmails = newEmails.filter(e => !existingIds.has(e.id));

                if (append) {
                    state.allLoadedEmails = [...state.allLoadedEmails, ...uniqueNewEmails];
                } else {
                    state.allLoadedEmails = newEmails;
                }

                state.hasMoreEmails = data.has_more !== false && newEmails.length >= app.config.maxEmailsPerPage;
                state.totalEmailsLoaded = state.allLoadedEmails.length;
                state.consecutiveErrors = 0;

                // Apply current filter and render
                applyCurrentFilter();
            } else {
                state.consecutiveErrors++;
                if (!append && emailList) {
                    emailList.innerHTML = '<div class="p-4 text-center text-red-500">Failed to load emails</div>';
                }
            }
        } catch (error) {
            console.error('Error loading emails:', error);
            state.consecutiveErrors++;
            if (!append && emailList) {
                emailList.innerHTML = '<div class="p-4 text-center text-red-500">Error loading emails</div>';
            }
        } finally {
            state.isLoading = false;
        }
    };

    // ===========================================
    // Email Filtering
    // ===========================================

    let currentFilter = 'inbox';

    /**
     * Filter emails by type
     */
    window.filterEmails = function(filterType) {
        currentFilter = filterType;

        // Update filter button states
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.classList.remove('active', 'bg-green-100', 'text-green-700');
            btn.classList.add('bg-gray-100', 'text-gray-600');
        });

        const activeBtn = document.querySelector(`[onclick*="filterEmails('${filterType}')"]`);
        if (activeBtn) {
            activeBtn.classList.remove('bg-gray-100', 'text-gray-600');
            activeBtn.classList.add('active', 'bg-green-100', 'text-green-700');
        }

        applyCurrentFilter();
    };

    /**
     * Apply current filter to emails
     */
    window.applyCurrentFilter = function(newEmailsToAppend = null) {
        let emailsToFilter = state.allLoadedEmails;

        // Apply filter
        let filteredEmails;
        switch(currentFilter) {
            case 'unread':
                filteredEmails = emailsToFilter.filter(e => !e.is_read);
                break;
            case 'urgent':
                filteredEmails = emailsToFilter.filter(e => e.is_urgent);
                break;
            case 'starred':
                filteredEmails = emailsToFilter.filter(e => e.is_starred);
                break;
            case 'sent':
                filteredEmails = emailsToFilter.filter(e =>
                    e.labels && e.labels.includes('SENT')
                );
                break;
            default: // inbox
                filteredEmails = emailsToFilter.filter(e =>
                    !e.deleted_at && (!e.labels || !e.labels.includes('TRASH'))
                );
        }

        state.emails = filteredEmails;
        renderEmailList(filteredEmails);
        updateUrgentCount();
    };

    // ===========================================
    // Email Rendering
    // ===========================================

    /**
     * Render email list
     */
    window.renderEmailList = function(emailList) {
        const container = document.getElementById('email-list');
        if (!container) return;

        if (!emailList || emailList.length === 0) {
            container.innerHTML = `
                <div class="p-8 text-center text-gray-500">
                    <i class="fas fa-inbox text-4xl mb-4"></i>
                    <p>No emails found</p>
                </div>
            `;
            return;
        }

        container.innerHTML = emailList.map(email => {
            const isSelected = email.id === state.selectedEmailId;
            const dateStr = app.formatDate(email.received_at);

            return `
                <div class="email-item p-4 border-b hover:bg-gray-50 cursor-pointer ${isSelected ? 'bg-blue-50' : ''} ${!email.is_read ? 'font-semibold bg-white' : 'bg-gray-50'}"
                     onclick="selectEmail('${email.id}')" data-email-id="${email.id}">
                    <div class="flex items-start justify-between">
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center gap-2">
                                ${email.is_urgent ? '<span class="text-red-500"><i class="fas fa-exclamation-circle"></i></span>' : ''}
                                ${email.is_starred ? '<span class="text-yellow-500"><i class="fas fa-star"></i></span>' : ''}
                                <span class="truncate ${!email.is_read ? 'font-semibold' : ''}">${app.escapeHtml(email.sender_name || email.sender || 'Unknown')}</span>
                            </div>
                            <div class="text-sm truncate ${!email.is_read ? 'font-semibold' : 'text-gray-600'}">${app.escapeHtml(email.subject || '(No subject)')}</div>
                            <div class="text-xs text-gray-500 truncate">${app.escapeHtml(email.snippet || '')}</div>
                        </div>
                        <div class="text-xs text-gray-500 ml-2 whitespace-nowrap">${dateStr}</div>
                    </div>
                </div>
            `;
        }).join('');
    };

    /**
     * Update urgent email count badge
     */
    window.updateUrgentCount = function() {
        const urgentCount = state.allLoadedEmails.filter(e => e.is_urgent).length;
        const badge = document.getElementById('urgent-badge');
        if (badge) {
            badge.textContent = urgentCount;
            badge.style.display = urgentCount > 0 ? 'inline' : 'none';
        }
    };

    // ===========================================
    // Email Selection & Actions
    // ===========================================

    /**
     * Select an email to view
     */
    window.selectEmail = async function(emailId) {
        state.selectedEmailId = emailId;
        const email = state.allLoadedEmails.find(e => e.id === emailId);

        if (!email) return;

        // Update list selection state
        document.querySelectorAll('.email-item').forEach(item => {
            item.classList.remove('bg-blue-50');
        });
        const selectedItem = document.querySelector(`[data-email-id="${emailId}"]`);
        if (selectedItem) {
            selectedItem.classList.add('bg-blue-50');
        }

        // Show email detail
        const detailView = document.getElementById('email-detail');
        if (detailView) {
            detailView.innerHTML = `
                <div class="p-6">
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="text-xl font-semibold">${app.escapeHtml(email.subject || '(No subject)')}</h2>
                        <div class="flex gap-2">
                            <button onclick="toggleStar('${email.id}')" class="p-2 hover:bg-gray-100 rounded" title="Star">
                                <i class="fas fa-star ${email.is_starred ? 'text-yellow-500' : 'text-gray-400'}"></i>
                            </button>
                            <button onclick="deleteEmail('${email.id}')" class="p-2 hover:bg-gray-100 rounded" title="Delete">
                                <i class="fas fa-trash text-gray-400"></i>
                            </button>
                        </div>
                    </div>
                    <div class="flex items-center gap-4 text-sm text-gray-600 mb-4">
                        <span><strong>From:</strong> ${app.escapeHtml(email.sender_name || email.sender)}</span>
                        <span>${app.formatDate(email.received_at)}</span>
                        ${email.is_urgent ? '<span class="px-2 py-1 bg-red-100 text-red-700 rounded text-xs">Urgent</span>' : ''}
                    </div>

                    <!-- AI Summary Section -->
                    <div id="ai-summary-section-${email.id}" class="mb-4 border-2 border-green-400 rounded-lg overflow-hidden shadow-sm">
                        <button onclick="toggleAISummary('${email.id}')" class="w-full bg-gradient-to-r from-green-100 to-blue-100 hover:from-green-200 hover:to-blue-200 p-3 flex items-center justify-between transition-colors">
                            <div class="flex items-center">
                                <i class="fas fa-brain text-green-600 mr-2"></i>
                                <span class="font-semibold text-green-700">AI Summary</span>
                                <span class="ml-2 text-xs text-green-600 bg-green-100 px-2 py-0.5 rounded-full">Click to expand</span>
                            </div>
                            <i id="ai-summary-arrow-${email.id}" class="fas fa-chevron-down text-green-600 transition-transform"></i>
                        </button>
                        <div id="ai-summary-content-${email.id}" class="hidden bg-white p-4 max-h-96 overflow-y-auto">
                            <div class="text-center text-gray-500">
                                <span class="text-sm">Click above to generate AI summary</span>
                            </div>
                        </div>
                    </div>

                    <div class="prose max-w-none">
                        ${email.body_html || app.escapeHtml(email.body_text || '').replace(/\n/g, '<br>')}
                    </div>
                    <div class="mt-6 flex gap-2">
                        <button onclick="replyToEmail('${email.id}')" class="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600">
                            <i class="fas fa-reply mr-2"></i>Reply
                        </button>
                        <button onclick="forwardEmail('${email.id}')" class="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300">
                            <i class="fas fa-share mr-2"></i>Forward
                        </button>
                    </div>
                </div>
            `;
            detailView.classList.remove('hidden');
        }

        // Mark as read if unread
        if (!email.is_read) {
            await markAsRead(emailId);
        }
    };

    /**
     * Mark email as read
     */
    window.markAsRead = async function(emailId) {
        try {
            const response = await app.apiJson(`/api/emails/${emailId}/read`, {
                method: 'PUT'
            });

            if (response.ok) {
                const email = state.allLoadedEmails.find(e => e.id === emailId);
                if (email) {
                    email.is_read = true;
                    applyCurrentFilter();
                }
            }
        } catch (error) {
            console.error('Error marking as read:', error);
        }
    };

    /**
     * Toggle star on email
     */
    window.toggleStar = async function(emailId) {
        try {
            const email = state.allLoadedEmails.find(e => e.id === emailId);
            if (!email) return;

            const endpoint = email.is_starred ? 'unstar' : 'star';
            const response = await app.apiJson(`/api/emails/${emailId}/${endpoint}`, {
                method: 'PUT'
            });

            if (response.ok) {
                email.is_starred = !email.is_starred;
                applyCurrentFilter();
                if (state.selectedEmailId === emailId) {
                    selectEmail(emailId);
                }
            }
        } catch (error) {
            console.error('Error toggling star:', error);
        }
    };

    /**
     * Delete email (move to trash)
     */
    window.deleteEmail = async function(emailId) {
        if (!confirm('Move this email to trash?')) return;

        try {
            const response = await app.apiRequest(`/api/emails/${emailId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                state.allLoadedEmails = state.allLoadedEmails.filter(e => e.id !== emailId);
                if (state.selectedEmailId === emailId) {
                    state.selectedEmailId = null;
                    const detailView = document.getElementById('email-detail');
                    if (detailView) detailView.classList.add('hidden');
                }
                applyCurrentFilter();
                app.showNotification('Email moved to trash', 'success');
            }
        } catch (error) {
            console.error('Error deleting email:', error);
            app.showNotification('Failed to delete email', 'error');
        }
    };

    // ===========================================
    // Email Search
    // ===========================================

    /**
     * Search emails
     */
    window.searchEmails = async function() {
        const searchInput = document.getElementById('searchInput');
        const query = searchInput ? searchInput.value.trim() : '';

        state.currentSearchQuery = query;
        state.loadedPages.clear();
        state.currentPage = 0;
        state.allLoadedEmails = [];

        await loadEmails();
    };

    /**
     * Clear search
     */
    window.clearSearch = function() {
        const searchInput = document.getElementById('searchInput');
        if (searchInput) searchInput.value = '';
        state.currentSearchQuery = '';
        state.loadedPages.clear();
        state.currentPage = 0;
        state.allLoadedEmails = [];
        loadEmails();
    };

    // ===========================================
    // Email Sync
    // ===========================================

    /**
     * Sync emails from provider
     */
    window.syncEmails = async function(pageToken = null, continuous = false) {
        if (state.isSyncing) return;

        state.isSyncing = true;
        const syncBtn = document.querySelector('[onclick*="syncEmails"]');
        if (syncBtn) {
            syncBtn.disabled = true;
            syncBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Syncing...';
        }

        try {
            const response = await app.apiJson('/api/emails/sync', {
                method: 'POST',
                body: JSON.stringify({
                    page_token: pageToken,
                    max_results: 50
                })
            });

            if (response.ok) {
                const result = await response.json();
                app.showNotification(`Synced ${result.emails_synced || 0} emails`, 'success');

                // Reload emails
                state.loadedPages.clear();
                state.currentPage = 0;
                state.allLoadedEmails = [];
                await loadEmails();
            } else {
                app.showNotification('Sync failed', 'error');
            }
        } catch (error) {
            console.error('Sync error:', error);
            app.showNotification('Sync error', 'error');
        } finally {
            state.isSyncing = false;
            if (syncBtn) {
                syncBtn.disabled = false;
                syncBtn.innerHTML = '<i class="fas fa-sync-alt mr-2"></i>Sync';
            }
        }
    };

})(window.SAIGBOX);
