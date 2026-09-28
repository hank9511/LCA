window.LCA_DEBUG = window.LCA_DEBUG || false;

function debugLog(message, data = null) {
    if (window.LCA_DEBUG) {
        if (data) {
            console.log(`[LCA Progress] ${message}`, data);
        } else {
            console.log(`[LCA Progress] ${message}`);
        }
    }
}

const LCA_STEPS = [
    {
        id: 1,
        name: "Connect openLCA",
        description: "Connecting to openLCA software...",
        icon: "🔌"
    },
    {
        id: 2,
        name: "Parse Data",
        description: "Parsing LCA data from Excel file...",
        icon: "📊"
    },
    {
        id: 3,
        name: "Create Flows",
        description: "Creating flows and processes in openLCA...",
        icon: "🔄"
    },
    {
        id: 4,
        name: "Build System",
        description: "Building product system model...",
        icon: "🏗️"
    },
    {
        id: 5,
        name: "Calculate",
        description: "Running LCA calculation...",
        icon: "⚙️"
    },
    {
        id: 6,
        name: "Assess Impacts",
        description: "Performing environmental impact assessment...",
        icon: "🌍"
    },
    {
        id: 7,
        name: "Generate Results",
        description: "Organizing and saving analysis results...",
        icon: "✨"
    }
];

function createEnhancedLCAProgressUI(fileName) {
    return `
        <div class="lca-status-container">
            <div class="lca-status-icon">🔄</div>
            <div class="lca-status-text">LCA analysis in progress</div>
            <div class="lca-status-details">Analysis file: ${fileName}</div>
            
            <!-- Progress information -->
            <div class="lca-progress-info">
                <span class="lca-progress-percentage" id="progressPercentage">0%</span>
                <span class="lca-progress-eta" id="progressETA">Estimated time remaining: calculating...</span>
            </div>
            
            <!-- Progress bar -->
            <div class="lca-progress-bar">
                <div class="lca-progress" id="progressBar" style="width: 0%"></div>
            </div>
            
            <!-- Step list -->
            <div class="lca-steps-list" id="stepsContainer">
                ${LCA_STEPS.map(step => `
                    <div class="lca-step-item pending" id="step-${step.id}">
                        <div class="lca-step-icon">${step.icon}</div>
                        <div class="lca-step-content">
                            <div class="lca-step-title">${step.name}</div>
                            <div class="lca-step-description">${step.description}</div>
                        </div>
                        <div class="lca-step-status pending">Pending</div>
                    </div>
                `).join('')}
            </div>
            
            <!-- Timer -->
            <div class="lca-status-timer">
                <small>Elapsed: <span id="analysisTimer">0</span> sec</small>
                <br>
                <small>💡 Background analysis mode — you can safely close this window</small>
                <br>
                <small style="color: #999; cursor: pointer;" onclick="window.LCA_DEBUG = !window.LCA_DEBUG; alert(window.LCA_DEBUG ? '✅ Debug mode enabled; check the browser console' : '❌ Debug mode disabled');">
                    🔧 Click to toggle debug mode
                </small>
            </div>
            
            <!-- Debug panel (shown only in debug mode) -->
            <div id="debugInfo" style="display: none; margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 5px; font-size: 12px; text-align: left;">
                <strong>🔍 Debug info:</strong>
                <pre id="debugContent" style="margin: 5px 0; white-space: pre-wrap; font-family: monospace; font-size: 11px;"></pre>
            </div>
        </div>
    `;
}

function updateProgress(progress, currentStep = 0, totalSteps = 7) {
    const progressBar = document.getElementById('progressBar');
    const progressPercentage = document.getElementById('progressPercentage');
    
    if (progressBar && progressPercentage) {
        
        progressBar.style.width = progress + '%';
        progressPercentage.textContent = Math.round(progress) + '%';
    }
}

function updateStepStatus(stepNumber, status) {
    const stepElement = document.getElementById(`step-${stepNumber}`);
    if (!stepElement) return;
    
    
    stepElement.classList.remove('pending', 'active', 'completed');
    
    
    stepElement.classList.add(status);
    
    
    const statusBadge = stepElement.querySelector('.lca-step-status');
    if (statusBadge) {
        statusBadge.className = `lca-step-status ${status}`;
        
        if (status === 'completed') {
            statusBadge.textContent = 'Completed';
            
            const iconElement = stepElement.querySelector('.lca-step-icon');
            if (iconElement) {
                iconElement.textContent = '✅';
                iconElement.classList.add('completed');
            }
        } else if (status === 'active') {
            statusBadge.textContent = 'In Progress';
        } else {
            statusBadge.textContent = 'Pending';
        }
    }
}

function getStepIdByName(stepName) {
    if (!stepName) return 0;
    
    
    const stepNumberMatch = stepName.match(/step\s*(\d+)/i);
    if (stepNumberMatch) {
        const stepNum = parseInt(stepNumberMatch[1]);
        if (stepNum >= 1 && stepNum <= 7) {
            console.log(`✅ Extracted step number from "${stepName}": ${stepNum}`);
            return stepNum;
        }
    }
    
    
    const keywords = {
        
        'Connect': 1,
        'connect': 1,
        'connection': 1,
        'ipc': 1,
        'openlca': 1,
        
        
        'Parse': 2,
        'pars': 2,
        'parse': 2,
        'read': 2,
        'excel': 2,
        
        
        'Flow': 3,
        'flow': 3,
        'creating flow': 3,
        'create flow': 3,
        
        
        'System': 4,
        'system': 4,
        'product system': 4,
        'building system': 4,
        
        
        'Calc': 5,
        'calculat': 5,
        'calculate': 5,
        'computing': 5,
        
        
        'Impact': 6,
        'impact': 6,
        'Assess': 6,
        'assess': 6,
        'lcia': 6,
        
        
        'Result': 7,
        'result': 7,
        'generat': 7,
        'saving': 7,
        'save': 7
    };
    
    const lowerStepName = stepName.toLowerCase();
    
    for (const [keyword, stepId] of Object.entries(keywords)) {
        if (lowerStepName.includes(keyword.toLowerCase())) {
            console.log(`✅ Identified step via keyword "${keyword}" from "${stepName}": ${stepId}`);
            return stepId;
        }
    }
    
    console.warn(`⚠️ Unrecognized step name: "${stepName}"`);
    return 0; 
}

function calculateETA(elapsedSeconds, progress) {
    if (progress <= 0) return 'Calculating...';
    
    const totalEstimated = (elapsedSeconds / progress) * 100;
    const remaining = totalEstimated - elapsedSeconds;
    
    if (remaining < 60) {
        return `About ${Math.round(remaining)} sec`;
    } else if (remaining < 3600) {
        return `About ${Math.round(remaining / 60)} min`;
    } else {
        return `About ${(remaining / 3600).toFixed(1)} hr`;
    }
}

function updateETA(elapsedSeconds, progress) {
    const etaElement = document.getElementById('progressETA');
    if (etaElement && progress > 0) {
        const eta = calculateETA(elapsedSeconds, progress);
        etaElement.textContent = `Estimated time remaining: ${eta}`;
    }
}

function pollLCATaskStatusEnhanced(taskId, fileId, fileName) {
    const content = document.getElementById('lcaAnalysisContent');
    const startTime = Date.now();
    
    
    content.innerHTML = createEnhancedLCAProgressUI(fileName);
    
    
    const timerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        const timerElement = document.getElementById('analysisTimer');
        if (timerElement) {
            timerElement.textContent = elapsed;
        }
    }, 1000);
    
    let lastStepId = 0;
    
    
    function checkStatus() {
        fetch(`/lca_task/${taskId}/status`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const status = data.status;
                const progress = data.progress || 0;
                const currentStep = data.current_step || 0;
                const totalSteps = data.total_steps || 7;
                const stepName = data.step_name || '';
                const elapsedSeconds = Math.floor((Date.now() - startTime) / 1000);
                
                
                debugLog('Received backend status update', {
                    status,
                    progress,
                    currentStep,
                    totalSteps,
                    stepName,
                    elapsedSeconds
                });
                
                
                updateDebugInfo({
                    Backend status: status,
                    Progress percent: progress + '%',
                    Current step number: currentStep,
                    Total steps: totalSteps,
                    Step name: stepName,
                    Elapsed time: elapsedSeconds + 'sec',
                    Last detected step: lastStepId,
                    Poll count: checkStatus.callCount || 0
                });
                checkStatus.callCount = (checkStatus.callCount || 0) + 1;
                
                
                updateProgress(progress, currentStep, totalSteps);
                
                
                updateETA(elapsedSeconds, progress);
                
                
                const detectedStepId = getStepIdByName(stepName);
                
                if (detectedStepId > 0) {
                    console.log(`🎯 Step change detected: ${lastStepId} → ${detectedStepId}`);
                    
                    
                    if (detectedStepId > lastStepId + 1) {
                        console.log(`⚡ Step jump detected; auto-completing intermediate steps ${lastStepId + 1} to ${detectedStepId - 1}`);
                        for (let i = lastStepId + 1; i < detectedStepId; i++) {
                            updateStepStatus(i, 'completed');
                            
                            setTimeout(() => {}, i * 100);
                        }
                    }
                    
                    
                    for (let i = 1; i < detectedStepId; i++) {
                        const stepElement = document.getElementById(`step-${i}`);
                        if (stepElement && !stepElement.classList.contains('completed')) {
                            updateStepStatus(i, 'completed');
                        }
                    }
                    
                    
                    if (detectedStepId !== lastStepId) {
                        updateStepStatus(detectedStepId, 'active');
                        lastStepId = detectedStepId;
                        console.log(`✅ Active step updated to: ${detectedStepId}`);
                    }
                } else {
                    
                    if (currentStep > 0 && currentStep !== lastStepId) {
                        console.log(`🔄 Using step number from backend: ${currentStep}`);
                        
                        
                        for (let i = lastStepId + 1; i < currentStep; i++) {
                            updateStepStatus(i, 'completed');
                        }
                        
                        updateStepStatus(currentStep, 'active');
                        lastStepId = currentStep;
                    }
                }
                
                
                if (status === 'completed') {
                    clearInterval(timerInterval);
                    
                    for (let i = 1; i <= 7; i++) {
                        updateStepStatus(i, 'completed');
                    }
                    updateProgress(100);
                    
                    
                    setTimeout(() => {
                        handleAnalysisComplete(data, elapsedSeconds, fileId);
                    }, 1000);
                    
                } else if (status === 'failed') {
                    clearInterval(timerInterval);
                    handleAnalysisError(data, fileId, fileName);
                } else {
                    
                    setTimeout(checkStatus, 2000); 
                }
            } else {
                
                if (data.error && data.error.includes('Task not found')) {
                    clearInterval(timerInterval);
                    checkLCACompletionInDB(fileId, fileName, timerInterval);
                } else {
                    console.error('Failed to get status:', data.error);
                    setTimeout(checkStatus, 3000); 
                }
            }
        })
        .catch(error => {
            console.error('Failed to check status:', error);
            setTimeout(checkStatus, 5000); 
        });
    }
    
    
    setTimeout(checkStatus, 1500);
}

function handleAnalysisComplete(data, responseTime, fileId) {
    const content = document.getElementById('lcaAnalysisContent');
    const result = data.result;
    
    content.innerHTML = `
        <div class="lca-status-container">
            <div class="lca-status-icon">✅</div>
            <div class="lca-status-text">LCA analysis complete!</div>
            <div class="lca-status-details">
                <p><strong>Analysis result summary:</strong></p>
                <ul>
                    <li>Analysis status: ${result?.success ? 'Success' : 'Failed'}</li>
                    <li>Duration: ${Math.floor(responseTime)} sec</li>
                    <li>Flows: ${data.flows_count || 'N/A'}</li>
                    <li>Processes: ${data.processes_count || 'N/A'}</li>
                </ul>
            </div>
            <div class="modal-actions">
                <button class="btn btn-primary" onclick="showLCAResults(${fileId})">View Detailed Results</button>
                <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">Close</button>
            </div>
        </div>
    `;
    
    
    setTimeout(() => {
        location.reload();
    }, 3000);
}

function handleAnalysisError(data, fileId, fileName) {
    const content = document.getElementById('lcaAnalysisContent');
    
    content.innerHTML = `
        <div class="lca-status-container">
            <div class="lca-status-icon">❌</div>
            <div class="lca-status-text">LCA analysis failed</div>
            <div class="lca-status-details">
                <p class="error-text">${data.error || 'Unknown error'}</p>
                <p style="margin-top: 15px;">Please check:</p>
                <ul style="text-align: left; display: inline-block;">
                    <li>Whether openLCA software is running</li>
                    <li>Whether the IPC server is enabled</li>
                    <li>Whether the Excel data format is correct</li>
                </ul>
            </div>
            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">Close</button>
                <button class="btn btn-primary" onclick="closeLCAAnalysisModal(); runLCAAnalysis(${fileId}, '${fileName}')">Retry</button>
            </div>
        </div>
    `;
}

function updateDebugInfo(info) {
    const debugContent = document.getElementById('debugContent');
    const debugInfo = document.getElementById('debugInfo');
    
    if (debugContent && window.LCA_DEBUG) {
        
        const formattedInfo = Object.entries(info)
            .map(([key, value]) => `${key}: ${value}`)
            .join('\n');
        
        debugContent.textContent = formattedInfo;
        
        
        if (debugInfo) {
            debugInfo.style.display = 'block';
        }
    } else if (debugInfo && !window.LCA_DEBUG) {
        
        debugInfo.style.display = 'none';
    }
}

window.pollLCATaskStatusEnhanced = pollLCATaskStatusEnhanced;
window.createEnhancedLCAProgressUI = createEnhancedLCAProgressUI;
window.updateDebugInfo = updateDebugInfo;
