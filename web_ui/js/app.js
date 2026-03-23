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

window.lastCrossPathData = null;

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
  if (page === "structure") { renderStructureTree(window.lastCrossPathData); }
  if (page === "unknown") {
    const data = window.lastCrossPathData;
    const el = document.getElementById("unknown-files");
    if (!data || !data.unknown_files || data.unknown_files.length === 0) {
      el.innerHTML = "<div class=\"alert alert-info\">Run a Cross-Path scan first to see unknown files.</div>";
    } else {
      var files = data.unknown_files;
      var html = "<div style=\"margin-bottom:12px;color:var(--text)\">" + files.length + " unknown file(s) (" + data.unknown_count + " total)</div>";
      files.forEach(function(f) {
        html += "<div style=\"padding:6px 0;border-bottom:1px solid #222;font-size:13px;word-break:break-all;display:flex;align-items:center;gap:8px\">";
        html += "<span style=\"color:var(--text);flex:1;word-break:break-all\">" + escHtml(f.path) + "</span>";
        html += "<span style=\"color:#666;white-space:nowrap\">" + fmtSize(f.size) + "</span>";
        html += "<button onclick=\"approveUnknown(\'" + escHtml(f.path) + "\')\" style=\"background:#22c55e;color:white;border:none;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px;white-space:nowrap\">Keep</button>";
        html += "<button onclick=\"rejectUnknown(\'" + escHtml(f.path) + "\')\" style=\"background:#ef4444;color:white;border:none;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px;white-space:nowrap\">Delete</button>";
        html += "</div>";
      });
      el.innerHTML = html;
    }
  }
  if (page === "duplicates") {
    const data = window.lastCrossPathData;
    const el = document.getElementById("dupe-groups");
    if (!data || !data.duplicates || data.duplicates.length === 0) {
      el.innerHTML = "<div class=\"alert alert-info\">Run a Cross-Path scan first to see duplicates.</div>";
    } else {
      var dupGroups = data.duplicates;
      var html = "<div style=\"margin-bottom:16px;color:var(--text)\"><strong>" + dupGroups.length + "</strong> duplicate group(s)</div>";
      dupGroups.forEach(function(group, idx) {
        var tier = group.tier || "likely";
        html += "<div class=\"duplicate-group\" data-tier=\"" + escHtml(tier) + "\" style=\"background:var(--surface);border:1px solid #333;border-radius:8px;padding:12px;margin-bottom:12px\">";
        html += "<div style=\"color:var(--warning);margin-bottom:8px\">Group " + (idx+1) + " -- " + group.files.length + " files</div>";
        group.files.forEach(function(f) {
          html += "<div style=\"padding:4px 0;border-bottom:1px solid #222;font-size:13px;word-break:break-all\">";
          html += "<span style=\"color:var(--text)\">" + escHtml(f.path) + "</span>";
          html += " <span style=\"color:#666\">" + fmtSize(f.size) + "</span>";
          html += "</div>";
        });
        html += "</div>";
      });
      el.innerHTML = html;
    }
  }
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
                       flt.type === 'name_contains'  ? `Name contains: ${Array.isArray(flt.values) ? flt.values.join(', ') : (flt.value || '')}` :
                       flt.type === 'path_contains'   ? `Path contains: ${Array.isArray(flt.values) ? flt.values.join(', ') : (flt.value || '')}` :
                       flt.type === 'name_pattern'   ? `Pattern: ${flt.value || ''}` :
                       flt.type === 'size_gt'        ? `Size > ${fmtSize(flt.value)}` :
                       flt.type === 'size_lt'        ? `Size < ${fmtSize(flt.value)}` :
                       flt.type === 'created_before' ? `Created before: ${flt.value || ''}` :
                       flt.type === 'created_after'  ? `Created after: ${flt.value || ''}` :
                       flt.type === 'modified_before' ? `Modified before: ${flt.value || ''}` :
                       flt.type === 'modified_after'  ? `Modified after: ${flt.value || ''}` :
                       flt.type === 'modified_within_days' ? `Modified within ${flt.value} days` :
                       flt.type === 'no_extension'   ? `No extension` :
                       flt.type === 'duplicate'      ? `Duplicate` :
                       flt.type || 'No filter';
    const actionBadge = rule.action === 'delete' ? 'badge-delete' : rule.action === 'skip' ? 'badge-skip' : 'badge-move';
    const actionLabel = rule.action === 'delete' ? '🗑 Delete' : rule.action === 'skip' ? '— Skip' : '→ Move';
    return `
      <div class="rule-card" data-idx="${idx}">
        <div class="rule-card-header">
          <span class="rule-handle">⠿</span>
          <span class="rule-name">${escHtml(rule.name || 'Unnamed rule')}</span>
          <span class="${actionBadge}" style="font-size:11px;padding:2px 6px;border-radius:4px;font-weight:bold">${actionLabel}</span>
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
  const actionType = document.getElementById('new-action-type')?.value || 'move';
  const category = document.getElementById('new-rule-category')?.value || 'Other';
  const subfolder = document.getElementById('new-rule-subfolder')?.value?.trim() || '';
  const template = document.getElementById('new-rule-template')?.value?.trim()
    || (subfolder ? '{category}/{subfolder}/{name}.{ext}' : '{category}/{name}.{ext}');

  const filter = { type: filterType };
  if (filterType === 'extension') {
    filter.values = filterValue.split(',').map(v => v.trim().replace(/^\./, '')).filter(Boolean);
  } else if (filterType === 'name_contains' || filterType === 'path_contains') {
    // B-7: name_contains and path_contains use array of values
    filter.values = filterValue.split(',').map(v => v.trim()).filter(Boolean);
  } else if (filterType === 'no_extension' || filterType === 'duplicate') {
    // These take no value
    filter.value = null;
  } else if (filterType) {
    filter.value = filterValue;
  }

  const rule = {
    name,
    action: actionType,
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
  const valueInput = document.getElementById('new-filter-value');
  if (!label) return;
  const labels = {
    extension: 'Extensions (comma-separated)',
    name_contains: 'Substrings (comma-separated)',
    name_pattern: 'Glob pattern (e.g. invoice_*)',
    size_gt: 'Minimum size in bytes',
    size_lt: 'Maximum size in bytes',
    created_before: 'Created before (YYYY-MM-DD)',
    created_after: 'Created after (YYYY-MM-DD)',
    modified_before: 'Modified before (YYYY-MM-DD)',
    modified_after: 'Modified after (YYYY-MM-DD)',
    modified_within_days: 'Modified within (number of days)',
    no_extension: 'No value needed (matches files without extension)',
    duplicate: 'No value needed (matches duplicate files)',
  };
  const hints = {
    extension: 'e.g. pdf, jpg, png',
    name_contains: 'e.g. Screenshot, IMG_ (comma-separated)',
    name_pattern: 'e.g. report_*.pdf',
    size_gt: 'e.g. 1048576 for 1 MB',
    size_lt: 'e.g. 1024 for 1 KB',
    created_before: 'Files created before this date',
    created_after: 'Files created after this date',
    modified_before: 'Files modified before this date',
    modified_after: 'Files modified after this date',
    modified_within_days: 'e.g. 30 for files modified in last 30 days',
    no_extension: 'Files with no extension (e.g. README, Makefile)',
    duplicate: 'Files flagged as duplicates in the scan',
  };
  label.textContent = labels[type] || 'Value';
  if (hint) hint.textContent = hints[type] || '';
  // Show/hide value input based on whether filter type needs a value
  const noValueTypes = ['no_extension', 'duplicate'];
  if (valueInput) {
    valueInput.style.display = noValueTypes.includes(type) ? 'none' : '';
  }
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

    // Rule name shown prominently (teal/green) above the file path
    const ruleName = item.rule_name || item.rule_matched || '';
    const matchReason = item.rule_match_reason || '';
    const ruleBadge = ruleName
      ? `<div style="margin-bottom:4px">
           <span style="background:#0d9488;color:white;border-radius:4px;padding:1px 6px;font-size:11px;font-weight:bold">${escHtml(ruleName)}</span>
           ${matchReason ? `<span style="color:#6b7280;font-size:11px;margin-left:6px">via ${escHtml(matchReason)}</span>` : ''}
         </div>`
      : '';

    return `
      <div class="action-item">
        <input type="checkbox" id="action-cb-${realIdx}" ${isDupKeep ? 'disabled' : ''} ${defaultChecked ? 'checked' : ''}>
        <span class="action-icon">${icon}</span>
        <div class="action-details">
          ${ruleBadge}
          <div class="action-src">${escHtml(item.src)}</div>
          ${item.dst ? `<div class="action-arrow">↓</div><div class="action-dst">${escHtml(item.dst)}</div>` : ''}
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
  const banner = document.getElementById('dry-run-banner');
  if (banner) banner.style.display = dryRun ? 'block' : 'none';
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
        <input type="text" id="set-base-output" data-tooltip="Where moved files will go. A trash subfolder is created automatically." value="${escHtml(s.base_output_dir || '')}">
      </div>
      <div class="form-group">
        <label>Trash Directory</label>
        <input type="text" id="set-trash-dir" value="${escHtml(s.trash_dir || '')}">
      </div>
      <div class="form-group">
        <label>Default Conflict Mode</label>
        <select id="set-conflict-mode" data-tooltip="Rename: adds _1, _2 to filename. Skip: leaves existing file as-is. Overwrite: replaces destination file.">
          <option value="rename" ${s.default_conflict_mode === 'rename' ? 'selected' : ''}>Rename (_1, _2…)</option>
          <option value="skip" ${s.default_conflict_mode === 'skip' ? 'selected' : ''}>Skip</option>
          <option value="overwrite" ${s.default_conflict_mode === 'overwrite' ? 'selected' : ''}>Overwrite (⚠ destructive)</option>
        </select>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Protected Folders</div>
      <div class="text-sm text-muted" style="margin-bottom:12px">These folders and their subfolders will never be modified by any action.</div>
      <div id="protected-folders-list">
        ${((s.protected_folders)||[]).map(function(p, i) {
          return '<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #222">' +
            '<span style="flex:1;font-family:monospace;font-size:13px;color:var(--text)">'+escHtml(p)+'</span>' +
            '<button class="btn btn-sm" style="padding:2px 8px;font-size:11px;color:var(--error)" data-tooltip="Remove this folder from the protected list." onclick="removeProtectedFolder('+i+')">✕ Remove</button></div>';
        }).join('')}
      </div>
      <div style="display:flex;gap:8px;margin-top:10px">
        <input type="text" id="set-protected-folder" placeholder="/path/to/safe/folder" style="flex:1;padding:8px;border-radius:6px;border:1px solid #333;background:var(--surface);color:var(--text)">
        <input type="file" id="set-protected-browse" webkitdirectory style="display:none" onchange="handleBrowseFolder(this, 'set-protected-folder')">
        <button class="btn btn-secondary" onclick="document.getElementById('set-protected-browse').click()">📁 Browse</button>
        <button class="btn btn-secondary" onclick="addProtectedFolder()">+ Add</button>
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

function addProtectedFolder() {
  const input = document.getElementById('set-protected-folder');
  if (!input || !input.value.trim()) return;
  if (!state.settings.protected_folders) state.settings.protected_folders = [];
  if (!state.settings.protected_folders.includes(input.value.trim())) {
    state.settings.protected_folders.push(input.value.trim());
  }
  input.value = '';
  renderSettings();
}

function removeProtectedFolder(idx) {
  if (!state.settings.protected_folders) return;
  state.settings.protected_folders.splice(idx, 1);
  renderSettings();
}

// ── Hover Tooltip System ─────────────────────────────────────────────────────
var _tooltipTimer = null;

document.addEventListener('mouseover', function(e) {
  var el = e.target.closest('[data-tooltip]');
  if (!el) return;
  clearTimeout(_tooltipTimer);
  _tooltipTimer = setTimeout(function() {
    showTooltip(el);
  }, 1000); // 1 second delay
});

document.addEventListener('mouseout', function(e) {
  var el = e.target.closest('[data-tooltip]');
  if (!el) return;
  clearTimeout(_tooltipTimer);
  hideTooltip();
});

function showTooltip(el) {
  hideTooltip();
  var text = el.getAttribute('data-tooltip');
  if (!text) return;
  var bubble = document.createElement('div');
  bubble.className = 'tooltip-bubble';
  bubble.textContent = text;
  bubble.id = 'active-tooltip';
  document.body.appendChild(bubble);
  // Position after DOM insertion so we can measure it
  var rect = el.getBoundingClientRect();
  var bW = bubble.offsetWidth;
  var bH = bubble.offsetHeight;
  var vW = window.innerWidth;
  var vH = window.innerHeight;
  var arrowH = 8;
  var pad = 10;

  // Default: show above the element
  var top = rect.top - bH - arrowH - pad;
  var left = rect.left + rect.width / 2 - bW / 2;

  // Flip below if not enough room above
  if (top < pad) {
    top = rect.bottom + arrowH + pad;
  }

  // Clamp horizontal
  if (left < pad) left = pad;
  if (left + bW > vW - pad) left = vW - bW - pad;

  bubble.style.top = top + 'px';
  bubble.style.left = left + 'px';
  bubble.classList.add('visible');
}

function hideTooltip() {
  clearTimeout(_tooltipTimer);
  var existing = document.getElementById('active-tooltip');
  if (existing) existing.remove();
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
  // Don't pre-load rules — user discovers them via Common Rules Library
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

// Cross-Path Scan
let crosspathPollCount = 0;

function pollCrossPathProgress() {
  crosspathPollCount = 0;
  (function poll() {
    api("GET", "/api/scans").then(function(scans) {
      var latest = scans[0];
      var statusEl = document.getElementById("crosspath-status");
      if (latest && statusEl) {
        statusEl.textContent = "Scanning… " + latest.total_files.toLocaleString() + " files checked";
      }
    }).catch(function(){});
    if (crosspathPollCount < 60) {
      crosspathPollCount++;
      setTimeout(poll, 1000);
    }
  })();
}
let crosspathInputCount = 1;

function addPathInput() {
  const container = document.getElementById("crosspath-paths");
  const input = document.createElement("input");
  input.type = "text";
  input.className = "path-input";
  input.id = "crosspath-input-" + crosspathInputCount;
  input.placeholder = "/path/to/folder";
  input.style = "width:100%;padding:10px;background:var(--surface);color:var(--text);border:1px solid #333;border-radius:8px;margin-bottom:8px";
  container.appendChild(input);
  crosspathInputCount++;
}

async function runCrossPathScan() {
  const resultsDiv = document.getElementById("crosspath-results");
  resultsDiv.innerHTML = "<div class=\"spinner\"></div> <span id=\"crosspath-status\">Preparing scan…</span>";
  const paths = [];
  for (let i = 0; i < crosspathInputCount; i++) {
    const el = document.getElementById("crosspath-input-" + i);
    if (el && el.value.trim()) paths.push(el.value.trim());
  }
  if (paths.length < 2) {
    resultsDiv.innerHTML = "<div class=\"alert alert-warn\">Need at least 2 folder paths.</div>";
    return;
  }
  try {
    // Start scan and poll for progress in parallel
    const scanPromise = api("POST", "/api/scan/multi", { paths, mode: "deep", include_hidden: false, exclude_dirs: [] });
    pollCrossPathProgress();
    const data = await scanPromise;
    window.lastCrossPathData = data;
    const tier1 = data.tier1 || [];
    const tier2 = data.tier2 || [];
    const tier3 = data.tier3 || [];
    const totalGroups = tier1.length + tier2.length + tier3.length;
    if (totalGroups === 0) {
      resultsDiv.innerHTML = "<div class=\"alert alert-success\">No duplicates found across the selected folders.</div>";
    } else {
      let html = "<div style=\"margin-bottom:16px;color:var(--text)\"><strong>" + totalGroups + "</strong> duplicate group(s) found</div>";

      if (tier1.length > 0) {
        html += "<div style=\"margin-top:12px\"><strong style=\"color:var(--text)\">Exact (Tier 1): " + tier1.length + " groups</strong></div>";
        tier1.forEach(function(group, idx) {
          html += "<div class=\"duplicate-group\" data-tier=\"exact\" style=\"background:var(--surface);border:1px solid #333;border-radius:8px;padding:12px;margin-top:8px\">";
          html += "<div style=\"color:var(--warning);margin-bottom:8px\">Group " + (idx+1) + " -- " + group.files.length + " files</div>";
          group.files.forEach(function(f) {
            html += "<div style=\"padding:4px 0;border-bottom:1px solid #222;font-size:13px;word-break:break-all\">" + escHtml(f.path) + " <span style=\"color:#666\">" + fmtSize(f.size) + "</span></div>";
          });
          html += "</div>";
        });
      }

      if (tier2.length > 0) {
        html += "<div style=\"margin-top:24px\"><strong style=\"color:var(--text)\">Likely (Tier 2): " + tier2.length + " groups</strong></div>";
        tier2.forEach(function(group, idx) {
          html += "<div class=\"duplicate-group\" data-tier=\"likely\" style=\"background:var(--surface);border:1px solid #333;border-radius:8px;padding:12px;margin-top:8px\">";
          html += "<div style=\"color:var(--warning);margin-bottom:8px\">Group " + (idx+1) + " -- " + group.files.length + " files</div>";
          group.files.forEach(function(f) {
            html += "<div style=\"padding:4px 0;border-bottom:1px solid #222;font-size:13px;word-break:break-all\">" + escHtml(f.path) + " <span style=\"color:#666\">" + fmtSize(f.size) + "</span></div>";
          });
          html += "</div>";
        });
      }

      // Tier 3 similar
      if (data.tier3 && data.tier3.length > 0) {
        html += "<div style=\"margin-top:24px\"><strong style=\"color:var(--text)\">Similar (Tier 3): " + data.tier3.length + " groups</strong></div>";
        data.tier3.forEach(function(group, idx) {
          var pct = Math.round(group.similarity * 100);
          html += "<div class=\"duplicate-group\" data-tier=\"similar\" style=\"background:var(--surface);border:1px solid #333;border-radius:8px;padding:12px;margin-top:8px\">";
          html += "<div style=\"color:var(--info);margin-bottom:8px\">Group " + (idx+1) + " (" + pct + "% similar) -- " + group.files.length + " files</div>";
          group.files.forEach(function(f) {
            html += "<div style=\"padding:4px 0;border-bottom:1px solid #222;font-size:13px;word-break:break-all\">" + escHtml(f.path) + " <span style=\"color:#666\">" + fmtSize(f.size) + "</span></div>";
          });
          html += "</div>";
        });
      }

      resultsDiv.innerHTML = html;
    }
    const struct = data.structure || {};
    if (struct.issues && struct.issues.length > 0) {
      var structHtml = "<div style=\"margin-top:24px\"><strong style=\"color:var(--text)\">Structure issues:</strong>";
      struct.issues.forEach(function(issue) {
        structHtml += "<div style=\"color:var(--warning);padding:4px 0\">" + escHtml(issue) + "</div>";
      });
      structHtml += "</div>";
      resultsDiv.innerHTML += structHtml;
    }
    if (data.unknown_count > 0) {
      resultsDiv.innerHTML += "<div style=\"margin-top:16px;color:var(--warning)\">" + data.unknown_count + " unknown file(s) detected</div>";
    }
  } catch(err) {
    resultsDiv.innerHTML = "<div class=\"alert alert-error\">Error: " + escHtml(err.message) + "</div>";
  }
}

function filterDupes(tier) {
  document.querySelectorAll(".filter-btn").forEach(function(b){ b.classList.remove("active"); });
  var btn = document.querySelector(".filter-btn[data-tier=\""+tier+"\"]");
  if (btn) btn.classList.add("active");
  document.querySelectorAll(".duplicate-group").forEach(function(el) {
    var t = el.getAttribute ? el.getAttribute('data-tier') : el.dataset.tier;
    el.style.display = (tier === "all" || t === tier) ? "block" : "none";
  });
}

function renderStructureTree(data) {
  var c = document.getElementById("structure-issues");
  if (!data || !data.structure) {
    c.innerHTML = "<div class=\"alert alert-info\">Run a Cross-Path scan first to see structure analysis.</div>";
    return;
  }
  var s = data.structure;
  var html = "<div style=\"display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap\">";
  html += "<div style=\"flex:1;min-width:100px;background:var(--surface);border:1px solid #333;border-radius:8px;padding:10px;text-align:center\"><div style=\"font-size:20px;font-weight:bold;color:var(--text)\">" + (s.total_folders||0).toLocaleString() + "</div><div style=\"font-size:11px;color:#666;text-transform:uppercase\">Folders</div></div>";
  html += "<div style=\"flex:1;min-width:100px;background:var(--surface);border:1px solid #333;border-radius:8px;padding:10px;text-align:center\"><div style=\"font-size:20px;font-weight:bold;color:var(--text)\">" + (s.depth||0) + "</div><div style=\"font-size:11px;color:#666;text-transform:uppercase\">Max Depth</div></div>";
  html += "<div style=\"flex:1;min-width:100px;background:var(--surface);border:1px solid #333;border-radius:8px;padding:10px;text-align:center\"><div style=\"font-size:20px;font-weight:bold;color:var(--text)\">" + (s.total_files||0).toLocaleString() + "</div><div style=\"font-size:11px;color:#666;text-transform:uppercase\">Files</div></div>";
  html += "<div style=\"flex:1;min-width:100px;background:var(--surface);border:1px solid #333;border-radius:8px;padding:10px;text-align:center\"><div style=\"font-size:20px;font-weight:bold;color:var(--text)\">" + fmtSize(s.total_size||0) + "</div><div style=\"font-size:11px;color:#666;text-transform:uppercase\">Total Size</div></div>";
  html += "</div>";
  if (s.issues && s.issues.length > 0) {
    html += "<div style=\"margin-bottom:16px\"><strong style=\"color:var(--warning);font-size:13px\">Issues (" + s.issues.length + "):</strong>";
    s.issues.slice(0,20).forEach(function(i){ html += "<div style=\"color:var(--warning);padding:3px 0;font-size:12px\">! " + escHtml(i) + "</div>"; });
    if(s.issues.length > 20) html += "<div style=\"color:#555;font-size:12px\">...and " + (s.issues.length-20) + " more</div>";
    html += "</div>";
  }
  if (s.tree && s.tree.length > 0) {
    html += "<div style=\"margin-top:16px\"><strong style=\"color:var(--text);font-size:13px;margin-bottom:8px;display:block\">Folder Tree:</strong>";
    s.tree.forEach(function(n){ html += rTN(n, 0); });
    html += "</div>";
  } else {
    html += "<div class=\"alert alert-success\">No structural issues found.</div>";
  }
  c.innerHTML = html;
}

function rTN(node, depth) {
  var hasKids = node.children && node.children.length > 0;
  var ind = depth * 18;
  var clr = node.has_issue ? "var(--error)" : (depth===0 ? "var(--text)" : "#94a3b8");
  var arrow = hasKids ? "<span style=\"color:#555;margin-right:4px;font-family:monospace\">&#9660;</span>" : "<span style=\"color:#444;margin-right:4px;font-family:monospace\">&#9646;</span>";
  var rowStyle = "display:flex;align-items:center;padding:5px " + ind + "px;border-radius:4px;cursor:" + (hasKids ? "pointer" : "default") + ";transition:background 0.1s";
  var h = "<div class=\"tree-node\" style=\"" + rowStyle + "\" onclick=\"tTN(this)\" data-path=\"" + escHtml(node.path||"") + "\">";
  h += arrow + "<span style=\"color:" + clr + ";font-size:13px;font-weight:" + (depth===0 ? "bold" : "normal") + ";flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\">" + escHtml(node.name||"") + "</span>";
  h += "<span style=\"color:#555;font-size:11px;margin-left:8px;white-space:nowrap\">" + (node.file_count||0) + " files &middot; " + fmtSize(node.size||0) + "</span>";
  if(node.has_issue) h += " <span style=\"color:var(--error);font-size:12px\">!</span>";
  h += "</div>";
  if(hasKids) {
    h += "<div class=\"tree-children\" style=\"display:block\">";
    node.children.forEach(function(c){ h += rTN(c, depth+1); });
    h += "</div>";
  }
  return h;
}

function tTN(el) {
  var kids = el.nextElementSibling;
  if(!kids || !kids.classList.contains("tree-children")) return;
  var exp = kids.style.display !== "none";
  kids.style.display = exp ? "none" : "block";
  var ar = el.querySelector("span");
  if(ar) ar.innerHTML = exp ? "&#9654;" : "&#9660;";
}

// ── Unknown File Approve / Reject ──────────────────────────────────────────
function approveUnknown(path) {
  // Create a rule to move this file to Unknown/Approved
  var template = "Unknown/Approved/{name}.{ext}";
  api("POST", "/api/plan", {
    manifest: window.lastCrossPathData ? window.lastCrossPathData.manifest : { files: [] },
    rules: [{
      name: "Approve",
      action: "move",
      filter: { type: "path_contains", values: [path] },
      destination_template: template,
      priority: 1,
    }],
    output_dir: "/tmp/file-organizer-output",
  }).then(function(plan) {
    // Remove from unknown_files list and re-render
    if (window.lastCrossPathData && window.lastCrossPathData.unknown_files) {
      window.lastCrossPathData.unknown_files = window.lastCrossPathData.unknown_files.filter(function(f) {
        return f.path !== path;
      });
      window.lastCrossPathData.unknown_count = Math.max(0, (window.lastCrossPathData.unknown_count || 1) - 1);
      navigate("unknown");
    }
    showAlert("unknown-alert", "success", "Approved: " + path.split("/").pop());
    console.log("Approved plan:", plan);
  }).catch(function(err) {
    showAlert("unknown-alert", "error", "Approve failed: " + err.message);
  });
}

function rejectUnknown(path) {
  // Create a rule to move this file to Trash
  var template = "Trash/{name}.{ext}";
  api("POST", "/api/plan", {
    manifest: window.lastCrossPathData ? window.lastCrossPathData.manifest : { files: [] },
    rules: [{
      name: "Reject",
      action: "move",
      filter: { type: "path_contains", values: [path] },
      destination_template: template,
      priority: 1,
    }],
    output_dir: "/tmp/file-organizer-output",
  }).then(function(plan) {
    // Remove from unknown_files list and re-render
    if (window.lastCrossPathData && window.lastCrossPathData.unknown_files) {
      window.lastCrossPathData.unknown_files = window.lastCrossPathData.unknown_files.filter(function(f) {
        return f.path !== path;
      });
      window.lastCrossPathData.unknown_count = Math.max(0, (window.lastCrossPathData.unknown_count || 1) - 1);
      navigate("unknown");
    }
    showAlert("unknown-alert", "success", "Rejected: " + path.split("/").pop());
    console.log("Rejected plan:", plan);
  }).catch(function(err) {
    showAlert("unknown-alert", "error", "Reject failed: " + err.message);
  });
}

// ── Folder Browse ─────────────────────────────────────────────────────────────
function browseForFolder(targetInputId) {
    var path = prompt("Enter the full path to the folder:");
    if (path) {
        var el = document.getElementById(targetInputId);
        if (el) el.value = path;
    }
}

function handleBrowseFolder(input, targetId) {
    var files = input.files;
    if (!files || files.length === 0) return;
    var dir = files[0].webkitRelativePath.split('/')[0];
    var target = document.getElementById(targetId);
    if (target) {
        var fullPath = files[0].path || '';
        if (fullPath) {
            target.value = fullPath.substring(0, fullPath.indexOf(dir) + dir.length) || dir;
        } else {
            target.value = '/' + dir;
        }
    }
    input.value = '';
}

// ── Mock Data Generator ───────────────────────────────────────────────────────
async function createMockData() {
    var path = document.getElementById('mock-path').value.trim();
    if (!path) { alert('Enter a path first'); return; }
    var sizeGb = parseInt(document.getElementById('mock-size').value);
    var cats = Array.from(document.querySelectorAll('.mock-cat:checked')).map(function(c) { return c.value; });
    var status = document.getElementById('mock-status');
    status.textContent = 'Generating...';
    status.style.color = '#666';
    try {
        var r = await fetch('/api/mock/create', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({path: path, size_gb: sizeGb, categories: cats})
        });
        var d = await r.json();
        status.textContent = 'Done! ' + (d.output || '');
        status.style.color = '#22c55e';
        document.getElementById('scan-path').value = path;
        navigate('scan');
    } catch(e) {
        status.textContent = 'Error: ' + e.message;
        status.style.color = '#ef4444';
    }
}

async function deleteMockData() {
    var path = document.getElementById('mock-path').value.trim();
    if (!path) { alert('Enter the path to delete'); return; }
    if (!confirm('Delete ' + path + '? This cannot be undone.')) return;
    var status = document.getElementById('mock-status');
    try {
        await fetch('/api/mock/delete', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({path: path})
        });
        status.textContent = 'Deleted.';
        status.style.color = '#f59e0b';
    } catch(e) {
        status.textContent = 'Error: ' + e.message;
        status.style.color = '#ef4444';
    }
}

// ── Rules — Collapsible Cards ─────────────────────────────────────────────────
function renderRules() {
    var container = document.getElementById('rules-list');
    if (!container) return;

    var html = '';

    // Common Rules Library button
    html += '<button class="btn btn-secondary" onclick="openCommonRulesModal()" style="margin-bottom:16px">📖 Common Rules Library</button>';

    if (!state.rules.length) {
        html += '<div class="empty-state"><div class="empty-state-icon">📋</div><div>No rules yet. Open the Common Rules Library or add your own.</div></div>';
        container.innerHTML = html;
        return;
    }

    html += state.rules.map(function(rule, idx) {
        var flt = rule.filter || {};
        var enabled = rule.enabled !== false;
        var extStr = '';
        if (flt.type === 'extension' && flt.values) {
            extStr = flt.values.map(function(v) { return '.' + v; }).join(', ');
        } else if (flt.type === 'name_contains' && flt.values) {
            extStr = flt.values.join(', ');
        } else if (flt.type === 'path_contains' && flt.values) {
            extStr = 'path: ' + flt.values.join(', ');
        } else if (flt.type === 'size_gt') {
            extStr = '> ' + fmtSize(flt.value);
        } else if (flt.type === 'size_lt') {
            extStr = '< ' + fmtSize(flt.value);
        } else if (flt.type === 'no_extension') {
            extStr = 'no extension';
        } else if (flt.type === 'duplicate') {
            extStr = 'duplicate';
        } else if (flt.value != null) {
            extStr = String(flt.value);
        }

        var arrowId = 'ra-' + idx;
        var detailsId = 'rd-' + idx;

        return '<div class="rule-card" style="background:var(--surface);border:1px solid #333;border-radius:8px;padding:12px;margin-bottom:8px">' +
            '<div style="display:flex;align-items:center;gap:10px">' +
            '<div style="flex:1;font-weight:bold;color:var(--text)">' + escHtml(rule.name || 'Unnamed rule') + '</div>' +
            '<label class="switch" style="display:flex;align-items:center;gap:6px;cursor:pointer">' +
            '<input type="checkbox" ' + (enabled ? 'checked' : '') + ' onchange="toggleRule(' + idx + ', this.checked)">' +
            '<span style="color:#666;font-size:11px">' + (enabled ? 'ON' : 'OFF') + '</span></label>' +
            '<span id="' + arrowId + '" onclick="toggleRuleDetails(this, \'' + detailsId + '\')" style="color:#555;cursor:pointer;font-size:16px;user-select:none">▼</span>' +
            '</div>' +
            '<div id="' + detailsId + '" class="rule-details" style="margin-top:8px;padding-top:8px;border-top:1px solid #333;display:none">' +
            '<div style="font-size:12px;color:#aaa;margin-bottom:4px"><strong>Filter:</strong> ' + escHtml(extStr) + '</div>' +
            '<div style="font-size:12px;color:#aaa;margin-bottom:4px"><strong>Category:</strong> ' + escHtml(rule.category || 'Other') + '</div>' +
            '<div style="font-size:12px;color:#aaa;margin-bottom:4px"><strong>Action:</strong> ' + escHtml(rule.action || 'move') + '</div>' +
            (rule.destination_template ? '<div style="font-size:12px;color:#aaa;margin-bottom:4px"><strong>Template:</strong> <code style="color:#888">' + escHtml(rule.destination_template) + '</code></div>' : '') +
            (rule.tags && rule.tags.length ? '<div style="font-size:12px;color:#aaa;margin-bottom:6px"><strong>Tags:</strong> ' + rule.tags.map(function(t) { return '<span style="background:#333;border-radius:3px;padding:1px 4px;margin-right:3px">' + escHtml(t) + '</span>'; }).join('') + '</div>' : '') +
            '<button onclick="openEditModal(' + idx + ')" class="btn btn-secondary" style="margin-top:6px">✏ Edit</button>' +
            '</div></div>';
    }).join('');

    container.innerHTML = html;
}

function toggleRuleDetails(arrow, detailsId) {
    var details = document.getElementById(detailsId);
    if (!details) return;
    var isHidden = details.style.display === 'none';
    details.style.display = isHidden ? 'block' : 'none';
    arrow.textContent = isHidden ? '▶' : '▼';
}

function toggleRule(idx, enabled) {
    if (state.rules[idx]) state.rules[idx].enabled = enabled;
    // Update the ON/OFF label
    var card = document.querySelector('.rule-card[data-idx="' + idx + '"]') || document.querySelectorAll('.rule-card')[idx];
    if (card) {
        var label = card.querySelector('.switch span');
        if (label) label.textContent = enabled ? 'ON' : 'OFF';
    }
}

function deleteRule(idx) {
    state.rules.splice(idx, 1);
    renderRules();
}

// ── Edit Rule Modal (full options) ────────────────────────────────────────────
var _editRuleIdx = null;

function openEditModal(idx) {
    _editRuleIdx = idx;
    var rule = state.rules[idx];
    if (!rule) return;
    var flt = rule.filter || {};
    var fltType = flt.type || 'extension';
    var fltValue = '';
    if (fltType === 'extension' && flt.values) {
        fltValue = flt.values.join(', ');
    } else if ((fltType === 'name_contains' || fltType === 'path_contains') && flt.values) {
        fltValue = flt.values.join(', ');
    } else if (flt.value != null) {
        fltValue = String(flt.value);
    }

    var body = '<div style="display:grid;gap:12px;text-align:left">' +

        '<div class="form-group"><label style="color:var(--text);font-size:13px">Rule Name</label>' +
        '<input type="text" id="edit-rule-name" value="' + escHtml(rule.name || '') + '" style="width:100%;padding:8px;border-radius:6px;border:1px solid #333;background:var(--surface);color:var(--text);box-sizing:border-box"></div>' +

        '<div class="form-group"><label style="color:var(--text);font-size:13px">Category</label>' +
        '<select id="edit-rule-category" style="width:100%;padding:8px;border-radius:6px;border:1px solid #333;background:var(--surface);color:var(--text)">' +
        ['Images','Documents','Videos','Audio','Code','Archives','Other'].map(function(c) {
            return '<option value="' + c + '"' + (rule.category === c ? ' selected' : '') + '>' + c + '</option>';
        }).join('') + '</select></div>' +

        '<div class="form-group"><label style="color:var(--text);font-size:13px">Action</label>' +
        '<select id="edit-rule-action" style="width:100%;padding:8px;border-radius:6px;border:1px solid #333;background:var(--surface);color:var(--text)">' +
        '<option value="move"' + (rule.action === 'move' ? ' selected' : '') + '>Move to category folder</option>' +
        '<option value="rename"' + (rule.action === 'rename' ? ' selected' : '') + '>Rename in place</option>' +
        '<option value="delete"' + (rule.action === 'delete' ? ' selected' : '') + '>Delete (use with caution)</option>' +
        '<option value="skip"' + (rule.action === 'skip' ? ' selected' : '') + '>Skip (do nothing)</option>' +
        '</select></div>' +

        '<div class="form-group"><label style="color:var(--text);font-size:13px">Filter Type</label>' +
        '<select id="edit-rule-filter-type" onchange="updateEditFilterLabel()" style="width:100%;padding:8px;border-radius:6px;border:1px solid #333;background:var(--surface);color:var(--text)">' +
        ['extension','name_contains','name_pattern','path_contains','size_gt','size_lt',
         'created_before','created_after','modified_before','modified_after',
         'modified_within_days','no_extension','duplicate'].map(function(t) {
            return '<option value="' + t + '"' + (fltType === t ? ' selected' : '') + '>' + t + '</option>';
        }).join('') + '</select></div>' +

        '<div class="form-group"><label id="edit-filter-label" style="color:var(--text);font-size:13px">Filter Value</label>' +
        '<input type="text" id="edit-rule-filter-value" value="' + escHtml(fltValue) + '" style="width:100%;padding:8px;border-radius:6px;border:1px solid #333;background:var(--surface);color:var(--text);box-sizing:border-box"></div>' +

        '<div class="form-group"><label style="color:var(--text);font-size:13px">Destination Template</label>' +
        '<input type="text" id="edit-rule-template" value="' + escHtml(rule.destination_template || '') + '" placeholder="{category}/{name}.{ext}" style="width:100%;padding:8px;border-radius:6px;border:1px solid #333;background:var(--surface);color:var(--text);box-sizing:border-box"></div>' +

        '<div class="form-group"><label style="color:var(--text);font-size:13px">Tags (comma-separated)</label>' +
        '<input type="text" id="edit-rule-tags" value="' + escHtml((rule.tags || []).join(', ')) + '" style="width:100%;padding:8px;border-radius:6px;border:1px solid #333;background:var(--surface);color:var(--text);box-sizing:border-box"></div>' +

        '<div class="form-group"><label style="color:var(--text);font-size:13px">Conflict Mode</label>' +
        '<select id="edit-rule-conflict" style="width:100%;padding:8px;border-radius:6px;border:1px solid #333;background:var(--surface);color:var(--text)">' +
        '<option value="rename"' + ((rule.conflict_mode || 'rename') === 'rename' ? ' selected' : '') + '>Rename (_1, _2…)</option>' +
        '<option value="skip"' + (rule.conflict_mode === 'skip' ? ' selected' : '') + '>Skip (leave existing)</option>' +
        '<option value="overwrite"' + (rule.conflict_mode === 'overwrite' ? ' selected' : '') + '>Overwrite</option>' +
        '</select></div>' +

        '</div>';

    document.getElementById('modal-title').textContent = '✏ Edit Rule';
    document.getElementById('modal-body').innerHTML = body;
    document.getElementById('modal-overlay').classList.add('open');

    // Override modal buttons for edit
    var actions = document.querySelector('.modal-actions');
    actions.innerHTML = '<button class="btn btn-secondary" onclick="modalCancel()">Cancel</button>' +
        '<button class="btn btn-danger" onclick="confirmEditRule()">Save</button>';
    _editRuleIdx = idx;
}

function updateEditFilterLabel() {
    var type = document.getElementById('edit-rule-filter-type') && document.getElementById('edit-rule-filter-type').value;
    var label = document.getElementById('edit-filter-label');
    if (!label) return;
    var labels = {
        extension: 'Extensions (comma-separated)',
        name_contains: 'Substrings (comma-separated)',
        name_pattern: 'Glob pattern',
        path_contains: 'Path substrings (comma-separated)',
        size_gt: 'Minimum size in bytes',
        size_lt: 'Maximum size in bytes',
        created_before: 'Created before (YYYY-MM-DD)',
        created_after: 'Created after (YYYY-MM-DD)',
        modified_before: 'Modified before (YYYY-MM-DD)',
        modified_after: 'Modified after (YYYY-MM-DD)',
        modified_within_days: 'Modified within days',
        no_extension: 'No value needed',
        duplicate: 'No value needed',
    };
    label.textContent = labels[type] || 'Value';
}

function confirmEditRule() {
    if (_editRuleIdx === null) return;
    var idx = _editRuleIdx;
    var rule = state.rules[idx];
    if (!rule) return;

    var filterType = document.getElementById('edit-rule-filter-type').value;
    var filterValue = document.getElementById('edit-rule-filter-value').value.trim();
    var filter = { type: filterType };
    if (filterType === 'extension') {
        filter.values = filterValue.split(',').map(function(v) { return v.trim().replace(/^\./, ''); }).filter(Boolean);
    } else if (filterType === 'name_contains' || filterType === 'path_contains') {
        filter.values = filterValue.split(',').map(function(v) { return v.trim(); }).filter(Boolean);
    } else if (filterType === 'no_extension' || filterType === 'duplicate') {
        filter.value = null;
    } else {
        filter.value = filterValue;
    }

    rule.name = document.getElementById('edit-rule-name').value.trim() || rule.name;
    rule.category = document.getElementById('edit-rule-category').value;
    rule.action = document.getElementById('edit-rule-action').value;
    rule.filter = filter;
    rule.destination_template = document.getElementById('edit-rule-template').value.trim();
    rule.conflict_mode = document.getElementById('edit-rule-conflict').value;
    var tagsVal = document.getElementById('edit-rule-tags').value.trim();
    rule.tags = tagsVal ? tagsVal.split(',').map(function(t) { return t.trim(); }).filter(Boolean) : [];

    document.getElementById('modal-overlay').classList.remove('open');
    _editRuleIdx = null;
    // Restore default modal buttons
    var actions = document.querySelector('.modal-actions');
    if (actions) actions.innerHTML = '<button class="btn btn-secondary" onclick="modalCancel()">Cancel</button><button class="btn btn-danger" onclick="modalConfirm()">Confirm</button>';
    renderRules();
}

// ── Common Rules Library Modal ─────────────────────────────────────────────────
var COMMON_RULES = [
    { id: 'cr-1', name: 'Protected env files', category: 'Other', desc: 'Skips .env, .ini, .cfg, .toml files', filterType: 'extension', filterValues: 'env, ini, cfg, toml', action: 'skip', template: '{parent}/{name}.{ext}', tags: ['protected'] },
    { id: 'cr-2', name: 'Keep tagged files', category: 'Other', desc: 'Skips files with KEEP in the name', filterType: 'name_contains', filterValues: 'KEEP', action: 'skip', template: '{parent}/{name}.{ext}', tags: ['protected'] },
    { id: 'cr-3', name: 'Images', category: 'Images', desc: 'Moves jpg/jpeg/png/webp/heic/gif/bmp/tiff/raw', filterType: 'extension', filterValues: 'jpg, jpeg, png, webp, heic, gif, bmp, tiff, raw', action: 'move', template: 'Images/{name}.{ext}', tags: ['images'] },
    { id: 'cr-4', name: 'Videos', category: 'Videos', desc: 'Moves mp4/mov/mkv/avi/webm/m4v', filterType: 'extension', filterValues: 'mp4, mov, mkv, avi, webm, m4v', action: 'move', template: 'Videos/{name}.{ext}', tags: ['videos'] },
    { id: 'cr-5', name: 'Documents', category: 'Documents', desc: 'Moves pdf/doc/docx/txt/md/rtf/odt/xlsx/xls/pptx/ppt', filterType: 'extension', filterValues: 'pdf, doc, docx, txt, md, rtf, odt, xlsx, xls, pptx, ppt', action: 'move', template: 'Documents/{name}.{ext}', tags: ['documents'] },
    { id: 'cr-6', name: 'Audio', category: 'Audio', desc: 'Moves mp3/wav/m4a/flac/aac/ogg', filterType: 'extension', filterValues: 'mp3, wav, m4a, flac, aac, ogg', action: 'move', template: 'Audio/{name}.{ext}', tags: ['audio'] },
    { id: 'cr-7', name: 'Code', category: 'Code', desc: 'Moves py/js/ts/java/c/cpp/cs/go/rs/sh/css/html/xml/yaml/json/sql', filterType: 'extension', filterValues: 'py, js, ts, java, c, cpp, cs, go, rs, sh, css, html, xml, yaml, json, sql', action: 'move', template: 'Code/{name}.{ext}', tags: ['code'] },
    { id: 'cr-8', name: 'Notebooks', category: 'Code', desc: 'Moves .ipynb Jupyter notebooks', filterType: 'extension', filterValues: 'ipynb', action: 'move', template: 'Code/Notebooks/{name}.{ext}', tags: ['code', 'notebooks'] },
    { id: 'cr-9', name: 'Archives', category: 'Archives', desc: 'Moves zip/rar/7z/tar/gz/bz2/dmg/iso', filterType: 'extension', filterValues: 'zip, rar, 7z, tar, gz, bz2, dmg, iso', action: 'move', template: 'Archives/{name}.{ext}', tags: ['archives'] },
    { id: 'cr-10', name: 'Data files', category: 'Data', desc: 'Moves csv/tsv/xlsx/xls/parquet/json/jsonl', filterType: 'extension', filterValues: 'csv, tsv, xlsx, xls, parquet, json, jsonl', action: 'move', template: 'Data/{name}.{ext}', tags: ['data'] },
    { id: 'cr-11', name: 'Design assets', category: 'Assets', desc: 'Moves psd/ai/fig/sketch/xd/svg', filterType: 'extension', filterValues: 'psd, ai, fig, sketch, xd, svg', action: 'move', template: 'Assets/Design/{name}.{ext}', tags: ['assets', 'design'] },
    { id: 'cr-12', name: 'Fonts', category: 'Assets', desc: 'Moves ttf/otf/woff/woff2', filterType: 'extension', filterValues: 'ttf, otf, woff, woff2', action: 'move', template: 'Assets/Fonts/{name}.{ext}', tags: ['assets', 'fonts'] },
    { id: 'cr-13', name: 'App installers', category: 'Apps', desc: 'Moves exe/msi/dmg/pkg/deb/rpm/apk', filterType: 'extension', filterValues: 'exe, msi, dmg, pkg, deb, rpm, apk', action: 'move', template: 'Apps/{name}.{ext}', tags: ['apps'] },
    { id: 'cr-14', name: 'Screenshots', category: 'Images', desc: 'Moves files with Screenshot or Skärmbild in name', filterType: 'name_contains', filterValues: 'Screenshot, Skärmbild', action: 'move', template: 'Images/Screenshots/{year}/{month}/{name}.{ext}', tags: ['images', 'screenshots'] },
    { id: 'cr-15', name: 'Camera photos', category: 'Images', desc: 'Moves IMG_/DSC_ camera files', filterType: 'name_contains', filterValues: 'IMG_, DSC_', action: 'move', template: 'Images/Camera/{year}/{month}/{name}.{ext}', tags: ['images', 'camera'] },
    { id: 'cr-16', name: 'Temp files', category: 'Temp', desc: 'Moves tmp/temp/log/bak/old/cache files', filterType: 'extension', filterValues: 'tmp, temp, log, bak, old, cache', action: 'move', template: 'Temp/{name}.{ext}', tags: ['temp'] },
    { id: 'cr-17', name: 'Large video files', category: 'LargeFiles', desc: 'Moves mp4/mov/mkv/avi/webm >500MB', filterType: 'size_gt', filterValues: '524288000', action: 'move', template: 'LargeFiles/Videos/{name}.{ext}', tags: ['large', 'videos'] },
    { id: 'cr-18', name: 'Large archives', category: 'LargeFiles', desc: 'Moves zip/rar/7z/tar/gz >500MB', filterType: 'size_gt', filterValues: '524288000', action: 'move', template: 'LargeFiles/Archives/{name}.{ext}', tags: ['large', 'archives'] },
    { id: 'cr-19', name: 'PDFs from Downloads', category: 'Documents', desc: 'Moves pdf from Downloads/ to Documents/PDFs/', filterType: 'path_contains', filterValues: 'Downloads', action: 'move', template: 'Documents/PDFs/{name}.{ext}', tags: ['downloads', 'documents'] },
    { id: 'cr-20', name: 'Docs from Downloads', category: 'Documents', desc: 'Moves doc/docx/txt/md from Downloads/', filterType: 'path_contains', filterValues: 'Downloads', action: 'move', template: 'Documents/{name}.{ext}', tags: ['downloads', 'documents'] },
    { id: 'cr-21', name: 'Archives from Downloads', category: 'Archives', desc: 'Moves archives from Downloads/', filterType: 'path_contains', filterValues: 'Downloads', action: 'move', template: 'Archives/Downloads/{name}.{ext}', tags: ['downloads', 'archives'] },
    { id: 'cr-22', name: 'Images from Downloads', category: 'Images', desc: 'Moves jpg/png/webp from Downloads/', filterType: 'path_contains', filterValues: 'Downloads', action: 'move', template: 'Images/Downloads/{name}.{ext}', tags: ['downloads', 'images'] },
    { id: 'cr-23', name: 'Very small files', category: 'Other', desc: 'Moves files <1KB to Other/SmallFiles/', filterType: 'size_lt', filterValues: '1024', action: 'move', template: 'Other/SmallFiles/{name}.{ext}', tags: ['size'], enabled: false },
    { id: 'cr-24', name: 'No extension', category: 'Unknown', desc: 'Moves files without extension to Unknown/', filterType: 'no_extension', filterValues: '', action: 'move', template: 'Unknown/{name}', tags: ['unknown'] },
    { id: 'cr-25', name: 'Fallback (catch-all)', category: 'Other', desc: 'Catches everything else and moves to Other/', filterType: 'default', filterValues: '', action: 'move', template: 'Other/{name}.{ext}', tags: ['fallback'] },
];

function openCommonRulesModal() {
    var html = '<div style="max-height:60vh;overflow-y:auto">' +
        '<p style="color:#888;font-size:13px;margin-bottom:16px">Select rules to add to your Rules Builder. Added rules can be toggled on/off and edited.</p>';

    COMMON_RULES.forEach(function(cr) {
        var alreadyAdded = state.rules.some(function(r) { return r.name === cr.name; });
        html += '<div style="margin-bottom:10px;padding:10px;background:var(--surface);border:1px solid #333;border-radius:6px">' +
            '<label style="display:flex;align-items:flex-start;gap:10px;cursor:pointer">' +
            '<input type="checkbox" class="common-rule-cb" value="' + cr.id + '"' + (alreadyAdded ? ' disabled checked' : '') + ' style="margin-top:3px;flex-shrink:0">' +
            '<div style="flex:1">' +
            '<div style="font-weight:bold;color:var(--text);font-size:13px">' + escHtml(cr.name) + '</div>' +
            '<div style="color:#888;font-size:12px;margin-top:2px">' + escHtml(cr.desc) + '</div>' +
            '<div style="color:#555;font-size:11px;margin-top:3px">Category: ' + escHtml(cr.category) + ' · Action: ' + escHtml(cr.action) + '</div>' +
            (alreadyAdded ? '<div style="color:#22c55e;font-size:11px;margin-top:3px">✓ Already added</div>' : '') +
            '</div></label></div>';
    });

    html += '</div>';
    document.getElementById('modal-title').textContent = '📖 Common Rules Library';
    document.getElementById('modal-body').innerHTML = html;
    var actions = document.querySelector('.modal-actions');
    actions.innerHTML = '<button class="btn btn-secondary" onclick="modalCancel()">Cancel</button>' +
        '<button class="btn btn-primary" onclick="addCommonRules()">+ Add Selected</button>';
    document.getElementById('modal-overlay').classList.add('open');
}

function addCommonRules() {
    var checkboxes = document.querySelectorAll('.common-rule-cb:checked:not(:disabled)');
    checkboxes.forEach(function(cb) {
        var crId = cb.value;
        var cr = COMMON_RULES.find(function(c) { return c.id === crId; });
        if (!cr) return;
        // Check if already added
        if (state.rules.some(function(r) { return r.name === cr.name; })) return;

        var filter = { type: cr.filterType };
        if (cr.filterType === 'extension') {
            filter.values = cr.filterValues.split(',').map(function(v) { return v.trim(); });
        } else if (cr.filterType === 'name_contains' || cr.filterType === 'path_contains') {
            filter.values = cr.filterValues.split(',').map(function(v) { return v.trim(); });
        } else if (cr.filterType === 'no_extension' || cr.filterType === 'duplicate') {
            filter.value = null;
        } else if (cr.filterValues) {
            filter.value = cr.filterValues;
        }

        state.rules.push({
            name: cr.name,
            category: cr.category,
            action: cr.action,
            filter: filter,
            destination_template: cr.template,
            conflict_mode: cr.action === 'skip' ? 'skip' : 'rename',
            tags: cr.tags || [],
            enabled: cr.enabled !== false,
        });
    });

    document.getElementById('modal-overlay').classList.remove('open');
    // Restore default modal buttons
    var actions = document.querySelector('.modal-actions');
    if (actions) actions.innerHTML = '<button class="btn btn-secondary" onclick="modalCancel()">Cancel</button><button class="btn btn-danger" onclick="modalConfirm()">Confirm</button>';
    renderRules();
    showAlert('rules-alert', 'success', 'Added ' + checkboxes.length + ' rule(s) from library.');
}

// Ensure toggleRule works with string idx from renderRules
var origToggleRule = toggleRule;

