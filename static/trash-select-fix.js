// Fix for Select All functionality in Trash view
(function() {
    console.log('Trash Select All Fix Loading...');
    
    // Function to select/deselect all checkboxes in trash
    window.selectAllTrash = function(checked) {
        console.log('Select All Trash:', checked);
        
        // Try multiple selectors for checkboxes
        const selectors = [
            'input[type="checkbox"].trash-checkbox',
            'input[type="checkbox"][data-email-id]',
            '.trash-item input[type="checkbox"]',
            '.email-checkbox',
            'input.checkbox',
            'input[type="checkbox"]'
        ];
        
        let checkboxes = null;
        for (const selector of selectors) {
            checkboxes = document.querySelectorAll(selector);
            if (checkboxes.length > 0) {
                console.log(`Found ${checkboxes.length} checkboxes with selector: ${selector}`);
                break;
            }
        }
        
        if (!checkboxes || checkboxes.length === 0) {
            console.error('No checkboxes found in trash view');
            return;
        }
        
        // Update all checkboxes
        checkboxes.forEach(function(checkbox) {
            // Skip the "select all" checkbox itself
            if (checkbox.id !== 'select-all' && checkbox.id !== 'selectAll') {
                checkbox.checked = checked;
                // Trigger change event in case there are listeners
                const event = new Event('change', { bubbles: true });
                checkbox.dispatchEvent(event);
            }
        });
        
        // Update count if there's a count display
        updateSelectedCount();
    };
    
    // Function to update selected count
    window.updateSelectedCount = function() {
        const checkboxes = document.querySelectorAll('input[type="checkbox"]:not(#select-all):not(#selectAll)');
        const checked = document.querySelectorAll('input[type="checkbox"]:not(#select-all):not(#selectAll):checked');
        
        // Try to find count display element
        const countElements = [
            document.getElementById('selected-count'),
            document.getElementById('trash-count'),
            document.querySelector('.selected-count'),
            document.querySelector('.trash-count')
        ];
        
        for (const element of countElements) {
            if (element) {
                element.textContent = `${checked.length} of ${checkboxes.length} selected`;
                break;
            }
        }
        
        console.log(`Selected: ${checked.length} of ${checkboxes.length}`);
    };
    
    // Hook into existing select all checkbox if it exists
    function attachSelectAllHandler() {
        const selectAllCheckbox = document.getElementById('select-all') || 
                                 document.getElementById('selectAll') ||
                                 document.querySelector('.select-all-checkbox');
        
        if (selectAllCheckbox) {
            console.log('Found select all checkbox, attaching handler');
            selectAllCheckbox.removeEventListener('change', handleSelectAll);
            selectAllCheckbox.addEventListener('change', handleSelectAll);
        }
    }
    
    function handleSelectAll(event) {
        window.selectAllTrash(event.target.checked);
    }
    
    // Try to attach immediately
    attachSelectAllHandler();
    
    // Also try after DOM is fully loaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', attachSelectAllHandler);
    }
    
    // Also watch for dynamic content changes
    const observer = new MutationObserver(function(mutations) {
        // Check if select all checkbox was added
        const selectAll = document.getElementById('select-all') || 
                         document.getElementById('selectAll');
        if (selectAll && !selectAll.hasAttribute('data-handler-attached')) {
            attachSelectAllHandler();
            selectAll.setAttribute('data-handler-attached', 'true');
        }
    });
    
    // Start observing
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
    
    console.log('Trash Select All Fix Loaded');
    
    // Make functions globally available
    window.trashSelectFix = {
        selectAll: window.selectAllTrash,
        updateCount: window.updateSelectedCount,
        attach: attachSelectAllHandler
    };
})();