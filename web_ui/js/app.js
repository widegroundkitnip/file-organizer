/**
 * File Organizer & Deduper — Phase 3 Web UI
 * Vanilla JS, no frameworks, no external imports.
 */

'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const state = {
  currentPage: 'scan',
  manifest: null,
  manifestPath: null,
  rules: [],
  actionPlan: [],
  settings: {},
  scans: [],
  scanMode: 'fast',
  filter: 'all',
};

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

function navigate(page) {
  state.currentPage = page;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const pageEl = document.getElementById(`page-${page}`);
  const navEl = document.querySelector(`[data-page="${page}"]`);
  if (pageEl) pageEl.classList.add('active');
  if (navEl)  navEl.classList.add('active');

  // Lazy-load page data
  if (page === 'results' && state.manifest)  renderResults();
  if (page === 'rules')                      renderRules();
  if (page === 'preview' && state.manifest)  renderPreview();
  if (page === 'execute')                    renderExecution();
  if (page === 'settings')                   renderSettings();
}

// ---------------------------------------------------------------------------
// API wrapper
// ---------------------------------------------------------------------------

async function api(method, endpoint, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(`/api${endpoint}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

function fmtSize(bytes) {
  if (bytes == null) return '';
  if (bytes < 1024)        return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024**3)     return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024**3).toFixed(2)} GB`;
}

function fmtDate(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function categoryClass(cat) {
  const map = {
    Images: 'cat-images', Videos: 'cat-videos', Audio: 'cat-audio',
    Documents: 'cat-documents', Code: 'cat-code', Archives: 'cat-archives',
    Other: 'cat-other',
  };
  return map[cat] || 'cat-other';
}

function categoryEmoji(cat) {
  const map = {
    Images: '🖼', Videos: '🎬', Audio: '🎵', Documents: '📄',
    Code: '💻', Archives: '📦', Other: '📁',
  };
  return map[cat] || '📁';
}

function getCategory(file) {
  const extMap = {
    jpg:'Images',jpeg:'Images',png:'Images',gif:'Images',bmp:'Images',tiff:'Images',
    webp:'Images',heic:'Images',raw:'Images',cr2:'Images',nef:'Images',arw:'Images',
    mp4:'Videos',mov:'Videos',avi:'Videos',mkv:'Videos',wmv:'Videos',flv:'Videos',
    webm:'Videos',m4v:'Videos',
    mp3:'Audio',wav:'Audio',flac:'Audio',aac:'Audio',ogg:'Audio',m4a:'Audio',wma:'Audio',
    pdf:'Documents',doc:'Documents',docx:'Documents',xls:'Documents',xlsx:'Documents',
    ppt:'Documents',pptx:'Documents',odt:'Documents',ods:'Documents',
    py:'Code',js:'Code',ts:'Code',java:'Code',cpp:'Code',c:'Code',h:'Code',
    rs:'Code',go:'Code',rb:'Code',php:'Code',html:'Code',css:'Code',
    json:'Code',yaml:'Code',toml:'Code',sh:'Code',
    zip:'Archives',rar:'Archives','7z':'Archives',tar:'Archives',gz:'Archives',bz2:'Archives',
  };
  return extMap[(file.ext||'').toLowerCase()] || 'Other';
}

function showAlert(containerId, type, msg) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="alert alert-${type}">${escHtml(msg)}</div>`;
  setTimeout(() => { if (el) el.innerHTML = ''; }, 6000);
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ---------------------------------------------------------------------------
// Scan page
// ---------------------------------------------------------------------------

async function loadScans() {
  try {
    state.scans = await api('GET', '/scans');
    renderScanHistory();
  } catch(e) {
    console.warn('Could not load scan history:', e.message);
  }
}

function renderScanHistory() {
  const el = document.getElementById('scan-history');
  if (!el) return;
  if (!state.scans.length) {
    el.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🔍</div><div>No previous scans</div></div>';
    return;
  }
  el.innerHTML = state.scans.slice(0, 8).map(s => `
    <div class="scan-history-item" onclick="loadScan('${escHtml(s.id)}')">
      <span style="font-size:18px">📁</span>
      <span class="scan-history-path">${escHtml(s.path)}</span>
      <span class="scan-history-meta">
        ${s.total_files.toLocaleString()} files · ${fmtDate(s.timestamp).split(',')[0]}
      </span>
    </div>
  `).join('');
}

async function loadScan(scanId) {
  try {
    const manifest = await api('GET', `/manifest/${scanId}`);
    state.manifest = manifest;
    state.manifestPath = null; // will be resolved from scan id
    // Try to find full path from scans list
    const scan = state.scans.find(s => s.id === scanId);
    if (scan) {
      // Reconstruct path (server returns full path in manifest path field — use id to build it)
      state.manifestPath = `/scans/${scanId}.json`; // relative; we need the server-side path
    }
    // Get actual manifest path from scans
    const scanMeta = state.scans.find(s => s.id === scanId);
    if (scanMeta) {
      // We need the real FS path — request it from a scan that returned it
      // Build it from the scan_output_dir in settings
      const settings = await api('GET', '/settings');
      const scanDir = settings.scan_output_dir || '';
      state.manifestPath = scanDir ? `${scanDir}/${scanId}.json` : null;
    }
    navigate('results');
  } catch(e) {
    showAlert('scan-alert', 'error', `Failed to load scan: ${e.message}`);
  }
}

async function startScan() {
  const pathInput = document.getElementById('scan-path');
  const path = (pathInput && pathInput.value.trim()) || '';
  if (!path) {
    showAlert('scan-alert', 'warning', 'Enter a folder path to scan.');
    return;
  }

  const btn = document.getElementById('btn-scan');
  const progress = document.getElementById('scan-progress');
  const statusEl = document.getElementById('scan-status');

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Scanning…';
  if (progress) progress.classList.remove('hidden');
  if (statusEl) statusEl.textContent = 'Scanning…';

  try {
    const result = await api('POST', '/scan', {
      path,
      mode: state.scanMode,
      include_hidden: document.getElementById('include-hidden')?.checked || false,
    });

    state.manifestPath = result.manifest_path;

    // Load manifest
    const manifest = await api('GET', `/manifest/${result.manifest_id}`);
    state.manifest = manifest;

    if (statusEl) statusEl.textContent = `✓ Found ${result.total_files.toLocaleString()} files`;
    showAlert('scan-alert', 'success', `Scan complete — ${result.total_files.toLocaleString()} files found.`);

    await loadScans();
    navigate('results');
  } catch(e) {
    showAlert('scan-alert', 'error', `Scan failed: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🔍 Start Scan';
    if (progress) progress.classList.add('hidden');
  }
}

// ---------------------------------------------------------------------------
// Results page
// ---------------------------------------------------------------------------

function renderResults() {
  const m = state.manifest;
  if (!m) {
    document.getElementById('results-content').innerHTML =
      '<div class="empty-state"><div class="empty-state-icon">📂</div><div>No scan loaded. Run a scan first.</div></div>';
    return;
  }

  const meta = m.scan_meta || {};
  const files = m.files || [];
  const dupGroups = m.duplicate_groups || [];
  const catPreview = m.category_preview || {};

  // Stats
  const statsHtml = `
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">${files.length.toLocaleString()}</div>
        <div class="stat-label">Total Files</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">${fmtSize(meta.total_size_bytes)}</div>
        <div class="stat-label">Total Size</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">${dupGroups.length}</div>
        <div class="stat-label">Duplicate Groups</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">${Object.keys(catPreview).length}</div>
        <div class="stat-label">Categories</div>
      </div>
    </div>
  `;

  // Category breakdown
  // Group files by category
  const byCategory = {};
  for (const f of files) {
    const cat = getCategory(f);
    if (!byCategory[cat]) byCategory[cat] = [];
    byCategory[cat].push(f);
  }

  const catHtml = Object.entries(byCategory)
    .sort((a,b) => b[1].length - a[1].length)
    .map(([cat, catFiles]) => {
      const filesHtml = catFiles.slice(0, 50).map(f =>
        `<div class="file-item">
          <span class="file-size">${fmtSize(f.size_bytes)}</span>
          <span class="text-mono">${escHtml(f.name)}</span>
        </div>`
      ).join('') + (catFiles.length > 50 ? `<div class="text-muted text-sm" style="padding:4px 0">… and ${catFiles.length - 50} more</div>` : '');

      return `
        <div class="category-section">
          <div class="category-header" onclick="toggleCategory(this)">
            <span>${categoryEmoji(cat)}</span>
            <span class="category-tag ${categoryClass(cat)}">${escHtml(cat)}</span>
            <span class="category-file-count">${catFiles.length.toLocaleString()} files</span>
            <span style="color:var(--muted);font-size:12px;margin-left:8px">▶</span>
          </div>
          <div class="category-files">${filesHtml}</div>
        </div>
      `;
    }).join('');

  // Duplicate groups
  let dupHtml = '';
  if (dupGroups.length) {
    dupHtml = `
      <div class="card">
        <div class="card-title">⚠ Duplicate Groups (${dupGroups.length})</div>
        ${dupGroups.map((g, gi) => `
          <div class="duplicate-group">
            <div class="dup-header">
              <span class="dup-tier ${g.tier}">${g.tier}</span>
              <span class="text-muted text-sm">${g.files.length} files in group</span>
            </div>
            ${g.files.map((fp, fi) => `
              <div class="dup-file ${fi === 0 ? 'keep' : ''}">
                <span>${fi === 0 ? '✓ keep' : '✗ dup'}</span>
                <span class="dup-file-path">${escHtml(fp)}</span>
              </div>
            `).join('')}
          </div>
        `).join('')}
      </div>
    `;
  }

  const metaHtml = `
    <div class="card">
      <div class="card-title">Scan Info</div>
      <div class="flex gap-12" style="flex-wrap:wrap">
        <div><span class="text-muted">Path: </span><span class="text-mono text-sm">${escHtml(meta.path || '')}</span></div>
        <div><span class="text-muted">Mode: </span>${escHtml(meta.mode || '')}</div>
        <div><span class="text-muted">Scanned: </span>${fmtDate(meta.timestamp)}</div>
        <div><span class="text-muted">Symlinks: </span>${meta.symlink_count || 0}</div>
      </div>
    </div>
  `;

  document.getElementById('results-content').innerHTML =
    statsHtml + metaHtml +
    `<div class="card"><div class="card-title">📁 Files by Category</div>${catHtml}</div>` +
    dupHtml;
}

function toggleCategory(header) {
  const files = header.nextElementSibling;
  const arrow = header.querySelector('span:last-child');
  files.classList.toggle('open');
  if (arrow) arrow.textContent = files.classList.contains('open') ? '▼' : '▶';
}

// ---------------------------------------------------------------------------
// Rules page
// ---------------------------------------------------------------------------

async function loadRules() {
  try {
    const data = await api('GET', '/rules');
    state.rules = data.rules || [];
  } catch(e) {
    console.warn('Could not load rules:', e.message);
  }
}

async function saveRules() {
  try {
    await api('PUT', '/rules', { rules: state.rules });
    showAlert('rules-alert', 'success', 'Rules saved.');
  } catch(e) {
    showAlert('rules-alert', 'error', `Save failed: ${e.message}`);
  }
}

function renderRules() {
  const container = document.getElementById('rules-list');
  if (!container) return;

  if (!state.rules.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📋</div>
        <div>No rules yet. Add a rule to get started.</div>
      </div>`;
    return;
  }

  container.innerHTML = state.rules.map((rule, idx) => {
    const flt = rule.filter || {};
    const filterDesc = flt.type === 'extension'     ? `Extension: .${(flt.values||[]).join(', .')}` :
                       flt.type === 'name_contains'  ? `Name contains: ${flt.value || ''}` :
                       flt.type === 'name_pattern'   ? `Pattern: ${flt.value || ''}` :
                       flt.type === 'size_gt'        ? `Size > ${fmtSize(flt.value)}` :
                       flt.type === 'size_lt'        ? `Size < ${fmtSize(flt.value)}` :
                       flt.type || 'No filter';
    return `
      <div class="rule-card" data-idx="${idx}">
        <div class="rule-card-header">
          <span class="rule-handle">⠿</span>
          <span class="rule-name">${escHtml(rule.name || 'Unnamed rule')}</span>
          <span class="category-tag ${categoryClass(rule.category || 'Other')}">${escHtml(rule.category || 'Other')}</span>
          <label class="checkbox-label" style="flex-shrink:0">
            <input type="checkbox" ${rule.enabled !== false ? 'checked' : ''} onchange="toggleRule(${idx}, this.checked)">
            On
          </label>
          <button class="rule-delete" onclick="deleteRule(${idx})" title="Delete rule">✕</button>
        </div>
        <div class="text-sm text-muted" style="margin-bottom:8px">
          <strong>Filter:</strong> ${escHtml(filterDesc)}
          ${rule.subfolder ? `&nbsp;·&nbsp;<strong>Subfolder:</strong> ${escHtml(rule.subfolder)}` : ''}
          ${rule.destination_template ? `&nbsp;·&nbsp;<strong>Template:</strong> <span class="text-mono">${escHtml(rule.destination_template)}</span>` : ''}
        </div>
        <div class="btn-group">
          <button class="btn btn-secondary" onclick="editRule(${idx})">✏ Edit</button>
        </div>
      </div>
    `;
  }).join('');
}

function addRule() {
  const name = document.getElementById('new-rule-name')?.value?.trim() || 'New Rule';
  const filterType = document.getElementById('new-filter-type')?.value || 'extension';
  const filterValue = document.getElementById('new-filter-value')?.value?.trim() || '';
  const category = document.getElementById('new-rule-category')?.value || 'Other';
  const subfolder = document.getElementById('new-rule-subfolder')?.value?.trim() || '';
  const template = document.getElementById('new-rule-template')?.value?.trim()
    || (subfolder ? '{category}/{subfolder}/{name}.{ext}' : '{category}/{name}.{ext}');

  const filter = { type: filterType };
  if (filterType === 'extension') {
    filter.values = filterValue.split(',').map(v => v.trim().replace(/^\./, '')).filter(Boolean);
  } else {
    filter.value = filterValue;
  }

  const rule = {
    name,
    category,
    subfolder,
    filter,
    destination_template: template,
    conflict_mode: 'rename',
    enabled: true,
  };

  state.rules.push(rule);
  renderRules();

  // Clear form
  ['new-rule-name','new-rule-name','new-filter-value','new-rule-subfolder'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  document.getElementById('add-rule-form')?.classList.add('hidden');
}

function deleteRule(idx) {
  state.rules.splice(idx, 1);
  renderRules();
}

function toggleRule(idx, enabled) {
  if (state.rules[idx]) state.rules[idx].enabled = enabled;
}

function editRule(idx) {
  const rule = state.rules[idx];
  if (!rule) return;
  const name = prompt('Rule name:', rule.name || '');
  if (name !== null) rule.name = name;
  renderRules();
}

function showAddRuleForm() {
  const form = document.getElementById('add-rule-form');
  if (form) form.classList.toggle('hidden');
}

function updateFilterValueLabel() {
  const type = document.getElementById('new-filter-type')?.value;
  const label = document.getElementById('filter-value-label');
  const hint = document.getElementById('filter-value-hint');
  if (!label) return;
  const labels = {
    extension: 'Extensions (comma-separated)',
    name_contains: 'Substring to match',
    name_pattern: 'Glob pattern (e.g. invoice_*)',
    size_gt: 'Minimum size in bytes',
    size_lt: 'Maximum size in bytes',
  };
  const hints = {
    extension: 'e.g. pdf, jpg, png',
    name_contains: 'e.g. Screenshot (case-insensitive)',
    name_pattern: 'e.g. report_*.pdf',
    size_gt: 'e.g. 1048576 for 1 MB',
    size_lt: 'e.g. 1024 for 1 KB',
  };
  label.textContent = labels[type] || 'Value';
  if (hint) hint.textContent = hints[type] || '';
}

// ---------------------------------------------------------------------------
// Preview page
// ---------------------------------------------------------------------------

async function buildPreview() {
  if (!state.manifest) {
    showAlert('preview-alert', 'warning', 'No scan loaded. Run a scan first.');
    return;
  }
  if (!state.manifestPath) {
    // Try to get it from scan meta + settings
    const settings = await api('GET', '/settings').catch(() => ({}));
    const scanDir = settings.scan_output_dir || '';
    const meta = state.manifest.scan_meta || {};
    const ts = (meta.timestamp || '').replace('T','_').replace(/:/g,'').substring(0,15);
    if (scanDir) {
      // Find the scan id from scans list
      if (state.scans.length) {
        state.manifestPath = `${scanDir}/${state.scans[0].id}.json`;
      }
    }
  }

  if (!state.manifestPath) {
    showAlert('preview-alert', 'error', 'Cannot determine manifest path. Re-run the scan.');
    return;
  }

  const btn = document.getElementById('btn-preview');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Planning…'; }

  try {
    const result = await api('POST', '/preview', {
      manifest_path: state.manifestPath,
      rules: state.rules,
    });
    state.actionPlan = result.actions || [];
    renderPreview(result.stats);
    showAlert('preview-alert', 'success',
      `Plan: ${result.stats.to_move} moves, ${result.stats.to_delete} deletes, ${result.stats.to_skip} skips`
    );
  } catch(e) {
    showAlert('preview-alert', 'error', `Preview failed: ${e.message}`);
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '👁 Build Preview'; }
  }
}

function renderPreview(stats) {
  const container = document.getElementById('preview-content');
  if (!container) return;

  if (!state.actionPlan.length) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📋</div><div>No preview yet. Click "Build Preview".</div></div>';
    return;
  }

  const statsHtml = stats ? `
    <div class="stats-grid mb-16">
      <div class="stat-card"><div class="stat-value">${stats.total}</div><div class="stat-label">Total</div></div>
      <div class="stat-card"><div class="stat-value text-primary">${stats.to_move}</div><div class="stat-label">Move</div></div>
      <div class="stat-card"><div class="stat-value text-error">${stats.to_delete}</div><div class="stat-label">Delete</div></div>
      <div class="stat-card"><div class="stat-value text-muted">${stats.to_skip}</div><div class="stat-label">Skip</div></div>
    </div>
  ` : '';

  const filterBar = `
    <div class="filter-bar" id="preview-filter-bar">
      ${['all','move','delete','skip'].map(f => `
        <button class="filter-chip ${state.filter === f ? 'active' : ''}" onclick="setPreviewFilter('${f}')">
          ${f.charAt(0).toUpperCase() + f.slice(1)}
          <span class="filter-count">(${state.actionPlan.filter(a => f === 'all' || a.action === f).length})</span>
        </button>
      `).join('')}
      <span style="margin-left:auto;display:flex;gap:6px">
        <button class="btn btn-secondary" style="padding:4px 10px;font-size:12px" onclick="selectAllActions('move')">All Moves</button>
        <button class="btn btn-secondary" style="padding:4px 10px;font-size:12px" onclick="selectAllActions('delete')">All Deletes</button>
        <button class="btn btn-secondary" style="padding:4px 10px;font-size:12px" onclick="deselectAll()">None</button>
      </span>
    </div>
  `;

  const filtered = state.filter === 'all' ? state.actionPlan : state.actionPlan.filter(a => a.action === state.filter);

  const actionsHtml = filtered.map((item, i) => {
    const realIdx = state.actionPlan.indexOf(item);
    const icon = item.action === 'move' ? '→' : item.action === 'delete' ? '🗑' : '—';
    const badgeClass = `badge-${item.action}`;

    // Pre-check logic: moves always checked; duplicate "keep" skips uncheckable; dup deletes unchecked
    const isDupKeep = item.rule_matched === '_duplicate_resolution' && item.action === 'skip';
    const isDupDelete = item.rule_matched === '_duplicate_resolution' && item.action === 'delete';
    const defaultChecked = item.action === 'move' || (item.action === 'delete' && !isDupDelete);

    return `
      <div class="action-item">
        <input type="checkbox" id="action-cb-${realIdx}" ${isDupKeep ? 'disabled' : ''} ${defaultChecked ? 'checked' : ''}>
        <span class="action-icon">${icon}</span>
        <div class="action-details">
          <div class="action-src">${escHtml(item.src)}</div>
          ${item.dst ? `<div class="action-arrow">↓</div><div class="action-dst">${escHtml(item.dst)}</div>` : ''}
          ${item.rule_matched ? `<div class="text-sm text-muted" style="margin-top:3px">Rule: ${escHtml(item.rule_matched)}</div>` : ''}
        </div>
        <span class="action-badge ${badgeClass}">${item.action}</span>
      </div>
    `;
  }).join('');

  container.innerHTML = statsHtml + filterBar +
    `<div id="actions-list">${actionsHtml || '<div class="empty-state"><div>No actions match filter.</div></div>'}</div>`;
}

function setPreviewFilter(f) {
  state.filter = f;
  const stats = state.actionPlan.length ? {
    total: state.actionPlan.length,
    to_move: state.actionPlan.filter(a => a.action === 'move').length,
    to_delete: state.actionPlan.filter(a => a.action === 'delete').length,
    to_skip: state.actionPlan.filter(a => a.action === 'skip').length,
  } : null;
  renderPreview(stats);
}

function selectAllActions(type) {
  state.actionPlan.forEach((item, i) => {
    if (item.action === type) {
      const cb = document.getElementById(`action-cb-${i}`);
      if (cb && !cb.disabled) cb.checked = true;
    }
  });
}

function deselectAll() {
  state.actionPlan.forEach((_, i) => {
    const cb = document.getElementById(`action-cb-${i}`);
    if (cb && !cb.disabled) cb.checked = false;
  });
}

function getSelectedActions() {
  return state.actionPlan.filter((_, i) => {
    const cb = document.getElementById(`action-cb-${i}`);
    return cb && cb.checked;
  });
}

// ---------------------------------------------------------------------------
// Execute page
// ---------------------------------------------------------------------------

function renderExecution() {
  const container = document.getElementById('execute-content');
  if (!container) return;

  const selected = getSelectedActions();
  const outputDir = document.getElementById('exec-output-dir')?.value || '/tmp/file-organizer-output';

  if (!selected.length && !state.actionPlan.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">⚙️</div>
        <div>Build a preview first, then come here to execute.</div>
      </div>`;
    return;
  }
}

async function executePlan() {
  const selected = getSelectedActions();
  if (!selected.length) {
    showAlert('execute-alert', 'warning', 'No actions selected. Go to Preview and select actions first.');
    return;
  }

  const outputDir = document.getElementById('exec-output-dir')?.value?.trim() || '/tmp/file-organizer-output';
  const dryRun = document.getElementById('exec-dry-run')?.checked || false;
  const onConflict = document.getElementById('exec-conflict')?.value || 'rename';

  const confirmed = await showConfirmModal(
    `Execute ${selected.length} action(s)?`,
    `${dryRun ? 'DRY RUN — ' : ''}This will ${dryRun ? 'simulate' : 'actually'} move/delete ${selected.length} files.\nOutput: ${outputDir}`
  );
  if (!confirmed) return;

  const btn = document.getElementById('btn-execute');
  const feedEl = document.getElementById('live-feed');
  const progressEl = document.getElementById('exec-progress-bar');

  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Executing…'; }

  addFeedLine('Starting execution…', 'move');

  try {
    const result = await api('POST', '/execute', {
      action_plan: selected,
      output_dir: outputDir,
      dry_run: dryRun,
      on_conflict: onConflict,
    });

    if (progressEl) progressEl.style.width = '100%';

    const lines = (result.stdout || '').split('\n').filter(Boolean);
    lines.forEach(line => {
      const cls = line.includes('[OK]') ? 'ok' : line.includes('[ERROR]') ? 'error' : line.includes('[SKIP]') ? 'skip' : 'move';
      addFeedLine(line, cls);
    });

    showAlert('execute-alert', 'success',
      `Done: ${result.completed} completed, ${result.failed} failed.${result.undo_log ? ` Undo log: ${result.undo_log}` : ''}`
    );
  } catch(e) {
    addFeedLine(`ERROR: ${e.message}`, 'error');
    showAlert('execute-alert', 'error', `Execute failed: ${e.message}`);
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '⚡ Execute Plan'; }
  }
}

function addFeedLine(text, cls = '') {
  const feed = document.getElementById('live-feed');
  if (!feed) return;
  const div = document.createElement('div');
  div.className = `feed-line ${cls}`;
  div.textContent = text;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

// ---------------------------------------------------------------------------
// Settings page
// ---------------------------------------------------------------------------

async function loadSettings() {
  try {
    state.settings = await api('GET', '/settings');
  } catch(e) {
    console.warn('Could not load settings:', e.message);
  }
}

async function saveSettings() {
  // Collect form values
  const settings = { ...state.settings };

  const baseOut = document.getElementById('set-base-output')?.value?.trim();
  if (baseOut) settings.base_output_dir = baseOut;

  const trashDir = document.getElementById('set-trash-dir')?.value?.trim();
  if (trashDir) settings.trash_dir = trashDir;

  const conflictMode = document.getElementById('set-conflict-mode')?.value;
  if (conflictMode) settings.default_conflict_mode = conflictMode;

  // Theme colors
  if (!settings.theme) settings.theme = {};
  const themeFields = [
    'primary_color','bg_color','surface_color','text_color',
    'accent_color','muted_color','success_color','warning_color','error_color'
  ];
  themeFields.forEach(k => {
    const el = document.getElementById(`theme-${k.replace(/_/g,'-')}`);
    if (el) settings.theme[k] = el.value;
  });

  try {
    await api('PUT', '/settings', settings);
    state.settings = settings;
    applyTheme(settings.theme || {});
    showAlert('settings-alert', 'success', 'Settings saved.');
  } catch(e) {
    showAlert('settings-alert', 'error', `Save failed: ${e.message}`);
  }
}

function renderSettings() {
  const s = state.settings;
  const t = s.theme || {};

  const el = document.getElementById('settings-content');
  if (!el) return;

  el.innerHTML = `
    <div class="card">
      <div class="card-title">General</div>
      <div class="form-group">
        <label>Base Output Directory</label>
        <input type="text" id="set-base-output" value="${escHtml(s.base_output_dir || '')}">
      </div>
      <div class="form-group">
        <label>Trash Directory</label>
        <input type="text" id="set-trash-dir" value="${escHtml(s.trash_dir || '')}">
      </div>
      <div class="form-group">
        <label>Default Conflict Mode</label>
        <select id="set-conflict-mode">
          <option value="rename" ${s.default_conflict_mode === 'rename' ? 'selected' : ''}>Rename (_1, _2…)</option>
          <option value="skip" ${s.default_conflict_mode === 'skip' ? 'selected' : ''}>Skip</option>
          <option value="overwrite" ${s.default_conflict_mode === 'overwrite' ? 'selected' : ''}>Overwrite (⚠ destructive)</option>
        </select>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Theme Colors</div>
      ${[
        ['primary_color','Primary (Indigo)'],
        ['bg_color','Background'],
        ['surface_color','Surface / Cards'],
        ['text_color','Text'],
        ['accent_color','Accent (Cyan)'],
        ['muted_color','Muted Text'],
        ['success_color','Success'],
        ['warning_color','Warning'],
        ['error_color','Error'],
      ].map(([k, label]) => `
        <div class="color-row">
          <span class="color-label">${label}</span>
          <div class="color-input-wrap">
            <input type="color" id="theme-${k.replace(/_/g,'-')}" value="${escHtml(t[k] || '#ffffff')}">
            <input type="text" id="theme-${k.replace(/_/g,'-')}-text" value="${escHtml(t[k] || '')}" style="width:100px" oninput="syncColorText('${k.replace(/_/g,'-')}')">
          </div>
        </div>
      `).join('')}
    </div>

    <div class="card">
      <div class="card-title">AI Categorizer</div>
      <div class="text-muted text-sm">AI categorization is deferred to Phase 4.</div>
      <div style="margin-top:8px">
        <label class="checkbox-label">
          <input type="checkbox" disabled ${s.ai_categorizer?.enabled ? 'checked' : ''}>
          Enable AI categorizer (Phase 4)
        </label>
      </div>
    </div>
  `;
}

function syncColorText(key) {
  const text = document.getElementById(`theme-${key}-text`);
  const color = document.getElementById(`theme-${key}`);
  if (text && color && /^#[0-9a-f]{6}$/i.test(text.value)) {
    color.value = text.value;
  }
}

function applyTheme(t) {
  const root = document.documentElement;
  if (t.primary_color)  root.style.setProperty('--primary', t.primary_color);
  if (t.bg_color)       root.style.setProperty('--bg', t.bg_color);
  if (t.surface_color)  root.style.setProperty('--surface', t.surface_color);
  if (t.text_color)     root.style.setProperty('--text', t.text_color);
  if (t.accent_color)   root.style.setProperty('--accent', t.accent_color);
  if (t.muted_color)    root.style.setProperty('--muted', t.muted_color);
  if (t.success_color)  root.style.setProperty('--success', t.success_color);
  if (t.warning_color)  root.style.setProperty('--warning', t.warning_color);
  if (t.error_color)    root.style.setProperty('--error', t.error_color);
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

let _modalResolve = null;

function showConfirmModal(title, body) {
  return new Promise(resolve => {
    _modalResolve = resolve;
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-body').textContent = body;
    document.getElementById('modal-overlay').classList.add('open');
  });
}

function modalConfirm() {
  document.getElementById('modal-overlay').classList.remove('open');
  if (_modalResolve) { _modalResolve(true); _modalResolve = null; }
}

function modalCancel() {
  document.getElementById('modal-overlay').classList.remove('open');
  if (_modalResolve) { _modalResolve(false); _modalResolve = null; }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  await loadSettings();
  applyTheme(state.settings.theme || {});
  await loadRules();
  await loadScans();
  navigate('scan');

  // Set scan mode toggle state
  document.querySelectorAll('.toggle-btn[data-mode]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.scanMode = btn.dataset.mode;
      document.querySelectorAll('.toggle-btn[data-mode]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  // Settings exec output dir defaults
  const execOut = document.getElementById('exec-output-dir');
  if (execOut && state.settings.base_output_dir) {
    execOut.value = state.settings.base_output_dir;
  }
}

document.addEventListener('DOMContentLoaded', init);
