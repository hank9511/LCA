function runLCAAnalysis(fileId, fileName, lciaMethod) {
    const modal = document.getElementById('lcaAnalysisModal');
    const content = document.getElementById('lcaAnalysisContent');
    
    
    const methodInfo = lciaMethod ? `<br><small>📊 使用方法: ${lciaMethod}</small>` : '';
    content.innerHTML = `
        <div class="lca-status-container">
            <div class="lca-status-icon">🔄</div>
            <div class="lca-status-text">正在启动LCA分析...</div>
            <div class="lca-status-details">分析文件: ${fileName}${methodInfo}</div>
            <div class="lca-progress-bar">
                <div class="lca-progress"></div>
            </div>
            <div class="lca-status-timer">
                <small>已用时: <span id="analysisTimer">0</span> 秒</small>
                <br>
                <small>💡 采用后台分析模式，即使页面关闭分析也会继续运行...</small>
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
        console.error('启动LCA分析失败:', error);
        showLCAError('启动分析失败，请检查网络连接', fileId, fileName);
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
                            分析文件: ${fileName}<br>
                            任务ID: ${taskId}<br>
                            <strong>当前步骤: ${stepInfo}</strong><br>
                            进度: ${currentStep}/${totalSteps} 步骤 (${progress}%)
                        </div>
                        <div class="lca-progress-bar">
                            <div class="lca-progress" style="width: ${progress}%"></div>
                        </div>
                        <div class="lca-step-indicator">
                            <small>📍 ${stepInfo}</small>
                        </div>
                        <div class="lca-status-timer">
                            <small>已用时: ${Math.floor(duration)} 秒</small>
                            <br>
                            <small>💡 后台分析中，您可以安全关闭此窗口...</small>
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
                    showLCAError('获取分析状态失败: ' + (data.error || '未知错误'), fileId, fileName);
                }
            }
        })
        .catch(error => {
            console.error('检查状态失败:', error);
            
            setTimeout(checkStatus, 5000); 
        });
    }
    
    
    setTimeout(checkStatus, 2000); 
}

function getStatusText(status) {
    const statusMap = {
        'queued': '排队中，等待可用并发槽位...',
        'running': '正在进行LCA分析...',
        'connecting': '连接openLCA中...',
        'parsing': '解析Excel文件中...',
        'creating_flows': '创建LCA流程中...',
        'building_processes': '建立流程关系中...',
        'creating_system': '创建产品系统中...',
        'running_assessment': '运行影响评估中...',
        'saving_results': '保存结果中...',
        'completed': 'LCA分析完成！',
        'failed': 'LCA分析失败'
    };
    return statusMap[status] || '处理中...';
}

function getCompletionActions(status, data, fileId, fileName) {
    if (status === 'completed') {
        const result = data.result;
        return `
            <div class="lca-completion-details">
                <p><strong>分析结果摘要：</strong></p>
                <ul>
                    <li>分析状态: ${result?.success ? '成功' : '失败'}</li>
                    <li>分析耗时: ${Math.floor(data.duration)} 秒</li>
                </ul>
            </div>
            <div class="modal-actions">
                <button class="btn btn-primary" onclick="showLCAResults(${fileId})">查看详细结果</button>
                <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">关闭</button>
            </div>
        `;
    } else {
        return `
            <div class="lca-error-details">
                <p><strong>错误信息：</strong></p>
                <p class="error-text">${data.error || '未知错误'}</p>
            </div>
            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">关闭</button>
                <button class="btn btn-primary" onclick="closeLCAAnalysisModal(); runLCAAnalysis(${fileId}, '${fileName}')">重试</button>
            </div>
        `;
    }
}

function showLCAError(errorMessage, fileId, fileName) {
    const content = document.getElementById('lcaAnalysisContent');
    content.innerHTML = `
        <div class="lca-status-container">
            <div class="lca-status-icon">❌</div>
            <div class="lca-status-text">启动分析失败</div>
            <div class="lca-status-details">
                <p class="error-text">${errorMessage}</p>
            </div>
            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">关闭</button>
                <button class="btn btn-primary" onclick="closeLCAAnalysisModal(); runLCAAnalysis(${fileId}, '${fileName}')">重试</button>
            </div>
        </div>
    `;
}

function saveLCAResultToDB(fileId, data) {
    
    
    console.log('LCA分析完成，结果:', data);
}

function checkLCACompletionInDB(fileId, fileName, timerInterval) {
    const content = document.getElementById('lcaAnalysisContent');
    
    
    content.innerHTML = `
        <div class="lca-status-container">
            <div class="lca-status-icon">🔍</div>
            <div class="lca-status-text">检查分析完成状态...</div>
            <div class="lca-status-details">正在查询数据库中的LCA结果记录...</div>
        </div>
    `;
    
    fetch(`/excel_file/${fileId}/check_lca_completion`)
    .then(response => response.json())
    .then(data => {
        if (data.success && data.has_results) {
            const result = data.latest_result;
            const statusIcon = result.status === 'completed' ? '✅' : result.status === 'failed' ? '❌' : '⏳';
            const statusText = result.status === 'completed' ? 'LCA分析已完成' : 
                              result.status === 'failed' ? 'LCA分析失败' : 'LCA分析状态未知';
            
            content.innerHTML = `
                <div class="lca-status-container">
                    <div class="lca-status-icon">${statusIcon}</div>
                    <div class="lca-status-text">${statusText}</div>
                    <div class="lca-status-details">
                        <p><strong>从数据库记录恢复的信息：</strong></p>
                        <ul style="text-align: left; display: inline-block;">
                            <li>分析状态: ${result.status}</li>
                            <li>创建时间: ${new Date(result.created_at).toLocaleString()}</li>
                            ${result.duration ? `<li>分析耗时: ${Math.floor(result.duration)} 秒</li>` : ''}
                        </ul>
                    </div>
                    <div class="modal-actions">
                        ${result.status === 'completed' ? `<button class="btn btn-primary" onclick="showLCAResults(${fileId})">查看详细结果</button>` : ''}
                        <button class="btn btn-warning" onclick="closeLCAAnalysisModal(); runLCAAnalysis(${fileId}, '${fileName}')">重新分析</button>
                        <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">关闭</button>
                    </div>
                </div>
            `;
        } else {
            
            content.innerHTML = `
                <div class="lca-status-container">
                    <div class="lca-status-icon">⚠️</div>
                    <div class="lca-status-text">任务状态丢失</div>
                    <div class="lca-status-details">
                        <p>分析任务状态信息丢失，且数据库中没有找到完成的结果记录。</p>
                        <p><strong>可能原因：</strong></p>
                        <ul style="text-align: left; display: inline-block;">
                            <li>服务器重启导致内存中的任务状态丢失</li>
                            <li>分析可能还在进行中，但无法跟踪状态</li>
                            <li>分析可能已完成但未保存到数据库</li>
                        </ul>
                        <p><strong>建议操作：</strong></p>
                        <ul style="text-align: left; display: inline-block;">
                            <li>检查openLCA软件中是否有新创建的模型</li>
                            <li>重新运行分析以确保完成</li>
                        </ul>
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-primary" onclick="showLCAResults(${fileId})">查看历史结果</button>
                        <button class="btn btn-success" onclick="createManualLCAResult(${fileId})">标记为已完成</button>
                        <button class="btn btn-warning" onclick="closeLCAAnalysisModal(); runLCAAnalysis(${fileId}, '${fileName}')">重新分析</button>
                        <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">关闭</button>
                    </div>
                </div>
            `;
        }
    })
    .catch(error => {
        console.error('检查完成状态失败:', error);
        content.innerHTML = `
            <div class="lca-status-container">
                <div class="lca-status-icon">❌</div>
                <div class="lca-status-text">检查失败</div>
                <div class="lca-status-details">
                    <p>无法检查分析完成状态：${error.message}</p>
                </div>
                <div class="modal-actions">
                    <button class="btn btn-warning" onclick="closeLCAAnalysisModal(); runLCAAnalysis(${fileId}, '${fileName}')">重新分析</button>
                    <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">关闭</button>
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
            <div class="lca-status-text">正在创建LCA完成记录...</div>
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
                    <div class="lca-status-text">LCA分析已标记为完成！</div>
                    <div class="lca-status-details">
                        <p>已成功创建LCA完成记录。</p>
                        <p><strong>记录ID:</strong> ${data.result_id}</p>
                        <p>现在您可以查看LCA结果了。</p>
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-primary" onclick="showLCAResults(${fileId})">查看LCA结果</button>
                        <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">关闭</button>
                    </div>
                </div>
            `;
        } else {
            content.innerHTML = `
                <div class="lca-status-container">
                    <div class="lca-status-icon">❌</div>
                    <div class="lca-status-text">创建记录失败</div>
                    <div class="lca-status-details">
                        <p class="error-text">${data.error}</p>
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">关闭</button>
                    </div>
                </div>
            `;
        }
    })
    .catch(error => {
        console.error('创建LCA记录失败:', error);
        content.innerHTML = `
            <div class="lca-status-container">
                <div class="lca-status-icon">❌</div>
                <div class="lca-status-text">网络错误</div>
                <div class="lca-status-details">
                    <p class="error-text">创建记录时发生网络错误</p>
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeLCAAnalysisModal()">关闭</button>
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
            <div class="loading-text">正在加载LCA分析结果...</div>
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
                    'completed': '已完成',
                    'failed': '失败',
                    'running': '运行中',
                    'pending': '等待中'
                }[result.status] || '未知';
                
                html += `
                    <div class="lca-result-card ${result.status}">
                        <div class="result-header">
                            <h4>${statusIcon} 分析 #${index + 1} - ${statusText}</h4>
                            <div class="result-time">
                                开始时间: ${result.start_time || 'N/A'}<br>
                                ${result.end_time ? `结束时间: ${result.end_time}` : ''}
                            </div>
                        </div>
                        <div class="result-details">
                `;
                
                if (result.status === 'completed') {
                    html += `
                        <div class="success-details">
                            <p><strong>分析结果:</strong></p>
                            <ul>
                                <li>流程数量: ${result.flows_count || 'N/A'}</li>
                                <li>过程数量: ${result.processes_count || 'N/A'}</li>
                                <li>产品系统数量: ${result.product_systems_count || 'N/A'}</li>
                                <li>分析耗时: ${result.duration_seconds ? result.duration_seconds.toFixed(2) + '秒' : 'N/A'}</li>
                                <li>openLCA连接: ${result.openLCA_connected ? '✅ 已连接' : '❌ 未连接'}</li>
                            </ul>
                            <div style="display: flex; gap: 10px; margin-top: 15px;">
                                <a href="/lca_result/${result.id}/visualization" class="btn btn-success btn-sm" target="_blank">📊 查看可视化图表</a>
                                <button class="btn btn-info btn-sm" onclick="showLCAResultDetails(${result.id})">查看详细信息</button>
                            </div>
                        </div>
                    `;
                } else if (result.status === 'failed') {
                    html += `
                        <div class="error-details">
                            <p><strong>错误信息:</strong></p>
                            <p class="error-text">${result.error_message || '未知错误'}</p>
                        </div>
                    `;
                } else if (result.status === 'running') {
                    html += `
                        <div class="running-details">
                            <p>分析正在进行中，请稍候...</p>
                            <button class="btn btn-secondary btn-sm" onclick="refreshLCAResults(${fileId})">刷新状态</button>
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
                    <div class="no-results-text">暂无LCA分析结果</div>
                    <div class="no-results-details">此文件尚未进行LCA分析，请点击"运行LCA分析"按钮开始分析</div>
                    <button class="btn btn-primary" onclick="closeLCAResultsModal(); runLCAAnalysis(${fileId}, 'Excel文件')">开始LCA分析</button>
                </div>
            `;
        }
    })
    .catch(error => {
        console.error('获取LCA结果失败:', error);
        content.innerHTML = `
            <div class="error-container">
                <div class="error-icon">❌</div>
                <div class="error-text">获取LCA分析结果失败</div>
                <div class="error-details">请检查网络连接或稍后重试</div>
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
        summaryEl.textContent = '端口状态获取失败，请稍后重试。';
        gridEl.innerHTML = '';
        return;
    }

    const total = queueStats.total_ipc_ports || 0;
    const healthy = queueStats.healthy_ports || 0;
    const running = queueStats.running_count || 0;
    const queued = queueStats.queued_count || 0;
    const checkedAt = queueStats.port_check_time || '-';

    summaryEl.innerHTML = `
        共 ${total} 个端口，健康 ${healthy} 个，执行中任务 ${running} 个，排队 ${queued} 个，
        最近检查：${checkedAt}
    `;

    const portStatus = Array.isArray(queueStats.port_status) ? queueStats.port_status : [];
    if (portStatus.length === 0) {
        gridEl.innerHTML = '<div class="lca-port-detail">暂无端口状态数据</div>';
        return;
    }

    gridEl.innerHTML = portStatus.map((item) => {
        const reachable = !!item.reachable;
        const busy = !!item.busy;
        const statusText = reachable ? '可连通' : '不可连通';
        const busyText = busy ? '占用中' : '空闲';
        const errorText = item.error ? `<div class="lca-port-detail">错误：${item.error}</div>` : '';
        return `
            <div class="lca-port-status-item ${reachable ? 'reachable' : 'unreachable'}">
                <div class="lca-port-title">IPC ${item.port}</div>
                <div class="lca-port-detail">状态：${statusText}</div>
                <div class="lca-port-detail">负载：${busyText}</div>
                <div class="lca-port-detail">延迟：${item.latency_ms || 0} ms</div>
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

    summaryEl.textContent = forceCheck ? '正在重新检测端口连通性...' : '正在加载端口状态...';
    const query = forceCheck ? '?force_check=1' : '';
    fetch(`/lca/queue/status${query}`)
        .then((response) => response.json())
        .then((data) => renderIpcPortStatus(data))
        .catch((error) => {
            console.error('获取IPC端口状态失败:', error);
            summaryEl.textContent = '端口状态获取失败，请检查后端服务。';
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

console.log('✅ LCA分析JavaScript库已加载');
