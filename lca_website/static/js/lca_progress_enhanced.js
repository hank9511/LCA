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
        name: "连接openLCA",
        description: "正在连接到openLCA软件...",
        icon: "🔌"
    },
    {
        id: 2,
        name: "解析数据",
        description: "解析Excel文件中的LCA数据...",
        icon: "📊"
    },
    {
        id: 3,
        name: "创建流程",
        description: "在openLCA中创建物质流和过程...",
        icon: "🔄"
    },
    {
        id: 4,
        name: "建立系统",
        description: "构建产品系统模型...",
        icon: "🏗️"
    },
    {
        id: 5,
        name: "计算分析",
        description: "运行LCA计算分析...",
        icon: "⚙️"
    },
    {
        id: 6,
        name: "评估影响",
        description: "进行环境影响评估...",
        icon: "🌍"
    },
    {
        id: 7,
        name: "生成结果",
        description: "整理和保存分析结果...",
        icon: "✨"
    }
];

function createEnhancedLCAProgressUI(fileName) {
    return `
        <div class="lca-status-container">
            <div class="lca-status-icon">🔄</div>
            <div class="lca-status-text">正在进行LCA分析</div>
            <div class="lca-status-details">分析文件: ${fileName}</div>
            
            <!-- 进度信息 -->
            <div class="lca-progress-info">
                <span class="lca-progress-percentage" id="progressPercentage">0%</span>
                <span class="lca-progress-eta" id="progressETA">预计剩余时间: 计算中...</span>
            </div>
            
            <!-- 进度条 -->
            <div class="lca-progress-bar">
                <div class="lca-progress" id="progressBar" style="width: 0%"></div>
            </div>
            
            <!-- 步骤列表 -->
            <div class="lca-steps-list" id="stepsContainer">
                ${LCA_STEPS.map(step => `
                    <div class="lca-step-item pending" id="step-${step.id}">
                        <div class="lca-step-icon">${step.icon}</div>
                        <div class="lca-step-content">
                            <div class="lca-step-title">${step.name}</div>
                            <div class="lca-step-description">${step.description}</div>
                        </div>
                        <div class="lca-step-status pending">等待中</div>
                    </div>
                `).join('')}
            </div>
            
            <!-- 计时器 -->
            <div class="lca-status-timer">
                <small>已用时: <span id="analysisTimer">0</span> 秒</small>
                <br>
                <small>💡 采用后台分析模式，您可以安全关闭此窗口</small>
                <br>
                <small style="color: #999; cursor: pointer;" onclick="window.LCA_DEBUG = !window.LCA_DEBUG; alert(window.LCA_DEBUG ? '✅ 调试模式已启用，请查看浏览器控制台' : '❌ 调试模式已关闭');">
                    🔧 点击切换调试模式
                </small>
            </div>
            
            <!-- 调试信息面板（仅在调试模式下显示） -->
            <div id="debugInfo" style="display: none; margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 5px; font-size: 12px; text-align: left;">
                <strong>🔍 调试信息：</strong>
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
            statusBadge.textContent = '已完成';
            
            const iconElement = stepElement.querySelector('.lca-step-icon');
            if (iconElement) {
                iconElement.textContent = '✅';
                iconElement.classList.add('completed');
            }
        } else if (status === 'active') {
            statusBadge.textContent = '进行中';
        } else {
            statusBadge.textContent = '等待中';
        }
    }
}

function getStepIdByName(stepName) {
    if (!stepName) return 0;
    
    
    const stepNumberMatch = stepName.match(/step\s*(\d+)/i);
    if (stepNumberMatch) {
        const stepNum = parseInt(stepNumberMatch[1]);
        if (stepNum >= 1 && stepNum <= 7) {
            console.log(`✅ 从"${stepName}"中提取到步骤编号: ${stepNum}`);
            return stepNum;
        }
    }
    
    
    const keywords = {
        
        '连接': 1,
        'connect': 1,
        'connection': 1,
        'ipc': 1,
        'openlca': 1,
        
        
        '解析': 2,
        'pars': 2,
        'parse': 2,
        'read': 2,
        'excel': 2,
        
        
        '流程': 3,
        'flow': 3,
        'creating flow': 3,
        'create flow': 3,
        
        
        '系统': 4,
        'system': 4,
        'product system': 4,
        'building system': 4,
        
        
        '计算': 5,
        'calculat': 5,
        'calculate': 5,
        'computing': 5,
        
        
        '影响': 6,
        'impact': 6,
        '评估': 6,
        'assess': 6,
        'lcia': 6,
        
        
        '结果': 7,
        'result': 7,
        'generat': 7,
        'saving': 7,
        'save': 7
    };
    
    const lowerStepName = stepName.toLowerCase();
    
    for (const [keyword, stepId] of Object.entries(keywords)) {
        if (lowerStepName.includes(keyword.toLowerCase())) {
            console.log(`✅ 通过关键词"${keyword}"从"${stepName}"中识别到步骤: ${stepId}`);
            return stepId;
        }
    }
    
    console.warn(`⚠️ 无法识别步骤名称: "${stepName}"`);
    return 0; 
}

function calculateETA(elapsedSeconds, progress) {
    if (progress <= 0) return '计算中...';
    
    const totalEstimated = (elapsedSeconds / progress) * 100;
    const remaining = totalEstimated - elapsedSeconds;
    
    if (remaining < 60) {
        return `约 ${Math.round(remaining)} 秒`;
    } else if (remaining < 3600) {
        return `约 ${Math.round(remaining / 60)} 分钟`;
    } else {
        return `约 ${(remaining / 3600).toFixed(1)} 小时`;
    }
}

function updateETA(elapsedSeconds, progress) {
    const etaElement = document.getElementById('progressETA');
    if (etaElement && progress > 0) {
        const eta = calculateETA(elapsedSeconds, progress);
        etaElement.textContent = `预计剩余时间: ${eta}`;
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
                
                
                debugLog('收到后端状态更新', {
                    status,
                    progress,
                    currentStep,
                    totalSteps,
                    stepName,
                    elapsedSeconds
                });
                
                
                updateDebugInfo({
                    后端状态: status,
                    进度百分比: progress + '%',
                    当前步骤编号: currentStep,
                    总步骤数: totalSteps,
                    步骤名称: stepName,
                    已用时间: elapsedSeconds + '秒',
                    上次识别步骤: lastStepId,
                    轮询次数: checkStatus.callCount || 0
                });
                checkStatus.callCount = (checkStatus.callCount || 0) + 1;
                
                
                updateProgress(progress, currentStep, totalSteps);
                
                
                updateETA(elapsedSeconds, progress);
                
                
                const detectedStepId = getStepIdByName(stepName);
                
                if (detectedStepId > 0) {
                    console.log(`🎯 检测到步骤变化: ${lastStepId} → ${detectedStepId}`);
                    
                    
                    if (detectedStepId > lastStepId + 1) {
                        console.log(`⚡ 检测到步骤跳跃，自动补全中间步骤 ${lastStepId + 1} 到 ${detectedStepId - 1}`);
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
                        console.log(`✅ 当前活动步骤更新为: ${detectedStepId}`);
                    }
                } else {
                    
                    if (currentStep > 0 && currentStep !== lastStepId) {
                        console.log(`🔄 使用后端返回的步骤编号: ${currentStep}`);
                        
                        
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
                    console.error('获取状态失败:', data.error);
                    setTimeout(checkStatus, 3000); 
                }
            }
        })
        .catch(error => {
            console.error('检查状态失败:', error);
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
            <div class="lca-status-text">LCA分析完成！</div>
            <div class="lca-status-details">
                <p><strong>分析结果摘要：</strong></p>
                <ul>
                    <li>分析状态: ${result?.success ? '成功' : '失败'}</li>
                    <li>分析耗时: ${Math.floor(responseTime)} 秒</li>
                    <li>物质流: ${data.flows_count || 'N/A'} 个</li>
                    <li>过程: ${data.processes_count || 'N/A'} 个</li>
                </ul>
            </div>
            <div class="modal-actions">
                <button class="btn btn-primary" onclick="showLCAResults(${fileId})">查看详细结果</button>
                <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">关闭</button>
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
            <div class="lca-status-text">LCA分析失败</div>
            <div class="lca-status-details">
                <p class="error-text">${data.error || '未知错误'}</p>
                <p style="margin-top: 15px;">请检查：</p>
                <ul style="text-align: left; display: inline-block;">
                    <li>openLCA软件是否正在运行</li>
                    <li>IPC服务器是否已启用</li>
                    <li>Excel数据格式是否正确</li>
                </ul>
            </div>
            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">关闭</button>
                <button class="btn btn-primary" onclick="closeLCAAnalysisModal(); runLCAAnalysis(${fileId}, '${fileName}')">重试</button>
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
