function runLCAAnalysis(fileId, fileName, lciaMethod) {
    const modal = document.getElementById('lcaAnalysisModal');
    const content = document.getElementById('lcaAnalysisContent');
    
    
    const methodInfo = lciaMethod ? `<br><small>📊 Method used: ${lciaMethod}</small>` : '';
    content.innerHTML = `
        <div class="lca-status-container">
            <div class="lca-status-icon">🔄</div>
            <div class="lca-status-text">Starting LCA analysis...</div>
            <div class="lca-status-details">Analysis file: ${fileName}${methodInfo}</div>
            <div class="lca-progress-bar">
                <div class="lca-progress"></div>
            </div>
            <div class="lca-status-timer">
                <small>Elapsed: <span id="analysisTimer">0</span> sec</small>
                <br>
                <small>💡 Background analysis mode — analysis continues even if you close the page...</small>
            </div>
        </div>
    `;
    
    modal.style.display = 'block';
    
    
    const requestBody = {};
    if (lciaMethod) {
        requestBody.lcia_method = lciaMethod;
        console.log(`🎯 [LCA Analysis] Using user-selected LCIA method: ${lciaMethod}`);
    }
    
    
    fetch(`/excel_file/${fileId}/run_lca_analysis_async`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            
            pollLCATaskStatus(data.task_id, fileId, fileName);
        } else {
            showLCAError(data.error, fileId, fileName);
        }
    })
    .catch(error => {
        console.error('Failed to start LCA analysis:', error);
        showLCAError('Failed to start analysis; please check network connection', fileId, fileName);
    });
}

function pollLCATaskStatus(taskId, fileId, fileName) {
    const content = document.getElementById('lcaAnalysisContent');
    let startTime = Date.now();
    
    
    const timerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        const timerElement = document.getElementById('analysisTimer');
        if (timerElement) {
            timerElement.textContent = elapsed;
        }
    }, 1000);
    
    
    function checkStatus() {
        fetch(`/lca_task/${taskId}/status`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const status = data.status;
                const progress = data.progress || 0;
                const duration = data.duration || 0;
                
                
                const stepInfo = data.step_name || 'Processing...';
                const currentStep = data.current_step || 0;
                const totalSteps = data.total_steps || 7;
                
                content.innerHTML = `
                    <div class="lca-status-container">
                        <div class="lca-status-icon">${status === 'completed' ? '✅' : status === 'failed' ? '❌' : '🔄'}</div>
                        <div class="lca-status-text">${getStatusText(status)}</div>
                        <div class="lca-status-details">
                            Analysis file: ${fileName}<br>
                            Task ID: ${taskId}<br>
                            <strong>Current step: ${stepInfo}</strong><br>
                            Progress: ${currentStep}/${totalSteps} steps (${progress}%)
                        </div>
                        <div class="lca-progress-bar">
                            <div class="lca-progress" style="width: ${progress}%"></div>
                        </div>
                        <div class="lca-step-indicator">
                            <small>📍 ${stepInfo}</small>
                        </div>
                        <div class="lca-status-timer">
                            <small>Elapsed: ${Math.floor(duration)} sec</small>
                            <br>
                            <small>💡 Background analysis in progress — you can safely close this window...</small>
                        </div>
                        ${status === 'completed' || status === 'failed' ? getCompletionActions(status, data, fileId, fileName) : ''}
                    </div>
                `;
                
                if (status === 'completed' || status === 'failed') {
                    clearInterval(timerInterval);
                    if (status === 'completed') {
                        
                        saveLCAResultToDB(fileId, data);
                    }
                } else {
                    
                    setTimeout(checkStatus, 3000); 
                }
            } else {
                clearInterval(timerInterval);
                if (data.error && data.error.includes('Task not found')) {
                    
                    checkLCACompletionInDB(fileId, fileName, timerInterval);
                } else {
                    showLCAError('Failed to get analysis status: ' + (data.error || 'Unknown error'), fileId, fileName);
                }
            }
        })
        .catch(error => {
            console.error('Failed to check status:', error);
            
            setTimeout(checkStatus, 5000); 
        });
    }
    
    
    setTimeout(checkStatus, 2000); 
}

function getStatusText(status) {
    const statusMap = {
        'queued': 'Queued, waiting for an available concurrency slot...',
        'running': 'Running LCA analysis...',
        'connecting': 'Connecting to openLCA...',
        'parsing': 'Parsing Excel file...',
        'creating_flows': 'Creating LCA flows...',
        'building_processes': 'Building process relationships...',
        'creating_system': 'Creating product system...',
        'running_assessment': 'Running impact assessment...',
        'saving_results': 'Saving results...',
        'completed': 'LCA analysis complete!',
        'failed': 'LCA analysis failed'
    };
    return statusMap[status] || 'Processing...';
}

function getCompletionActions(status, data, fileId, fileName) {
    if (status === 'completed') {
        const result = data.result;
        return `
            <div class="lca-completion-details">
                <p><strong>Analysis result summary:</strong></p>
                <ul>
                    <li>Analysis status: ${result?.success ? 'Success' : 'Failed'}</li>
                    <li>Duration: ${Math.floor(data.duration)} sec</li>
                </ul>
            </div>
            <div class="modal-actions">
                <button class="btn btn-primary" onclick="showLCAResults(${fileId})">View Detailed Results</button>
                <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">Close</button>
            </div>
        `;
    } else {
        return `
            <div class="lca-error-details">
                <p><strong>Error message:</strong></p>
                <p class="error-text">${data.error || 'Unknown error'}</p>
            </div>
            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">Close</button>
                <button class="btn btn-primary" onclick="closeLCAAnalysisModal(); runLCAAnalysis(${fileId}, '${fileName}')">Retry</button>
            </div>
        `;
    }
}

function showLCAError(errorMessage, fileId, fileName) {
    const content = document.getElementById('lcaAnalysisContent');
    content.innerHTML = `
        <div class="lca-status-container">
            <div class="lca-status-icon">❌</div>
            <div class="lca-status-text">Failed to start analysis</div>
            <div class="lca-status-details">
                <p class="error-text">${errorMessage}</p>
            </div>
            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">Close</button>
                <button class="btn btn-primary" onclick="closeLCAAnalysisModal(); runLCAAnalysis(${fileId}, '${fileName}')">Retry</button>
            </div>
        </div>
    `;
}

function saveLCAResultToDB(fileId, data) {
    
    
    console.log('LCA analysis complete, result:', data);
}

function checkLCACompletionInDB(fileId, fileName, timerInterval) {
    const content = document.getElementById('lcaAnalysisContent');
    
    
    content.innerHTML = `
        <div class="lca-status-container">
            <div class="lca-status-icon">🔍</div>
            <div class="lca-status-text">Checking analysis completion status...</div>
            <div class="lca-status-details">Querying LCA result records in the database...</div>
        </div>
    `;
    
    fetch(`/excel_file/${fileId}/check_lca_completion`)
    .then(response => response.json())
    .then(data => {
        if (data.success && data.has_results) {
            const result = data.latest_result;
            const statusIcon = result.status === 'completed' ? '✅' : result.status === 'failed' ? '❌' : '⏳';
            const statusText = result.status === 'completed' ? 'LCA analysis completed' : 
                              result.status === 'failed' ? 'LCA analysis failed' : 'LCA analysis status unknown';
            
            content.innerHTML = `
                <div class="lca-status-container">
                    <div class="lca-status-icon">${statusIcon}</div>
                    <div class="lca-status-text">${statusText}</div>
                    <div class="lca-status-details">
                        <p><strong>Information recovered from database record:</strong></p>
                        <ul style="text-align: left; display: inline-block;">
                            <li>Analysis status: ${result.status}</li>
                            <li>Created At: ${new Date(result.created_at).toLocaleString()}</li>
                            ${result.duration ? `<li>Duration: ${Math.floor(result.duration)} sec</li>` : ''}
                        </ul>
                    </div>
                    <div class="modal-actions">
                        ${result.status === 'completed' ? `<button class="btn btn-primary" onclick="showLCAResults(${fileId})">View Detailed Results</button>` : ''}
                        <button class="btn btn-warning" onclick="closeLCAAnalysisModal(); runLCAAnalysis(${fileId}, '${fileName}')">Re-analyze</button>
                        <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">Close</button>
                    </div>
                </div>
            `;
        } else {
            
            content.innerHTML = `
                <div class="lca-status-container">
                    <div class="lca-status-icon">⚠️</div>
                    <div class="lca-status-text">Task status lost</div>
                    <div class="lca-status-details">
                        <p>Task status was lost and no completed result was found in the database.</p>
                        <p><strong>Possible causes:</strong></p>
                        <ul style="text-align: left; display: inline-block;">
                            <li>Server restart caused in-memory task status to be lost</li>
                            <li>Analysis may still be running but status cannot be tracked</li>
                            <li>Analysis may have completed but was not saved to the database</li>
                        </ul>
                        <p><strong>Suggested actions:</strong></p>
                        <ul style="text-align: left; display: inline-block;">
                            <li>Check whether new models were created in openLCA</li>
                            <li>Re-run the analysis to ensure completion</li>
                        </ul>
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-primary" onclick="showLCAResults(${fileId})">View Historical Results</button>
                        <button class="btn btn-success" onclick="createManualLCAResult(${fileId})">Mark as Completed</button>
                        <button class="btn btn-warning" onclick="closeLCAAnalysisModal(); runLCAAnalysis(${fileId}, '${fileName}')">Re-analyze</button>
                        <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">Close</button>
                    </div>
                </div>
            `;
        }
    })
    .catch(error => {
        console.error('Failed to check completion status:', error);
        content.innerHTML = `
            <div class="lca-status-container">
                <div class="lca-status-icon">❌</div>
                <div class="lca-status-text">Check failed</div>
                <div class="lca-status-details">
                    <p>Unable to check analysis completion status: ${error.message}</p>
                </div>
                <div class="modal-actions">
                    <button class="btn btn-warning" onclick="closeLCAAnalysisModal(); runLCAAnalysis(${fileId}, '${fileName}')">Re-analyze</button>
                    <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">Close</button>
                </div>
            </div>
        `;
    });
}

function createManualLCAResult(fileId) {
    const content = document.getElementById('lcaAnalysisContent');
    
    content.innerHTML = `
        <div class="lca-status-container">
            <div class="lca-status-icon">⏳</div>
            <div class="lca-status-text">Creating LCA completion record...</div>
        </div>
    `;
    
    fetch(`/excel_file/${fileId}/create_manual_lca_result`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            content.innerHTML = `
                <div class="lca-status-container">
                    <div class="lca-status-icon">✅</div>
                    <div class="lca-status-text">LCA analysis marked as completed!</div>
                    <div class="lca-status-details">
                        <p>Successfully created LCA completion record.</p>
                        <p><strong>Record ID:</strong> ${data.result_id}</p>
                        <p>You can now view the LCA results.</p>
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-primary" onclick="showLCAResults(${fileId})">View LCA Results</button>
                        <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">Close</button>
                    </div>
                </div>
            `;
        } else {
            content.innerHTML = `
                <div class="lca-status-container">
                    <div class="lca-status-icon">❌</div>
                    <div class="lca-status-text">Failed to create record</div>
                    <div class="lca-status-details">
                        <p class="error-text">${data.error}</p>
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">Close</button>
                    </div>
                </div>
            `;
        }
    })
    .catch(error => {
        console.error('Failed to create LCA record:', error);
        content.innerHTML = `
            <div class="lca-status-container">
                <div class="lca-status-icon">❌</div>
                <div class="lca-status-text">Network error</div>
                <div class="lca-status-details">
                    <p class="error-text">Network error while creating record</p>
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">Close</button>
                </div>
            </div>
        `;
    });
}

function showLCAResults(fileId) {
    const modal = document.getElementById('lcaResultsModal');
    const content = document.getElementById('lcaResultsContent');
    
    
    content.innerHTML = `
        <div class="loading-container">
            <div class="loading-icon">⏳</div>
            <div class="loading-text">Loading LCA analysis results...</div>
        </div>
    `;
    
    modal.style.display = 'block';
    
    
    fetch(`/excel_file/${fileId}/lca_results`)
    .then(response => response.json())
    .then(data => {
        if (data.success && data.results.length > 0) {
            let html = '<div class="lca-results-container">';
            
            data.results.forEach((result, index) => {
                const statusIcon = {
                    'completed': '✅',
                    'failed': '❌',
                    'running': '🔄',
                    'pending': '⏳'
                }[result.status] || '❓';
                
                const statusText = {
                    'completed': 'Completed',
                    'failed': 'Failed',
                    'running': 'Running',
                    'pending': 'Pending'
                }[result.status] || 'Unknown';
                
                html += `
                    <div class="lca-result-card ${result.status}">
                        <div class="result-header">
                            <h4>${statusIcon} Analysis #${index + 1} - ${statusText}</h4>
                            <div class="result-time">
                                Start time: ${result.start_time || 'N/A'}<br>
                                ${result.end_time ? `End time: ${result.end_time}` : ''}
                            </div>
                        </div>
                        <div class="result-details">
                `;
                
                if (result.status === 'completed') {
                    html += `
                        <div class="success-details">
                            <p><strong>Analysis results:</strong></p>
                            <ul>
                                <li>Number of flows: ${result.flows_count || 'N/A'}</li>
                                <li>Number of processes: ${result.processes_count || 'N/A'}</li>
                                <li>Number of product systems: ${result.product_systems_count || 'N/A'}</li>
                                <li>Duration: ${result.duration_seconds ? result.duration_seconds.toFixed(2) + 'sec' : 'N/A'}</li>
                                <li>openLCA connection: ${result.openLCA_connected ? '✅ Connected' : '❌ Not connected'}</li>
                            </ul>
                            <div style="display: flex; gap: 10px; margin-top: 15px;">
                                <a href="/lca_result/${result.id}/visualization" class="btn btn-success btn-sm" target="_blank">📊 View Visualization Charts</a>
                                <button class="btn btn-info btn-sm" onclick="showLCAResultDetails(${result.id})">View Details</button>
                            </div>
                        </div>
                    `;
                } else if (result.status === 'failed') {
                    html += `
                        <div class="error-details">
                            <p><strong>Error message:</strong></p>
                            <p class="error-text">${result.error_message || 'Unknown error'}</p>
                        </div>
                    `;
                } else if (result.status === 'running') {
                    html += `
                        <div class="running-details">
                            <p>Analysis in progress, please wait...</p>
                            <button class="btn btn-secondary btn-sm" onclick="refreshLCAResults(${fileId})">Refresh Status</button>
                        </div>
                    `;
                }
                
                html += `
                        </div>
                    </div>
                `;
            });
            
            html += '</div>';
            content.innerHTML = html;
        } else {
            content.innerHTML = `
                <div class="no-results">
                    <div class="no-results-icon">📊</div>
                    <div class="no-results-text">No LCA analysis results</div>
                    <div class="no-results-details">This file has not been analyzed yet. Click "Run LCA Analysis" to start.</div>
                    <button class="btn btn-primary" onclick="closeLCAResultsModal(); runLCAAnalysis(${fileId}, 'Excel File')">Start LCA Analysis</button>
                </div>
            `;
        }
    })
    .catch(error => {
        console.error('Failed to get LCA results:', error);
        content.innerHTML = `
            <div class="error-container">
                <div class="error-icon">❌</div>
                <div class="error-text">Failed to get LCA analysis results</div>
                <div class="error-details">Please check network connection or retry later</div>
            </div>
        `;
    });
}

function showLCAResultDetails(resultId) {
    
    window.open(`/lca_result/${resultId}/visualization`, '_blank');
}

function refreshLCAResults(fileId) {
    showLCAResults(fileId);
}

function closeLCAAnalysisModal() {
    const modal = document.getElementById('lcaAnalysisModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function closeLCAResultsModal() {
    const modal = document.getElementById('lcaResultsModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function renderIpcPortStatus(queueStats) {
    const summaryEl = document.getElementById('lcaPortStatusSummary');
    const gridEl = document.getElementById('lcaPortStatusGrid');
    if (!summaryEl || !gridEl) {
        return;
    }

    if (!queueStats || !queueStats.success) {
        summaryEl.textContent = 'Failed to get port status; please retry later.';
        gridEl.innerHTML = '';
        return;
    }

    const total = queueStats.total_ipc_ports || 0;
    const healthy = queueStats.healthy_ports || 0;
    const running = queueStats.running_count || 0;
    const queued = queueStats.queued_count || 0;
    const checkedAt = queueStats.port_check_time || '-';

    summaryEl.innerHTML = `
        Total ${total} port(s), healthy ${healthy}, running tasks ${running}, queued ${queued}, 
        Last checked: ${checkedAt}
    `;

    const portStatus = Array.isArray(queueStats.port_status) ? queueStats.port_status : [];
    if (portStatus.length === 0) {
        gridEl.innerHTML = '<div class="lca-port-detail">No port status data</div>';
        return;
    }

    gridEl.innerHTML = portStatus.map((item) => {
        const reachable = !!item.reachable;
        const busy = !!item.busy;
        const statusText = reachable ? 'Reachable' : 'Unreachable';
        const busyText = busy ? 'Busy' : 'Idle';
        const errorText = item.error ? `<div class="lca-port-detail">Error: ${item.error}</div>` : '';
        return `
            <div class="lca-port-status-item ${reachable ? 'reachable' : 'unreachable'}">
                <div class="lca-port-title">IPC ${item.port}</div>
                <div class="lca-port-detail">Status: ${statusText}</div>
                <div class="lca-port-detail">Load: ${busyText}</div>
                <div class="lca-port-detail">Latency: ${item.latency_ms || 0} ms</div>
                ${errorText}
            </div>
        `;
    }).join('');
}

function fetchIpcPortStatus(forceCheck = false) {
    const summaryEl = document.getElementById('lcaPortStatusSummary');
    const gridEl = document.getElementById('lcaPortStatusGrid');
    if (!summaryEl || !gridEl) {
        return;
    }

    summaryEl.textContent = forceCheck ? 'Re-checking port connectivity...' : 'Loading port status...';
    const query = forceCheck ? '?force_check=1' : '';
    fetch(`/lca/queue/status${query}`)
        .then((response) => response.json())
        .then((data) => renderIpcPortStatus(data))
        .catch((error) => {
            console.error('Failed to get IPC port status:', error);
            summaryEl.textContent = 'Failed to get port status; please check the backend service.';
        });
}

function refreshIpcPortStatus() {
    fetchIpcPortStatus(true);
}

document.addEventListener('DOMContentLoaded', function() {
    
    window.onclick = function(event) {
        const analysisModal = document.getElementById('lcaAnalysisModal');
        const resultsModal = document.getElementById('lcaResultsModal');
        
        if (event.target == analysisModal) {
            closeLCAAnalysisModal();
        }
        if (event.target == resultsModal) {
            closeLCAResultsModal();
        }
    };

    
    if (document.getElementById('lcaPortStatusGrid')) {
        fetchIpcPortStatus(false);
        window.__lcaPortStatusTimer = window.setInterval(() => {
            fetchIpcPortStatus(false);
        }, 15000);
    }
});

function runLCAAnalysisWithMethod(fileId, fileName, lciaMethod) {
    return runLCAAnalysis(fileId, fileName, lciaMethod);
}

console.log('✅ LCA analysis JavaScript library loaded');
