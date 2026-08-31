document.addEventListener('DOMContentLoaded', function() {
    
    initFlashMessages();
    initFormValidation();
    initProjectActions();
});

function initFlashMessages() {
    const flashMessages = document.querySelectorAll('.flash-message');
    
    flashMessages.forEach(message => {
        
        setTimeout(() => {
            message.style.opacity = '0';
            setTimeout(() => {
                message.remove();
            }, 300);
        }, 3000);
        
        
        message.addEventListener('click', function() {
            this.style.opacity = '0';
            setTimeout(() => {
                this.remove();
            }, 300);
        });
    });
}

function initFormValidation() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        
        const formId = form.getAttribute('id');
        if (formId === 'deleteForm' || formId === 'deleteProjectForm') {
            console.log('⏭️ 跳过删除表单的验证:', formId);
            return;
        }
        
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let isValid = true;
            
            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    isValid = false;
                    field.classList.add('error');
                    
                    
                    showFieldError(field, '此字段为必填项');
                } else {
                    field.classList.remove('error');
                    clearFieldError(field);
                }
            });
            
            if (!isValid) {
                e.preventDefault();
                showNotification('请填写所有必填字段', 'error');
            }
        });
    });
}

function showFieldError(field, message) {
    
    clearFieldError(field);
    
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'field-error';
    errorDiv.textContent = message;
    errorDiv.style.color = '#e74c3c';
    errorDiv.style.fontSize = '0.8rem';
    errorDiv.style.marginTop = '0.25rem';
    
    
    field.parentNode.appendChild(errorDiv);
}

function clearFieldError(field) {
    const existingError = field.parentNode.querySelector('.field-error');
    if (existingError) {
        existingError.remove();
    }
}

function initProjectActions() {
    
    const deleteButtons = document.querySelectorAll('[data-action="delete-project"]');
    
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            
            const projectName = this.getAttribute('data-project-name');
            if (confirm(`确定要删除项目 "${projectName}" 吗？此操作不可撤销。`)) {
                
                const form = document.createElement('form');
                form.method = 'POST';
                form.action = this.getAttribute('data-delete-url');
                
                const csrfInput = document.createElement('input');
                csrfInput.type = 'hidden';
                csrfInput.name = 'csrf_token';
                csrfInput.value = getCSRFToken();
                
                form.appendChild(csrfInput);
                document.body.appendChild(form);
                form.submit();
            }
        });
    });
}

function getCSRFToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    return metaTag ? metaTag.getAttribute('content') : '';
}

function showNotification(message, type = 'info') {
    
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    
    notification.style.position = 'fixed';
    notification.style.top = '20px';
    notification.style.right = '20px';
    notification.style.padding = '1rem 1.5rem';
    notification.style.borderRadius = '5px';
    notification.style.color = 'white';
    notification.style.fontWeight = '500';
    notification.style.zIndex = '1000';
    notification.style.maxWidth = '300px';
    notification.style.boxShadow = '0 4px 6px rgba(0,0,0,0.1)';
    
    
    switch(type) {
        case 'success':
            notification.style.backgroundColor = '#27ae60';
            break;
        case 'error':
            notification.style.backgroundColor = '#e74c3c';
            break;
        case 'warning':
            notification.style.backgroundColor = '#f39c12';
            break;
        default:
            notification.style.backgroundColor = '#3498db';
    }
    
    
    document.body.appendChild(notification);
    
    
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            notification.remove();
        }, 300);
    }, 3000);
    
    
    notification.style.transition = 'all 0.3s ease';
}

function initTableSorting() {
    const tables = document.querySelectorAll('.data-table table');
    
    tables.forEach(table => {
        const headers = table.querySelectorAll('th[data-sortable]');
        
        headers.forEach(header => {
            header.addEventListener('click', function() {
                const column = this.cellIndex;
                const rows = Array.from(table.querySelectorAll('tbody tr'));
                const isAscending = this.classList.contains('sort-asc');
                
                
                rows.sort((a, b) => {
                    const aValue = a.cells[column].textContent.trim();
                    const bValue = b.cells[column].textContent.trim();
                    
                    if (isAscending) {
                        return bValue.localeCompare(aValue);
                    } else {
                        return aValue.localeCompare(bValue);
                    }
                });
                
                
                const tbody = table.querySelector('tbody');
                rows.forEach(row => tbody.appendChild(row));
                
                
                headers.forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
                this.classList.add(isAscending ? 'sort-desc' : 'sort-asc');
            });
        });
    });
}

function initSearch() {
    const searchInputs = document.querySelectorAll('.search-input');
    
    searchInputs.forEach(input => {
        input.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            const targetSelector = this.getAttribute('data-search-target');
            const targetElements = document.querySelectorAll(targetSelector);
            
            targetElements.forEach(element => {
                const text = element.textContent.toLowerCase();
                if (text.includes(searchTerm)) {
                    element.style.display = '';
                } else {
                    element.style.display = 'none';
                }
            });
        });
    });
}

function exportData(format = 'csv') {
    const table = document.querySelector('.data-table table');
    if (!table) return;
    
    const rows = Array.from(table.querySelectorAll('tr'));
    let data = '';
    
    if (format === 'csv') {
        rows.forEach(row => {
            const cells = Array.from(row.querySelectorAll('th, td'));
            const rowData = cells.map(cell => `"${cell.textContent.trim()}"`).join(',');
            data += rowData + '\n';
        });
        
        
        const blob = new Blob([data], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'lca_data.csv';
        a.click();
        window.URL.revokeObjectURL(url);
    }
}

window.showNotification = showNotification;
window.exportData = exportData;
