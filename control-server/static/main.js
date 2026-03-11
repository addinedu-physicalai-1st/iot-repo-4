// Smart Farm Main Dashboard Controller

let agvRobotId = "R01";
let currentRobotNode = null;

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
                Object.keys(data.sensors).forEach(nodeId => {
                    const envBox = document.getElementById(`env-${nodeId.toLowerCase()}`);
                    if (envBox) {
                        const sData = data.sensors[nodeId];
                        envBox.querySelector('.v.temp').innerText = sData.temperature;
                        envBox.querySelector('.v.hum').innerText = sData.humidity;
                        envBox.querySelector('.v.lux').innerText = sData.light;

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

    // Update Identity
    if (state.robot_id) {
        agvRobotId = state.robot_id;
        const idMark = document.getElementById("agv-id-display");
        if (idMark) idMark.innerText = state.robot_id;
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

    // Set dummy state
    document.getElementById('ctrl-led').checked = Math.random() > 0.5;
    document.getElementById('ctrl-fan').checked = false;
    document.getElementById('ctrl-val').checked = false;
}

function closeNodeModal() {
    document.getElementById('node-modal').classList.add('hidden');
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
            if (data.ok) addLocalLog(`[CTRL] 수동 제어: ${currNode.toUpperCase()} ${device.toUpperCase()} 밸브 ${state}`, 'cmd-out');
        });
}

// Full Logs Modal
function openFullLogsModal() {
    const tbody = document.getElementById('full-logs-body');
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;">데이터 불러오는 중...</td></tr>`;
    document.getElementById('logs-modal').classList.remove('hidden');

    fetch('/api/tasks?limit=20')
        .then(res => res.json())
        .then(data => {
            if (data.ok && data.tasks) {
                tbody.innerHTML = "";
                data.tasks.forEach(task => {
                    const time = task.created_at ? task.created_at.substring(5, 19).replace('T', ' ') : "-";
                    const status = task.status || (task.task_status === 2 ? "완료" : "진행중");
                    const dest = task.destination || task.destination_node || "-";

                    tbody.innerHTML += `
                        <tr>
                            <td><strong>GOTO</strong> (ID: ${task.id || task.task_id})</td>
                            <td><span class="badge">${dest.toUpperCase()}</span></td>
                            <td>${status}</td>
                            <td class="time">${time}</td>
                        </tr>
                    `;
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;">기록이 없습니다.</td></tr>`;
            }
        });
}

function closeFullLogsModal() {
    document.getElementById('logs-modal').classList.add('hidden');
}
