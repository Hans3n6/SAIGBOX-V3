/**
 * Business Profile Management
 * Handles the enhanced business profile UI with auto-population from company website
 */

(function() {
    'use strict';

    // State
    let businessProfile = null;
    let isLoading = false;
    let hasChanges = false;

    // Field configurations for each section
    const PROFILE_SECTIONS = {
        company: {
            title: 'Company Overview',
            icon: 'fa-building',
            fields: [
                { key: 'company_name', label: 'Company Name', type: 'text', placeholder: 'Your Company Name' },
                { key: 'company_website', label: 'Website', type: 'url', placeholder: 'https://www.example.com' },
                { key: 'industry', label: 'Industry', type: 'select', options: [
                    'Agriculture', 'Manufacturing', 'Technology', 'Healthcare', 'Finance',
                    'Retail', 'Construction', 'Energy', 'Transportation', 'Education', 'Other'
                ]},
                { key: 'company_size', label: 'Company Size', type: 'select', options: [
                    '1-10', '11-50', '51-200', '201-500', '501-1000', '1000+'
                ]},
                { key: 'founded_year', label: 'Founded Year', type: 'number', placeholder: '2010' }
            ]
        },
        sales: {
            title: 'Sales Context',
            icon: 'fa-handshake',
            fields: [
                { key: 'sales_cycle_length', label: 'Sales Cycle Length', type: 'select', options: [
                    '1-2 weeks', '2-4 weeks', '1-2 months', '2-3 months', '3-6 months', '6+ months'
                ]},
                { key: 'average_deal_size_min', label: 'Min Deal Size ($)', type: 'number', placeholder: '5000' },
                { key: 'average_deal_size_max', label: 'Max Deal Size ($)', type: 'number', placeholder: '50000' },
                { key: 'sales_methodology', label: 'Sales Methodology', type: 'select', options: [
                    'SPIN Selling', 'Challenger Sale', 'Solution Selling', 'Consultative', 'MEDDIC', 'None/Custom'
                ]},
                { key: 'decision_makers', label: 'Target Decision Makers', type: 'tags', placeholder: 'Add role (e.g., CEO, CTO)' },
                { key: 'common_objections', label: 'Common Objections', type: 'objections' },
                { key: 'competitors', label: 'Key Competitors', type: 'competitors' }
            ]
        },
        target: {
            title: 'Target Market (for Prospecting)',
            icon: 'fa-bullseye',
            fields: [
                { key: 'target_industries', label: 'Target Industries', type: 'tags', placeholder: 'Add industry' },
                { key: 'target_company_sizes', label: 'Target Company Sizes', type: 'multiselect', options: [
                    '1-10', '11-50', '51-200', '201-500', '501-1000', '1000+'
                ]},
                { key: 'target_job_titles', label: 'Target Job Titles', type: 'tags', placeholder: 'Add job title' },
                { key: 'target_locations', label: 'Target Locations', type: 'tags', placeholder: 'Add location' },
                { key: 'excluded_industries', label: 'Excluded Industries', type: 'tags', placeholder: 'Add industry to exclude' }
            ]
        },
        products: {
            title: 'Products & Services',
            icon: 'fa-box',
            fields: [
                { key: 'products_services', label: 'Products/Services', type: 'products' },
                { key: 'pricing_model', label: 'Pricing Model', type: 'textarea', placeholder: 'Describe your pricing structure...' }
            ]
        },
        value: {
            title: 'Value Proposition',
            icon: 'fa-gem',
            fields: [
                { key: 'elevator_pitch', label: 'Elevator Pitch', type: 'textarea', placeholder: 'Brief company description (2-3 sentences)...' },
                { key: 'value_proposition', label: 'Value Proposition', type: 'textarea', placeholder: 'What unique value do you provide?' },
                { key: 'key_differentiators', label: 'Key Differentiators', type: 'tags', placeholder: 'Add differentiator' },
                { key: 'unique_selling_points', label: 'Unique Selling Points', type: 'tags', placeholder: 'Add USP' }
            ]
        },
        pain: {
            title: 'Pain Points & Solutions',
            icon: 'fa-lightbulb',
            fields: [
                { key: 'customer_pain_points', label: 'Customer Pain Points', type: 'tags', placeholder: 'Add pain point' },
                { key: 'solutions_offered', label: 'Solutions You Offer', type: 'solutions' }
            ]
        },
        success: {
            title: 'Success Stories',
            icon: 'fa-trophy',
            fields: [
                { key: 'notable_clients', label: 'Notable Clients', type: 'tags', placeholder: 'Add client name' },
                { key: 'testimonials', label: 'Testimonials', type: 'testimonials' },
                { key: 'case_studies', label: 'Case Studies', type: 'casestudies' }
            ]
        },
        communication: {
            title: 'Communication Settings',
            icon: 'fa-comments',
            fields: [
                { key: 'cold_email_tone', label: 'Email Tone', type: 'select', options: [
                    'professional', 'casual', 'technical', 'friendly', 'formal'
                ]},
                { key: 'preferred_outreach_channels', label: 'Preferred Channels', type: 'multiselect', options: [
                    'email', 'phone', 'linkedin', 'sms', 'video_call'
                ]},
                { key: 'follow_up_cadence', label: 'Follow-up Cadence', type: 'select', options: [
                    'aggressive', 'moderate', 'conservative'
                ]},
                { key: 'calendar_link', label: 'Calendar Link', type: 'url', placeholder: 'https://calendly.com/...' },
                { key: 'email_signature', label: 'Email Signature (Text)', type: 'textarea', placeholder: 'Your email signature...' }
            ]
        },
        metrics: {
            title: 'Success Metrics',
            icon: 'fa-chart-pie',
            fields: [
                { key: 'win_rate', label: 'Win Rate (%)', type: 'number', placeholder: '35', max: 100 },
                { key: 'average_response_time', label: 'Avg Response Time', type: 'select', options: [
                    'Same day', 'Within 24 hours', '1-2 days', '3-5 days', '1 week+'
                ]},
                { key: 'nps_score', label: 'NPS Score', type: 'number', placeholder: '50', min: -100, max: 100 },
                { key: 'customer_retention_rate', label: 'Retention Rate (%)', type: 'number', placeholder: '85', max: 100 }
            ]
        }
    };

    /**
     * Load business profile from server
     */
    window.loadBusinessProfile = async function() {
        if (isLoading) return;
        isLoading = true;

        const container = document.getElementById('business-profile-content');
        if (!container) return;

        container.innerHTML = `
            <div class="text-center py-12 text-gray-500">
                <i class="fas fa-spinner fa-spin text-4xl mb-4"></i>
                <p>Loading business profile...</p>
            </div>
        `;

        try {
            const token = localStorage.getItem('auth_token');
            const response = await fetch('/api/sales-dashboard/business-profile', {
                headers: { 'Authorization': `Bearer ${token}` }
            });

            if (response.ok) {
                const data = await response.json();
                businessProfile = data.profile || {};
            } else {
                businessProfile = {};
            }

            renderBusinessProfile();
        } catch (error) {
            console.error('Error loading business profile:', error);
            container.innerHTML = `
                <div class="text-center py-12 text-red-500">
                    <i class="fas fa-exclamation-circle text-4xl mb-4"></i>
                    <p>Error loading business profile</p>
                    <button onclick="loadBusinessProfile()" class="mt-4 text-blue-600 hover:underline">Try Again</button>
                </div>
            `;
        } finally {
            isLoading = false;
        }
    };

    /**
     * Render the full business profile UI
     */
    function renderBusinessProfile() {
        const container = document.getElementById('business-profile-content');
        if (!container) return;

        let html = '';

        // Quick Setup Banner (if profile is mostly empty)
        if (isProfileEmpty()) {
            html += `
                <div class="bg-blue-50 border border-blue-200 rounded-lg p-6 mb-6">
                    <div class="flex items-start">
                        <i class="fas fa-magic text-blue-600 text-2xl mr-4 mt-1"></i>
                        <div class="flex-1">
                            <h4 class="font-semibold text-blue-800 mb-2">Quick Setup Available</h4>
                            <p class="text-blue-700 mb-4">Enter your company website and let AI fill in your profile automatically.</p>
                            <button onclick="showQuickSetupModal()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
                                <i class="fas fa-magic mr-2"></i>Start Quick Setup
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }

        // Render each section
        for (const [sectionKey, section] of Object.entries(PROFILE_SECTIONS)) {
            html += renderSection(sectionKey, section);
        }

        container.innerHTML = html;

        // Initialize tag inputs and other special fields
        initializeSpecialFields();
    }

    /**
     * Check if profile is mostly empty
     */
    function isProfileEmpty() {
        if (!businessProfile) return true;
        const importantFields = ['company_name', 'industry', 'elevator_pitch', 'value_proposition'];
        return importantFields.filter(f => businessProfile[f]).length < 2;
    }

    /**
     * Render a single section
     */
    function renderSection(sectionKey, section) {
        let fieldsHtml = '';
        for (const field of section.fields) {
            fieldsHtml += renderField(field);
        }

        return `
            <div class="bg-white rounded-lg shadow mb-6">
                <div class="border-b px-6 py-4 flex items-center">
                    <i class="fas ${section.icon} text-gray-500 mr-3"></i>
                    <h4 class="font-semibold text-lg">${section.title}</h4>
                </div>
                <div class="p-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                    ${fieldsHtml}
                </div>
            </div>
        `;
    }

    /**
     * Render a single field based on its type
     */
    function renderField(field) {
        const value = businessProfile?.[field.key];
        const id = `bp-${field.key}`;

        let inputHtml = '';
        const wrapperClass = field.type === 'textarea' || field.type.includes('tags') ||
                            field.type === 'products' || field.type === 'objections' ||
                            field.type === 'competitors' || field.type === 'solutions' ||
                            field.type === 'testimonials' || field.type === 'casestudies'
            ? 'md:col-span-2' : '';

        switch (field.type) {
            case 'text':
            case 'url':
            case 'number':
                inputHtml = `
                    <input type="${field.type === 'url' ? 'url' : field.type === 'number' ? 'number' : 'text'}"
                        id="${id}"
                        value="${escapeHtml(value || '')}"
                        placeholder="${field.placeholder || ''}"
                        ${field.min !== undefined ? `min="${field.min}"` : ''}
                        ${field.max !== undefined ? `max="${field.max}"` : ''}
                        onchange="markProfileChanged()"
                        class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                `;
                break;

            case 'textarea':
                inputHtml = `
                    <textarea id="${id}"
                        placeholder="${field.placeholder || ''}"
                        onchange="markProfileChanged()"
                        rows="3"
                        class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent">${escapeHtml(value || '')}</textarea>
                `;
                break;

            case 'select':
                const optionsHtml = (field.options || []).map(opt =>
                    `<option value="${opt}" ${value === opt ? 'selected' : ''}>${opt}</option>`
                ).join('');
                inputHtml = `
                    <select id="${id}" onchange="markProfileChanged()"
                        class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                        <option value="">Select...</option>
                        ${optionsHtml}
                    </select>
                `;
                break;

            case 'multiselect':
                const checkboxesHtml = (field.options || []).map(opt => {
                    const checked = Array.isArray(value) && value.includes(opt);
                    return `
                        <label class="inline-flex items-center mr-4 mb-2">
                            <input type="checkbox" value="${opt}" ${checked ? 'checked' : ''}
                                onchange="markProfileChanged()"
                                class="bp-multiselect-${field.key} rounded border-gray-300 text-blue-600 focus:ring-blue-500">
                            <span class="ml-2 text-sm">${opt}</span>
                        </label>
                    `;
                }).join('');
                inputHtml = `<div class="flex flex-wrap">${checkboxesHtml}</div>`;
                break;

            case 'tags':
                const tagsValue = Array.isArray(value) ? value : [];
                inputHtml = `
                    <div class="bp-tags-container" data-field="${field.key}">
                        <div class="flex flex-wrap gap-2 mb-2 bp-tags-list">
                            ${tagsValue.map(tag => `
                                <span class="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm flex items-center">
                                    ${escapeHtml(tag)}
                                    <button onclick="removeTag('${field.key}', '${escapeHtml(tag)}')" class="ml-2 text-blue-600 hover:text-blue-800">&times;</button>
                                </span>
                            `).join('')}
                        </div>
                        <div class="flex">
                            <input type="text" id="${id}-input" placeholder="${field.placeholder || ''}"
                                onkeypress="handleTagKeypress(event, '${field.key}')"
                                class="flex-1 border border-gray-300 rounded-l-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                            <button onclick="addTag('${field.key}')"
                                class="bg-blue-600 text-white px-4 rounded-r-lg hover:bg-blue-700">Add</button>
                        </div>
                    </div>
                `;
                break;

            case 'products':
                inputHtml = renderProductsField(value);
                break;

            case 'objections':
                inputHtml = renderObjectionsField(value);
                break;

            case 'competitors':
                inputHtml = renderCompetitorsField(value);
                break;

            case 'solutions':
                inputHtml = renderSolutionsField(value);
                break;

            case 'testimonials':
                inputHtml = renderTestimonialsField(value);
                break;

            case 'casestudies':
                inputHtml = renderCaseStudiesField(value);
                break;

            default:
                inputHtml = `<span class="text-gray-500">Unknown field type: ${field.type}</span>`;
        }

        return `
            <div class="${wrapperClass}">
                <label class="block text-sm font-medium text-gray-700 mb-1">${field.label}</label>
                ${inputHtml}
            </div>
        `;
    }

    /**
     * Render products/services field
     */
    function renderProductsField(value) {
        const products = Array.isArray(value) ? value : [];
        return `
            <div id="bp-products-list" class="space-y-3">
                ${products.map((p, i) => `
                    <div class="flex items-start gap-2 bg-gray-50 p-3 rounded-lg">
                        <div class="flex-1">
                            <input type="text" value="${escapeHtml(p.name || '')}"
                                placeholder="Product/Service Name"
                                data-idx="${i}" data-field="name"
                                onchange="updateProduct(${i}, 'name', this.value)"
                                class="w-full border border-gray-300 rounded px-2 py-1 mb-2 text-sm">
                            <textarea data-idx="${i}" data-field="description"
                                onchange="updateProduct(${i}, 'description', this.value)"
                                placeholder="Description..."
                                rows="2"
                                class="w-full border border-gray-300 rounded px-2 py-1 text-sm">${escapeHtml(p.description || '')}</textarea>
                        </div>
                        <button onclick="removeProduct(${i})" class="text-red-500 hover:text-red-700">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                `).join('')}
            </div>
            <button onclick="addProduct()" class="mt-2 text-blue-600 hover:text-blue-700 text-sm">
                <i class="fas fa-plus mr-1"></i>Add Product/Service
            </button>
        `;
    }

    /**
     * Render objections field
     */
    function renderObjectionsField(value) {
        const objections = Array.isArray(value) ? value : [];
        return `
            <div id="bp-objections-list" class="space-y-3">
                ${objections.map((o, i) => `
                    <div class="flex items-start gap-2 bg-gray-50 p-3 rounded-lg">
                        <div class="flex-1">
                            <input type="text" value="${escapeHtml(o.objection || '')}"
                                placeholder="Common Objection"
                                onchange="updateObjection(${i}, 'objection', this.value)"
                                class="w-full border border-gray-300 rounded px-2 py-1 mb-2 text-sm">
                            <textarea onchange="updateObjection(${i}, 'response', this.value)"
                                placeholder="Your response..."
                                rows="2"
                                class="w-full border border-gray-300 rounded px-2 py-1 text-sm">${escapeHtml(o.response || '')}</textarea>
                        </div>
                        <button onclick="removeObjection(${i})" class="text-red-500 hover:text-red-700">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                `).join('')}
            </div>
            <button onclick="addObjection()" class="mt-2 text-blue-600 hover:text-blue-700 text-sm">
                <i class="fas fa-plus mr-1"></i>Add Objection
            </button>
        `;
    }

    /**
     * Render competitors field
     */
    function renderCompetitorsField(value) {
        const competitors = Array.isArray(value) ? value : [];
        return `
            <div id="bp-competitors-list" class="space-y-3">
                ${competitors.map((c, i) => `
                    <div class="flex items-start gap-2 bg-gray-50 p-3 rounded-lg">
                        <div class="flex-1">
                            <input type="text" value="${escapeHtml(c.name || '')}"
                                placeholder="Competitor Name"
                                onchange="updateCompetitor(${i}, 'name', this.value)"
                                class="w-full border border-gray-300 rounded px-2 py-1 mb-2 text-sm">
                            <textarea onchange="updateCompetitor(${i}, 'differentiator', this.value)"
                                placeholder="How you're different..."
                                rows="2"
                                class="w-full border border-gray-300 rounded px-2 py-1 text-sm">${escapeHtml(c.differentiator || '')}</textarea>
                        </div>
                        <button onclick="removeCompetitor(${i})" class="text-red-500 hover:text-red-700">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                `).join('')}
            </div>
            <button onclick="addCompetitor()" class="mt-2 text-blue-600 hover:text-blue-700 text-sm">
                <i class="fas fa-plus mr-1"></i>Add Competitor
            </button>
        `;
    }

    /**
     * Render solutions field
     */
    function renderSolutionsField(value) {
        const solutions = Array.isArray(value) ? value : [];
        return `
            <div id="bp-solutions-list" class="space-y-3">
                ${solutions.map((s, i) => `
                    <div class="flex items-start gap-2 bg-gray-50 p-3 rounded-lg">
                        <div class="flex-1">
                            <input type="text" value="${escapeHtml(s.pain || '')}"
                                placeholder="Pain Point"
                                onchange="updateSolution(${i}, 'pain', this.value)"
                                class="w-full border border-gray-300 rounded px-2 py-1 mb-2 text-sm">
                            <textarea onchange="updateSolution(${i}, 'solution', this.value)"
                                placeholder="Your solution..."
                                rows="2"
                                class="w-full border border-gray-300 rounded px-2 py-1 text-sm">${escapeHtml(s.solution || '')}</textarea>
                        </div>
                        <button onclick="removeSolution(${i})" class="text-red-500 hover:text-red-700">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                `).join('')}
            </div>
            <button onclick="addSolution()" class="mt-2 text-blue-600 hover:text-blue-700 text-sm">
                <i class="fas fa-plus mr-1"></i>Add Solution
            </button>
        `;
    }

    /**
     * Render testimonials field
     */
    function renderTestimonialsField(value) {
        const testimonials = Array.isArray(value) ? value : [];
        return `
            <div id="bp-testimonials-list" class="space-y-3">
                ${testimonials.map((t, i) => `
                    <div class="flex items-start gap-2 bg-gray-50 p-3 rounded-lg">
                        <div class="flex-1">
                            <input type="text" value="${escapeHtml(t.name || '')}"
                                placeholder="Client Name & Title"
                                onchange="updateTestimonial(${i}, 'name', this.value)"
                                class="w-full border border-gray-300 rounded px-2 py-1 mb-2 text-sm">
                            <textarea onchange="updateTestimonial(${i}, 'quote', this.value)"
                                placeholder="Testimonial quote..."
                                rows="2"
                                class="w-full border border-gray-300 rounded px-2 py-1 text-sm">${escapeHtml(t.quote || '')}</textarea>
                        </div>
                        <button onclick="removeTestimonial(${i})" class="text-red-500 hover:text-red-700">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                `).join('')}
            </div>
            <button onclick="addTestimonial()" class="mt-2 text-blue-600 hover:text-blue-700 text-sm">
                <i class="fas fa-plus mr-1"></i>Add Testimonial
            </button>
        `;
    }

    /**
     * Render case studies field
     */
    function renderCaseStudiesField(value) {
        const studies = Array.isArray(value) ? value : [];
        return `
            <div id="bp-casestudies-list" class="space-y-3">
                ${studies.map((s, i) => `
                    <div class="flex items-start gap-2 bg-gray-50 p-3 rounded-lg">
                        <div class="flex-1">
                            <input type="text" value="${escapeHtml(s.title || '')}"
                                placeholder="Case Study Title"
                                onchange="updateCaseStudy(${i}, 'title', this.value)"
                                class="w-full border border-gray-300 rounded px-2 py-1 mb-2 text-sm">
                            <textarea onchange="updateCaseStudy(${i}, 'summary', this.value)"
                                placeholder="Summary..."
                                rows="2"
                                class="w-full border border-gray-300 rounded px-2 py-1 text-sm">${escapeHtml(s.summary || '')}</textarea>
                        </div>
                        <button onclick="removeCaseStudy(${i})" class="text-red-500 hover:text-red-700">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                `).join('')}
            </div>
            <button onclick="addCaseStudy()" class="mt-2 text-blue-600 hover:text-blue-700 text-sm">
                <i class="fas fa-plus mr-1"></i>Add Case Study
            </button>
        `;
    }

    /**
     * Initialize special fields (tags, etc.)
     */
    function initializeSpecialFields() {
        // Any additional initialization
    }

    // ========================================
    // Field Update Functions
    // ========================================

    window.markProfileChanged = function() {
        hasChanges = true;
    };

    // Tags
    window.handleTagKeypress = function(event, fieldKey) {
        if (event.key === 'Enter') {
            event.preventDefault();
            addTag(fieldKey);
        }
    };

    window.addTag = function(fieldKey) {
        const input = document.getElementById(`bp-${fieldKey}-input`);
        if (!input) return;

        const value = input.value.trim();
        if (!value) return;

        if (!businessProfile[fieldKey]) {
            businessProfile[fieldKey] = [];
        }
        if (!businessProfile[fieldKey].includes(value)) {
            businessProfile[fieldKey].push(value);
            hasChanges = true;
            renderBusinessProfile();
        }
        input.value = '';
    };

    window.removeTag = function(fieldKey, tagValue) {
        if (!businessProfile[fieldKey]) return;
        businessProfile[fieldKey] = businessProfile[fieldKey].filter(t => t !== tagValue);
        hasChanges = true;
        renderBusinessProfile();
    };

    // Products
    window.addProduct = function() {
        if (!businessProfile.products_services) businessProfile.products_services = [];
        businessProfile.products_services.push({ name: '', description: '' });
        hasChanges = true;
        renderBusinessProfile();
    };

    window.updateProduct = function(idx, field, value) {
        if (!businessProfile.products_services) return;
        businessProfile.products_services[idx][field] = value;
        hasChanges = true;
    };

    window.removeProduct = function(idx) {
        if (!businessProfile.products_services) return;
        businessProfile.products_services.splice(idx, 1);
        hasChanges = true;
        renderBusinessProfile();
    };

    // Objections
    window.addObjection = function() {
        if (!businessProfile.common_objections) businessProfile.common_objections = [];
        businessProfile.common_objections.push({ objection: '', response: '' });
        hasChanges = true;
        renderBusinessProfile();
    };

    window.updateObjection = function(idx, field, value) {
        if (!businessProfile.common_objections) return;
        businessProfile.common_objections[idx][field] = value;
        hasChanges = true;
    };

    window.removeObjection = function(idx) {
        if (!businessProfile.common_objections) return;
        businessProfile.common_objections.splice(idx, 1);
        hasChanges = true;
        renderBusinessProfile();
    };

    // Competitors
    window.addCompetitor = function() {
        if (!businessProfile.competitors) businessProfile.competitors = [];
        businessProfile.competitors.push({ name: '', differentiator: '' });
        hasChanges = true;
        renderBusinessProfile();
    };

    window.updateCompetitor = function(idx, field, value) {
        if (!businessProfile.competitors) return;
        businessProfile.competitors[idx][field] = value;
        hasChanges = true;
    };

    window.removeCompetitor = function(idx) {
        if (!businessProfile.competitors) return;
        businessProfile.competitors.splice(idx, 1);
        hasChanges = true;
        renderBusinessProfile();
    };

    // Solutions
    window.addSolution = function() {
        if (!businessProfile.solutions_offered) businessProfile.solutions_offered = [];
        businessProfile.solutions_offered.push({ pain: '', solution: '' });
        hasChanges = true;
        renderBusinessProfile();
    };

    window.updateSolution = function(idx, field, value) {
        if (!businessProfile.solutions_offered) return;
        businessProfile.solutions_offered[idx][field] = value;
        hasChanges = true;
    };

    window.removeSolution = function(idx) {
        if (!businessProfile.solutions_offered) return;
        businessProfile.solutions_offered.splice(idx, 1);
        hasChanges = true;
        renderBusinessProfile();
    };

    // Testimonials
    window.addTestimonial = function() {
        if (!businessProfile.testimonials) businessProfile.testimonials = [];
        businessProfile.testimonials.push({ name: '', quote: '' });
        hasChanges = true;
        renderBusinessProfile();
    };

    window.updateTestimonial = function(idx, field, value) {
        if (!businessProfile.testimonials) return;
        businessProfile.testimonials[idx][field] = value;
        hasChanges = true;
    };

    window.removeTestimonial = function(idx) {
        if (!businessProfile.testimonials) return;
        businessProfile.testimonials.splice(idx, 1);
        hasChanges = true;
        renderBusinessProfile();
    };

    // Case Studies
    window.addCaseStudy = function() {
        if (!businessProfile.case_studies) businessProfile.case_studies = [];
        businessProfile.case_studies.push({ title: '', summary: '' });
        hasChanges = true;
        renderBusinessProfile();
    };

    window.updateCaseStudy = function(idx, field, value) {
        if (!businessProfile.case_studies) return;
        businessProfile.case_studies[idx][field] = value;
        hasChanges = true;
    };

    window.removeCaseStudy = function(idx) {
        if (!businessProfile.case_studies) return;
        businessProfile.case_studies.splice(idx, 1);
        hasChanges = true;
        renderBusinessProfile();
    };

    // ========================================
    // Save Profile
    // ========================================

    window.saveBusinessProfile = async function() {
        // Collect all field values
        const profileData = collectProfileData();

        try {
            const token = localStorage.getItem('auth_token');
            const response = await fetch('/api/sales-dashboard/business-profile', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(profileData)
            });

            if (response.ok) {
                const result = await response.json();
                businessProfile = result.profile || profileData;
                hasChanges = false;
                showNotification('Business profile saved successfully!', 'success');
            } else {
                throw new Error('Failed to save');
            }
        } catch (error) {
            console.error('Error saving business profile:', error);
            showNotification('Error saving business profile', 'error');
        }
    };

    /**
     * Collect all profile data from the form
     */
    function collectProfileData() {
        const data = { ...businessProfile };

        // Collect simple fields
        for (const section of Object.values(PROFILE_SECTIONS)) {
            for (const field of section.fields) {
                const el = document.getElementById(`bp-${field.key}`);
                if (el) {
                    if (field.type === 'number') {
                        data[field.key] = el.value ? parseFloat(el.value) : null;
                    } else {
                        data[field.key] = el.value || null;
                    }
                }

                // Handle multiselect
                if (field.type === 'multiselect') {
                    const checkboxes = document.querySelectorAll(`.bp-multiselect-${field.key}:checked`);
                    data[field.key] = Array.from(checkboxes).map(cb => cb.value);
                }
            }
        }

        return data;
    }

    // ========================================
    // Quick Setup Modal
    // ========================================

    window.showQuickSetupModal = function() {
        const modal = document.createElement('div');
        modal.id = 'quick-setup-modal';
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        modal.innerHTML = `
            <div class="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4">
                <div class="border-b px-6 py-4 flex justify-between items-center">
                    <h3 class="text-lg font-semibold">Quick Setup</h3>
                    <button onclick="closeQuickSetupModal()" class="text-gray-400 hover:text-gray-600">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div id="quick-setup-content" class="p-6">
                    <p class="text-gray-600 mb-4">Enter your company website URL and we'll analyze it to pre-fill your business profile.</p>
                    <div class="mb-4">
                        <label class="block text-sm font-medium text-gray-700 mb-1">Company Website</label>
                        <input type="url" id="quick-setup-url"
                            placeholder="https://www.yourcompany.com"
                            class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500">
                    </div>
                    <button onclick="runQuickSetup()" class="w-full bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
                        <i class="fas fa-magic mr-2"></i>Analyze Website
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    };

    window.closeQuickSetupModal = function() {
        const modal = document.getElementById('quick-setup-modal');
        if (modal) modal.remove();
    };

    window.runQuickSetup = async function() {
        const urlInput = document.getElementById('quick-setup-url');
        const url = urlInput?.value?.trim();

        if (!url) {
            showNotification('Please enter a website URL', 'error');
            return;
        }

        const content = document.getElementById('quick-setup-content');
        content.innerHTML = `
            <div class="text-center py-8">
                <i class="fas fa-spinner fa-spin text-4xl text-blue-600 mb-4"></i>
                <p class="text-gray-600">Analyzing your website...</p>
                <p class="text-sm text-gray-500 mt-2">This may take a moment</p>
            </div>
        `;

        try {
            const token = localStorage.getItem('auth_token');
            const response = await fetch('/api/sales-dashboard/scrape-profile', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ website_url: url })
            });

            if (response.ok) {
                const result = await response.json();
                showQuickSetupReview(result.profile_data);
            } else {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to analyze website');
            }
        } catch (error) {
            console.error('Quick setup error:', error);
            content.innerHTML = `
                <div class="text-center py-8 text-red-500">
                    <i class="fas fa-exclamation-circle text-4xl mb-4"></i>
                    <p>Error analyzing website</p>
                    <p class="text-sm mt-2">${escapeHtml(error.message)}</p>
                    <button onclick="closeQuickSetupModal(); showQuickSetupModal();"
                        class="mt-4 text-blue-600 hover:underline">Try Again</button>
                </div>
            `;
        }
    };

    /**
     * Show review screen for quick setup results
     */
    function showQuickSetupReview(profileData) {
        const content = document.getElementById('quick-setup-content');

        const fieldsToShow = [
            { key: 'company_name', label: 'Company Name' },
            { key: 'industry', label: 'Industry' },
            { key: 'elevator_pitch', label: 'Elevator Pitch' },
            { key: 'value_proposition', label: 'Value Proposition' }
        ];

        let fieldsHtml = '';
        for (const field of fieldsToShow) {
            const value = profileData[field.key];
            if (value) {
                fieldsHtml += `
                    <div class="mb-3">
                        <label class="block text-sm font-medium text-gray-700 mb-1">${field.label}</label>
                        <div class="bg-gray-50 p-2 rounded text-sm">${escapeHtml(value)}</div>
                    </div>
                `;
            }
        }

        content.innerHTML = `
            <div class="max-h-96 overflow-y-auto">
                <div class="flex items-center text-green-600 mb-4">
                    <i class="fas fa-check-circle text-2xl mr-2"></i>
                    <span class="font-medium">Website analyzed successfully!</span>
                </div>
                <p class="text-gray-600 mb-4">Here's what we found. Click "Apply" to fill in your profile.</p>
                ${fieldsHtml}
                ${profileData.products_services?.length ? `
                    <div class="mb-3">
                        <label class="block text-sm font-medium text-gray-700 mb-1">Products/Services Found</label>
                        <div class="bg-gray-50 p-2 rounded text-sm">${profileData.products_services.length} items</div>
                    </div>
                ` : ''}
            </div>
            <div class="flex gap-3 mt-4">
                <button onclick="closeQuickSetupModal()"
                    class="flex-1 border border-gray-300 px-4 py-2 rounded-lg hover:bg-gray-50">Cancel</button>
                <button onclick="applyQuickSetup()"
                    class="flex-1 bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700">
                    <i class="fas fa-check mr-2"></i>Apply
                </button>
            </div>
        `;

        // Store for apply
        window._quickSetupData = profileData;
    }

    window.applyQuickSetup = function() {
        const data = window._quickSetupData;
        if (!data) return;

        // Merge with existing profile
        for (const [key, value] of Object.entries(data)) {
            if (value !== null && value !== undefined && !key.startsWith('_')) {
                // Only overwrite if existing value is empty/null
                if (!businessProfile[key]) {
                    businessProfile[key] = value;
                }
            }
        }

        hasChanges = true;
        closeQuickSetupModal();
        renderBusinessProfile();
        showNotification('Profile data applied! Review and save your changes.', 'success');
    };

    // ========================================
    // Utilities
    // ========================================

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
        // Use global showNotification if available
        if (typeof window.showNotification === 'function' && window.showNotification !== showNotification) {
            window.showNotification(message, type);
        } else {
            // Fallback
            alert(message);
        }
    }

})();
