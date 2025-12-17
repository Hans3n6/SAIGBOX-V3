/**
 * SAIGBOX Core Application Module
 * Handles global state, initialization, and shared utilities
 */

// Create global namespace
window.SAIGBOX = window.SAIGBOX || {};

(function(app) {
    'use strict';

    // ===========================================
    // Global State
    // ===========================================
    app.state = {
        authToken: '',
        currentView: 'inbox',
        selectedEmailId: null,
        emails: [],
        trashedEmails: [],
        allLoadedEmails: [],
        loadedPages: new Set(),
        currentPage: 0,
        isLoading: false,
        hasMoreEmails: true,
        totalEmailsLoaded: 0,
        consecutiveErrors: 0,
        syncQueue: [],
        userEmail: '',
        isAutoLoading: false,
        currentSearchQuery: '',
        isSyncing: false,
        // Action items
        actionItems: [],
        // Sales dashboard
        opportunities: [],
        currentOpportunityFilter: 'all',
        currentOpportunityEmails: [],
        currentSelectedEmailId: null,
        // SAIG
        saigContext: {},
        chatHistory: [],
        // Huddles
        huddles: [],
        currentHuddle: null
    };

    // ===========================================
    // Configuration
    // ===========================================
    app.config = {
        apiBaseUrl: '',
        maxEmailsPerPage: 50,
        syncInterval: 30000,
        debounceWait: 300
    };

    // ===========================================
    // Utility Functions
    // ===========================================

    /**
     * Show notification toast
     */
    app.showNotification = function(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `fixed bottom-4 right-4 px-6 py-3 rounded-lg shadow-lg z-50 ${
            type === 'error' ? 'bg-red-500' :
            type === 'success' ? 'bg-green-500' :
            type === 'warning' ? 'bg-yellow-500' :
            'bg-blue-500'
        } text-white`;
        notification.textContent = message;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transition = 'opacity 0.3s';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    };

    /**
     * Debounce function
     */
    app.debounce = function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    };

    /**
     * Format date for display
     */
    app.formatDate = function(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        const now = new Date();
        const diffMs = now - date;
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffDays === 0) {
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } else if (diffDays === 1) {
            return 'Yesterday';
        } else if (diffDays < 7) {
            return date.toLocaleDateString([], { weekday: 'short' });
        } else {
            return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
        }
    };

    /**
     * Escape HTML to prevent XSS
     */
    app.escapeHtml = function(text) {
        if (!text) return '';
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    };

    /**
     * Make authenticated API request
     */
    app.apiRequest = async function(url, options = {}) {
        const headers = options.headers || {};

        if (app.state.authToken && app.state.authToken !== 'session') {
            headers['Authorization'] = `Bearer ${app.state.authToken}`;
        }

        const response = await fetch(url, {
            ...options,
            headers,
            credentials: 'include'
        });

        return response;
    };

    /**
     * Make authenticated JSON API request
     */
    app.apiJson = async function(url, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...(options.headers || {})
        };

        if (app.state.authToken && app.state.authToken !== 'session') {
            headers['Authorization'] = `Bearer ${app.state.authToken}`;
        }

        const response = await fetch(url, {
            ...options,
            headers,
            credentials: 'include'
        });

        return response;
    };

    // ===========================================
    // View Management
    // ===========================================

    /**
     * Switch between application views
     */
    app.switchView = function(view) {
        app.state.currentView = view;

        // Stop auto-loading when leaving inbox
        if (view !== 'inbox') {
            app.state.isAutoLoading = false;
        }

        // Hide all views
        document.querySelectorAll('[id$="-view"]').forEach(el => el.classList.add('hidden'));

        // Show selected view
        const viewElement = document.getElementById(`${view}-view`);
        if (viewElement) {
            viewElement.classList.remove('hidden');
        }

        // Show/hide inbox controls
        const inboxControls = document.getElementById('inbox-controls');
        if (inboxControls) {
            inboxControls.style.display = view === 'inbox' ? 'flex' : 'none';
        }

        // Update title
        const titles = {
            'inbox': 'Inbox',
            'actions': 'Action Items',
            'sales-dashboard': 'Sales Dashboard',
            'huddles': 'Huddles',
            'trash': 'Trash',
            'saig': 'SAIG'
        };
        const viewTitle = document.getElementById('view-title');
        if (viewTitle) {
            viewTitle.textContent = titles[view] || 'Inbox';
        }

        // Update nav links
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active-nav');
            link.style.backgroundColor = '';
        });

        const activeLink = document.querySelector(`[onclick*="switchView('${view}')"]`);
        if (activeLink) {
            activeLink.classList.add('active-nav');
        }

        // Load view-specific data
        app.loadViewData(view);
    };

    /**
     * Load data for a specific view
     */
    app.loadViewData = function(view) {
        switch(view) {
            case 'inbox':
                if (typeof loadEmails === 'function') loadEmails();
                break;
            case 'actions':
                if (typeof loadActionItems === 'function') loadActionItems();
                break;
            case 'sales-dashboard':
                if (typeof loadSalesDashboard === 'function') loadSalesDashboard();
                break;
            case 'huddles':
                if (typeof loadHuddles === 'function') loadHuddles();
                break;
            case 'trash':
                if (typeof loadTrash === 'function') loadTrash();
                break;
        }
    };

    // ===========================================
    // Initialization
    // ===========================================

    /**
     * Initialize the application
     */
    app.init = function() {
        // Get auth token from cookie or storage
        const cookies = document.cookie.split(';');
        for (const cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'access_token') {
                app.state.authToken = value;
                break;
            }
        }

        // If no token in cookie, use session auth
        if (!app.state.authToken) {
            app.state.authToken = 'session';
        }

        // Load user email from the page if available
        const userEmailEl = document.querySelector('[data-user-email]');
        if (userEmailEl) {
            app.state.userEmail = userEmailEl.dataset.userEmail;
        }

        // Setup event listeners
        app.setupEventListeners();

        // Load initial view
        app.switchView('inbox');
    };

    /**
     * Setup global event listeners
     */
    app.setupEventListeners = function() {
        // Search input
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    if (typeof searchEmails === 'function') searchEmails();
                }
            });
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Escape to close modals
            if (e.key === 'Escape') {
                document.querySelectorAll('.modal').forEach(m => m.classList.add('hidden'));
            }

            // Ctrl/Cmd + K for search
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                const searchInput = document.getElementById('searchInput');
                if (searchInput) searchInput.focus();
            }
        });
    };

    // Make switchView globally accessible
    window.switchView = app.switchView;

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', app.init);
    } else {
        app.init();
    }

})(window.SAIGBOX);
