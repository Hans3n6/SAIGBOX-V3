/**
 * SAIGBOX Action Items Module
 * Handles action item management and tracking
 */

(function(app) {
    'use strict';

    const state = app.state;

    // ===========================================
    // Action Items State
    // ===========================================

    state.actionItems = state.actionItems || [];

    // ===========================================
    // Action Items Loading
    // ===========================================

    /**
     * Load action items from server
     */
    window.loadActionItems = async function() {
        const container = document.getElementById('action-list');
        if (container) {
            container.innerHTML = '<div class="p-4 text-center"><i class="fas fa-spinner fa-spin mr-2"></i>Loading action items...</div>';
        }

        try {
            const response = await app.apiRequest('/api/actions');

            if (response.ok) {
                state.actionItems = await response.json();
                renderActionItems();
            } else {
                if (container) {
                    container.innerHTML = '<div class="p-4 text-center text-red-500">Failed to load action items</div>';
                }
            }
        } catch (error) {
            console.error('Error loading action items:', error);
            if (container) {
                container.innerHTML = '<div class="p-4 text-center text-red-500">Error loading action items</div>';
            }
        }
    };

    // ===========================================
    // Action Items Rendering
    // ===========================================

    /**
     * Group action items by source email
     */
    function groupByEmail(items) {
        const groups = {};
        const noEmail = [];

        items.forEach(item => {
            if (item.email_id && item.email_subject) {
                if (!groups[item.email_id]) {
                    groups[item.email_id] = {
                        email_id: item.email_id,
                        email_subject: item.email_subject,
                        email_sender: item.email_sender,
                        items: []
                    };
                }
                groups[item.email_id].items.push(item);
            } else {
                noEmail.push(item);
            }
        });

        return { groups: Object.values(groups), noEmail };
    }

    /**
     * Render email group header
     */
    function renderEmailGroupHeader(group, isCollapsed = false) {
        const itemCount = group.items.length;
        const pendingCount = group.items.filter(i => i.status === 'pending').length;

        return `
            <div class="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg mb-3 overflow-hidden border border-blue-100">
                <div class="p-3 cursor-pointer" onclick="toggleEmailGroup('${group.email_id}')">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center flex-1 min-w-0">
                            <i id="email-group-chevron-${group.email_id}" class="fas ${isCollapsed ? 'fa-chevron-right' : 'fa-chevron-down'} text-blue-400 mr-3 transition-transform text-sm"></i>
                            <div class="flex-1 min-w-0">
                                <div class="font-medium text-gray-800 truncate">${app.escapeHtml(group.email_subject || 'No Subject')}</div>
                                <div class="text-xs text-gray-500 flex items-center gap-2 mt-0.5">
                                    <span><i class="fas fa-user mr-1"></i>${app.escapeHtml(group.email_sender || 'Unknown')}</span>
                                    <span class="text-blue-600"><i class="fas fa-tasks mr-1"></i>${itemCount} task${itemCount !== 1 ? 's' : ''}</span>
                                    ${pendingCount > 0 ? `<span class="text-yellow-600"><i class="fas fa-clock mr-1"></i>${pendingCount} pending</span>` : ''}
                                </div>
                            </div>
                        </div>
                        <button onclick="event.stopPropagation(); openEmailFromAction('${group.email_id}')"
                                class="text-blue-500 hover:text-blue-600 px-2 py-1 text-sm"
                                title="View email">
                            <i class="fas fa-envelope"></i>
                        </button>
                    </div>
                </div>
                <div id="email-group-items-${group.email_id}" class="${isCollapsed ? 'hidden' : ''} border-t border-blue-100 bg-white">
                    ${group.items.map(item => renderActionItem(item, true)).join('')}
                </div>
            </div>
        `;
    }

    /**
     * Toggle email group collapse
     */
    window.toggleEmailGroup = function(emailId) {
        const items = document.getElementById(`email-group-items-${emailId}`);
        const chevron = document.getElementById(`email-group-chevron-${emailId}`);
        if (items && chevron) {
            items.classList.toggle('hidden');
            chevron.classList.toggle('fa-chevron-down');
            chevron.classList.toggle('fa-chevron-right');
        }
    };

    /**
     * Render action items list
     * @param {Array} items - Optional. If provided, uses these items; otherwise uses state.actionItems
     */
    window.renderActionItems = function(items) {
        const container = document.getElementById('action-list');
        if (!container) return;

        // Use passed items or fall back to state
        const actionItems = items || state.actionItems || [];

        // Also update state if items were passed
        if (items && Array.isArray(items)) {
            state.actionItems = items;
        }

        if (!actionItems || actionItems.length === 0) {
            container.innerHTML = `
                <div class="p-8 text-center text-gray-500">
                    <i class="fas fa-check-circle text-4xl mb-4"></i>
                    <p>No action items</p>
                    <p class="text-sm">Action items will appear here when extracted from emails</p>
                </div>
            `;
            return;
        }

        // Separate pending and completed
        const pending = actionItems.filter(a => a.status === 'pending' || a.status === 'overdue');
        const completed = actionItems.filter(a => a.status === 'completed');

        // Group pending items by email
        const pendingGrouped = groupByEmail(pending);
        const completedGrouped = groupByEmail(completed);

        container.innerHTML = `
            <!-- Pending Section -->
            <div class="mb-6">
                <h3 class="text-lg font-semibold mb-3 flex items-center">
                    <i class="fas fa-clock text-yellow-500 mr-2"></i>
                    Pending (${pending.length})
                </h3>
                <div class="space-y-2">
                    ${pending.length === 0 ? '<div class="text-gray-500 text-sm pl-2">No pending items</div>' : ''}
                    ${pendingGrouped.groups.map(group => renderEmailGroupHeader(group)).join('')}
                    ${pendingGrouped.noEmail.length > 0 ? `
                        <div class="mt-4">
                            <div class="text-xs text-gray-400 uppercase tracking-wide mb-2 pl-1">Manual Tasks</div>
                            ${pendingGrouped.noEmail.map(item => renderActionItem(item)).join('')}
                        </div>
                    ` : ''}
                </div>
            </div>

            <!-- Completed Section -->
            <div>
                <h3 class="text-lg font-semibold mb-3 flex items-center">
                    <i class="fas fa-check-circle text-green-500 mr-2"></i>
                    Completed (${completed.length})
                </h3>
                <div class="space-y-2">
                    ${completed.length === 0 ? '<div class="text-gray-500 text-sm pl-2">No completed items</div>' : ''}
                    ${completedGrouped.groups.map(group => renderEmailGroupHeader(group, true)).join('')}
                    ${completedGrouped.noEmail.length > 0 ? `
                        <div class="mt-4">
                            <div class="text-xs text-gray-400 uppercase tracking-wide mb-2 pl-1">Manual Tasks</div>
                            ${completedGrouped.noEmail.map(item => renderActionItem(item)).join('')}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    };

    /**
     * Toggle action item expansion
     */
    window.toggleActionExpand = function(actionId) {
        const details = document.getElementById(`action-details-${actionId}`);
        const chevron = document.getElementById(`action-chevron-${actionId}`);
        if (details && chevron) {
            details.classList.toggle('hidden');
            chevron.classList.toggle('fa-chevron-down');
            chevron.classList.toggle('fa-chevron-up');
        }
    };

    /**
     * Format due date with relative timing and urgency colors
     */
    function formatDueDate(dueDateStr, isCompleted) {
        if (!dueDateStr) return null;

        const dueDate = new Date(dueDateStr);
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);
        const dueDateOnly = new Date(dueDate.getFullYear(), dueDate.getMonth(), dueDate.getDate());

        const diffDays = Math.ceil((dueDateOnly - today) / (1000 * 60 * 60 * 24));

        let label, colorClass;

        if (isCompleted) {
            label = dueDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            colorClass = 'text-gray-500 bg-gray-100';
        } else if (diffDays < 0) {
            label = `${Math.abs(diffDays)}d overdue`;
            colorClass = 'text-red-700 bg-red-100';
        } else if (diffDays === 0) {
            label = 'Due today';
            colorClass = 'text-orange-700 bg-orange-100';
        } else if (diffDays === 1) {
            label = 'Due tomorrow';
            colorClass = 'text-yellow-700 bg-yellow-100';
        } else if (diffDays <= 7) {
            label = `${diffDays}d left`;
            colorClass = 'text-blue-700 bg-blue-100';
        } else {
            label = dueDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            colorClass = 'text-gray-600 bg-gray-100';
        }

        return { label, colorClass };
    }

    /**
     * Render single action item (expandable)
     * @param {Object} item - The action item to render
     * @param {boolean} inGroup - Whether this item is rendered inside an email group
     */
    function renderActionItem(item, inGroup = false) {
        const priorityColors = {
            high: 'text-red-600 bg-red-50',
            medium: 'text-yellow-600 bg-yellow-50',
            low: 'text-green-600 bg-green-50'
        };

        const getPriorityLabel = (priority) => {
            const p = String(priority).toLowerCase();
            if (p === 'high' || priority === 1) return 'High';
            if (p === 'medium' || priority === 2) return 'Medium';
            if (p === 'low' || priority === 3) return 'Low';
            return 'Medium';
        };

        const isCompleted = item.status === 'completed';
        const dueDateInfo = formatDueDate(item.due_date, isCompleted);

        // Different styling for items inside groups vs standalone
        const containerClass = inGroup
            ? 'border-b border-gray-100 last:border-b-0 hover:bg-gray-50'
            : 'bg-white rounded-lg shadow-sm hover:shadow-md mb-3';

        return `
            <div class="${containerClass} transition-all duration-200 overflow-hidden">
                <!-- Collapsed Header - Always Visible -->
                <div class="p-3 cursor-pointer select-none" onclick="toggleActionExpand('${item.id}')">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center flex-1 min-w-0">
                            <i id="action-chevron-${item.id}" class="fas fa-chevron-down text-gray-400 mr-2 transition-transform text-xs"></i>
                            <span class="${isCompleted ? 'line-through text-gray-400' : 'text-gray-800'} truncate text-sm">
                                ${app.escapeHtml(item.title)}
                            </span>
                        </div>
                        <div class="flex items-center space-x-1 ml-3 flex-shrink-0">
                            ${dueDateInfo ? `
                                <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${dueDateInfo.colorClass}">
                                    <i class="fas fa-calendar-alt mr-1 text-[10px]"></i>${dueDateInfo.label}
                                </span>
                            ` : ''}
                            <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs ${priorityColors[item.priority] || priorityColors.medium}">
                                ${getPriorityLabel(item.priority)}
                            </span>
                            ${!isCompleted ? `
                                <button onclick="event.stopPropagation(); toggleActionComplete('${item.id}')"
                                        class="text-green-500 hover:text-green-600 p-1"
                                        title="Mark as complete">
                                    <i class="fas fa-check text-xs"></i>
                                </button>
                            ` : `
                                <span class="text-green-500 p-1" title="Completed">
                                    <i class="fas fa-check-circle text-xs"></i>
                                </span>
                            `}
                            <button onclick="event.stopPropagation(); deleteActionItem('${item.id}')"
                                    class="text-red-400 hover:text-red-500 p-1"
                                    title="Delete action">
                                <i class="fas fa-trash text-xs"></i>
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Expanded Details - Hidden by Default -->
                <div id="action-details-${item.id}" class="hidden border-t border-gray-100 bg-gray-50 px-3 py-2">
                    ${item.description ? `
                        <div class="mb-2">
                            <div class="text-xs font-medium text-gray-500 mb-1">Description</div>
                            <p class="text-sm text-gray-700">${app.escapeHtml(item.description)}</p>
                        </div>
                    ` : ''}
                    ${item.source_quote ? `
                        <div class="mb-2">
                            <div class="text-xs font-medium text-gray-500 mb-1">From email</div>
                            <p class="text-xs text-gray-600 italic bg-white p-2 rounded border-l-2 border-blue-300">"${app.escapeHtml(item.source_quote)}"</p>
                        </div>
                    ` : ''}

                    <div class="flex flex-wrap items-center gap-3 text-xs text-gray-500">
                        ${item.auto_created ? `
                            <span class="flex items-center text-blue-600">
                                <i class="fas fa-robot mr-1"></i>
                                AI-extracted
                            </span>
                        ` : ''}
                        ${!inGroup && item.email_id ? `
                            <button onclick="event.stopPropagation(); openEmailFromAction('${item.email_id}')"
                                    class="flex items-center text-blue-500 hover:text-blue-600">
                                <i class="fas fa-envelope mr-1"></i>
                                View email
                            </button>
                        ` : ''}
                        ${item.confidence_score ? `
                            <span class="flex items-center" title="AI confidence score">
                                <i class="fas fa-brain mr-1"></i>
                                ${item.confidence_score}%
                            </span>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    }

    // ===========================================
    // Action Item Operations
    // ===========================================

    /**
     * Toggle action item completion
     */
    window.toggleActionComplete = async function(itemId) {
        const item = state.actionItems.find(a => a.id === itemId);
        if (!item) return;

        const newStatus = item.status === 'completed' ? 'pending' : 'completed';

        try {
            const endpoint = newStatus === 'completed' ? 'complete' : 'reopen';
            const response = await app.apiJson(`/api/actions/${itemId}/${endpoint}`, {
                method: 'PUT'
            });

            if (response.ok) {
                item.status = newStatus;
                if (newStatus === 'completed') {
                    item.completed_at = new Date().toISOString();
                } else {
                    item.completed_at = null;
                }
                renderActionItems();
                app.showNotification(newStatus === 'completed' ? 'Action completed!' : 'Action reopened', 'success');
            }
        } catch (error) {
            console.error('Error updating action item:', error);
            app.showNotification('Failed to update action', 'error');
        }
    };

    /**
     * Delete action item
     */
    window.deleteActionItem = async function(itemId) {
        if (!confirm('Delete this action item?')) return;

        try {
            const response = await app.apiRequest(`/api/actions/${itemId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                state.actionItems = state.actionItems.filter(a => a.id !== itemId);
                renderActionItems();
                app.showNotification('Action deleted', 'success');
            }
        } catch (error) {
            console.error('Error deleting action item:', error);
            app.showNotification('Failed to delete action', 'error');
        }
    };

    /**
     * Create new action item
     */
    window.createActionItem = async function(title, description = '', priority = 'medium', dueDate = null) {
        try {
            const response = await app.apiJson('/api/actions', {
                method: 'POST',
                body: JSON.stringify({
                    title,
                    description,
                    priority,
                    due_date: dueDate
                })
            });

            if (response.ok) {
                const newItem = await response.json();
                state.actionItems.unshift(newItem);
                renderActionItems();
                app.showNotification('Action created', 'success');
                return newItem;
            }
        } catch (error) {
            console.error('Error creating action item:', error);
            app.showNotification('Failed to create action', 'error');
        }
        return null;
    };

    /**
     * Extract action items from email
     */
    window.extractActionItems = async function(emailId) {
        try {
            app.showNotification('Extracting action items...', 'info');

            const response = await app.apiJson(`/api/actions/extract?email_id=${emailId}`, {
                method: 'POST'
            });

            if (response.ok) {
                const items = await response.json();
                if (items.length > 0) {
                    state.actionItems = [...items, ...state.actionItems];
                    renderActionItems();
                    app.showNotification(`Extracted ${items.length} action item(s)`, 'success');
                } else {
                    app.showNotification('No action items found in this email', 'info');
                }
                return items;
            }
        } catch (error) {
            console.error('Error extracting action items:', error);
            app.showNotification('Failed to extract actions', 'error');
        }
        return [];
    };

    /**
     * Edit action item (show modal)
     */
    window.editActionItem = function(itemId) {
        const item = state.actionItems.find(a => a.id === itemId);
        if (!item) return;

        // For now, use prompt - could be enhanced with a modal
        const newTitle = prompt('Edit action item title:', item.title);
        if (newTitle && newTitle !== item.title) {
            updateActionItem(itemId, { title: newTitle });
        }
    };

    /**
     * Update action item
     */
    async function updateActionItem(itemId, updates) {
        try {
            const response = await app.apiJson(`/api/actions/${itemId}`, {
                method: 'PUT',
                body: JSON.stringify(updates)
            });

            if (response.ok) {
                const updatedItem = await response.json();
                const index = state.actionItems.findIndex(a => a.id === itemId);
                if (index !== -1) {
                    state.actionItems[index] = { ...state.actionItems[index], ...updatedItem };
                }
                renderActionItems();
                app.showNotification('Action updated', 'success');
            }
        } catch (error) {
            console.error('Error updating action item:', error);
            app.showNotification('Failed to update action', 'error');
        }
    }

    // ===========================================
    // Action Item Modal
    // ===========================================

    /**
     * Show create action modal
     */
    window.showCreateActionModal = function() {
        const modal = document.getElementById('create-action-modal');
        if (modal) {
            modal.classList.remove('hidden');
        }
    };

    /**
     * Close create action modal
     */
    window.closeCreateActionModal = function() {
        const modal = document.getElementById('create-action-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
    };

})(window.SAIGBOX);
