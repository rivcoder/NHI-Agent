// NHI Governance Agent - frontend js file

const API_BASE = window.location.origin;

// state variables
let currentTab = "scan";
let scanResults = null;
let isScanning = false;

// runs on page load
document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    checkBackendHealth();
    loadGitLabProjects();
});

// handles tab switching

function initTabs() {
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });
}

function switchTab(tabId) {
    currentTab = tabId;

    // Update tab buttons
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.tab === tabId);
    });

    // Update panels
    document.querySelectorAll(".tab-panel").forEach(panel => {
        panel.classList.toggle("active", panel.id === `panel-${tabId}`);
    });

    // Load data for non-scan tabs
    if (tabId === "history") loadHistoryTab();
    if (tabId === "index") loadIndexTab();
}

// API health check

async function checkBackendHealth() {
    const indicator = document.getElementById("statusIndicator");
    try {
        const res = await fetch(`${API_BASE}/api/health`);
        if (res.ok) {
            setStatus("Ready", "ready");
        } else {
            setStatus("API Error", "error");
        }
    } catch {
        setStatus("Offline", "error");
    }
}

function setStatus(text, state) {
    const indicator = document.getElementById("statusIndicator");
    const statusText = indicator.querySelector(".status-text");
    statusText.textContent = text;
    indicator.className = "status-indicator " + state;
}

// scan functions

async function startScan() {
    const repoUrl = document.getElementById("repoUrl").value.trim();
    if (!repoUrl) {
        shakeElement(document.getElementById("repoUrl"));
        return;
    }

    // Validate GitLab or GitHub URL structure
    if (repoUrl.toLowerCase() !== "demo" && !repoUrl.toLowerCase().includes("gitlab.com") && !repoUrl.toLowerCase().includes("github.com")) {
        showError("Invalid repository URL. The NHI Governance Agent supports GitLab and GitHub repositories (e.g., https://github.com/user/repo).");
        shakeElement(document.getElementById("repoUrl"));
        return;
    }

    const token = document.getElementById("gitlabToken") ? document.getElementById("gitlabToken").value.trim() : "";
    const body = { repo_url: repoUrl };
    if (token) {
        body.gitlab_token = token;
    }
    await executeScan(`${API_BASE}/api/scan`, body);
}

async function startDemoScan() {
    await executeScan(`${API_BASE}/api/scan/demo`, {});
}

async function executeScan(url, body) {
    if (isScanning) return;
    isScanning = true;

    // UI: scanning state
    const btnScan = document.getElementById("btnScan");
    const btnDemo = document.getElementById("btnDemo");
    btnScan.classList.add("scanning");
    btnScan.querySelector(".btn-text").textContent = "Scanning...";
    btnDemo.style.pointerEvents = "none";
    btnDemo.style.opacity = "0.5";
    setStatus("Scanning", "scanning");

    // Show progress
    showProgress();
    hideResults();

    try {
        // Simulate progress steps
        updateProgress(20, "Connecting to repository...");
        await sleep(400);
        updateProgress(40, "Discovering NHI patterns...");

        const res = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        updateProgress(70, "Gemini scoring risk levels...");
        await sleep(300);

        const data = await res.json();
        updateProgress(90, "Compiling results...");
        await sleep(200);

        if (data.status === "ok") {
            scanResults = data;
            updateProgress(100, `Complete — ${data.summary.total} findings in ${data.elapsed}s`);
            await sleep(500);
            hideProgress();
            renderResults(data);
            await loadMetrics(data.repo);
            setStatus("Scan Complete", "ready");
        } else if (data.status === "profile") {
            hideProgress();
            setStatus("Select Repo", "ready");
            showProfileRepos(data.message, data.repos);
        } else {
            throw new Error(data.message || "Scan failed");
        }
    } catch (err) {
        hideProgress();
        setStatus("Error", "error");
        const isNetworkErr = err.message.toLowerCase().includes("fetch") || 
                             err.message.toLowerCase().includes("network") || 
                             err.message.toLowerCase().includes("connect");
        showError(err.message, isNetworkErr);
    } finally {
        isScanning = false;
        btnScan.classList.remove("scanning");
        btnScan.querySelector(".btn-text").textContent = "Scan Repository";
        btnDemo.style.pointerEvents = "";
        btnDemo.style.opacity = "";
    }
}

// render findings and statistics

function renderResults(data) {
    // Hide empty state
    document.getElementById("emptyState").classList.add("hidden");

    // Render stat cards
    renderStats(data.summary);

    // Show critical alert if needed
    const alertEl = document.getElementById("criticalAlert");
    if (data.summary.critical > 0) {
        document.getElementById("criticalAlertText").textContent =
            `${data.summary.critical} critical NHI${data.summary.critical > 1 ? 's' : ''} detected — immediate rotation required.`;
        alertEl.classList.add("active");
    } else {
        alertEl.classList.remove("active");
    }

    // Render findings
    renderFindings(data.findings);
}

function renderStats(summary) {
    const grid = document.getElementById("statsGrid");
    grid.innerHTML = "";
    grid.classList.add("active");

    const cards = [
        { label: "Total",    value: summary.total,    cls: "total" },
        { label: "Critical", value: summary.critical, cls: "critical" },
        { label: "High",     value: summary.high,     cls: "high" },
        { label: "Medium",   value: summary.medium,   cls: "medium" },
        { label: "Low",      value: summary.low,      cls: "low" },
    ];

    cards.forEach((c, i) => {
        const card = document.createElement("div");
        card.className = `stat-card ${c.cls}`;
        card.style.animationDelay = `${i * 0.08}s`;
        card.innerHTML = `
            <div class="stat-label">${c.label}</div>
            <div class="stat-value" data-target="${c.value}">0</div>
        `;
        grid.appendChild(card);
    });

    // Animate count-up
    setTimeout(() => {
        grid.querySelectorAll(".stat-value").forEach(el => {
            animateCount(el, 0, parseInt(el.dataset.target), 600);
        });
    }, 100);
}

function animateCount(el, start, end, duration) {
    const startTime = performance.now();
    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(start + (end - start) * eased);
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

function renderFindings(findings) {
    const container = document.getElementById("findingsContainer");
    const list = document.getElementById("findingsList");
    list.innerHTML = "";
    container.classList.add("active");

    // Sort by risk priority
    const riskOrder = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, UNKNOWN: 4 };
    findings.sort((a, b) => (riskOrder[a.risk] || 4) - (riskOrder[b.risk] || 4));

    findings.forEach((f, i) => {
        const card = document.createElement("div");
        card.className = "finding-card";
        card.style.animationDelay = `${i * 0.06}s`;

        const riskClass = (f.risk || "unknown").toLowerCase();

        card.innerHTML = `
            <div class="finding-header" onclick="toggleFinding(this)">
                <span class="risk-badge ${riskClass}">${f.risk || "UNKNOWN"}</span>
                <span class="finding-file">${escapeHtml(f.file)}</span>
                <span class="finding-line">L${f.line}</span>
                <span class="finding-chevron">▶</span>
            </div>
            <div class="finding-body">
                <div class="finding-details">
                    <div class="detail-row">
                        <span class="detail-label">Type</span>
                        <span class="detail-value">${escapeHtml(f.type || "—")}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Pattern</span>
                        <span class="detail-value"><code>${escapeHtml(f.pattern)}</code></span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Content</span>
                        <span class="detail-value"><code>${escapeHtml(f.content)}</code></span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Reason</span>
                        <span class="detail-value">${escapeHtml(f.reason || "—")}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Action</span>
                        <span class="detail-value">${escapeHtml(f.action || "—")}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label" style="color: var(--risk-critical);">Breach Cost</span>
                        <span class="detail-value" style="color: var(--risk-critical); font-weight: 600;">💸 ${escapeHtml(f.breach_cost || "N/A")} USD (Est.)</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label" style="color: var(--risk-high);">Blast Radius</span>
                        <span class="detail-value" style="color: var(--risk-high); font-weight: 500;">💥 ${escapeHtml(f.blast_radius || "N/A")}</span>
                    </div>
                    <div class="remediation-box" id="remed-${i}">
                        <button class="btn-remediate-preview" onclick="previewRemediation(${i})">
                            <span>🤖</span> Ask Gemini Remediation Assistant
                        </button>
                    </div>
                </div>
            </div>
        `;
        list.appendChild(card);
    });
}

function toggleFinding(header) {
    header.closest(".finding-card").classList.toggle("open");
}

// scan history functions

async function loadHistoryTab() {
    await Promise.all([loadDrifts(), loadChart(), loadHistoryTable()]);
}

async function loadDrifts() {
    try {
        const res = await fetch(`${API_BASE}/api/drift`);
        const data = await res.json();
        const container = document.getElementById("driftAlerts");
        container.innerHTML = "";

        if (data.drifts && data.drifts.length > 0) {
            data.drifts.forEach((d, i) => {
                const card = document.createElement("div");
                card.className = "drift-card";
                card.style.animationDelay = `${i * 0.08}s`;
                card.innerHTML = `
                    <span class="drift-icon">⚡</span>
                    <div class="drift-info">
                        <div class="drift-file">${escapeHtml(d.file)} · <code>${escapeHtml(d.pattern)}</code></div>
                        <div class="drift-change">
                            <span class="risk-badge ${d.from.toLowerCase()}" style="font-size:0.65rem;padding:1px 6px;">${d.from}</span>
                            <span class="drift-arrow"> → </span>
                            <span class="risk-badge ${d.to.toLowerCase()}" style="font-size:0.65rem;padding:1px 6px;">${d.to}</span>
                        </div>
                    </div>
                `;
                container.appendChild(card);
            });
        }
    } catch {}
}

async function loadChart() {
    try {
        const res = await fetch(`${API_BASE}/api/chart?repo=https://gitlab.com/demo/acme-payments`);
        const data = await res.json();
        const chartArea = document.getElementById("chartArea");
        const chartEmpty = document.getElementById("chartEmpty");

        if (data.chart && data.chart.length > 0) {
            chartArea.style.display = "block";
            chartEmpty.classList.remove("active");
            drawChart(data.chart);
        } else {
            chartArea.style.display = "none";
            chartEmpty.classList.add("active");
        }
    } catch {
        document.getElementById("chartArea").style.display = "none";
        document.getElementById("chartEmpty").classList.add("active");
    }
}

function drawChart(chartData) {
    const canvas = document.getElementById("riskChart");
    const ctx = canvas.getContext("2d");

    // Set canvas size
    const container = canvas.parentElement;
    canvas.width = container.offsetWidth;
    canvas.height = 250;

    const w = canvas.width;
    const h = canvas.height;
    const padL = 50, padR = 20, padT = 20, padB = 40;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;

    ctx.clearRect(0, 0, w, h);

    // Find max
    const maxVal = Math.max(
        ...chartData.map(d => Math.max(d.critical, d.high, d.medium, d.low)),
        1
    );

    const colors = {
        critical: "#ff3b5c",
        high:     "#ff8c42",
        medium:   "#ffd43b",
        low:      "#3bf08a",
    };

    // Draw grid lines
    ctx.strokeStyle = "rgba(56, 68, 100, 0.2)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = padT + (plotH / 4) * i;
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(w - padR, y);
        ctx.stroke();

        // Y-axis labels
        ctx.fillStyle = "#545d68";
        ctx.font = "11px 'Outfit'";
        ctx.textAlign = "right";
        ctx.fillText(Math.round(maxVal - (maxVal / 4) * i), padL - 8, y + 4);
    }

    // Draw lines for each risk level
    ["low", "medium", "high", "critical"].forEach(key => {
        ctx.beginPath();
        ctx.strokeStyle = colors[key];
        ctx.lineWidth = 2;
        ctx.lineJoin = "round";

        chartData.forEach((d, i) => {
            const x = padL + (plotW / (chartData.length - 1 || 1)) * i;
            const y = padT + plotH - (d[key] / maxVal) * plotH;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();

        // Draw dots
        chartData.forEach((d, i) => {
            const x = padL + (plotW / (chartData.length - 1 || 1)) * i;
            const y = padT + plotH - (d[key] / maxVal) * plotH;
            ctx.beginPath();
            ctx.arc(x, y, 3, 0, Math.PI * 2);
            ctx.fillStyle = colors[key];
            ctx.fill();
        });
    });

    // X-axis labels
    ctx.fillStyle = "#545d68";
    ctx.font = "10px 'Outfit'";
    ctx.textAlign = "center";
    chartData.forEach((d, i) => {
        const x = padL + (plotW / (chartData.length - 1 || 1)) * i;
        ctx.fillText(d.date, x, h - 8);
    });
}

async function loadHistoryTable() {
    try {
        const res = await fetch(`${API_BASE}/api/history`);
        const data = await res.json();
        const tbody = document.getElementById("historyTableBody");
        tbody.innerHTML = "";

        if (data.scans && data.scans.length > 0) {
            data.scans.forEach(scan => {
                const s = scan.summary || {};
                const date = scan.scanned_at ? new Date(scan.scanned_at).toLocaleString() : "—";
                const repo = scan.repo || "—";
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${date}</td>
                    <td style="font-family:var(--font-mono);font-size:0.78rem;color:var(--text-code)">${escapeHtml(repo)}</td>
                    <td>${scan.total || 0}</td>
                    <td style="color:var(--risk-critical)">${s.critical || 0}</td>
                    <td style="color:var(--risk-high)">${s.high || 0}</td>
                    <td style="color:var(--risk-medium)">${s.medium || 0}</td>
                    <td style="color:var(--risk-low)">${s.low || 0}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch {}
}

async function seedDemoData() {
    try {
        setStatus("Seeding...", "scanning");
        const res = await fetch(`${API_BASE}/api/seed`, { method: "POST" });
        const data = await res.json();
        if (data.status === "ok") {
            setStatus("Seeded", "ready");
            await loadHistoryTab();
        } else {
            setStatus("Seed Failed", "error");
        }
    } catch (err) {
        setStatus("Offline", "error");
    }
}

// nhi identity index

async function loadIndexTab() {
    try {
        const res = await fetch(`${API_BASE}/api/nhis`);
        const data = await res.json();
        const container = document.getElementById("nhiList");
        const statsEl = document.getElementById("indexStats");
        container.innerHTML = "";

        const allNhis = data.nhis || [];
        // Only show active/unresolved NHIs in the central identity index
        const nhis = allNhis.filter(n => n.status !== "REMEDIATED" && n.current_risk !== "RESOLVED");

        if (nhis.length === 0) {
            container.innerHTML = `<div class="empty-state"><div class="empty-icon">🗂️</div><h3>No NHIs tracked yet</h3><p>Run scans or seed demo data to populate the index.</p></div>`;
            statsEl.innerHTML = "";
            return;
        }

        // Stats
        const counts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
        nhis.forEach(n => {
            const r = n.current_risk || "UNKNOWN";
            if (counts[r] !== undefined) counts[r]++;
        });

        statsEl.innerHTML = `
            <div class="index-stat"><span class="count" style="color:var(--risk-critical)">${counts.CRITICAL}</span> Critical</div>
            <div class="index-stat"><span class="count" style="color:var(--risk-high)">${counts.HIGH}</span> High</div>
            <div class="index-stat"><span class="count" style="color:var(--risk-medium)">${counts.MEDIUM}</span> Medium</div>
            <div class="index-stat"><span class="count" style="color:var(--risk-low)">${counts.LOW}</span> Low</div>
            <div class="index-stat"><span class="count" style="color:var(--text-primary)">${nhis.length}</span> Total</div>
        `;

        // Sort by risk
        const riskOrder = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, UNKNOWN: 4 };
        nhis.sort((a, b) => (riskOrder[a.current_risk] || 4) - (riskOrder[b.current_risk] || 4));

        // Render NHI cards
        nhis.forEach((nhi, i) => {
            const risk = nhi.current_risk || "UNKNOWN";
            const riskClass = risk.toLowerCase();
            const history = nhi.history || [];
            let driftBadge = "";
            if (history.length >= 2) {
                const prev = history[history.length - 2].risk;
                const curr = history[history.length - 1].risk;
                if (prev !== curr) {
                    driftBadge = `<span class="nhi-drift-badge">⚡ ${prev} → ${curr}</span>`;
                }
            }

            // Build mini timeline
            let timeline = "";
            if (history.length > 0) {
                const riskColors = {
                    CRITICAL: "var(--risk-critical)",
                    HIGH:     "var(--risk-high)",
                    MEDIUM:   "var(--risk-medium)",
                    LOW:      "var(--risk-low)",
                    UNKNOWN:  "var(--risk-unknown)",
                };
                const riskHeights = { CRITICAL: 100, HIGH: 75, MEDIUM: 50, LOW: 25, UNKNOWN: 10 };
                timeline = '<div class="history-timeline">' +
                    history.map(h =>
                        `<div class="timeline-bar" style="height:${riskHeights[h.risk] || 10}%;background:${riskColors[h.risk] || riskColors.UNKNOWN}" title="${h.risk} — ${h.scanned_at || ''}"></div>`
                    ).join("") +
                    '</div>';
            }

            const card = document.createElement("div");
            card.className = "nhi-card";
            card.style.animationDelay = `${i * 0.05}s`;
            card.innerHTML = `
                <div class="nhi-header" onclick="this.closest('.nhi-card').classList.toggle('open')">
                    <span class="risk-badge ${riskClass}">${risk}</span>
                    <span class="nhi-file">${escapeHtml(nhi.file || "?")} · <code>${escapeHtml(nhi.pattern || "?")}</code></span>
                    ${driftBadge}
                    <span class="nhi-chevron">▶</span>
                </div>
                <div class="nhi-body">
                    <div class="nhi-details">
                        <div class="detail-row">
                            <span class="detail-label">Repo</span>
                            <span class="detail-value"><code>${escapeHtml(nhi.repo || "—")}</code></span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Type</span>
                            <span class="detail-value">${escapeHtml(nhi.type || "—")}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Action</span>
                            <span class="detail-value">${escapeHtml(nhi.action || "—")}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label" style="color: var(--risk-critical);">Breach Cost</span>
                            <span class="detail-value" style="color: var(--risk-critical); font-weight: 600;">💸 ${escapeHtml(nhi.breach_cost || "N/A")} USD (Est.)</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label" style="color: var(--risk-high);">Blast Radius</span>
                            <span class="detail-value" style="color: var(--risk-high); font-weight: 500;">💥 ${escapeHtml(nhi.blast_radius || "N/A")}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">First Seen</span>
                            <span class="detail-value">${nhi.first_seen ? new Date(nhi.first_seen).toLocaleString() : "—"}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Last Seen</span>
                            <span class="detail-value">${nhi.last_seen ? new Date(nhi.last_seen).toLocaleString() : "—"}</span>
                        </div>
                        <div class="nhi-history">
                            <h4>Risk Timeline (${history.length} scan${history.length !== 1 ? 's' : ''})</h4>
                            ${timeline}
                        </div>
                    </div>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (err) {
        document.getElementById("nhiList").innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><h3>Could not load NHI Index</h3><p>${escapeHtml(err.message)}</p></div>`;
    }
}

// download results as csv

function exportCSV() {
    if (!scanResults || !scanResults.findings) return;

    const headers = ["file", "line", "pattern", "risk", "type", "content", "reason", "action"];
    const rows = scanResults.findings.map(f =>
        headers.map(h => `"${(f[h] || "").toString().replace(/"/g, '""')}"`).join(",")
    );
    const csv = [headers.join(","), ...rows].join("\n");

    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `nhi-scan-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
}

// basic helpers

function showProgress() {
    const el = document.getElementById("progressContainer");
    el.classList.add("active");
    updateProgress(0, "Initializing scan...");
}

function hideProgress() {
    document.getElementById("progressContainer").classList.remove("active");
}

function updateProgress(pct, text) {
    document.getElementById("progressFill").style.width = pct + "%";
    document.getElementById("progressText").textContent = text;
}

function hideResults() {
    document.getElementById("statsGrid").classList.remove("active");
    document.getElementById("criticalAlert").classList.remove("active");
    document.getElementById("findingsContainer").classList.remove("active");
    document.getElementById("emptyState").classList.remove("hidden");
    document.getElementById("metricsDashboard").style.display = "none";
}

function showError(msg, showBackendTip = false) {
    const list = document.getElementById("findingsList");
    document.getElementById("findingsContainer").classList.add("active");
    document.getElementById("emptyState").classList.add("hidden");
    
    let tipHtml = "";
    if (showBackendTip) {
        tipHtml = `<p style="color:var(--text-muted);font-size:0.78rem;margin-top:8px;">Make sure the backend is running: <code>python backend/server.py</code></p>`;
    }
    
    list.innerHTML = `
        <div style="background:rgba(255,59,92,0.06);border:1px solid rgba(255,59,92,0.25);border-radius:10px;padding:24px;text-align:center;">
            <p style="color:var(--risk-critical);font-weight:600;margin-bottom:6px;">⚠️ Scan Failed</p>
            <p style="color:var(--text-secondary);font-size:0.85rem;">${escapeHtml(msg)}</p>
            ${tipHtml}
        </div>
    `;
}

function shakeElement(el) {
    el.style.animation = "none";
    el.offsetHeight; // trigger reflow
    el.style.animation = "shake 0.4s ease";
    el.style.borderColor = "var(--risk-critical)";
    setTimeout(() => {
        el.style.borderColor = "";
        el.style.animation = "";
    }, 1000);
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// secret remediation logic

function extractSecretValue(content) {
    let parts = content.split(/[=:]/);
    if (parts.length < 2) return content.trim();
    let val = parts.slice(1).join('=').trim();
    val = val.replace(/^['"`]|['"`]$/g, '');
    return val;
}

function updateRemediationStatus(box, msg) {
    const msgEl = box.querySelector(".status-msg");
    if (msgEl) msgEl.textContent = msg;
}

// Add shake keyframes dynamically
const shakeStyle = document.createElement("style");
shakeStyle.textContent = `
    @keyframes shake {
        0%, 100% { transform: translateX(0); }
        20% { transform: translateX(-6px); }
        40% { transform: translateX(6px); }
        60% { transform: translateX(-4px); }
        80% { transform: translateX(4px); }
    }
`;
document.head.appendChild(shakeStyle);

// new helpers for loading projects and metrics

async function loadGitLabProjects() {
    const select = document.getElementById("repoSelect");
    try {
        const res = await fetch(`${API_BASE}/api/gitlab/projects`);
        const data = await res.json();
        if (data.status === "ok" && data.projects && data.projects.length > 0) {
            data.projects.forEach(p => {
                const opt = document.createElement("option");
                opt.value = p.url;
                opt.textContent = p.name;
                select.appendChild(opt);
            });
        }
    } catch (err) {
        console.warn("Failed to load GitLab projects", err);
    }
}

function selectRepo(val) {
    const input = document.getElementById("repoUrl");
    if (val && val !== "demo") {
        input.value = val;
    } else if (val === "demo") {
        input.value = "";
    }
}

async function loadMetrics(repo) {
    const dashboard = document.getElementById("metricsDashboard");
    try {
        const res = await fetch(`${API_BASE}/api/metrics?repo=${encodeURIComponent(repo)}`);
        const data = await res.json();
        if (data.status === "ok" && data.metrics) {
            const m = data.metrics;
            
            // Render Health Score & Grade
            document.getElementById("scoreVal").textContent = m.score;
            document.getElementById("scoreGrade").textContent = m.grade;
            
            // SVG stroke dash offset calculation
            // dasharray = 213.6 (2 * PI * r, r=34)
            const offset = 213.6 - (213.6 * m.score) / 100;
            const ring = document.getElementById("scoreRingFill");
            ring.style.strokeDashoffset = offset;
            
            // Change ring color based on score
            if (m.score >= 90) ring.style.stroke = "var(--risk-low)";
            else if (m.score >= 70) ring.style.stroke = "var(--risk-medium)";
            else if (m.score >= 50) ring.style.stroke = "var(--risk-high)";
            else ring.style.stroke = "var(--risk-critical)";
            
            // Render Remediation Rate & MTTR
            document.getElementById("remedRateVal").textContent = `${m.remediation_rate}%`;
            document.getElementById("mttrVal").textContent = `${m.mttr_hours}h`;
            
            dashboard.style.display = "block";
        }
    } catch (err) {
        console.warn("Failed to load repo metrics", err);
        dashboard.style.display = "none";
    }
}

async function previewRemediation(index) {
    const box = document.getElementById(`remed-${index}`);
    box.innerHTML = `
        <div class="remediation-status">
            <span class="spinner">⏳</span>
            <span class="status-msg">Gemini is analyzing context and generating fix patch...</span>
        </div>
    `;
    
    const finding = scanResults.findings[index];
    const file = finding.file;
    const line = finding.line;
    const content = finding.content;
    const pattern = finding.pattern;
    
    let secretValue = extractSecretValue(content);
    let cleanFile = file.replace(/[^a-zA-Z0-9]/g, '_');
    let secretName = `SECRET_${cleanFile}_L${line}`.toUpperCase();
    
    let placeholder = `env.${secretName}`;
    if (file.endsWith('.py')) {
        placeholder = `os.environ['${secretName}']`;
    } else if (file.endsWith('.js') || file.endsWith('.ts')) {
        placeholder = `process.env.${secretName}`;
    } else if (file.endsWith('.yml') || file.endsWith('.yaml')) {
        placeholder = `\${${secretName}}`;
    }

    try {
        const repoUrl = scanResults ? scanResults.repo : "https://gitlab.com/demo/acme-payments";
        
        const res = await fetch(`${API_BASE}/api/remediate/generate-patch`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                repo_url: repoUrl,
                file_path: file,
                line: line,
                secret_value: secretValue,
                secret_placeholder: placeholder
            })
        });
        
        const data = await res.json();
        if (data.status !== "ok") {
            throw new Error(data.message || "Failed to generate patch");
        }
        
        const patch = data.patch;
        
        let diffLines = patch.code_patch.split('\n');
        let diffHtml = diffLines.map(dl => {
            if (dl.startsWith('-')) {
                return `<span class="diff-line del">${escapeHtml(dl)}</span>`;
            } else if (dl.startsWith('+')) {
                return `<span class="diff-line add">${escapeHtml(dl)}</span>`;
            }
            return `<span class="diff-line">${escapeHtml(dl)}</span>`;
        }).join('');
        
        let wifHtml = "";
        if (patch.wif_recommendation && !patch.wif_recommendation.startsWith("No Workload Identity")) {
            wifHtml = `
                <div class="wif-recommendation-container" style="margin-top: 10px;">
                    <h4><span>☁️</span> Google Cloud Workload Identity Federation Migration Guide</h4>
                    <p class="wif-text">To eliminate hardcoded service account keys, configure Workload Identity Federation. This allows GitLab workloads to authenticate directly via IAM without private keys.</p>
                    <div class="wif-commands">${escapeHtml(patch.wif_recommendation)}</div>
                </div>
            `;
        }
        
        box.innerHTML = `
            <div class="patch-preview-container">
                <p class="patch-explanation"><strong>Gemini Explanation:</strong> ${escapeHtml(patch.explanation)}</p>
                
                <div class="diff-view-block">
                    ${diffHtml}
                </div>
                
                ${wifHtml}
                
                <div style="display: flex; gap: 10px; margin-top: 8px;">
                    <button class="btn-remediate" onclick="applyRemediation(${index})">
                        <span>🛡️</span> Apply Code Fix & Store Secret
                    </button>
                    <button class="btn-remediate-preview" style="background:transparent; border-color:var(--border-subtle); color:var(--text-secondary)" onclick="resetRemediation(${index})">
                        Cancel
                    </button>
                </div>
            </div>
        `;
    } catch (err) {
        box.innerHTML = `
            <div class="remediation-error">
                <p>❌ AI Analysis failed: ${err.message}</p>
                <button class="btn-remediate-retry" onclick="previewRemediation(${index})">Retry</button>
            </div>
        `;
    }
}

async function applyRemediation(index) {
    const box = document.getElementById(`remed-${index}`);
    box.innerHTML = `
        <div class="remediation-status">
            <span class="spinner">⏳</span>
            <span class="status-msg">Migrating secret and opening merge/pull request...</span>
        </div>
    `;
    
    const finding = scanResults.findings[index];
    const file = finding.file;
    const line = finding.line;
    const content = finding.content;
    
    let secretValue = extractSecretValue(content);
    let cleanFile = file.replace(/[^a-zA-Z0-9]/g, '_');
    let secretName = `SECRET_${cleanFile}_L${line}`.toUpperCase();
    
    let placeholder = `env.${secretName}`;
    if (file.endsWith('.py')) {
        placeholder = `os.environ['${secretName}']`;
    } else if (file.endsWith('.js') || file.endsWith('.ts')) {
        placeholder = `process.env.${secretName}`;
    } else if (file.endsWith('.yml') || file.endsWith('.yaml')) {
        placeholder = `\${${secretName}}`;
    }
    
    try {
        const repoUrl = scanResults ? scanResults.repo : "https://gitlab.com/demo/acme-payments";
        const isGitHub = repoUrl.toLowerCase().includes("github.com");
        const platformName = isGitHub ? "GitHub" : "GitLab";
        const actionName = isGitHub ? "Pull Request" : "Merge Request";
        
        updateRemediationStatus(box, "Migrating secret to GCP Secret Manager...");
        const smRes = await fetch(`${API_BASE}/api/remediate/secret-manager`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                secret_name: secretName,
                secret_value: secretValue
            })
        });
        const smData = await smRes.json();
        
        updateRemediationStatus(box, `Creating branch and committing fix to ${platformName}...`);
        const gitRes = await fetch(`${API_BASE}/api/remediate/gitlab-mr`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                repo_url: repoUrl,
                file_path: file,
                line: line,
                secret_value: secretValue,
                secret_placeholder: placeholder
            })
        });
        const gitData = await gitRes.json();
        
        const successMessage = gitData.message || `Secret successfully stored in Google Secret Manager and replacement ${actionName} opened in ${platformName}.`;
        
        box.innerHTML = `
            <div class="remediation-success">
                <p class="success-title">🛡️ Remediation Complete!</p>
                <p class="success-desc">${escapeHtml(successMessage)}</p>
                <div class="remediation-links">
                    <a href="${gitData.mr_url}" target="_blank" class="mr-link-btn">
                        <span>🚀</span> View ${platformName} ${actionName}
                    </a>
                </div>
                <div class="secret-ref-box">
                    <span class="ref-label">Secret Manager Path:</span>
                    <code>${smData.secret_path}</code>
                </div>
            </div>
        `;
        
        await loadMetrics(repoUrl);
    } catch (err) {
        box.innerHTML = `
            <div class="remediation-error">
                <p>❌ Remediation failed: ${err.message}</p>
                <button class="btn-remediate-retry" onclick="applyRemediation(${index})">Retry</button>
            </div>
        `;
    }
}

function resetRemediation(index) {
    const box = document.getElementById(`remed-${index}`);
    box.innerHTML = `
        <button class="btn-remediate-preview" onclick="previewRemediation(${index})">
            <span>🤖</span> Ask Gemini Remediation Assistant
        </button>
    `;
}

function showProfileRepos(message, repos) {
    const list = document.getElementById("findingsList");
    document.getElementById("findingsContainer").classList.add("active");
    document.getElementById("emptyState").classList.add("hidden");
    
    let buttonsHtml = "";
    if (repos && repos.length > 0) {
        buttonsHtml = repos.map(r => `
            <button class="btn-demo" style="width:100%; text-align:left; justify-content:flex-start; margin-bottom:8px; font-family:var(--font-mono); font-size:0.85rem;" onclick="scanSelectedRepo('${escapeHtml(r)}')">
                <span>📁</span> ${escapeHtml(r)}
            </button>
        `).join('');
    } else {
        buttonsHtml = `<p style="color:var(--text-secondary); font-size:0.85rem; text-align:center; padding:12px;">No public repositories found for this profile.</p>`;
    }
    
    list.innerHTML = `
        <div style="background:rgba(88,166,255,0.06);border:1px solid rgba(88,166,255,0.25);border-radius:10px;padding:24px;">
            <p style="color:var(--accent-blue);font-weight:600;margin-bottom:12px;">📋 Profile Page Detected</p>
            <p style="color:var(--text-primary);font-size:0.85rem;margin-bottom:16px;">${escapeHtml(message)}</p>
            <div style="display:flex; flex-direction:column; gap:4px;">
                ${buttonsHtml}
            </div>
        </div>
    `;
}

function scanSelectedRepo(repoUrl) {
    document.getElementById("repoUrl").value = repoUrl;
    startScan();
}

