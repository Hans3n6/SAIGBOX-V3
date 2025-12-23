/**
 * Lead Acquisition Module
 * Handles prospect finding, enrichment, LinkedIn, and CRM integration UI
 */

(function() {
    'use strict';

    // State
    let currentTab = 'prospect-finder';
    let prospects = [];
    let linkedInConnections = [];
    let crmConnections = [];

    // Helper function to build auth headers (avoids sending "Bearer null")
    function getAuthHeaders(includeContentType = false) {
        const headers = {};
        const token = localStorage.getItem('authToken');
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        if (includeContentType) {
            headers['Content-Type'] = 'application/json';
        }
        return headers;
    }

    // Helper function for authenticated fetch with cookie fallback
    async function authFetch(url, options = {}) {
        const headers = options.headers || {};
        const token = localStorage.getItem('authToken');
        if (token && !headers['Authorization']) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        return fetch(url, {
            ...options,
            headers: headers,
            credentials: 'include'  // Include cookies for auth fallback
        });
    }

    /**
     * Initialize the Lead Acquisition section in Sales Dashboard
     * Called when Sales Dashboard view is loaded
     */
    window.initLeadAcquisition = function() {
        const content = document.getElementById('lead-acquisition-content');
        if (!content) return;

        // Load the default tab content
        loadTabContent(currentTab);
    };

    // Auto-initialize when Sales Dashboard is shown
    document.addEventListener('DOMContentLoaded', function() {
        // Check if we're on sales dashboard by watching for view changes
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.target.id === 'sales-dashboard-view' &&
                    !mutation.target.classList.contains('hidden')) {
                    initLeadAcquisition();
                }
            });
        });

        const salesView = document.getElementById('sales-dashboard-view');
        if (salesView) {
            observer.observe(salesView, { attributes: true, attributeFilter: ['class'] });
        }
    });

    /**
     * Switch between lead acquisition tabs
     */
    window.switchLeadTab = function(tab) {
        currentTab = tab;

        // Update tab styles - find the clicked button by data-tab attribute
        document.querySelectorAll('.lead-tab-btn').forEach(btn => {
            if (btn.dataset.tab === tab) {
                btn.classList.remove('border-transparent', 'text-gray-500');
                btn.classList.add('border-blue-500', 'text-blue-600', 'active-lead-tab');
            } else {
                btn.classList.remove('border-blue-500', 'text-blue-600', 'active-lead-tab');
                btn.classList.add('border-transparent', 'text-gray-500');
            }
        });

        loadTabContent(tab);
    };

    /**
     * Load content for a specific tab
     */
    function loadTabContent(tab) {
        const content = document.getElementById('lead-acquisition-content');
        if (!content) return;

        switch (tab) {
            case 'prospect-finder':
                renderProspectFinder(content);
                break;
            case 'enrichment':
                renderEnrichment(content);
                break;
            case 'linkedin':
                renderLinkedIn(content);
                break;
            case 'crm':
                renderCRM(content);
                break;
        }
    }

    // ============================================
    // PROSPECT FINDER TAB
    // ============================================

    function renderProspectFinder(container) {
        container.innerHTML = `
            <div class="space-y-6">
                <!-- Search Section -->
                <div class="bg-gray-50 rounded-lg p-6">
                    <h4 class="font-semibold mb-4">Find Prospects from Company Website</h4>
                    <div class="flex gap-4">
                        <input type="url" id="prospect-url"
                            placeholder="https://example.com"
                            class="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500">
                        <button onclick="findProspects()"
                            class="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700">
                            <i class="fas fa-search mr-2"></i>Find Prospects
                        </button>
                    </div>
                </div>

                <!-- Results Section -->
                <div id="prospect-results" class="hidden">
                    <div class="flex justify-between items-center mb-4">
                        <h4 class="font-semibold">Found Prospects</h4>
                        <div class="space-x-2">
                            <button onclick="scoreProspects()"
                                class="text-blue-600 hover:text-blue-700">
                                <i class="fas fa-star mr-1"></i>Score All
                            </button>
                            <button onclick="addAllToProspects()"
                                class="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700">
                                <i class="fas fa-plus mr-2"></i>Add All
                            </button>
                        </div>
                    </div>
                    <div id="prospect-list" class="space-y-3">
                        <!-- Prospects will be rendered here -->
                    </div>
                </div>

                <!-- Recent Sources -->
                <div>
                    <h4 class="font-semibold mb-4">Recent Searches</h4>
                    <div id="recent-sources" class="space-y-2">
                        <p class="text-gray-500 text-sm">No recent searches</p>
                    </div>
                </div>
            </div>
        `;

        loadRecentSources();
    }

    window.findProspects = async function() {
        const url = document.getElementById('prospect-url').value.trim();
        if (!url) {
            showNotification('Please enter a website URL', 'error');
            return;
        }

        const resultsDiv = document.getElementById('prospect-results');
        const listDiv = document.getElementById('prospect-list');

        listDiv.innerHTML = `
            <div class="text-center py-8">
                <i class="fas fa-spinner fa-spin text-3xl text-blue-600 mb-4"></i>
                <p class="text-gray-600">Searching for prospects...</p>
            </div>
        `;
        resultsDiv.classList.remove('hidden');

        try {
            const token = localStorage.getItem('authToken');
            const response = await fetch('/api/prospecting/find', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ website_url: url })
            });

            const data = await response.json();

            if (data.success && data.contacts?.length > 0) {
                prospects = data.contacts;
                renderProspectList(listDiv, data);
            } else {
                listDiv.innerHTML = `
                    <div class="text-center py-8 text-gray-500">
                        <i class="fas fa-search text-4xl mb-4"></i>
                        <p>No contacts found on this website</p>
                    </div>
                `;
            }

            loadRecentSources();

        } catch (error) {
            console.error('Error finding prospects:', error);
            listDiv.innerHTML = `
                <div class="text-center py-8 text-red-500">
                    <i class="fas fa-exclamation-circle text-4xl mb-4"></i>
                    <p>Error searching for prospects</p>
                </div>
            `;
        }
    };

    function renderProspectList(container, data) {
        let html = `
            <div class="mb-4 p-4 bg-blue-50 rounded-lg">
                <div class="flex items-center justify-between">
                    <div>
                        <strong>${data.company?.name || data.domain}</strong>
                        <span class="text-gray-500 ml-2">${data.domain}</span>
                    </div>
                    <span class="text-sm text-blue-600">${data.contacts?.length || 0} contacts found</span>
                </div>
            </div>
        `;

        for (const contact of (data.contacts || [])) {
            html += `
                <div class="border rounded-lg p-4 hover:bg-gray-50">
                    <div class="flex justify-between items-start">
                        <div>
                            <div class="font-medium">${escapeHtml(contact.full_name || contact.email || 'Unknown')}</div>
                            ${contact.job_title ? `<div class="text-sm text-gray-500">${escapeHtml(contact.job_title)}</div>` : ''}
                            ${contact.email ? `<div class="text-sm text-blue-600">${escapeHtml(contact.email)}</div>` : ''}
                        </div>
                        <div class="flex items-center space-x-2">
                            ${contact.confidence ? `
                                <span class="text-xs px-2 py-1 rounded ${contact.confidence > 0.7 ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}">
                                    ${Math.round(contact.confidence * 100)}%
                                </span>
                            ` : ''}
                            ${contact.linkedin_url ? `
                                <a href="${contact.linkedin_url}" target="_blank" class="text-blue-600 hover:text-blue-700">
                                    <i class="fab fa-linkedin"></i>
                                </a>
                            ` : ''}
                            <button onclick="addToProspects('${escapeHtml(JSON.stringify(contact))}')"
                                class="text-green-600 hover:text-green-700">
                                <i class="fas fa-plus"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }

        container.innerHTML = html;
    }

    async function loadRecentSources() {
        try {
            const response = await authFetch('/api/prospecting/sources?limit=5');
            const data = await response.json();

            const container = document.getElementById('recent-sources');
            if (!container) return;

            if (data.sources?.length > 0) {
                container.innerHTML = data.sources.map(s => `
                    <div class="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                        <div>
                            <div class="font-medium text-sm">${escapeHtml(s.domain)}</div>
                            <div class="text-xs text-gray-500">${s.contacts_found} contacts</div>
                        </div>
                        <span class="text-xs text-gray-400">${s.status}</span>
                    </div>
                `).join('');
            }
        } catch (error) {
            console.error('Error loading sources:', error);
        }
    }

    // ============================================
    // ENRICHMENT TAB
    // ============================================

    function renderEnrichment(container) {
        container.innerHTML = `
            <div class="space-y-6">
                <!-- Credits Status -->
                <div id="enrichment-credits" class="bg-gray-50 rounded-lg p-4">
                    <div class="text-sm text-gray-500">Loading credits...</div>
                </div>

                <!-- Email Finder -->
                <div class="border rounded-lg p-6">
                    <h4 class="font-semibold mb-4">Find Email</h4>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                        <input type="text" id="enrich-domain" placeholder="company.com"
                            class="border border-gray-300 rounded-lg px-3 py-2">
                        <input type="text" id="enrich-first" placeholder="First Name"
                            class="border border-gray-300 rounded-lg px-3 py-2">
                        <input type="text" id="enrich-last" placeholder="Last Name"
                            class="border border-gray-300 rounded-lg px-3 py-2">
                    </div>
                    <button onclick="findEmail()"
                        class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
                        <i class="fas fa-search mr-2"></i>Find Email
                    </button>
                    <div id="email-result" class="mt-4 hidden"></div>
                </div>

                <!-- Email Verifier -->
                <div class="border rounded-lg p-6">
                    <h4 class="font-semibold mb-4">Verify Email</h4>
                    <div class="flex gap-4">
                        <input type="email" id="verify-email" placeholder="email@example.com"
                            class="flex-1 border border-gray-300 rounded-lg px-3 py-2">
                        <button onclick="verifyEmail()"
                            class="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700">
                            <i class="fas fa-check mr-2"></i>Verify
                        </button>
                    </div>
                    <div id="verify-result" class="mt-4 hidden"></div>
                </div>
            </div>
        `;

        loadEnrichmentCredits();
    }

    async function loadEnrichmentCredits() {
        try {
            const response = await authFetch('/api/prospecting/enrich/credits');
            const data = await response.json();

            const container = document.getElementById('enrichment-credits');
            if (!container) return;

            const providers = data.providers || {};
            container.innerHTML = `
                <div class="flex justify-between items-center">
                    <span class="font-medium">Enrichment Credits</span>
                    <div class="space-x-4">
                        ${Object.entries(providers).map(([name, info]) => `
                            <span class="text-sm">
                                <strong>${name}:</strong>
                                ${info.remaining || info.live_remaining || 0} remaining
                            </span>
                        `).join('')}
                    </div>
                </div>
            `;
        } catch (error) {
            console.error('Error loading credits:', error);
        }
    }

    window.findEmail = async function() {
        const domain = document.getElementById('enrich-domain').value.trim();
        const firstName = document.getElementById('enrich-first').value.trim();
        const lastName = document.getElementById('enrich-last').value.trim();

        if (!domain) {
            showNotification('Domain is required', 'error');
            return;
        }

        const resultDiv = document.getElementById('email-result');
        resultDiv.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Searching...';
        resultDiv.classList.remove('hidden');

        try {
            const token = localStorage.getItem('authToken');
            const response = await fetch('/api/prospecting/enrich/email', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ domain, first_name: firstName, last_name: lastName })
            });

            const data = await response.json();

            if (data.success && data.contact?.email) {
                resultDiv.innerHTML = `
                    <div class="p-4 bg-green-50 rounded-lg">
                        <div class="font-medium text-green-800">${data.contact.email}</div>
                        <div class="text-sm text-green-600">
                            Confidence: ${Math.round((data.metadata?.confidence || 0) * 100)}%
                            ${data.contact.email_verified ? ' | Verified' : ''}
                        </div>
                    </div>
                `;
            } else {
                resultDiv.innerHTML = `
                    <div class="p-4 bg-yellow-50 rounded-lg text-yellow-800">
                        No email found. ${data.metadata?.error || ''}
                    </div>
                `;
            }
        } catch (error) {
            resultDiv.innerHTML = `<div class="p-4 bg-red-50 text-red-800">Error: ${error.message}</div>`;
        }
    };

    window.verifyEmail = async function() {
        const email = document.getElementById('verify-email').value.trim();
        if (!email) {
            showNotification('Email is required', 'error');
            return;
        }

        const resultDiv = document.getElementById('verify-result');
        resultDiv.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Verifying...';
        resultDiv.classList.remove('hidden');

        try {
            const token = localStorage.getItem('authToken');
            const response = await fetch('/api/prospecting/enrich/verify', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email })
            });

            const data = await response.json();

            const isValid = data.contact?.email_verified;
            resultDiv.innerHTML = `
                <div class="p-4 ${isValid ? 'bg-green-50' : 'bg-red-50'} rounded-lg">
                    <div class="font-medium ${isValid ? 'text-green-800' : 'text-red-800'}">
                        ${isValid ? 'Valid Email' : 'Invalid Email'}
                    </div>
                    <div class="text-sm ${isValid ? 'text-green-600' : 'text-red-600'}">
                        Type: ${data.contact?.email_type || 'Unknown'}
                    </div>
                </div>
            `;
        } catch (error) {
            resultDiv.innerHTML = `<div class="p-4 bg-red-50 text-red-800">Error: ${error.message}</div>`;
        }
    };

    // ============================================
    // LINKEDIN TAB
    // ============================================

    function renderLinkedIn(container) {
        container.innerHTML = `
            <div class="space-y-6">
                <!-- Import Section -->
                <div class="border rounded-lg p-6">
                    <h4 class="font-semibold mb-4">Import LinkedIn Connections</h4>
                    <p class="text-sm text-gray-600 mb-4">
                        Export your connections from LinkedIn (Settings > Data privacy > Get a copy of your data)
                        and upload the Connections.csv file.
                    </p>
                    <input type="file" id="linkedin-csv" accept=".csv"
                        class="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4
                        file:rounded-full file:border-0 file:text-sm file:font-semibold
                        file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100">
                    <button onclick="importLinkedInCSV()"
                        class="mt-4 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
                        <i class="fas fa-upload mr-2"></i>Import Connections
                    </button>
                </div>

                <!-- Connections List -->
                <div>
                    <div class="flex justify-between items-center mb-4">
                        <h4 class="font-semibold">Your Connections</h4>
                        <input type="text" id="linkedin-search" placeholder="Search..."
                            onkeyup="searchLinkedInConnections()"
                            class="border border-gray-300 rounded-lg px-3 py-2 text-sm">
                    </div>
                    <div id="linkedin-connections" class="space-y-2">
                        <p class="text-gray-500 text-sm">No connections imported yet</p>
                    </div>
                </div>
            </div>
        `;

        loadLinkedInConnections();
    }

    window.importLinkedInCSV = async function() {
        const fileInput = document.getElementById('linkedin-csv');
        const file = fileInput.files[0];

        if (!file) {
            showNotification('Please select a CSV file', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            const token = localStorage.getItem('authToken');
            const response = await fetch('/api/prospecting/linkedin/import', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });

            const data = await response.json();

            if (data.success) {
                showNotification(`Imported ${data.imported} connections`, 'success');
                loadLinkedInConnections();
            } else {
                showNotification('Error importing connections', 'error');
            }
        } catch (error) {
            console.error('Error importing LinkedIn:', error);
            showNotification('Error importing connections', 'error');
        }
    };

    async function loadLinkedInConnections(search = '') {
        try {
            const token = localStorage.getItem('authToken');
            const url = `/api/prospecting/linkedin/connections?limit=50${search ? `&search=${encodeURIComponent(search)}` : ''}`;
            const response = await fetch(url, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const data = await response.json();

            const container = document.getElementById('linkedin-connections');
            if (!container) return;

            if (data.connections?.length > 0) {
                linkedInConnections = data.connections;
                container.innerHTML = data.connections.map(c => `
                    <div class="flex justify-between items-center p-3 border rounded-lg hover:bg-gray-50">
                        <div>
                            <div class="font-medium">${escapeHtml(c.full_name)}</div>
                            <div class="text-sm text-gray-500">${escapeHtml(c.position || '')} at ${escapeHtml(c.company || '')}</div>
                        </div>
                        <div class="flex space-x-2">
                            ${c.linkedin_url ? `<a href="${c.linkedin_url}" target="_blank" class="text-blue-600"><i class="fab fa-linkedin"></i></a>` : ''}
                            <button onclick="convertToProspect('${c.id}')" class="text-green-600 hover:text-green-700" title="Add as prospect">
                                <i class="fas fa-user-plus"></i>
                            </button>
                        </div>
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<p class="text-gray-500 text-sm">No connections found</p>';
            }
        } catch (error) {
            console.error('Error loading connections:', error);
        }
    }

    window.searchLinkedInConnections = function() {
        const search = document.getElementById('linkedin-search').value;
        loadLinkedInConnections(search);
    };

    window.convertToProspect = async function(connectionId) {
        try {
            const token = localStorage.getItem('authToken');
            const response = await fetch(`/api/prospecting/linkedin/convert/${connectionId}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();
            if (data.success) {
                showNotification('Added as prospect', 'success');
            } else {
                showNotification(data.error || 'Error adding prospect', 'error');
            }
        } catch (error) {
            console.error('Error converting:', error);
            showNotification('Error adding prospect', 'error');
        }
    };

    // ============================================
    // CRM TAB
    // ============================================

    function renderCRM(container) {
        container.innerHTML = `
            <div class="space-y-6">
                <!-- HubSpot Connection -->
                <div class="border rounded-lg p-6">
                    <div class="flex items-center justify-between mb-4">
                        <div class="flex items-center">
                            <img src="https://www.hubspot.com/favicon.ico" class="w-6 h-6 mr-3" alt="HubSpot">
                            <h4 class="font-semibold">HubSpot CRM</h4>
                        </div>
                        <div id="hubspot-status">
                            <span class="text-gray-500">Not connected</span>
                        </div>
                    </div>
                    <div id="hubspot-connect">
                        <p class="text-sm text-gray-600 mb-4">
                            Connect your HubSpot CRM to sync contacts and deals.
                        </p>
                        <div class="mb-4">
                            <label class="block text-sm font-medium text-gray-700 mb-1">API Key</label>
                            <input type="password" id="hubspot-api-key" placeholder="Enter HubSpot API Key"
                                class="w-full border border-gray-300 rounded-lg px-3 py-2">
                        </div>
                        <button onclick="connectHubSpot()"
                            class="bg-orange-500 text-white px-4 py-2 rounded-lg hover:bg-orange-600">
                            <i class="fas fa-plug mr-2"></i>Connect HubSpot
                        </button>
                    </div>
                    <div id="hubspot-actions" class="hidden space-y-4">
                        <div class="flex space-x-4">
                            <button onclick="importFromCRM('hubspot')"
                                class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
                                <i class="fas fa-download mr-2"></i>Import Contacts
                            </button>
                            <button onclick="exportToCRM('hubspot')"
                                class="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700">
                                <i class="fas fa-upload mr-2"></i>Export Prospects
                            </button>
                            <button onclick="disconnectCRM('hubspot')"
                                class="text-red-600 hover:text-red-700">
                                <i class="fas fa-unlink mr-2"></i>Disconnect
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Sync History -->
                <div>
                    <h4 class="font-semibold mb-4">Sync History</h4>
                    <div id="crm-sync-history" class="space-y-2">
                        <p class="text-gray-500 text-sm">No sync history</p>
                    </div>
                </div>
            </div>
        `;

        loadCRMConnections();
        loadSyncHistory();
    }

    async function loadCRMConnections() {
        try {
            const token = localStorage.getItem('authToken');
            const response = await fetch('/api/prospecting/crm/connections', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const data = await response.json();

            crmConnections = data.connections || [];

            const hubspot = crmConnections.find(c => c.provider === 'hubspot' && c.is_active);
            if (hubspot) {
                document.getElementById('hubspot-status').innerHTML = `
                    <span class="text-green-600"><i class="fas fa-check-circle mr-1"></i>Connected</span>
                `;
                document.getElementById('hubspot-connect').classList.add('hidden');
                document.getElementById('hubspot-actions').classList.remove('hidden');
            }
        } catch (error) {
            console.error('Error loading CRM connections:', error);
        }
    }

    window.connectHubSpot = async function() {
        const apiKey = document.getElementById('hubspot-api-key').value.trim();
        if (!apiKey) {
            showNotification('API Key is required', 'error');
            return;
        }

        try {
            const token = localStorage.getItem('authToken');
            const response = await fetch('/api/prospecting/crm/connect/hubspot', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ api_key: apiKey })
            });

            const data = await response.json();
            if (data.success) {
                showNotification('HubSpot connected!', 'success');
                loadCRMConnections();
            } else {
                showNotification(data.error || 'Connection failed', 'error');
            }
        } catch (error) {
            console.error('Error connecting HubSpot:', error);
            showNotification('Connection failed', 'error');
        }
    };

    window.importFromCRM = async function(provider) {
        try {
            const token = localStorage.getItem('authToken');
            const response = await fetch(`/api/prospecting/crm/import/${provider}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();
            if (data.success) {
                showNotification(`Imported ${data.imported} contacts, updated ${data.updated}`, 'success');
                loadSyncHistory();
            } else {
                showNotification(data.error || 'Import failed', 'error');
            }
        } catch (error) {
            console.error('Error importing:', error);
            showNotification('Import failed', 'error');
        }
    };

    window.exportToCRM = async function(provider) {
        try {
            const token = localStorage.getItem('authToken');
            const response = await fetch(`/api/prospecting/crm/export/${provider}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ export_all: true })
            });

            const data = await response.json();
            if (data.success) {
                showNotification(`Exported ${data.created} contacts`, 'success');
                loadSyncHistory();
            } else {
                showNotification(data.error || 'Export failed', 'error');
            }
        } catch (error) {
            console.error('Error exporting:', error);
            showNotification('Export failed', 'error');
        }
    };

    window.disconnectCRM = async function(provider) {
        if (!confirm(`Disconnect ${provider}?`)) return;

        try {
            const token = localStorage.getItem('authToken');
            await fetch(`/api/prospecting/crm/disconnect/${provider}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            showNotification('Disconnected', 'success');
            loadCRMConnections();
        } catch (error) {
            console.error('Error disconnecting:', error);
        }
    };

    async function loadSyncHistory() {
        try {
            const token = localStorage.getItem('authToken');
            const response = await fetch('/api/prospecting/crm/sync-history?limit=10', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const data = await response.json();

            const container = document.getElementById('crm-sync-history');
            if (!container) return;

            if (data.history?.length > 0) {
                container.innerHTML = data.history.map(h => `
                    <div class="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                        <div>
                            <div class="text-sm font-medium">${h.direction} - ${h.sync_type}</div>
                            <div class="text-xs text-gray-500">
                                ${h.records_created} created, ${h.records_updated} updated
                            </div>
                        </div>
                        <span class="text-xs text-gray-400">${new Date(h.started_at).toLocaleDateString()}</span>
                    </div>
                `).join('');
            }
        } catch (error) {
            console.error('Error loading sync history:', error);
        }
    }

    // ============================================
    // UTILITIES
    // ============================================

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function showNotification(message, type = 'info') {
        if (typeof window.showNotification === 'function' && window.showNotification !== showNotification) {
            window.showNotification(message, type);
        } else {
            alert(message);
        }
    }

})();
