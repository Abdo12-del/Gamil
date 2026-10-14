/**
 * Gamil CloudPool — Unified Storage & Background Auto-Scaler Frontend Logic
 * يدعم:
 * 1. الوضع الموحد البسيط (Simple Unified Mode): يعرض فقط السعة الإجمالية، المساحة المستخدمة، وتقدم رفع الملفات.
 * 2. وضع المهندس المتقدم (Advanced Engineer Mode): يعرض تفاصيل الحسابات، خزنة التوسع التلقائي، وأدوات GitHub المدمجة.
 */

let state = {
  dashboard: null,
  accounts: [],
  files: [],
  duplicates: null,
  autoscale: null,
  selectedFolder: 'all',
  selectedAccount: 'all',
  activeTab: 'autoscale',
  simpleMode: true,
};

function formatBytes(bytes) {
  const n = Number(bytes) || 0;
  if (n === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(n) / Math.log(1024));
  const val = n / Math.pow(1024, i);
  return `${val.toFixed(i >= 2 ? 2 : 0)} ${units[i]}`;
}

function getFileIcon(mimeType, fileName) {
  const m = (mimeType || '').toLowerCase();
  const name = (fileName || '').toLowerCase();
  if (m.includes('chunk') || name.includes('.rclone_chunk.') || name.includes('[جزء ')) return '🧩';
  if (m.includes('pdf') || name.endsWith('.pdf')) return '📕';
  if (m.includes('video') || name.endsWith('.mp4')) return '🎬';
  if (m.includes('image') || name.endsWith('.png') || name.endsWith('.jpg')) return '🖼️';
  if (m.includes('document') || name.endsWith('.gdoc') || name.endsWith('.docx')) return '📝';
  if (m.includes('spreadsheet')) return '📊';
  if (m.includes('zip') || name.endsWith('.zip')) return '📦';
  return '📄';
}

function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  const el = document.createElement('div');
  el.className = `toast ${type === 'warn' ? 'warn' : type === 'error' ? 'error' : ''}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => {
    el.remove();
  }, 4500);
}

function toggleUiMode() {
  state.simpleMode = !state.simpleMode;
  const simpleView = document.getElementById('simpleUnifiedView');
  const advView = document.getElementById('advancedEngineerView');
  const btn = document.getElementById('modeToggleBtn');

  if (state.simpleMode) {
    simpleView.style.display = 'block';
    advView.style.display = 'none';
    btn.innerHTML = '🔧 عرض لوحة المهندس المتقدمة (التفاصيل التقنية)';
    btn.className = 'btn btn-emerald';
  } else {
    simpleView.style.display = 'none';
    advView.style.display = 'block';
    btn.innerHTML = '✨ العودة للواجهة الموحدة المبسطة';
    btn.className = 'btn btn-primary';
    loadAutoscaleStatus();
  }
}

function switchTab(tabName) {
  state.activeTab = tabName;
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });
  document.querySelectorAll('.tab-panel').forEach((panel) => {
    panel.classList.toggle('active', panel.id === `tab-${tabName}`);
  });

  if (tabName === 'autoscale') {
    loadAutoscaleStatus();
  } else if (tabName === 'upload') {
    runPlacementSimulation();
  } else if (tabName === 'dedupe') {
    loadDuplicates();
  } else if (tabName === 'rclone') {
    loadRcloneConfig();
  } else if (tabName === 'accounts') {
    loadAccountsDetails();
    renderApiQuotaMonitor();
  }
}

// ==================== تحديث كافة البيانات ====================

async function refreshAllData() {
  try {
    const [dashRes, accRes, autoRes] = await Promise.all([
      fetch('/api/dashboard'),
      fetch('/api/accounts'),
      fetch('/api/autoscale/status'),
    ]);
    state.dashboard = await dashRes.json();
    state.accounts = await accRes.json();
    state.autoscale = await autoRes.json();

    renderSimpleUnifiedBanner();
    renderPoolBanner();
    renderAlerts();
    renderSidebarFilters();
    populateAccountSelects();
    renderAuditLogs();
    renderAccountsCards();
    renderApiQuotaMonitor();
    renderAutoscalePanel();

    await Promise.all([loadFiles(), loadDuplicates()]);
  } catch (err) {
    console.error('Failed to refresh dashboard:', err);
  }
}

function renderSimpleUnifiedBanner() {
  if (!state.dashboard) return;
  const { pool } = state.dashboard;
  document.getElementById('simpleTotalAndFreeText').textContent = `السعة الإجمالية: ${formatBytes(pool.total_bytes)}`;
  document.getElementById('simpleUsedSummaryText').textContent = `المستخدم: ${formatBytes(pool.used_bytes)} (${pool.used_pct}%) • المتاح الفوري: ${formatBytes(pool.free_bytes)} (قابل للتوسع تلقائيًا)`;
  document.getElementById('simpleUnifiedProgressBar').style.width = `${Math.min(100, Math.max(2, pool.used_pct))}%`;
}

// ==================== الرفع السلس مع شريط تقدم حي وتوسع خلفي ====================

async function runSeamlessAnimatedUpload(fileName, sizeMb, virtualPath, targetAccountId = null) {
  const titleEl = document.getElementById('liveUploadTitle');
  const pctEl = document.getElementById('liveUploadPercent');
  const barEl = document.getElementById('liveUploadProgressBar');
  const statusEl = document.getElementById('liveUploadStatusText');

  titleEl.textContent = `جاري رفع: ${fileName} (${(sizeMb / 1024).toFixed(2)} GB)`;
  pctEl.textContent = '12%';
  barEl.style.width = '12%';
  statusEl.textContent = 'جاري تدفق البيانات وحساب البصمة الرقمية (Resumable Stream)...';

  await new Promise((r) => setTimeout(r, 320));
  pctEl.textContent = '48%';
  barEl.style.width = '48%';
  statusEl.textContent = 'جاري فحص السعة المتبقية وتأمين المساحة في الخلفية تلقائيًا...';

  const res = await fetch('/api/autoscale/upload-seamless', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      file_name: fileName,
      size_mb: sizeMb,
      virtual_path: virtualPath,
      target_account_id: targetAccountId,
    }),
  });
  const data = await res.json();

  await new Promise((r) => setTimeout(r, 320));
  pctEl.textContent = '100%';
  barEl.style.width = '100%';

  if (res.ok && data.success) {
    statusEl.textContent = data.message;
    showToast(data.message, 'success');
    await refreshAllData();
  } else {
    statusEl.textContent = data.detail || 'تعذر إكمال الرفع';
    showToast(data.detail || 'تعذر إكمال الرفع', 'error');
  }
}

async function handleSimpleModeFileUpload(e) {
  e.preventDefault();
  const fileInput = document.getElementById('simpleFileInput');
  if (!fileInput.files.length) return;
  const f = fileInput.files[0];
  const folder = document.getElementById('simpleFolderSelect').value;

  const titleEl = document.getElementById('liveUploadTitle');
  const pctEl = document.getElementById('liveUploadPercent');
  const barEl = document.getElementById('liveUploadProgressBar');
  const statusEl = document.getElementById('liveUploadStatusText');

  titleEl.textContent = `جاري رفع: ${f.name}`;
  pctEl.textContent = '35%';
  barEl.style.width = '35%';
  statusEl.textContent = 'جاري الرفع والتوجيه التلقائي في الخلفية...';

  const formData = new FormData();
  formData.append('file', f);
  formData.append('virtual_path', folder);
  formData.append('preferred_account_id', 'auto');
  formData.append('force_duplicate', 'false');

  const res = await fetch('/api/files/upload', {
    method: 'POST',
    body: formData,
  });
  const data = await res.json();

  pctEl.textContent = '100%';
  barEl.style.width = '100%';
  statusEl.textContent = data.message || 'اكتملت العملية';
  showToast(data.message || 'اكتمل الرفع', data.duplicate_blocked ? 'warn' : 'success');
  fileInput.value = '';
  await refreshAllData();
}

function syncSearchFromSimple() {
  const val = document.getElementById('simpleSearchInput').value;
  const advInput = document.getElementById('fileSearchInput');
  if (advInput) advInput.value = val;
  loadFiles();
}

// ==================== لوحة التوسع التلقائي وأدوات GitHub ====================

async function loadAutoscaleStatus() {
  const res = await fetch('/api/autoscale/status');
  state.autoscale = await res.json();
  renderAutoscalePanel();
}

function renderAutoscalePanel() {
  if (!state.autoscale) return;
  const standbyContainer = document.getElementById('standbyPoolListContainer');
  const driversContainer = document.getElementById('githubDriversContainer');
  const sessionsContainer = document.getElementById('resumableSessionsContainer');
  if (!standbyContainer || !driversContainer || !sessionsContainer) return;

  const standbyList = state.autoscale.standby_pool || [];
  standbyContainer.innerHTML = standbyList
    .map(
      (st) => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:0.6rem 0.85rem;background:var(--bg-surface);border:1px solid ${st.is_consumed ? '#10b981' : 'var(--border-color)'};border-radius:8px;margin-bottom:0.45rem;font-size:0.82rem;">
        <div>
          <strong>${st.name}</strong>
          <div style="font-size:0.74rem;color:var(--text-secondary);direction:ltr;text-align:right;">${st.email} • ${st.driver_tool}</div>
        </div>
        <div style="display:flex;align-items:center;gap:0.5rem;">
          <span style="font-weight:700;">+${formatBytes(st.quota_bytes)}</span>
          <span class="status-badge" style="background:${st.is_consumed ? 'rgba(16,185,129,0.2)' : 'rgba(59,130,246,0.18)'};color:${st.is_consumed ? '#34d399' : '#93c5fd'};">
            ${st.is_consumed ? '✅ تم تفعيله تلقائيًا' : '⏳ جاهز بالاحتياط'}
          </span>
        </div>
      </div>
    `
    )
    .join('');

  driversContainer.innerHTML = (state.autoscale.github_drivers || [])
    .map(
      (d) => `
      <div style="padding:0.6rem 0.8rem;background:var(--bg-surface);border:1px solid var(--border-color);border-radius:8px;margin-bottom:0.45rem;font-size:0.8rem;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <strong>🔗 ${d.name}</strong>
          <a href="${d.repo}" target="_blank" rel="noopener" class="hash-code" style="text-decoration:none;">GitHub ↗</a>
        </div>
        <div style="color:var(--text-secondary);font-size:0.76rem;margin-top:0.2rem;">${d.role}</div>
      </div>
    `
    )
    .join('');

  const sessions = state.autoscale.recent_sessions || [];
  if (sessions.length === 0) {
    sessionsContainer.innerHTML = `<div style="font-size:0.8rem;color:var(--text-muted);padding:0.75rem;background:var(--bg-surface);border-radius:8px;">لم يتم تسجيل جلسات توسع أثناء الرفع بعد — جرّب زر الرفع الاختباري (8.2 GB) لرؤية التوسع اللحظي.</div>`;
  } else {
    sessionsContainer.innerHTML = sessions
      .map(
        (s) => `
        <div style="padding:0.6rem 0.8rem;background:var(--bg-surface);border-right:3px solid ${s.autoscale_triggered ? '#10b981' : '#3b82f6'};border-radius:8px;margin-bottom:0.45rem;font-size:0.8rem;">
          <div style="display:flex;justify-content:space-between;">
            <strong>📄 ${s.file_name} (${formatBytes(s.total_bytes)})</strong>
            <span style="color:#34d399;font-weight:700;">100% مكتمل</span>
          </div>
          <div style="font-size:0.75rem;color:var(--text-secondary);margin-top:0.2rem;">
            ${s.autoscale_triggered ? '⚡ تم تفعيل توسعة مساحة تلقائية في الخلفية أثناء الرفع' : '✅ تم الاستيعاب ضمن السعة النشطة'} • عدد الشرائح الموزعة: ${(s.allocations || []).length}
          </div>
        </div>
      `
      )
      .join('');
  }
}

async function triggerManualBackgroundProvision() {
  const res = await fetch('/api/autoscale/provision-now', { method: 'POST' });
  const data = await res.json();
  if (res.ok && data.success) {
    showToast(data.message, 'success');
    await refreshAllData();
  }
}

async function submitStandbyAccount(e) {
  e.preventDefault();
  const name = document.getElementById('standbyNameInput').value.trim();
  const email = document.getElementById('standbyEmailInput').value.trim();
  const res = await fetch('/api/autoscale/standby', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, quota_gb: 15 }),
  });
  const data = await res.json();
  if (res.ok) {
    document.getElementById('standbyNameInput').value = '';
    document.getElementById('standbyEmailInput').value = '';
    showToast(data.message, 'success');
    await refreshAllData();
  }
}

// ==================== عرض لوحة التحكم المتقدمة والملفات ====================

function renderPoolBanner() {
  const { pool, accounts, settings } = state.dashboard;
  document.getElementById('statTotalPool').textContent = formatBytes(pool.total_bytes);
  document.getElementById('statAccountsCount').textContent = `مجمعة عبر ${pool.accounts_count} حسابات متصلة`;
  document.getElementById('statFreePool').textContent = formatBytes(pool.free_bytes);
  document.getElementById('statPolicyLabel').textContent = `سياسة التوجيه النشطة: ${settings.placement_policy.toUpperCase()}`;
  document.getElementById('statUsedPool').textContent = `${formatBytes(pool.used_bytes)} (${pool.used_pct}%)`;
  document.getElementById('statTotalFiles').textContent = `${pool.total_files} ملف مفهرس في قاعدة SQLite`;
  document.getElementById('statWastedDupes').textContent = formatBytes(pool.wasted_duplicate_bytes);
  document.getElementById('statDupesCount').textContent =
    pool.duplicate_groups_count > 0
      ? `في ${pool.duplicate_groups_count} مجموعات تكرار بالبصمة الرقمية`
      : 'لا توجد ملفات مكررة حاليًا ✨';

  document.getElementById('dedupeTabBadge').textContent = pool.duplicate_groups_count;
  document.getElementById('poolUtilizationText').textContent = `${pool.used_pct}% مستخدم من إجمالي التجمع (${formatBytes(pool.used_bytes)} من ${formatBytes(pool.total_bytes)})`;

  const bar = document.getElementById('segmentedPoolBar');
  const legend = document.getElementById('segmentedLegend');
  bar.innerHTML = '';
  legend.innerHTML = '';

  accounts.forEach((acc) => {
    const shareOfTotalPool = pool.total_bytes > 0 ? (acc.used_bytes / pool.total_bytes) * 100 : 0;
    const seg = document.createElement('div');
    seg.className = 'segment-item';
    seg.style.width = `${Math.max(shareOfTotalPool, 0.5)}%`;
    seg.style.backgroundColor = acc.color;
    seg.title = `${acc.name}: ${formatBytes(acc.used_bytes)} / ${formatBytes(acc.total_bytes)}`;
    bar.appendChild(seg);

    const leg = document.createElement('div');
    leg.className = 'legend-item';
    leg.innerHTML = `
      <span class="legend-dot" style="background: ${acc.color};"></span>
      <span><strong>${acc.name}</strong>: ${formatBytes(acc.used_bytes)} / ${formatBytes(acc.total_bytes)} (${acc.used_pct}%)</span>
    `;
    legend.appendChild(leg);
  });
}

function renderAlerts() {
  const container = document.getElementById('alertsContainer');
  const alerts = state.dashboard.alerts || [];
  container.innerHTML = '';

  alerts.forEach((al) => {
    const div = document.createElement('div');
    const cls = al.severity === 'high' ? 'alert-high' : al.severity === 'warning' ? 'alert-warning' : 'alert-info';
    div.className = `alert-item ${cls}`;

    let actionBtn = '';
    if (al.title.includes('مكررة')) {
      actionBtn = `<button class="btn btn-amber btn-sm" onclick="switchTab('dedupe')">معالجة التكرارات</button>`;
    } else if (al.title.includes('ملاحظة سعة') || al.title.includes('امتلاء')) {
      actionBtn = `<button class="btn btn-violet btn-sm" onclick="triggerPoolRebalance()">⚖️ موازنة تلقائية</button>`;
    }

    div.innerHTML = `
      <div>
        <strong>🔔 ${al.title}:</strong>
        <span style="margin-right: 0.35rem;">${al.message}</span>
      </div>
      ${actionBtn}
    `;
    container.appendChild(div);
  });
}

function renderSidebarFilters() {
  const foldersList = document.getElementById('virtualFoldersList');
  const accList = document.getElementById('accountFilterList');
  const folders = state.dashboard.folders || [];
  const totalFiles = state.dashboard.pool.total_files;

  foldersList.innerHTML = `
    <li class="folder-item ${state.selectedFolder === 'all' ? 'active' : ''}" onclick="selectFolder('all')">
      <span>🌐 جميع المجلدات الموحدة</span>
      <span class="folder-meta">${totalFiles}</span>
    </li>
  `;

  folders.forEach((f) => {
    const li = document.createElement('li');
    li.className = `folder-item ${state.selectedFolder === f.virtual_path ? 'active' : ''}`;
    li.onclick = () => selectFolder(f.virtual_path);
    li.innerHTML = `
      <span>📁 ${f.virtual_path}</span>
      <span class="folder-meta" title="موزع عبر ${f.accounts_spanned} حسابات">${f.files_count} ملف • ${formatBytes(f.folder_bytes)}</span>
    `;
    foldersList.appendChild(li);
  });

  accList.innerHTML = `
    <li class="folder-item ${state.selectedAccount === 'all' ? 'active' : ''}" onclick="selectAccountFilter('all')">
      <span>🔗 العرض المدمج (Union)</span>
      <span class="folder-meta">الكل</span>
    </li>
  `;

  state.accounts.forEach((acc) => {
    const li = document.createElement('li');
    li.className = `folder-item ${state.selectedAccount === acc.id ? 'active' : ''}`;
    li.onclick = () => selectAccountFilter(acc.id);
    li.innerHTML = `
      <span style="display:flex;align-items:center;gap:0.4rem;">
        <span class="legend-dot" style="background:${acc.color};"></span>
        <span style="max-width:145px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${acc.name}</span>
      </span>
      <span class="folder-meta">${acc.file_count}</span>
    `;
    accList.appendChild(li);
  });
}

function selectFolder(folderPath) {
  state.selectedFolder = folderPath;
  renderSidebarFilters();
  loadFiles();
}

function selectAccountFilter(accId) {
  state.selectedAccount = accId;
  renderSidebarFilters();
  loadFiles();
}

function resetExplorerFilters() {
  state.selectedFolder = 'all';
  state.selectedAccount = 'all';
  document.getElementById('fileSearchInput').value = '';
  document.getElementById('categoryFilterSelect').value = 'all';
  renderSidebarFilters();
  loadFiles();
}

async function loadFiles() {
  const q = document.getElementById('fileSearchInput').value.trim();
  const category = document.getElementById('categoryFilterSelect').value;

  const params = new URLSearchParams();
  if (state.selectedAccount !== 'all') params.set('account_id', state.selectedAccount);
  if (state.selectedFolder !== 'all') params.set('virtual_path', state.selectedFolder);
  if (q) params.set('q', q);
  if (category !== 'all') params.set('category', category);

  const res = await fetch(`/api/files?${params.toString()}`);
  const data = await res.json();
  state.files = data.files || [];
  renderFilesTable();
  renderSimpleFilesTable();
}

function renderSimpleFilesTable() {
  const tbody = document.getElementById('simpleFilesTableBody');
  if (!tbody) return;
  tbody.innerHTML = '';

  state.files.forEach((f) => {
    const tr = document.createElement('tr');
    const icon = getFileIcon(f.mime_type, f.name);
    const gdriveBtn = f.web_view_link
      ? `<a href="${f.web_view_link}" target="_blank" rel="noopener" class="btn btn-outline btn-sm">🔗 فتح</a>`
      : '';

    tr.innerHTML = `
      <td>
        <div class="file-name-cell">
          <span class="file-icon">${icon}</span>
          <div class="file-title">${f.name}</div>
        </div>
      </td>
      <td><span style="color:var(--text-secondary);">📁 ${f.virtual_path}</span></td>
      <td style="font-weight:700;">${formatBytes(f.size)}</td>
      <td style="color:var(--text-muted);font-size:0.8rem;">${(f.modified_at || '').slice(0, 10)}</td>
      <td>
        <div style="display:flex;gap:0.35rem;">
          ${gdriveBtn}
          <a href="/api/files/${f.id}/download" class="btn btn-outline btn-sm">⬇️ تنزيل</a>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function renderFilesTable() {
  const tbody = document.getElementById('filesTableBody');
  tbody.innerHTML = '';

  if (state.files.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" style="text-align: center; padding: 2.5rem; color: var(--text-secondary);">
          لا توجد ملفات مطابقة لمعايير التصفية الحالية.
        </td>
      </tr>
    `;
    return;
  }

  state.files.forEach((f) => {
    const tr = document.createElement('tr');
    const icon = getFileIcon(f.mime_type, f.name);
    const dupBadge = f.is_duplicate
      ? `<span class="dup-badge" title="هذا الملف مكرر بنفس بصمة MD5">⚠️ مكرر ×${f.duplicate_count}</span>`
      : '';
    const chunkBadge =
      f.is_chunk || f.name.includes('[جزء ')
        ? `<span class="dup-badge" style="background:rgba(139,92,246,0.22);color:#ddd6fe;border-color:#8b5cf6;">🧩 موزع عبر التوسع التلقائي</span>`
        : '';

    const gdriveBtn = f.web_view_link
      ? `<a href="${f.web_view_link}" target="_blank" rel="noopener" class="btn btn-outline btn-sm" title="فتح في Google Drive">🔗 فتح</a>`
      : '';

    const safeFileName = f.name.replace(/'/g, "\\'");

    tr.innerHTML = `
      <td>
        <div class="file-name-cell">
          <span class="file-icon">${icon}</span>
          <div>
            <div class="file-title">${f.name}</div>
            <div class="file-sub">
              <span>📁 ${f.virtual_path}</span>
              <span>•</span>
              <span>🕒 ${(f.modified_at || '').slice(0, 10)}</span>
              ${dupBadge}
              ${chunkBadge}
            </div>
          </div>
        </div>
      </td>
      <td>
        <span class="account-pill" style="border-color: ${f.account_color}66;">
          <span class="legend-dot" style="background: ${f.account_color};"></span>
          ${f.account_name}
        </span>
        <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.2rem; direction: ltr; text-align: right;">
          ${f.account_email}
        </div>
      </td>
      <td style="font-weight: 700; white-space: nowrap;">${formatBytes(f.size)}</td>
      <td>
        <span class="hash-code" title="${f.md5_hash}">${(f.md5_hash || '').slice(0, 14)}…</span>
      </td>
      <td>
        <div style="display: flex; gap: 0.35rem; flex-wrap: wrap;">
          ${gdriveBtn}
          <button class="btn btn-outline btn-sm" onclick="openMoveFileModal(${f.id}, '${safeFileName}', '${f.account_id}')">
            ⇄ نقل لحساب آخر
          </button>
          <a href="/api/files/${f.id}/download" class="btn btn-outline btn-sm">⬇️</a>
          <button class="btn btn-danger btn-sm" onclick="deleteFileById(${f.id})">🗑️</button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// ==================== إدارة الحسابات وخزنة الرموز ====================

async function loadAccountsDetails() {
  const res = await fetch('/api/accounts');
  state.accounts = await res.json();
  renderAccountsCards();
}

function renderAccountsCards() {
  const grid = document.getElementById('accountsCardsGrid');
  if (!grid) return;
  grid.innerHTML = '';

  state.accounts.forEach((acc) => {
    const card = document.createElement('div');
    card.className = 'account-card';
    const dailyPct = ((acc.daily_uploaded_bytes / acc.daily_upload_limit) * 100).toFixed(2);
    const canDelete = acc.id !== 'gdrive_ngacademy_main';

    card.innerHTML = `
      <div class="acc-header">
        <div>
          <div class="acc-title" style="display:flex;align-items:center;gap:0.45rem;">
            <span class="legend-dot" style="background:${acc.color};width:12px;height:12px;"></span>
            ${acc.name}
          </div>
          <div class="acc-email">${acc.email}</div>
        </div>
        <span class="status-badge">🟢 متصل (${acc.account_type})</span>
      </div>

      <div>
        <div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:0.3rem;">
          <span>المساحة المستخدمة: <strong>${formatBytes(acc.used_bytes)}</strong></span>
          <span>المتاح: <strong style="color:#34d399;">${formatBytes(acc.free_bytes)}</strong> (${acc.used_pct}%)</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill" style="width:${Math.min(100, acc.used_pct)}%; background:${acc.color};"></div>
        </div>
      </div>

      <div class="acc-meta-grid">
        <div>
          <div style="color:var(--text-muted);">معرّف Rclone Remote:</div>
          <div style="font-weight:700;direction:ltr;text-align:right;">${acc.rclone_remote}</div>
        </div>
        <div>
          <div style="color:var(--text-muted);">حصة الرفع اليومية (750GB):</div>
          <div style="font-weight:700;">${formatBytes(acc.daily_uploaded_bytes)} (${dailyPct}%)</div>
        </div>
        <div>
          <div style="color:var(--text-muted);">رمز الوصول المشفر (Vault):</div>
          <div class="hash-code">${acc.masked_access_token || 'enc:aes256gcm'}</div>
        </div>
        <div>
          <div style="color:var(--text-muted);">عدد الملفات المفهرسة:</div>
          <div style="font-weight:700;">${acc.file_count} ملف</div>
        </div>
      </div>

      <div style="font-size:0.78rem;color:var(--text-secondary);">
        ${acc.notes || ''}
      </div>

      <div style="display:flex;justify-content:space-between;gap:0.5rem;margin-top:auto;">
        <button class="btn btn-outline btn-sm" onclick="refreshOAuthToken('${acc.id}')">
          🔄 تجديد رمز OAuth 2.0
        </button>
        <button class="btn btn-outline btn-sm" onclick="selectAccountFilter('${acc.id}'); switchTab('explorer');">
          📂 تصفح ملفات الحساب
        </button>
        ${canDelete ? `<button class="btn btn-danger btn-sm" onclick="removeAccount('${acc.id}')">فصل</button>` : ''}
      </div>
    `;
    grid.appendChild(card);
  });
}

function renderApiQuotaMonitor() {
  const box = document.getElementById('apiQuotaMonitorBox');
  if (!box || !state.dashboard || !state.dashboard.api_quota_monitor) return;
  const qm = state.dashboard.api_quota_monitor;
  const pct = ((qm.current_minute_units / qm.user_limit_per_min) * 100).toFixed(2);

  box.innerHTML = `
    <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:8px;padding:0.75rem;">
      <div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:0.35rem;">
        <span>استهلاك الدقيقة الحالية: <strong>${qm.current_minute_units.toLocaleString()} وحدة</strong></span>
        <span style="color:#34d399;">الحد المسموح للمستخدم: ${qm.user_limit_per_min.toLocaleString()} وحدة/دقيقة (${pct}%)</span>
      </div>
      <div class="progress-track" style="margin-bottom:0.6rem;">
        <div class="progress-fill" style="width:${Math.max(2, pct)}%;background:#10b981;"></div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:0.5rem;font-size:0.74rem;color:var(--text-secondary);">
        <span class="hash-code">files.get = 5u</span>
        <span class="hash-code">files.update = 50u</span>
        <span class="hash-code">files.list = 100u</span>
        <span class="hash-code">files.download = 200u</span>
        <span class="hash-code">Sustained Write = 3 req/s</span>
      </div>
    </div>
  `;
}

async function generateOAuthLink() {
  const cid = document.getElementById('gcpClientIdInput').value.trim();
  const res = await fetch(`/api/oauth/generate-url?client_id=${encodeURIComponent(cid)}`);
  const data = await res.json();
  const box = document.getElementById('oauthUrlResultBox');
  box.innerHTML = `
    <div style="background:var(--bg-surface);border:1px solid var(--border-color);padding:0.65rem;border-radius:8px;margin-top:0.4rem;">
      <div style="margin-bottom:0.3rem;color:#34d399;font-weight:600;">✅ تم توليد رابط الموافقة الرسمي (Offline Refresh Token):</div>
      <div class="hash-code" style="word-break:break-all;white-space:normal;padding:0.4rem;">${data.auth_url}</div>
    </div>
  `;
}

async function refreshOAuthToken(accountId) {
  const res = await fetch(`/api/accounts/${accountId}/refresh-token`, { method: 'POST' });
  const data = await res.json();
  if (data.success) {
    showToast(data.message, 'success');
    await refreshAllData();
  }
}

async function removeAccount(accountId) {
  const res = await fetch(`/api/accounts/${accountId}`, { method: 'DELETE' });
  const data = await res.json();
  if (res.ok) {
    showToast(data.message, 'warn');
    await refreshAllData();
  } else {
    showToast(data.detail || 'تعذر حذف الحساب', 'error');
  }
}

function openAddAccountModal() {
  document.getElementById('addAccountModal').classList.add('open');
}

function closeAddAccountModal() {
  document.getElementById('addAccountModal').classList.remove('open');
}

function openImportRcloneModal() {
  document.getElementById('importRcloneModal').classList.add('open');
}

function closeImportRcloneModal() {
  document.getElementById('importRcloneModal').classList.remove('open');
}

async function submitImportRclone() {
  const confText = document.getElementById('rcloneImportTextarea').value.trim();
  if (!confText) return;

  const res = await fetch('/api/rclone/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conf_text: confText }),
  });
  const data = await res.json();
  if (res.ok && data.success) {
    closeImportRcloneModal();
    showToast(data.message, 'success');
    await refreshAllData();
  } else {
    showToast(data.detail || 'خطأ في استيراد rclone.conf', 'error');
  }
}

async function submitNewAccount(e) {
  e.preventDefault();
  const payload = {
    name: document.getElementById('newAccName').value.trim(),
    email: document.getElementById('newAccEmail').value.trim(),
    provider: document.getElementById('newAccProvider').value,
    total_gb: parseFloat(document.getElementById('newAccTotalGb').value) || 15,
    refresh_token: document.getElementById('newAccRefreshToken').value.trim() || null,
    color: '#06b6d4',
    priority: 1,
  };

  const res = await fetch('/api/accounts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (res.ok) {
    closeAddAccountModal();
    showToast(data.message, 'success');
    document.getElementById('newAccName').value = '';
    document.getElementById('newAccEmail').value = '';
    await refreshAllData();
  } else {
    showToast(data.detail || 'حدث خطأ أثناء إضافة الحساب', 'error');
  }
}

function populateAccountSelects() {
  const uploadSel = document.getElementById('uploadTargetAccount');
  const moveSel = document.getElementById('moveTargetAccountSelect');
  if (!uploadSel || !moveSel) return;

  uploadSel.innerHTML = `<option value="auto">🤖 اختيار تلقائي ذكي (وفق سياسة Union)</option>`;
  moveSel.innerHTML = '';

  state.accounts.forEach((acc) => {
    const label = `${acc.name} (متاح: ${formatBytes(acc.free_bytes)})`;
    uploadSel.innerHTML += `<option value="${acc.id}">${label}</option>`;
    moveSel.innerHTML += `<option value="${acc.id}">${label}</option>`;
  });
}

function openMoveFileModal(fileId, fileName, currentAccId) {
  document.getElementById('moveFileIdInput').value = fileId;
  document.getElementById('moveFileNameLabel').textContent = `نقل الملف: "${fileName}" إلى حساب آخر دون تغيير مساره الموحد:`;
  const sel = document.getElementById('moveTargetAccountSelect');
  Array.from(sel.options).forEach((opt) => {
    if (opt.value !== currentAccId) sel.value = opt.value;
  });
  document.getElementById('moveFileModal').classList.add('open');
}

function closeMoveFileModal() {
  document.getElementById('moveFileModal').classList.remove('open');
}

async function confirmMoveFile() {
  const fileId = document.getElementById('moveFileIdInput').value;
  const targetAccountId = document.getElementById('moveTargetAccountSelect').value;

  const res = await fetch(`/api/files/${fileId}/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_account_id: targetAccountId }),
  });
  const data = await res.json();
  if (res.ok && data.success) {
    closeMoveFileModal();
    showToast(data.message, 'success');
    await refreshAllData();
  } else {
    showToast(data.detail || 'تعذر نقل الملف', 'error');
  }
}

async function deleteFileById(fileId) {
  const res = await fetch(`/api/files/${fileId}`, { method: 'DELETE' });
  const data = await res.json();
  if (res.ok) {
    showToast(data.message, 'warn');
    await refreshAllData();
  }
}

async function triggerPoolRebalance() {
  const res = await fetch('/api/pool/rebalance', { method: 'POST' });
  const data = await res.json();
  if (data.success) {
    showToast(data.message, 'success');
    await refreshAllData();
  } else {
    showToast(data.message || 'تعذر موازنة المساحة', 'warn');
  }
}

async function handleRealFileUpload(e) {
  e.preventDefault();
  const fileInput = document.getElementById('uploadFileInput');
  if (!fileInput.files.length) return;

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('virtual_path', document.getElementById('uploadVirtualPath').value);
  formData.append('preferred_account_id', document.getElementById('uploadTargetAccount').value);
  formData.append('force_duplicate', document.getElementById('uploadForceDuplicate').checked);

  const res = await fetch('/api/files/upload', {
    method: 'POST',
    body: formData,
  });
  const data = await res.json();
  renderUploadFeedback(data, res.ok);
  await refreshAllData();
}

async function quickTestUpload(name, sizeMb, virtualPath, seed) {
  const res = await fetch('/api/files/create-synthetic', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      size_mb: sizeMb,
      virtual_path: virtualPath,
      content_seed: seed,
      preferred_account_id: document.getElementById('uploadTargetAccount').value,
      force_duplicate: document.getElementById('uploadForceDuplicate').checked,
    }),
  });
  const data = await res.json();
  renderUploadFeedback(data, res.ok);
  await refreshAllData();
}

async function quickTestChunkedUpload() {
  const res = await fetch('/api/files/upload-chunked', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'الأرشيف_السنوي_الكامل_لأكاديمية_NG_2026_4K.tar',
      size_gb: 16.0,
      chunk_size_gb: 4.0,
      virtual_path: '/تسجيلات وميديا',
    }),
  });
  const data = await res.json();
  const box = document.getElementById('uploadResultBox');
  if (res.ok && data.success) {
    const chunksList = data.plan.chunks
      .map(
        (c) =>
          `<div style="font-size:0.76rem;margin-top:0.2rem;">🧩 <strong>${c.chunk_name}</strong> (${formatBytes(c.size_bytes)}) ⬅️ وُجّه إلى: <span style="color:#60a5fa;">${c.account_name}</span></div>`
      )
      .join('');
    box.innerHTML = `
      <div class="alert-item alert-info" style="border-color:#8b5cf6;background:rgba(139,92,246,0.14);">
        <div>
          <strong>🎉 ${data.message}</strong>
          <div style="margin-top:0.4rem;">${chunksList}</div>
        </div>
      </div>
    `;
    showToast(data.message, 'success');
    await refreshAllData();
  } else {
    showToast(data.detail || 'فشل التقسيم', 'error');
  }
}

async function quickTestDuplicateBlock() {
  await fetch('/api/files/create-synthetic', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'نسخة_مكررة_من_كتاب_Mindset_Carol_Dweck.pdf',
      size_mb: 5.01,
      virtual_path: '/كتب',
      content_seed: 'duplicate_test',
      force_duplicate: false,
    }),
  });
  await fetch('/api/files/create-synthetic', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'نسخة_ثانية_مكررة_من_كتاب_Mindset.pdf',
      size_mb: 5.01,
      virtual_path: '/كتب',
      content_seed: 'duplicate_test',
      force_duplicate: false,
    }),
  })
    .then((r) => r.json())
    .then(async (data2) => {
      renderUploadFeedback(data2, true);
      await refreshAllData();
    });
}

function renderUploadFeedback(data, ok) {
  const box = document.getElementById('uploadResultBox');
  if (data.duplicate_blocked) {
    box.innerHTML = `
      <div class="alert-item alert-warning">
        <div>
          <strong>🛑 تم إيقاف رفع الملف المكرر تلقائيًا وتوفير المساحة!</strong>
          <div style="margin-top:0.25rem;">${data.message}</div>
          <div style="margin-top:0.25rem;font-size:0.78rem;">بصمة MD5 المطابقة: <span class="hash-code">${data.md5_hash}</span></div>
        </div>
      </div>
    `;
    showToast(data.message, 'warn');
  } else if (ok && data.success) {
    box.innerHTML = `
      <div class="alert-item alert-info" style="border-color:#10b981;background:rgba(16,185,129,0.12);color:#d1fae5;">
        <div>
          <strong>✅ ${data.message}</strong>
          <div style="margin-top:0.25rem;font-size:0.82rem;">🧭 سبب الاختيار: ${data.placement_reason}</div>
          <div style="margin-top:0.25rem;font-size:0.76rem;">بصمة MD5 المسجلة في الفهرس: <span class="hash-code">${data.md5_hash}</span></div>
        </div>
      </div>
    `;
    showToast(data.message, 'success');
  } else {
    box.innerHTML = `<div class="alert-item alert-high">${data.detail || 'فشل الرفع'}</div>`;
    showToast(data.detail || 'فشل الرفع', 'error');
  }
}

async function runPlacementSimulation() {
  const policy = document.getElementById('simPolicySelect').value;
  const sizeMb = parseFloat(document.getElementById('simFileSizeMb').value) || 100;
  const virtualPath = document.getElementById('simVirtualPath').value;

  const res = await fetch('/api/placement/simulate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      file_name: 'archive_bundle.bin',
      file_size_bytes: Math.round(sizeMb * 1024 * 1024),
      virtual_path: virtualPath,
      policy: policy,
    }),
  });
  const sim = await res.json();
  const container = document.getElementById('simulationResultContainer');

  if (!sim.success && sim.requires_chunking && sim.chunk_plan) {
    const chunksHtml = sim.chunk_plan.chunks
      .map(
        (c) => `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:0.45rem 0.7rem;border-radius:7px;background:var(--bg-surface);border:1px solid #8b5cf6;margin-bottom:0.35rem;font-size:0.78rem;">
          <span>🧩 الجزء #${c.part_number}: <strong>${c.chunk_name}</strong> (${formatBytes(c.size_bytes)})</span>
          <span class="account-pill" style="border-color:${c.account_color};">${c.account_name}</span>
        </div>
      `
      )
      .join('');

    container.innerHTML = `
      <div style="background:rgba(139,92,246,0.12);border:1px solid #8b5cf6;border-radius:10px;padding:1rem;">
        <div style="font-weight:700;color:#ddd6fe;margin-bottom:0.35rem;">
          🧩 الملف (${formatBytes(sizeMb * 1024 * 1024)}) أكبر من أي حساب منفرد — تم تفعيل خطة التقسيم التلقائي (Multi-Account Chunker):
        </div>
        <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.75rem;">
          ${sim.chunk_plan.reason}
        </div>
        ${chunksHtml}
      </div>
    `;
    return;
  }

  if (!sim.success || !sim.selected) {
    container.innerHTML = `
      <div class="alert-item alert-high">
        <strong>❌ لا يمكن توجيه الملف بهذا الحجم (${sizeMb} MB):</strong> ${sim.reason}
      </div>
    `;
    return;
  }

  let candidatesHtml = sim.candidates
    .map((c, idx) => {
      const isWinner = c.account_id === sim.selected.account_id;
      return `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:0.55rem 0.75rem;border-radius:8px;background:${isWinner ? 'rgba(16,185,129,0.15)' : 'var(--bg-surface)'};border:1px solid ${isWinner ? '#10b981' : 'var(--border-color)'};margin-bottom:0.4rem;font-size:0.8rem;">
          <div>
            <strong>${isWinner ? '🏆 الحساب الفائز: ' : `#${idx + 1} `}${c.name}</strong>
            <span style="color:var(--text-secondary);margin-right:0.4rem;">(${c.path_exists ? 'يحتوي على المجلد مسبقًا' : 'مجلد جديد'})</span>
          </div>
          <div style="font-weight:700;color:#34d399;">متاح: ${formatBytes(c.free_bytes)} (${c.file_count} ملف)</div>
        </div>
      `;
    })
    .join('');

  container.innerHTML = `
    <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:10px;padding:1rem;">
      <div style="font-weight:700;color:#60a5fa;margin-bottom:0.35rem;">
        🎯 قرار محرك التوزيع: توجيه الملف إلى (${sim.selected.name})
      </div>
      <div style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:0.85rem;">
        ${sim.reason}
      </div>
      <div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:0.4rem;">ترتيب الحسابات المرشحة وفق السياسة:</div>
      ${candidatesHtml}
    </div>
  `;
}

async function saveActivePolicyFromSim() {
  const policy = document.getElementById('simPolicySelect').value;
  const res = await fetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ placement_policy: policy, pre_upload_dedupe: true }),
  });
  const data = await res.json();
  if (data.success) {
    showToast(`تم اعتماد سياسة التوزيع (${policy.toUpperCase()}) كسياسة افتراضية للنظام.`, 'success');
    await refreshAllData();
  }
}

async function loadDuplicates() {
  const res = await fetch('/api/duplicates');
  state.duplicates = await res.json();
  renderDuplicatesList();
}

function renderDuplicatesList() {
  const container = document.getElementById('duplicatesListContainer');
  if (!container || !state.duplicates) return;

  const { groups } = state.duplicates;
  if (!groups || groups.length === 0) {
    container.innerHTML = `
      <div style="text-align:center;padding:2.5rem;background:var(--bg-surface);border-radius:12px;border:1px solid var(--border-color);">
        <div style="font-size:2.2rem;margin-bottom:0.5rem;">✨</div>
        <h3>لا توجد أي ملفات مكررة في جميع حساباتك!</h3>
        <p style="color:var(--text-secondary);font-size:0.85rem;">تم فحص جميع بصمات MD5 عبر كافة الحسابات المربوطة، والمساحة مستغلة بكفاءة 100%.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = groups
    .map((g) => {
      const scopeBadge = g.is_cross_account
        ? `<span class="dup-badge" style="background:rgba(139,92,246,0.25);color:#ddd6fe;border-color:#8b5cf6;">🌐 تكرار عابر للحسابات (${g.accounts_involved.join(' + ')})</span>`
        : `<span class="dup-badge">⚠️ تكرار داخل نفس الحساب (${g.accounts_involved[0]})</span>`;

      const filesRows = g.files
        .map(
          (f, idx) => `
          <div style="display:flex;justify-content:space-between;align-items:center;padding:0.5rem 0.75rem;background:rgba(255,255,255,0.03);border-radius:8px;margin-top:0.4rem;font-size:0.82rem;">
            <div>
              <strong>${idx === 0 ? '🟢 النسخة الأصلية (تبقى محفوظة): ' : '🔴 نسخة زائدة (تُحذف عند التنظيف): '}</strong>
              <span>${f.name}</span>
              <span style="color:var(--text-muted);margin-right:0.5rem;">(${f.virtual_path})</span>
            </div>
            <div style="display:flex;align-items:center;gap:0.6rem;">
              <span class="account-pill">${f.account_name}</span>
              <span style="font-weight:700;">${formatBytes(f.size)}</span>
            </div>
          </div>
        `
        )
        .join('');

      return `
        <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:12px;padding:1.1rem;margin-bottom:1rem;">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.75rem;">
            <div>
              <div style="font-weight:700;font-size:0.95rem;display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
                <span>📄 ${g.primary_name}</span>
                ${scopeBadge}
              </div>
              <div style="font-size:0.78rem;color:var(--text-secondary);margin-top:0.2rem;">
                بصمة المحتوى المتطابقة (MD5): <span class="hash-code">${g.md5_hash}</span> • عدد النسخ: <strong>${g.copies_count}</strong> • المساحة المهدرة: <strong style="color:#fbbf24;">${formatBytes(g.wasted_bytes)}</strong>
              </div>
            </div>
            <button class="btn btn-amber btn-sm" onclick="cleanDuplicateGroup('${g.md5_hash}')">
              🧹 حذف النسخة الزائدة وتوفير ${formatBytes(g.wasted_bytes)}
            </button>
          </div>
          <div style="margin-top:0.6rem;">${filesRows}</div>
        </div>
      `;
    })
    .join('');
}

async function cleanDuplicateGroup(md5Hash) {
  const res = await fetch(`/api/duplicates/clean?md5_hash=${encodeURIComponent(md5Hash)}`, {
    method: 'POST',
  });
  const data = await res.json();
  showToast(data.message, 'success');
  await refreshAllData();
}

async function cleanAllDuplicates() {
  const res = await fetch('/api/duplicates/clean', { method: 'POST' });
  const data = await res.json();
  showToast(data.message, 'success');
  await refreshAllData();
}

async function loadRcloneConfig() {
  const res = await fetch('/api/rclone-config');
  const data = await res.json();
  document.getElementById('rcloneConfCode').textContent = data.rclone_conf;
  document.getElementById('rcloneCommandsCode').textContent = data.cli_commands;
  const dcEl = document.getElementById('dockerComposeCode');
  if (dcEl && data.docker_compose) {
    dcEl.textContent = data.docker_compose;
  }
}

function copyRcloneConfig() {
  const text = document.getElementById('rcloneConfCode').textContent;
  navigator.clipboard.writeText(text);
  showToast('تم نسخ ملف إعدادات rclone.conf إلى الحافظة!', 'success');
}

function renderAuditLogs() {
  const container = document.getElementById('auditLogsContainer');
  if (!container || !state.dashboard) return;
  const logs = state.dashboard.logs || [];

  container.innerHTML = logs
    .map((l) => {
      const badgeColor =
        l.level === 'success' ? '#10b981' : l.level === 'warning' ? '#f59e0b' : '#3b82f6';
      return `
        <div style="background:var(--bg-surface);border-right:3px solid ${badgeColor};padding:0.7rem 0.9rem;border-radius:8px;font-size:0.82rem;">
          <div style="display:flex;justify-content:space-between;margin-bottom:0.2rem;">
            <strong>${l.title}</strong>
            <span style="font-size:0.72rem;color:var(--text-muted);direction:ltr;">${(l.created_at || '').replace('T', ' ').slice(0, 19)}</span>
          </div>
          <div style="color:var(--text-secondary);font-size:0.78rem;">${l.details}</div>
        </div>
      `;
    })
    .join('');
}

async function resetDemoState() {
  const res = await fetch('/api/reset-demo', { method: 'POST' });
  const data = await res.json();
  showToast(data.message, 'success');
  await refreshAllData();
}

window.addEventListener('DOMContentLoaded', () => {
  refreshAllData();
});
