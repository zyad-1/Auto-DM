/**
 * Dashboard SPA — Campaigns overview, Settings (with OAuth), Error Logs
 */
(function () {
    "use strict";
    const $ = s => document.querySelector(s);
    const $$ = s => [...document.querySelectorAll(s)];
    function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
    function timeAgo(iso) { if (!iso) return ""; const d = Math.floor((Date.now() - new Date(iso)) / 1000); if (d < 60) return "just now"; if (d < 3600) return Math.floor(d/60) + "m ago"; if (d < 86400) return Math.floor(d/3600) + "h ago"; return Math.floor(d/86400) + "d ago"; }
    function toast(msg, type = "success") { const c = $("#toast-container"), el = document.createElement("div"); el.className = "toast toast-" + type; el.textContent = msg; c.appendChild(el); setTimeout(() => { el.classList.add("hiding"); setTimeout(() => el.remove(), 300); }, 3500); }
    function fmtFollowers(n) { if (!n) return "0"; if (n >= 1000000) return (n/1000000).toFixed(1) + "M"; if (n >= 1000) return (n/1000).toFixed(1) + "K"; return String(n); }
    async function api(path, opts = {}) {
        const res = await fetch("/api" + path, { headers: { "Content-Type": "application/json", ...(opts.headers || {}) }, ...opts });
        if (res.status === 401) { window.location.href = "/login"; return; }
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Request failed");
        return data;
    }

    /* Tabs */
    $$(".nav-btn[data-tab]").forEach(btn => {
        btn.addEventListener("click", () => {
            $$(".nav-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            $$(".tab-panel").forEach(p => p.classList.remove("active"));
            $("#tab-" + btn.dataset.tab).classList.add("active");
            $("#sidebar").classList.remove("open");
            if (btn.dataset.tab === "logs") loadErrorLogs();
        });
    });

    /* URL params — tab, OAuth status messages */
    const params = new URLSearchParams(window.location.search);
    if (params.get("tab")) {
        const tabBtn = $('[data-tab="' + params.get("tab") + '"]');
        if (tabBtn) tabBtn.click();
    }
    if (params.get("status") === "connected") {
        const username = params.get("username");
        toast("✅ @" + (username || "account") + " connected successfully!");
        history.replaceState(null, "", "/dashboard?tab=settings");
    }
    if (params.get("status") === "refreshed") {
        toast("Token refreshed! Valid for 60 more days");
        history.replaceState(null, "", "/dashboard?tab=settings");
    }
    if (params.get("error")) {
        toast("Connection failed: " + params.get("error"), "error");
        history.replaceState(null, "", "/dashboard?tab=settings");
    }

    /* Mobile + Logout */
    $("#hamburger").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
    $("#btn-logout").addEventListener("click", async () => { await fetch("/api/auth/logout", { method: "POST" }); window.location.href = "/login"; });

    /* Health */
    async function checkHealth() { try { const d = await fetch("/health").then(r => r.json()); $(".status-dot").className = "status-dot " + (d.status === "ok" ? "online" : "offline"); $(".status-text").textContent = d.status === "ok" ? "System Online" : "Offline"; } catch { $(".status-dot").className = "status-dot offline"; $(".status-text").textContent = "Offline"; } }
    checkHealth(); setInterval(checkHealth, 30000);

    /* ═══ Settings & OAuth ═══ */
    let configData = null;
    let bannerDismissed = false;
    
    // Add window.currentUser globally
    window.currentUser = null;
    
    async function fetchUserContext() {
        try {
            const res = await fetch('/api/auth/me');
            if (res.ok) {
                const user = await res.json();
                window.currentUser = user;
                
                // Add admin nav link if applicable
                if (user.role === 'admin' && !document.querySelector('a[href="/admin"]')) {
                    const nav = document.getElementById('sidebar-nav-container') || document.querySelector('.sidebar-nav');
                    if (nav) {
                        const adminLink = document.createElement('a');
                        adminLink.className = 'nav-btn';
                        adminLink.href = '/admin';
                        // Check if we are currently on the admin page
                        if (window.location.pathname === '/admin') adminLink.classList.add('active');
                        adminLink.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg><span>Admin Panel</span>`;
                        nav.appendChild(adminLink);
                    }
                }
                
                renderSidebarAccount();
            }
        } catch(e) {}
    }
    
    // Call it immediately
    fetchUserContext();

    async function loadSettings() {
        try {
            configData = await api("/config");
            $("#token-masked").textContent = configData.access_token_masked || "Not set";
            $("#input-page-id").value = configData.page_id || "";
            $("#input-ig-account-id").value = configData.instagram_account_id || "";
            renderOAuthCard();
            renderSidebarAccount();
            renderExpiryBanner();
        } catch {}
    }
    loadSettings();

    /* OAuth Card Rendering */
    function renderOAuthCard() {
        const container = $("#oauth-card-container");
        if (!container || !configData) return;

        if (configData.oauth_connected) {
            // ── Connected State ──
            const statusLabel = configData.token_status === "expired" ? "Expired" :
                                configData.token_status === "expiring" ? "Expiring soon" : "Active";
            const statusDotCls = configData.token_status || "active";
            const daysText = configData.token_days_left !== null ?
                (configData.token_days_left > 0 ? "Expires in " + configData.token_days_left + " days" : "Expired") : "";

            const avatarInner = configData.ig_profile_pic
                ? '<img src="' + esc(configData.ig_profile_pic) + '" alt="" onerror="this.parentElement.innerHTML=\'<div class=ig-profile-avatar-placeholder>' + esc((configData.ig_username || "?")[0].toUpperCase()) + '</div>\'">'
                : '<div class="ig-profile-avatar-placeholder">' + esc((configData.ig_username || "?")[0].toUpperCase()) + '</div>';

            container.innerHTML = `
            <div class="oauth-card glass-card">
                <div class="oauth-connected">
                    <div class="oauth-connected-header">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                        Connected Account
                    </div>
                    <div class="ig-profile-row">
                        <div class="ig-profile-avatar">${avatarInner}</div>
                        <div class="ig-profile-info">
                            <div class="ig-profile-username">@${esc(configData.ig_username || "unknown")}</div>
                            <div class="ig-profile-meta">
                                <span class="badge badge-type">${esc(configData.ig_account_type || "Business")}</span>
                                <span>👥 ${fmtFollowers(configData.ig_followers)} followers</span>
                            </div>
                        </div>
                    </div>
                    <div class="ig-token-row">
                        <span class="token-dot ${statusDotCls}"></span>
                        <span>Token: <strong>${statusLabel}</strong></span>
                        <span style="margin-left:auto">${daysText}</span>
                    </div>
                    <div class="oauth-actions">
                        <a href="/auth/instagram/refresh" class="btn btn-sm btn-refresh">⟳ Refresh Token</a>
                        <button class="btn btn-sm btn-disconnect" id="btn-disconnect-ig">Disconnect</button>
                    </div>
                </div>
            </div>`;

            // Disconnect handler
            const dcBtn = $("#btn-disconnect-ig");
            if (dcBtn) {
                dcBtn.addEventListener("click", async () => {
                    if (!confirm("Disconnect @" + (configData.ig_username || "") + "? Your automations will be paused.")) return;
                    try {
                        await fetch("/auth/instagram/disconnect", { method: "POST" });
                        toast("Instagram disconnected");
                        loadSettings();
                    } catch { toast("Disconnect failed", "error"); }
                });
            }
        } else {
            // ── Not Connected State ──
            container.innerHTML = `
            <div class="oauth-card glass-card">
                <div class="oauth-not-connected">
                    <div class="oauth-ig-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="5"/><circle cx="17.5" cy="6.5" r="1.5" fill="currentColor" stroke="none"/></svg>
                    </div>
                    <h3 class="oauth-title">Connect Instagram Account</h3>
                    <p class="oauth-subtitle">Connect your Instagram Business or Creator account automatically with one click.</p>
                    <a href="/auth/instagram" class="ig-connect-btn">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="5"/><circle cx="17.5" cy="6.5" r="1.5" fill="currentColor" stroke="none"/></svg>
                        Connect with Instagram
                    </a>
                    <div class="or-divider">or connect manually below</div>
                </div>
            </div>`;
        }
    }

    /* Sidebar Account Widget */
    function renderSidebarAccount() {
        const widget = $("#sidebar-account-widget");
        if (!widget || !configData) return;

        if (configData.oauth_connected && configData.ig_username) {
            const avatarInner = configData.ig_profile_pic
                ? '<img src="' + esc(configData.ig_profile_pic) + '" alt="">'
                : '<span style="color:#fff;font-size:.7rem;font-weight:700">' + esc(configData.ig_username[0].toUpperCase()) + '</span>';
            widget.innerHTML = `
            <div class="sidebar-account">
                <div class="sidebar-account-avatar">${avatarInner}</div>
                <div class="sidebar-account-info">
                    <div class="sidebar-account-name">@${esc(configData.ig_username)}</div>
                    <div class="sidebar-account-status">Instagram Connected</div>
                </div>
            </div>`;
        } else {
            widget.innerHTML = '<div class="sidebar-no-account">No IG account linked<br><a href="/auth/instagram">Connect →</a></div>';
        }
    }

    /* Token Expiry Banner */
    function renderExpiryBanner() {
        const container = $("#expiry-banner-container");
        if (!container || !configData || bannerDismissed) { if (container) container.innerHTML = ""; return; }

        if (configData.token_status === "expiring") {
            container.innerHTML = `
            <div class="expiry-banner banner-warning">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                <span class="banner-text">⚠️ Instagram token expires in <strong>${configData.token_days_left}</strong> days.</span>
                <a href="/auth/instagram/refresh" class="btn btn-sm btn-refresh">Refresh Now</a>
                <button class="banner-close" id="banner-dismiss"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
            </div>`;
            $("#banner-dismiss")?.addEventListener("click", () => { bannerDismissed = true; container.innerHTML = ""; });
        } else if (configData.token_status === "expired") {
            container.innerHTML = `
            <div class="expiry-banner banner-error">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                <span class="banner-text">❌ Token expired. Automations paused.</span>
                <a href="/auth/instagram" class="btn btn-sm btn-primary">Reconnect Now</a>
                <button class="banner-close" id="banner-dismiss"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
            </div>`;
            $("#banner-dismiss")?.addEventListener("click", () => { bannerDismissed = true; container.innerHTML = ""; });
        } else {
            container.innerHTML = "";
        }
    }

    /* Multi-Page Selector (OAuth) */
    (function checkPageSelector() {
        if (!params.get("select_pages")) return;
        const expiresIn = params.get("expires_in") || "5184000";
        history.replaceState(null, "", "/dashboard?tab=settings");

        // Read pages from cookie
        let pages = [];
        try {
            const raw = decodeURIComponent(document.cookie.split("oauth_pages=")[1]?.split(";")[0] || "[]");
            pages = JSON.parse(raw);
        } catch { toast("Failed to read pages data", "error"); return; }

        if (!pages.length) return;

        const overlay = $("#page-selector-overlay");
        const list = $("#page-list");
        if (!overlay || !list) return;

        list.innerHTML = pages.map(p => `
            <div class="page-list-item" data-page-id="${esc(p.id)}" data-page-token="${esc(p.access_token || "")}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/></svg>
                <span class="page-name">${esc(p.name)}</span>
                <span class="page-id">${esc(p.id)}</span>
            </div>
        `).join("");

        overlay.classList.add("open");

        list.querySelectorAll(".page-list-item").forEach(item => {
            item.addEventListener("click", async () => {
                item.style.opacity = "0.5";
                item.style.pointerEvents = "none";
                try {
                    const res = await fetch("/auth/instagram/select-page", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            page_id: item.dataset.pageId,
                            page_access_token: item.dataset.pageToken,
                            expires_in: expiresIn,
                        }),
                    });
                    const data = await res.json();
                    if (data.success) {
                        overlay.classList.remove("open");
                        toast("✅ Instagram connected!");
                        loadSettings();
                    } else {
                        toast(data.error || "Failed", "error");
                        item.style.opacity = "1";
                        item.style.pointerEvents = "auto";
                    }
                } catch {
                    toast("Connection failed", "error");
                    item.style.opacity = "1";
                    item.style.pointerEvents = "auto";
                }
            });
        });

        $("#page-selector-close")?.addEventListener("click", () => overlay.classList.remove("open"));
    })();

    /* Settings Form (manual credentials) */
    $("#settings-form").addEventListener("submit", async e => {
        e.preventDefault();
        const p = { access_token: $("#input-access-token").value.trim(), page_id: $("#input-page-id").value.trim(), instagram_account_id: $("#input-ig-account-id").value.trim() };
        if (!p.access_token || !p.page_id || !p.instagram_account_id) { toast("Fill in all fields", "error"); return; }
        await api("/config", { method: "POST", body: JSON.stringify(p) });
        toast("Credentials saved"); $("#input-access-token").value = ""; loadSettings();
    });

    /* ═══ Campaigns (read-only overview) ═══ */
    let campaigns = [];
    function renderKw(kw) { return kw.split(",").map(k => k.trim()).filter(Boolean).map(k => '<span class="keyword-tag">' + esc(k) + '</span>').join(""); }
    function renderCampaigns() {
        const grid = $("#campaigns-grid"), empty = $("#empty-state");
        if (!campaigns.length) { grid.innerHTML = ""; empty.style.display = "block"; return; }
        empty.style.display = "none";
        grid.innerHTML = campaigns.map(c => `
            <div class="campaign-card" data-id="${c.id}">
                <div class="campaign-card-header">
                    <div class="campaign-card-info">
                        <h3><span class="badge ${c.is_active ? "badge-active" : "badge-inactive"}">${c.is_active ? "Active" : "Inactive"}</span>
                        <span class="badge badge-type">${c.campaign_type === "story_reply" ? "Story" : "Comment"}</span>
                        ${c.cta_enabled ? '<span class="badge badge-cta">CTA</span>' : ""}
                        ${c.require_follow ? '<span class="badge badge-follow">Follow✓</span>' : ""}
                        Campaign #${c.id}</h3>
                        <span class="post-id-label">${c.campaign_type === "story_reply" ? "Story: " + esc(c.story_id || "Any") : "Post: " + esc(c.post_id || "—")}</span>
                    </div>
                    <div class="campaign-card-actions">
                        <button class="btn btn-sm btn-ghost" data-action="history" data-id="${c.id}">History</button>
                        <button class="btn btn-sm btn-ghost" data-action="test" data-id="${c.id}">Test</button>
                        <a href="/automation" class="btn btn-sm btn-ghost">Edit</a>
                    </div>
                </div>
                <div class="analytics-row">
                    <div class="analytics-stat"><span class="analytics-value">${c.trigger_count||0}</span><span class="analytics-label">Triggers</span></div>
                    <div class="analytics-stat"><span class="analytics-value">${c.reply_sent_count||0}</span><span class="analytics-label">Replies</span></div>
                    <div class="analytics-stat"><span class="analytics-value">${c.dm_sent_count||0}</span><span class="analytics-label">DMs</span></div>
                    <div class="analytics-stat stat-danger"><span class="analytics-value">${c.failed_count||0}</span><span class="analytics-label">Failed</span></div>
                </div>
                <div class="campaign-details">
                    <div class="campaign-detail"><div class="campaign-detail-label">Keywords</div><div class="campaign-detail-value">${renderKw(c.keywords)}</div></div>
                    <div class="campaign-detail"><div class="campaign-detail-label">DM Message</div><div class="campaign-detail-value">${esc(c.dm_message_text)}</div></div>
                </div>
            </div>`).join("");
        grid.querySelectorAll("[data-action]").forEach(btn => btn.addEventListener("click", handleAction));
    }
    async function loadCampaigns() { try { campaigns = await api("/campaigns"); renderCampaigns(); } catch {} }
    loadCampaigns();

    async function handleAction(e) {
        const btn = e.currentTarget, action = btn.dataset.action, id = +btn.dataset.id;
        if (action === "test") testCampaign(id);
        else if (action === "history") showHistory(id);
    }

    /* Test */
    async function testCampaign(id) {
        try {
            const r = await api("/campaigns/" + id + "/test", { method: "POST" });
            const cls = r.would_trigger ? "test-pass" : "test-fail";
            const icon = r.would_trigger ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>' : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
            let issues = "";
            if (r.issues && r.issues.length) issues = '<div class="test-issues"><h4>Issues:</h4><ul>' + r.issues.map(i => "<li>" + esc(i) + "</li>").join("") + "</ul></div>";
            $("#test-result").innerHTML = '<div class="test-status ' + cls + '">' + icon + '<span>' + (r.would_trigger ? "Would Trigger ✓" : "Would NOT Trigger ✗") + '</span></div><div class="test-details"><div class="test-detail-row"><span>Credentials</span><span class="' + (r.has_credentials ? 'check-yes' : 'check-no') + '">' + (r.has_credentials ? "✓" : "✗") + '</span></div><div class="test-detail-row"><span>IG Account ID</span><span class="' + (r.has_ig_account_id ? 'check-yes' : 'check-no') + '">' + (r.has_ig_account_id ? "✓" : "✗") + '</span></div></div>' + issues;
            $("#test-modal-overlay").classList.add("open");
        } catch {}
    }
    $("#test-modal-close").addEventListener("click", () => $("#test-modal-overlay").classList.remove("open"));
    $("#test-modal-overlay").addEventListener("click", e => { if (e.target === e.currentTarget) e.currentTarget.classList.remove("open"); });

    /* History */
    let currentHistoryId = null;
    async function showHistory(id) {
        currentHistoryId = id;
        const list = $("#history-list"), retryBtn = $("#btn-retry-all");
        $("#history-title").textContent = "Trigger History — Campaign #" + id;
        list.innerHTML = '<div class="post-grid-loading">Loading…</div>';
        $("#history-modal-overlay").classList.add("open");
        try {
            const triggers = await api("/campaigns/" + id + "/triggers");
            if (!triggers.length) { list.innerHTML = '<div class="post-grid-loading">No triggers recorded yet.</div>'; retryBtn.style.display = "none"; return; }
            const hasFailed = triggers.some(t => t.reply_status === "failed" || t.dm_status === "failed");
            retryBtn.style.display = hasFailed ? "inline-flex" : "none";
            list.innerHTML = triggers.map(t => {
                const f = t.reply_status === "failed" || t.dm_status === "failed";
                return '<div class="history-entry ' + (f ? "history-failed" : "") + '"><div class="history-entry-header"><span class="history-user">@' + esc(t.username) + '</span><span class="history-time">' + timeAgo(t.created_at) + '</span></div><p class="history-text">' + esc(t.comment_text) + '</p><div class="history-statuses"><span class="status-pill status-' + t.reply_status + '">Reply: ' + t.reply_status + '</span><span class="status-pill status-' + t.dm_status + '">DM: ' + t.dm_status + '</span>' + (f ? '<button class="btn btn-sm btn-danger-outline" data-retry-id="' + t.id + '">⟳ Retry</button>' : '') + '</div>' + (t.reply_error ? '<p class="history-error">Reply: ' + esc(t.reply_error) + '</p>' : '') + (t.dm_error ? '<p class="history-error">DM: ' + esc(t.dm_error) + '</p>' : '') + '</div>';
            }).join("");
            list.querySelectorAll("[data-retry-id]").forEach(btn => {
                btn.addEventListener("click", async () => { btn.disabled = true; btn.textContent = "Retrying…"; try { await api("/triggers/" + btn.dataset.retryId + "/retry", { method: "POST" }); toast("Retried"); showHistory(id); loadCampaigns(); } catch { btn.disabled = false; btn.textContent = "⟳ Retry"; } });
            });
        } catch { list.innerHTML = '<div class="post-grid-loading">Failed to load.</div>'; }
    }
    $("#btn-retry-all").addEventListener("click", async () => { if (!currentHistoryId || !confirm("Retry all failed?")) return; try { const r = await api("/campaigns/" + currentHistoryId + "/retry-all", { method: "POST" }); toast("Retried " + r.retried + " triggers"); loadCampaigns(); } catch {} });
    $("#history-modal-close").addEventListener("click", () => $("#history-modal-overlay").classList.remove("open"));
    $("#history-modal-overlay").addEventListener("click", e => { if (e.target === e.currentTarget) e.currentTarget.classList.remove("open"); });

    /* Error Logs */
    async function loadErrorLogs() {
        const container = $("#logs-container"), empty = $("#logs-empty");
        try {
            const logs = await api("/error-logs");
            if (!logs.length) { container.innerHTML = ""; empty.style.display = "block"; return; }
            empty.style.display = "none";
            container.innerHTML = logs.map(l => '<div class="log-entry log-' + l.level.toLowerCase() + '"><div class="log-header"><span class="log-badge log-badge-' + l.level.toLowerCase() + '">' + esc(l.level) + '</span><span class="log-source">' + esc(l.source) + '</span>' + (l.campaign_id ? '<span class="log-campaign">Campaign #' + l.campaign_id + '</span>' : '') + '<span class="log-time">' + timeAgo(l.created_at) + '</span></div><p class="log-message">' + esc(l.message) + '</p>' + (l.details ? '<pre class="log-details">' + esc(l.details) + '</pre>' : '') + '</div>').join("");
        } catch { container.innerHTML = '<div class="post-grid-loading">Failed to load.</div>'; }
    }
    $("#btn-clear-logs").addEventListener("click", async () => { if (!confirm("Clear all logs?")) return; await api("/error-logs", { method: "DELETE" }); toast("Logs cleared"); loadErrorLogs(); });

    document.addEventListener("keydown", e => { if (e.key === "Escape") { $("#test-modal-overlay").classList.remove("open"); $("#history-modal-overlay").classList.remove("open"); $("#page-selector-overlay").classList.remove("open"); } });
})();
