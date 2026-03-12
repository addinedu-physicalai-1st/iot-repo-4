// Smart Farm Main Dashboard Controller

let agvRobotId = "R01";
let currentRobotNode = null;
let nodeDetailChart = null;
let latestNurseryData = {}; // 육묘장 노드별 최신 센서/장치 데이터 저장소

// Initialize on load
document.addEventListener("DOMContentLoaded", () => {
    console.log("Dashboard initialized. Connecting to API...");

    // Check Auth Status (just UI update)
    fetch('/api/status/auth')
        .then(res => res.json())
        .then(data => {
            if (data.logged_in) document.getElementById('current-user').innerText = data.username;
        });

    // Start Polling loops
    setInterval(pollSensorData, 3000);
    setInterval(pollRobotState, 1000);
    setInterval(pollCameraState, 2000);
    setInterval(pollRobotLogs, 5000);

    // Initial fetch
    pollSensorData();
    pollRobotState();
});

// ==========================================
// 1. Data Polling: Nursery Sensors
// ==========================================
function pollSensorData() {
    fetch('/api/sensor/latest')
        .then(res => res.json())
        .then(data => {
            if (data.ok && data.sensors) {
                latestNurseryData = data.sensors; // 전역 저장소 업데이트
                Object.keys(data.sensors).forEach(nodeId => {
                    const envBox = document.getElementById(`env-${nodeId.toLowerCase()}`);
                    if (envBox) {
                        const sData = data.sensors[nodeId];
                        envBox.querySelector('.v.temp').innerText = sData.temperature;
                        envBox.querySelector('.v.hum').innerText = sData.humidity;
                        envBox.querySelector('.v.lux').innerText = sData.light;

                        // 현재 팝업이 이 노드에 대해 열려있다면 스위치 상태 동기화
                        if (!document.getElementById('node-modal').classList.contains('hidden')) {
                            const modalTitle = document.getElementById('modal-title').innerText;
                            if (modalTitle.includes(nodeId.toUpperCase())) {
                                updateModalSwitches(sData);
                            }
                        }

                        // Flash border to indicate data arrival
                        const nodeElement = envBox.parentElement;
                        nodeElement.style.borderColor = "rgba(66, 211, 146, 0.8)";
                        setTimeout(() => nodeElement.style.borderColor = "", 500);
                    }
                });
            }
        }).catch(err => console.error("Sensor fetch err:", err));
}

// ==========================================
// 2. Data Polling: AGV Robot State
// ==========================================
function pollRobotState() {
    fetch('/api/robot_state')
        .then(res => res.json())
        .then(data => {
            if (data.ok && data.state) {
                updateRobotPosition(data.state);
            }
        }).catch(err => console.error("Robot state fetch err:", err));
}

function updateRobotPosition(state) {
    const agvElem = document.getElementById("agv-robot");
    const nodeName = state.node_name || state.node || null; // handles both legacy and new names

    if (!nodeName || nodeName.includes("-")) return;

    // Only update if node changed to trigger CSS transition smoothly
    if (currentRobotNode !== nodeName) {
        currentRobotNode = nodeName;
        agvElem.classList.remove('hidden');

        // Find track node element location
        const targetNode = document.getElementById(`node-${nodeName.toLowerCase()}`);
        if (targetNode) {
            // Apply position from CSS styling mapped to %
            agvElem.style.left = targetNode.style.left || getComputedStyle(targetNode).left;
            agvElem.style.top = targetNode.style.top || getComputedStyle(targetNode).top;

            // Highlight active node
            document.querySelectorAll('.track-node').forEach(n => n.style.borderColor = "");
            targetNode.style.borderColor = "#42d392";
            targetNode.style.boxShadow = "0 0 15px rgba(66, 211, 146, 0.6)";
        }
    }

    // Update Battery
    if (state.battery) {
        agvElem.querySelector('.bat span').innerText = state.battery;
    }

    // Simulate Load Status (If state contains loaded flag, show plant icon)
    // For demo: if node is an S node or Outbound, simulate dropoff/pickup
    const loadIcon = agvElem.querySelector('.agv-load');
    if (state.loaded || (nodeName.startsWith('s') && Math.random() > 0.5)) {
        loadIcon.classList.remove('hidden');
    } else {
        loadIcon.classList.add('hidden');
    }

    // Inbound/Outbound Status (Simulation for GUI effect)
    if (nodeName === 'a01') document.querySelector('#node-a01 .plant-indicator').classList.remove('hidden');
    if (nodeName === 'a04' && loadIcon.classList.contains('hidden')) document.querySelector('#node-a04 .plant-indicator').classList.add('hidden');
}

// ==========================================
// 3. Data Polling: AGV Camera
// ==========================================
function pollCameraState() {
    fetch('/api/camera/status')
        .then(res => res.json())
        .then(data => {
            const badge = document.getElementById("cam-fps");
            if (data.ok && data.connected) {
                badge.innerText = `${data.fps} FPS`;
                badge.style.background = "rgba(35, 134, 54, 0.6)";
            } else {
                badge.innerText = `OFFLINE`;
                badge.style.background = "rgba(248, 81, 73, 0.6)";
            }
        }).catch(() => { });
}

// ==========================================
// 4. Data Polling: Logs
// ==========================================
function pollRobotLogs() {
    fetch('/api/tasks?limit=5')
        .then(res => res.json())
        .then(data => {
            if (data.ok && data.tasks) {
                const container = document.getElementById("agv-log-container");
                container.innerHTML = "";
                data.tasks.slice(0, 5).forEach(task => {
                    const time = task.created_at ? task.created_at.substring(11, 19) : "00:00:00";
                    const status = task.status || "WAIT";
                    const dest = task.destination || task.destination_node || "-";
                    const cssClass = status === 'COMPLETED' || status === 2 ? 'cmd-in' : 'cmd-out';

                    container.innerHTML += `
                        <div class="log-entry ${cssClass}">
                            <span class="time">[${time}]</span>
                            <span>Dest: ${dest.toUpperCase()} | Status: ${status}</span>
                        </div>
                    `;
                });
            }
        }).catch(() => { });
}

// ==========================================
// User Actions: Robot Control
// ==========================================
// ==========================================
// GOTO Control Modal
// ==========================================
function openGotoModal() {
    document.getElementById('goto-modal').classList.remove('hidden');
}

function closeGotoModal() {
    document.getElementById('goto-modal').classList.add('hidden');
}

function sendGotoCmd() {
    const dest = document.getElementById('dest-select').value;
    if (!dest) {
        alert("목적지를 선택해주세요.");
        return;
    }

    fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ robot_id: agvRobotId, destination: dest })
    })
        .then(res => res.json())
        .then(data => {
            if (data.ok) {
                addLocalLog(`[SEND] GOTO ${dest.toUpperCase()} 명령 전송 성공`, 'sys-msg');
                closeGotoModal();
                document.getElementById('dest-select').value = "";
            } else {
                addLocalLog(`[ERROR] 전송 실패: ${data.error}`, 'sys-msg');
            }
        }).catch(err => addLocalLog(`[ERROR] 네트워크 오류`, 'sys-msg'));
}

function emergencyStop() {
    fetch('/api/robot/emergency_stop', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            addLocalLog(`🚨 [EMERGENCY] 긴급 정지 발동!`, 'sys-msg');
            document.getElementById('agv-robot').style.borderColor = "#f85149";
        });
}

function addLocalLog(msg, cssClass) {
    const container = document.getElementById("agv-log-container");
    const time = new Date().toTimeString().split(' ')[0];
    container.innerHTML = `<div class="log-entry ${cssClass}"><span class="time">[${time}]</span> ${msg}</div>` + container.innerHTML;
}

// ==========================================
// Modal Actions
// ==========================================
function openNodeModal(nodeId) {
    document.getElementById('modal-title').innerText = `상세 관제: ${nodeId.toUpperCase()}`;
    document.getElementById('node-modal').classList.remove('hidden');

    // Reset fields
    document.getElementById('node-crop-name').innerText = "조회 중...";
    document.getElementById('node-incoming-date').innerText = "-";
    document.getElementById('node-outgoing-date').innerText = "-";

    // Fetch details from API
    fetch(`/api/node/${nodeId}/details`)
        .then(res => res.json())
        .then(data => {
            if (data.ok) {
                const cropText = data.variety_name
                    ? `${data.variety_name}(${data.crop_name})`
                    : data.crop_name;
                document.getElementById('node-crop-name').innerText = cropText;
                document.getElementById('node-incoming-date').innerText = data.incoming_date;
                document.getElementById('node-outgoing-date').innerText = data.outgoing_date;
            } else {
                document.getElementById('node-crop-name').innerText = "데이터 없음";
            }
        }).catch(() => {
            document.getElementById('node-crop-name').innerText = "연결 오류";
        });

    // Fetch History & Render Chart
    fetch(`/api/node/${nodeId}/history`)
        .then(res => res.json())
        .then(data => {
            if (data.ok) {
                updateNodeChart(data.history);
            }
        });

    // 데이터 저장소에서 현재 노드의 상태를 찾아 스위치 설정
    const nodeData = latestNurseryData[nodeId.toLowerCase()];
    if (nodeData) {
        updateModalSwitches(nodeData);
    } else {
        // 데이터가 없으면 초기화
        document.getElementById('ctrl-pump').checked = false;
        document.getElementById('ctrl-fan').checked = false;
        document.getElementById('ctrl-heater').checked = false;
        document.getElementById('ctrl-led').checked = false;
    }
}

/**
 * 팝업창 내의 스위치들을 데이터 상태에 맞게 업데이트하는 헬퍼 함수
 */
function updateModalSwitches(nodeData) {
    if (!nodeData) return;
    
    // 서버에서 전달받은 "LED_ON", "LED_OFF" 등의 문자열을 boolean으로 변환
    if (nodeData.pump) document.getElementById('ctrl-pump').checked = nodeData.pump.includes("_ON");
    if (nodeData.fan) document.getElementById('ctrl-fan').checked = nodeData.fan.includes("_ON");
    if (nodeData.heater) document.getElementById('ctrl-heater').checked = nodeData.heater.includes("_ON");
    if (nodeData.led) document.getElementById('ctrl-led').checked = nodeData.led.includes("_ON");
}

function closeNodeModal() {
    document.getElementById('node-modal').classList.add('hidden');
    if (nodeDetailChart) {
        nodeDetailChart.destroy();
        nodeDetailChart = null;
    }
}

function updateNodeChart(history) {
    const ctx = document.getElementById('node-env-chart').getContext('2d');

    if (nodeDetailChart) {
        nodeDetailChart.destroy();
    }

    nodeDetailChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: history.labels,
            datasets: [
                {
                    label: '온도 (℃)',
                    data: history.temp,
                    borderColor: '#f85149',
                    backgroundColor: 'rgba(248, 81, 73, 0.1)',
                    yAxisID: 'y-temp',
                    tension: 0.3,
                    pointRadius: 0
                },
                {
                    label: '습도 (%)',
                    data: history.humi,
                    borderColor: '#58a6ff',
                    backgroundColor: 'rgba(88, 166, 255, 0.1)',
                    yAxisID: 'y-humi',
                    tension: 0.3,
                    pointRadius: 0
                },
                {
                    label: '조도 (lx)',
                    data: history.light,
                    borderColor: '#f2cc60',
                    backgroundColor: 'rgba(242, 204, 96, 0.1)',
                    yAxisID: 'y-light',
                    tension: 0.3,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    labels: { color: '#8b949e', font: { size: 10 } }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#8b949e', maxRotation: 0, autoSkip: true, maxTicksLimit: 6 },
                    grid: { color: 'rgba(48, 54, 61, 0.3)' }
                },
                'y-temp': {
                    type: 'linear', position: 'left',
                    title: { display: true, text: '℃', color: '#f85149' },
                    ticks: { color: '#f85149' },
                    grid: { drawOnChartArea: false }
                },
                'y-humi': {
                    type: 'linear', position: 'right',
                    title: { display: true, text: '%', color: '#58a6ff' },
                    ticks: { color: '#58a6ff' },
                    grid: { drawOnChartArea: false }
                },
                'y-light': {
                    display: false,
                    type: 'linear', position: 'right',
                }
            }
        }
    });
}

function toggleDevice(device) {
    const state = document.getElementById(`ctrl-${device}`).checked ? "ON" : "OFF";
    const currNode = document.getElementById('modal-title').innerText.replace('상세 관제: ', '').toLowerCase().trim();

    fetch('/api/sensor/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: currNode, device: device, state: state })
    }).then(res => res.json())
        .then(data => {
            if (data.ok) {
                addLocalLog(`[CTRL] 수동 제어: ${currNode.toUpperCase()} ${device.toUpperCase()} ${state}`, 'cmd-out');
                // 육묘장 로그 탭이 열려있다면 즉시 갱신
                if (!document.getElementById('logs-modal').classList.contains('hidden')) {
                    fetchNurseryLogs();
                }
            }
        });
}

// Full Logs Modal
let currentLogTab = 'agv';

function switchLogTab(tabName) {
    currentLogTab = tabName;
    // Update button states
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.innerText.includes(tabName === 'agv' ? 'AGV' : tabName === 'inout' ? '입출고' : '육묘장'));
    });
    // Update content visibility
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('hidden', content.id !== `tab-${tabName}`);
    });
    // Fetch data for the selected tab
    refreshActiveLogTab();
}

function refreshActiveLogTab() {
    if (currentLogTab === 'agv') fetchAgvLogs();
    else if (currentLogTab === 'inout') fetchInOutLogs();
    else if (currentLogTab === 'nursery') fetchNurseryLogs();
}

function openFullLogsModal() {
    document.getElementById('logs-modal').classList.remove('hidden');
    refreshActiveLogTab();
}

function fetchAgvLogs() {
    const tbody = document.getElementById('full-logs-body');
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;">데이터 불러오는 중...</td></tr>`;
    fetch(`/api/tasks?limit=20&t=${new Date().getTime()}`)
        .then(res => res.json())
        .then(data => {
            if (data.ok && data.tasks && data.tasks.length > 0) {
                tbody.innerHTML = "";
                data.tasks.forEach(task => {
                    const time = task.created_at ? task.created_at.substring(5, 19).replace('T', ' ') : "-";
                    const statusVal = task.status || task.task_status;
                    const statusLabel = statusVal === 2 || statusVal === 'COMPLETED' ? "완료" : (statusVal === 1 ? "진행중" : "대기");
                    const src = task.source_node || "-";
                    const dest = task.destination || task.destination_node || "-";
                    const curr = task.current_location || "-";

                    tbody.innerHTML += `
                        <tr>
                            <td><strong>GOTO</strong> (ID: ${task.id || task.task_id})</td>
                            <td><span class="badge sys-msg">${src.toUpperCase()}</span></td>
                            <td><span class="badge">${dest.toUpperCase()}</span></td>
                            <td><span class="badge status-badge">${curr.toUpperCase()}</span></td>
                            <td>${statusLabel}</td>
                            <td class="time">${time}</td>
                        </tr>
                    `;
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;">기록이 없습니다.</td></tr>`;
            }
        });
}

function fetchInOutLogs() {
    const tbody = document.getElementById('inout-logs-body');
    tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;">데이터 불러오는 중...</td></tr>`;
    fetch(`/api/logs/inout?limit=20&t=${new Date().getTime()}`)
        .then(res => res.json())
        .then(data => {
            if (data.ok && data.logs && data.logs.length > 0) {
                tbody.innerHTML = "";
                data.logs.forEach(log => {
                    const time = log.time ? log.time.substring(5, 19).replace('T', ' ') : "-";
                    const statusVal = log.task_status === 2 ? "완료" : "진행중";
                    const combinedStatus = `${log.type}${statusVal}`; // 예: 입고완료, 출고진행중
                    
                    const statusClass = log.task_status === 2 ? 'sys-msg' : 'cmd-out';

                    tbody.innerHTML += `
                        <tr>
                            <td>${log.task_id}</td>
                            <td><span class="badge ${statusClass}">${combinedStatus}</span></td>
                            <td class="time">${time}</td>
                        </tr>
                    `;
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;">기록이 없습니다.</td></tr>`;
            }
        });
}

function fetchNurseryLogs() {
    const tbody = document.getElementById('nursery-logs-body');
    tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;">데이터 불러오는 중...</td></tr>`;
    fetch(`/api/logs/nursery?limit=20&t=${new Date().getTime()}`)
        .then(res => res.json())
        .then(data => {
            if (data.ok && data.logs && data.logs.length > 0) {
                tbody.innerHTML = "";
                data.logs.forEach(log => {
                    const time = log.time ? log.time.substring(5, 19).replace('T', ' ') : "-";
                    const typeClass = log.type === 'CONTROL' ? 'cmd-out' : 'sys-msg';
                    tbody.innerHTML += `
                        <tr>
                            <td><span class="badge ${typeClass}">${log.type}</span></td>
                            <td>${log.msg}</td>
                            <td class="time">${time}</td>
                        </tr>
                    `;
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;">기록이 없습니다.</td></tr>`;
            }
        });
}

function closeFullLogsModal() {
    document.getElementById('logs-modal').classList.add('hidden');
}
