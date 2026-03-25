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
  selectedProfile: 'generic',
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
        html += "<button onclick=\"openFolder(\'" + escHtml(f.path) + "\')\" style=\"background:rgba(255,255,255,0.08);border:none;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px;color:var(--text);white-space:nowrap\" title=\"Open containing folder\">📁 Open folder</button>";
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
          html += "<div style=\"padding:4px 0;border-bottom:1px solid #222;font-size:13px;word-break:break-all;display:flex;align-items:center;gap:6px\">";
          html += "<span style=\"color:var(--text);flex:1;word-break:break-all\">" + escHtml(f.path) + "</span>";
          html += "<span style=\"color:#666;white-space:nowrap\">" + fmtSize(f.size) + "</span>";
          html += "<button onclick=\"openFolder(\'" + escHtml(f.path) + "\')\" style=\"background:rgba(255,255,255,0.08);border:none;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px;color:var(--text);white-space:nowrap\" title=\"Open containing folder\">📁 Open folder</button>";
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
    Images: 'cat-images', Video: 'cat-videos', Audio: 'cat-audio',
    Documents: 'cat-documents', Code: 'cat-code', Archives: 'cat-archives',
    Other: 'cat-other',
  };
  return map[cat] || 'cat-other';
}

function categoryEmoji(cat) {
  const map = {
    Images: '🖼', Video: '🎬', Audio: '🎵', Documents: '📄',
    Code: '💻', Archives: '📦', Other: '📁',
  };
  return map[cat] || '📁';
}

function getCategory(file) {
  const extMap = {
    jpg:'Images',jpeg:'Images',png:'Images',gif:'Images',bmp:'Images',tiff:'Images',
    webp:'Images',heic:'Images',raw:'Images',cr2:'Images',nef:'Images',arw:'Images',
    mp4:'Video',mov:'Video',avi:'Video',mkv:'Video',wmv:'Video',flv:'Video',
    webm:'Video',m4v:'Video',
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
    // Scan history is a convenience feature — fail silently rather than alarm the user
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
      <span class="scan-history-path" onclick="event.stopPropagation();openFolder('${escHtml(s.path)}')" style="cursor:pointer" title="Open folder">${escHtml(s.path)}</span>
      <span class="scan-history-meta">
        ${s.total_files.toLocaleString()} files · ${fmtDate(s.timestamp).split(',')[0]}
      </span>
    </div>
  `).join('');
}

async function loadScan(scanId) {
  try {
    // BUG-022: Use stable backend endpoint to get scan metadata + manifest path
    const scanMeta = await api('GET', `/api/scans/${scanId}`);
    state.manifestPath = scanMeta.manifest_path;
    // Load manifest from the stable path returned by the backend
    const manifest = await api('GET', `/manifest/${scanId}`);
    state.manifest = manifest;
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

  // Detected project roots (from project detection scan)
  const projRoots = m.detected_project_roots || [];
  const projStats = m.project_detection_stats || {};
  let projHtml = '';
  if (projRoots.length > 0) {
    const badgeColor = { high: 'var(--success)', medium: 'var(--warning)', low: 'var(--muted)', informational: 'var(--muted)' };
    projHtml = `
      <div class="card" style="margin-top:12px">
        <div class="card-title">🛡️ Detected Project Roots (${projRoots.length})</div>
        <div style="margin-bottom:8px;font-size:12px;color:var(--muted)">
          Confidence: ${Object.entries(projStats.by_confidence_label || {}).map(([k,v]) => `${v} ${k}`).join(', ')}
          &nbsp;|&nbsp;Kinds: ${Object.entries(projStats.by_kind || {}).map(([k,v]) => `${v} ${k}`).join(', ')}
        </div>
        ${projRoots.map(p => {
          const bc = badgeColor[p.confidence_label] || 'var(--muted)';
          return `
          <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #222;flex-wrap:wrap">
            <span style="font-size:11px;font-weight:bold;padding:2px 7px;border-radius:10px;background:${bc}22;color:${bc};border:1px solid ${bc}44">${p.confidence_label?.toUpperCase() || '?'}</span>
            <span style="color:var(--text);flex:1;font-size:13px;word-break:break-all" title="${escHtml(p.why_detected || '')}">${escHtml(p.relative_path || p.path)}</span>
            <span style="color:var(--muted);font-size:11px;white-space:nowrap">${p.markers ? p.markers.slice(0,4).join(', ') : ''}</span>
            <button onclick="ignoreProjectDetection('${escHtml(p.path)}')" style="background:rgba(255,255,255,0.06);border:none;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px;color:var(--muted)">Ignore</button>
          </div>`;
        }).join('')}
      </div>`;
  }

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
    // Silently skip — rules can always be created from scratch
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
    destinations: [],   // CORE-001: multi-destination fan-out (use edit modal to set)
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
      scope_mode: document.querySelector('input[name="scope_mode"]:checked')?.value || 'preserve_parent_boundaries',
      parent_folders: settings.parent_folders || [],
      project_roots: (state.manifest && state.manifest.detected_project_roots) || [],
    });
    state.actionPlan = result.actions || [];
    renderPreview(result.stats);
    showAlert('preview-alert', 'success',
      `Plan: ${result.stats.moves} moves, ${result.stats.deletes} deletes, ${result.stats.skips} skips`
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

  // Group actions by category
  var groups = {
    organize: { label: "📁 Organize", items: [], color: "var(--accent)" },
    duplicates: { label: "🔁 Duplicates", items: [], color: "var(--warning)" },
    skipped: { label: "✓ Skipped", items: [], color: "#22c55e" },
    blocked: { label: "⛔ Blocked", items: [], color: "var(--error)" },
    unknown: { label: "⚠ Unknown", items: [], color: "#f59e0b" }
  };
  state.actionPlan.forEach(function(a) {
    // Backend emits: classification, blocked, blocked_reason, action, status
    if (a.action === "skip" || a.status === "skipped_no_rule") groups.skipped.items.push(a);
    else if (a.blocked || a.status === "blocked_boundary" || a.status === "blocked") groups.blocked.items.push(a);
    else if (a.action === "unknown_review" || a.classification === "unknown" || a.classification === "system") groups.unknown.items.push(a);
    else groups.organize.items.push(a);
  });

  // Build action row HTML
  function buildActionRow(item, realIdx) {
    var icon = item.action === 'move' ? '→' : item.action === 'delete' ? '🗑' : '—';
    var badgeClass = 'badge-' + (item.action || 'move');
    var isDupKeep = item.rule_matched === '_duplicate_resolution' && item.action === 'skip';
    var isDupDelete = item.rule_matched === '_duplicate_resolution' && item.action === 'delete';
    var defaultChecked = item.action === 'move' || (item.action === 'delete' && !isDupDelete);

    var row = '<div class="action-item">';
    row += '<input type="checkbox" id="action-cb-' + realIdx + '" ' + (isDupKeep ? 'disabled' : '') + ' ' + (defaultChecked ? 'checked' : '') + '>';
    row += '<span class="action-icon">' + icon + '</span>';
    row += '<div class="action-details">';

    // Rule badge + reason per item
    if (item.rule_name) {
      var reasonText = item.rule_match_reason ? '<span style="color:#6b7280;font-size:11px;margin-left:6px">via ' + escHtml(item.rule_match_reason) + '</span>' : '';
      row += '<div style="margin-bottom:4px"><span style="background:rgba(139,92,246,0.2);color:var(--accent);padding:2px 8px;border-radius:12px;font-size:11px;font-weight:bold">' + escHtml(item.rule_name) + '</span>' + reasonText + '</div>';
    }
    row += '<div class="action-src"><a href="#" onclick="openFolder(\'' + escHtml(item.src) + '\');return false" style="color:inherit;text-decoration:none;cursor:pointer" title="Open source folder">' + escHtml(item.src) + '</a></div>';
    if (item.dst && item.action !== 'skip') {
      row += '<div class="action-arrow">↓</div><div class="action-dst"><a href="#" onclick="openFolder(\'' + escHtml(item.dst) + '\');return false" style="color:inherit;text-decoration:none;cursor:pointer" title="Open destination folder">' + escHtml(item.dst) + '</a></div>';
    }
    if (item.rule_match_reason && !item.rule_name) {
      row += '<div style="color:#555;font-size:11px;margin-top:4px">' + escHtml(item.rule_match_reason) + '</div>';
    }
    if (item.blocked_reason) {
      row += '<div style="color:var(--error);font-size:11px;margin-top:4px">⛔ ' + escHtml(item.blocked_reason) + '</div>';
    }
    row += '</div>';
    row += '<span class="action-badge ' + badgeClass + '">' + (item.action || 'move') + '</span>';
    row += '</div>';
    return row;
  }

  // Collapsible group sections — risky items first (blocked, unknown, skipped),
  // then routine moves (organize, duplicates). A visual divider separates the two.
  var groupsHtml = '';
  var needsReviewOrder = ['blocked', 'unknown', 'skipped'];
  var routineOrder = ['organize', 'duplicates'];

  needsReviewOrder.concat(routineOrder).forEach(function(gKey, idx) {
    var g = groups[gKey];
    if (!g.items.length) return;
    // Insert a visual divider between the two sections
    if (idx === needsReviewOrder.length && routineOrder.some(function(rk) { return groups[rk].items.length > 0; })) {
      groupsHtml += '<div style="border-top:2px solid rgba(255,255,255,0.1);margin:16px 0 12px;padding-top:12px">';
      groupsHtml += '<div style="font-size:11px;color:#555;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px">&#9654; Routine moves — these are safe and expected</div></div>';
    }
    var groupId = 'group-' + gKey;
    var count = g.items.length;
    groupsHtml += '<div style="margin-bottom:12px">';
    groupsHtml += '<div class="filter-chip active" style="background:' + g.color + ';color:white;cursor:pointer;display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:8px;margin-bottom:8px" onclick="toggleGroup(\'' + groupId + '\')">';
    groupsHtml += '<span style="font-size:14px;font-weight:bold">' + g.label + '</span>';
    groupsHtml += '<span style="margin-left:auto;font-size:12px;opacity:0.9">' + count + ' item' + (count !== 1 ? 's' : '') + '</span>';
    groupsHtml += '<span style="font-size:10px;margin-left:4px">▾</span>';
    groupsHtml += '</div>';
    groupsHtml += '<div id="' + groupId + '" class="group-items">';
    g.items.forEach(function(item) {
      var realIdx = state.actionPlan.indexOf(item);
      groupsHtml += buildActionRow(item, realIdx);
    });
    groupsHtml += '</div></div>';
  });

  // Stats bar (summary)
  var total = state.actionPlan.length;
  // Simulation banner + file counts
  var protectedCount = state.actionPlan.filter(function(a) {
    return a.blocked || a.status === 'blocked_boundary' || a.status === 'blocked';
  }).length;
  var movesCount = stats ? (stats.moves || 0) : state.actionPlan.filter(function(a) { return a.action === 'move'; }).length;
  var deletesCount = stats ? (stats.deletes || 0) : state.actionPlan.filter(function(a) { return a.action === 'delete'; }).length;

  var simBanner = '<div style="background:#f59e0b15;border:1px solid #f59e0b40;border-radius:8px;padding:12px 16px;margin-bottom:14px">' +
    '<div style="font-size:15px;font-weight:bold;color:#f59e0b;margin-bottom:6px">&#9888; This is a simulation &#8212; no files will be changed.</div>' +
    '<div style="font-size:13px;color:var(--muted)">' +
    '<span style="color:var(--accent);font-weight:600">' + movesCount + '</span> file' + (movesCount !== 1 ? 's' : '') + ' would be moved' +
    (deletesCount > 0 ? ',&nbsp;&nbsp;<span style="color:var(--error);font-weight:600">' + deletesCount + '</span> file' + (deletesCount !== 1 ? 's' : '') + ' would be deleted' : '') +
    (protectedCount > 0 ? ',&nbsp;&nbsp;<span style="color:#f59e0b;font-weight:600">' + protectedCount + '</span> file' + (protectedCount !== 1 ? 's' : '') + ' would be protected' : '') + '.' +
    '</div></div>';

  var statsHtml = '<div class="stats-grid mb-16">' +
    '<div class="stat-card"><div class="stat-value">' + (stats ? stats.total : total) + '</div><div class="stat-label">Total</div></div>' +
    '<div class="stat-card"><div class="stat-value text-primary">' + movesCount + '</div><div class="stat-label">Move</div></div>' +
    '<div class="stat-card"><div class="stat-value text-error">' + deletesCount + '</div><div class="stat-label">Delete</div></div>' +
    '<div class="stat-card"><div class="stat-value text-muted">' + (stats ? (stats.skips || 0) : state.actionPlan.filter(function(a){return a.action==='skip';}).length) + '</div><div class="stat-label">Skip</div></div>' +
    '</div>';

  container.innerHTML = simBanner + statsHtml + groupsHtml;

  // Collapsed by default for large groups
  ['blocked', 'unknown', 'skipped'].forEach(function(gKey) {
    var g = groups[gKey];
    if (g.items.length > 0) {
      var el = document.getElementById('group-' + gKey);
      if (el) el.style.display = 'none';
    }
  });
}

function toggleGroup(groupId) {
  var el = document.getElementById(groupId);
  if (!el) return;
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

function setPreviewFilter(f) {
  state.filter = f;
  const total = state.actionPlan.length;
  const moves = state.actionPlan.filter(a => a.action === 'move').length;
  const deletes = state.actionPlan.filter(a => a.action === 'delete').length;
  const skips = state.actionPlan.filter(a => a.action === 'skip').length;
  const stats = total ? { total, moves, deletes, skips } : null;
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

function updateExecuteBanners() {
  const dryRun = document.getElementById('exec-dry-run')?.checked || false;
  const banner = document.getElementById('dry-run-banner');
  const warningBanner = document.getElementById('execute-warning-banner');
  if (banner) banner.style.display = dryRun ? 'block' : 'none';
  if (warningBanner) warningBanner.style.display = dryRun ? 'none' : 'block';
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
  const warningBanner = document.getElementById('execute-warning-banner');
  if (banner) banner.style.display = dryRun ? 'block' : 'none';
  if (warningBanner) warningBanner.style.display = dryRun ? 'none' : 'block';
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

    // UX-005: human-readable post-run summary
    const moved = result.moved || result.completed || 0;
    const deleted = result.deleted || 0;
    const skipped = result.skipped || 0;
    const protected_ = result.protected || 0;
    const dryLabel = dryRun ? 'Dry run complete — no files were changed.' : '';
    const summaryParts = [];
    if (moved > 0)  summaryParts.push(`${moved} file${moved !== 1 ? 's' : ''} moved`);
    if (deleted > 0) summaryParts.push(`${deleted} file${deleted !== 1 ? 's' : ''} deleted`);
    if (skipped > 0) summaryParts.push(`${skipped} skipped`);
    if (protected_ > 0) summaryParts.push(`${protected_} protected`);
    const summary = summaryParts.length
      ? summaryParts.join(', ') + '.'
      : 'No files were changed.';
    const undoNote = result.undo_log
      ? `Your undo log is saved — you can restore if needed.`
      : '';
    const fullSummary = [dryLabel, summary, undoNote].filter(Boolean).join(' ');
    showAlert('execute-alert', 'success', fullSummary);
    // Show distinct dry-run result banner for simulation runs
    var dryResultBanner = document.getElementById('dry-run-result-banner');
    if (dryResultBanner) {
      dryResultBanner.style.display = dryRun ? 'block' : 'none';
    }
  } catch(e) {
    addFeedLine(`ERROR: ${e.message}`, 'error');
    showAlert('execute-alert', 'error', `Execute failed: ${e.message}`);
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '⚡ Run for real'; }
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
  await loadProfiles();
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

// Show/hide scan-result nav items based on whether data exists
function showResultNavItems() {
  ['crosspath', 'structure', 'duplicates', 'unknown'].forEach(function(page) {
    var nav = document.querySelector('[data-page="' + page + '"]');
    if (nav) nav.style.display = '';
  });
}

function openFolder(path) {
  // Use POST /api/open-path for long paths (avoids URL length limits);
  // fall back to GET for short paths.
  if (path.length > 1500) {
    fetch('/api/open-path', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path: path})
    }).catch(function() {
      showAlert('scan-alert', 'error', 'Could not open folder — check that it exists and try again.');
    });
  } else {
    fetch('/api/open-folder?path=' + encodeURIComponent(path)).catch(function() {
      showAlert('scan-alert', 'error', 'Could not open folder — check that it exists and try again.');
    });
  }
}

function showCrosspathNavItems() {
  ['crosspath', 'structure', 'duplicates', 'unknown'].forEach(function(page) {
    var nav = document.querySelector('[data-page="' + page + '"]');
    if (nav) nav.style.display = '';
  });
}

// Stub — previously referenced but not defined; no-op
function updateIntentScopeVisibility() {
  // Currently a no-op — intent/scope mode UI controls are rendered but not wired to visible behavior
}

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
  const idx = crosspathInputCount;
  const row = document.createElement("div");
  row.style = "display:flex;gap:8px;align-items:center;margin-bottom:8px";
  const input = document.createElement("input");
  input.type = "text";
  input.className = "path-input";
  input.id = "crosspath-input-" + idx;
  input.placeholder = "/path/to/folder";
  input.style = "flex:1;padding:10px;background:var(--surface);color:var(--text);border:1px solid #333;border-radius:8px";
  // Hidden file input kept only as fallback for webkitdirectory (Chromium)
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.id = "crosspath-browse-" + idx;
  fileInput.setAttribute("webkitdirectory", "");
  fileInput.style = "display:none";
  fileInput.onchange = function() { handleBrowseFolder(this, 'crosspath-input-' + idx); };
  const btn = document.createElement("button");
  btn.className = "btn btn-secondary";
  btn.style = "white-space:nowrap";
  btn.textContent = "📁 Browse";
  btn.onclick = function() { asyncBrowseFolderByIndex(idx); };
  row.appendChild(input);
  row.appendChild(fileInput);
  row.appendChild(btn);
  container.appendChild(row);
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
    showResultNavItems();
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
function ignoreProjectDetection(path) {
  // Dismiss a detected project root from the current session list
  // (stored in a session dismissed set; re-render results)
  if (!window._ignoredProjectRoots) window._ignoredProjectRoots = new Set();
  window._ignoredProjectRoots.add(path);
  // Re-render results to hide the dismissed root
  if (state.manifest) {
    if (!state.manifest._origDetectedProjectRoots) {
      state.manifest._origDetectedProjectRoots = state.manifest.detected_project_roots || [];
    }
    state.manifest.detected_project_roots = state.manifest._origDetectedProjectRoots.filter(
      function(p) { return !window._ignoredProjectRoots.has(p.path); }
    );
    renderResults();
  }
  showAlert('preview-alert', 'success', 'Detection dismissed for this session');
}

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
async function browseForFolder(targetInputId) {
    try {
        var r = await fetch('/api/dialog/folder', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({start_dir: ''})
        });
        var d = await r.json();
        if (d.ok && d.path) {
            var el = document.getElementById(targetInputId);
            if (el) el.value = d.path;
        }
    } catch(e) {
        // Fallback: manual path entry
        var path = prompt("Enter the full path to the folder:");
        if (path) {
            var el = document.getElementById(targetInputId);
            if (el) el.value = path;
        }
    }
}

async function asyncBrowseFolderByIndex(idx) {
    await browseForFolder('crosspath-input-' + idx);
}

function handleBrowseFolder(input, targetId) {
    var files = input.files;
    if (!files || files.length === 0) return;
    var dir = files[0].webkitRelativePath.split('/')[0];
    var target = document.getElementById(targetId);
    if (!target) return;
    var fullPath = files[0].path || '';
    var resolvedPath = '';
    if (fullPath) {
        resolvedPath = fullPath.substring(0, fullPath.indexOf(dir) + dir.length) || dir;
    } else {
        resolvedPath = '/' + dir;
    }
    if (target.tagName === 'INPUT') {
        target.value = resolvedPath;
        // Sync a companion display div if it exists (e.g. scan-path → scan-path-display)
        var dispId = targetId + '-display';
        var disp = document.getElementById(dispId);
        if (disp) {
            disp.textContent = resolvedPath;
            disp.classList.remove('path-display-empty');
            disp.style.color = 'var(--text)';
            disp.onclick = null;
        }
    } else {
        // Div display — update text and mark as non-empty
        target.textContent = resolvedPath;
        target.classList.remove('path-display-empty');
        target.style.color = 'var(--text)';
        target.onclick = null; // no longer clickable once set (file picker is the control)
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

// Live rule status polling state
var _ruleStatusInterval = null;
var _ruleStatus = {}; // ruleIdx -> status string: 'idle'|'running'|'success'|'warning'|'error'

function startRuleStatusPolling() {
    if (_ruleStatusInterval) return;
    _ruleStatusInterval = setInterval(pollRuleStatus, 2000);
}

function stopRuleStatusPolling() {
    if (_ruleStatusInterval) {
        clearInterval(_ruleStatusInterval);
        _ruleStatusInterval = null;
    }
}

async function pollRuleStatus() {
    if (state.currentPage !== 'rules') {
        stopRuleStatusPolling();
        return;
    }
    try {
        var data = await api('GET', '/api/rules/status');
        var newStatus = {};
        if (Array.isArray(data.statuses)) {
            data.statuses.forEach(function(s) {
                for (var i = 0; i < state.rules.length; i++) {
                    if (state.rules[i].name === s.rule_name || state.rules[i].name === s.name) {
                        newStatus[i] = s.status || 'idle';
                        break;
                    }
                }
            });
        } else if (data.statuses && typeof data.statuses === 'object') {
            Object.keys(data.statuses).forEach(function(key) {
                for (var i = 0; i < state.rules.length; i++) {
                    if (state.rules[i].name === key) {
                        newStatus[i] = data.statuses[key] || 'idle';
                        break;
                    }
                }
            });
        }
        _ruleStatus = newStatus;
        applyRuleStatusDots();
    } catch(e) {
        // Silently ignore polling failures
    }
}

function applyRuleStatusDots() {
    state.rules.forEach(function(rule, idx) {
        var status = _ruleStatus[idx] || 'idle';
        var dot = document.getElementById('rule-status-dot-' + idx);
        if (dot) {
            dot.className = 'rule-status-dot rule-status-' + status;
            dot.title = status.charAt(0).toUpperCase() + status.slice(1);
        }
    });
}

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
        var status = _ruleStatus[idx] || 'idle';

        return '<div class="rule-card" style="background:var(--surface);border:1px solid #333;border-radius:8px;padding:12px;margin-bottom:8px">' +
            '<div style="display:flex;align-items:center;gap:10px">' +
            '<span class="rule-status-dot rule-status-' + escHtml(status) + '" id="rule-status-dot-' + idx + '" title="' + escHtml(status) + '"></span>' +
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
            (rule.destinations && rule.destinations.length ? '<div style="font-size:12px;color:#aaa;margin-bottom:4px"><strong>Fan-out:</strong> <span style="background:#6366f140;color:#a5b4fc;border-radius:3px;padding:1px 5px">' + rule.destinations.length + ' dest' + (rule.destinations.length === 1 ? '' : 's') + '</span> — <span style="color:#6366f1">copies to ' + rule.destinations.length + ' location' + (rule.destinations.length === 1 ? '' : 's') + '</span></div>' : '') +
            (rule.tags && rule.tags.length ? '<div style="font-size:12px;color:#aaa;margin-bottom:6px"><strong>Tags:</strong> ' + rule.tags.map(function(t) { return '<span style="background:#333;border-radius:3px;padding:1px 4px;margin-right:3px">' + escHtml(t) + '</span>'; }).join('') + '</div>' : '') +
            '<button onclick="openEditModal(' + idx + ')" class="btn btn-secondary" style="margin-top:6px">✏ Edit</button>' +
            '</div></div>';
    }).join('');

    container.innerHTML = html;

    // Start polling when rules page is shown
    startRuleStatusPolling();
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

    // Build destinations string from array (CORE-001: multi-destination fan-out)
    var destinationsStr = '';
    if (rule.destinations && rule.destinations.length) {
        destinationsStr = rule.destinations.join('\n');
    }
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
        ['Images','Documents','Video','Audio','Code','Archives','Other'].map(function(c) {
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

        '<div class="form-group"><label style="color:var(--text);font-size:13px">Additional Destinations <span style="color:#666;font-weight:normal">(fan-out · one per line)</span></label>' +
        '<textarea id="edit-rule-destinations" rows="3" placeholder="Backups/{name}.{ext}\nArchive/{year}/{month}/{name}.{ext}" style="width:100%;padding:8px;border-radius:6px;border:1px solid #333;background:var(--surface);color:var(--text);box-sizing:border-box;font-family:monospace;font-size:12px;resize:vertical">' + escHtml(destinationsStr) + '</textarea>' +
        '<div style="font-size:11px;color:#666;margin-top:2px">Separate multiple destinations with newlines. Leave empty for single destination.</div></div>' +

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
    // CORE-001: multi-destination fan-out — parse newline-separated destinations
    var destLines = document.getElementById('edit-rule-destinations').value.split('\n');
    rule.destinations = destLines.map(function(d) { return d.trim(); }).filter(Boolean);
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
    { id: 'cr-4', name: 'Videos', category: 'Video', desc: 'Moves mp4/mov/mkv/avi/webm/m4v', filterType: 'extension', filterValues: 'mp4, mov, mkv, avi, webm, m4v', action: 'move', template: 'Video/{name}.{ext}', tags: ['videos'] },
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

// ─── Run Profiles ───────────────────────────────────────────────────────────

async function loadProfiles() {
    try {
        var profiles = await api("GET", "/api/profiles");
        var container = document.getElementById("profile-selector");
        if (!container) return;

        container.innerHTML = profiles.map(function(p) {
            return '<button class="profile-card" data-profile="' + escHtml(p.id) + '" onclick="selectProfile(\'' + escHtml(p.id) + '\')" ' +
                'title="' + escHtml(p.description) + '" style="' +
                'display:inline-flex;align-items:center;gap:6px;padding:8px 14px;border-radius:8px;border:1px solid rgba(255,255,255,0.1);' +
                'background:rgba(255,255,255,0.04);cursor:pointer;font-size:13px;color:var(--text);transition:all 0.15s">' +
                '<span style="font-size:16px">' + p.icon + '</span>' +
                '<span>' + escHtml(p.name) + '</span>' +
                '</button>';
        }).join("");

        // Init first profile as selected
        if (profiles.length > 0) {
            selectProfile(profiles[0].id);
        }
    } catch(e) {
        console.error("loadProfiles failed", e);
    }
}

function selectProfile(profileId) {
    state.selectedProfile = profileId;
    document.querySelectorAll(".profile-card").forEach(function(el) {
        el.style.borderColor = el.dataset.profile === profileId
            ? "var(--accent)"
            : "rgba(255,255,255,0.1)";
        el.style.background = el.dataset.profile === profileId
            ? "rgba(139,92,246,0.15)"
            : "rgba(255,255,255,0.04)";
    });
    updateIntentScopeVisibility();
    // Sync scope_mode from profile
    syncScopeModeFromProfile(profileId);
    // BUG-013/014: calling generateProfileRules on profile selection and showing results
    generateProfileRules(profileId);
}

async function syncScopeModeFromProfile(profileId) {
    try {
        var profiles = await api("GET", "/api/profiles");
        var profile = profiles.find(function(p) { return p.id === profileId; });
        if (!profile) return;
        var allowed = profile.allowed_scope_modes || [];
        var defaultSm = profile.default_scope_mode || "preserve_parent_boundaries";
        // Hide scope mode options not allowed for this profile
        document.querySelectorAll('input[name="scope_mode"]').forEach(function(radio) {
            var label = radio.closest('label');
            if (!label) return;
            if (allowed.length === 0 || allowed.includes(radio.value)) {
                label.style.display = '';
            } else {
                label.style.display = 'none';
            }
        });
        // Check the default
        var defaultRadio = document.querySelector('input[name="scope_mode"][value="' + defaultSm + '"]');
        if (defaultRadio) defaultRadio.checked = true;
    } catch(e) {
        console.warn("syncScopeModeFromProfile failed", e);
    }
}

async function generateProfileRules(profileId) {
    try {
        var res = await api("POST", "/api/profiles/" + profileId + "/generate-rules");
        if (res.count > 0) {
            await loadRules();
            renderRules();
            showAlert("rules-alert", "info",
                "Profile rules added (" + res.count + ") — <strong>disabled by default</strong>. Go to Rules to enable what you need before previewing."
            );
            // Show prominent banner so the user can't miss this information
            var banner = document.getElementById("profile-info-banner");
            if (banner) {
                banner.style.display = "block";
                banner.style.background = "rgba(139,92,246,0.15)";
                banner.style.border = "1px solid rgba(139,92,246,0.4)";
                banner.style.color = "var(--accent)";
                banner.innerHTML = "&#128275; <strong>" + res.count + " rules generated</strong> — all disabled by default. Go to <strong>Rules</strong> to enable what you need before previewing.";
            }
        } else {
            // No rules generated — clear the banner
            var banner = document.getElementById("profile-info-banner");
            if (banner) {
                banner.style.display = "none";
            }
        }
    } catch(e) {
        console.error("generateProfileRules failed", e);
    }
}

// ─── Help System ─────────────────────────────────────────────────────────────

var helpSections = {
  scan: `<h2 style="color:var(--accent);margin-bottom:12px">🔍 Scan</h2>
<p>Enter a folder path and click <strong>Scan</strong> to inventory all files. The app finds duplicates, organizes files by type, and builds a folder map.</p>
<h3 style="margin-top:16px;color:var(--text)">Run Profile</h3>
<p>Choose a <strong>Run Profile</strong> to pre-load relevant rules. Generic = no rules. Images/Videos/Documents/Code = category-specific rules. Duplicates = focus on finding dupes. Clicking a profile adds its rules to the Rules Builder (rules start disabled — enable what you want).</p>
<h3 style="margin-top:16px;color:var(--text)">Scan Modes</h3>
<p><strong>Fast</strong>: filename + size duplicates only. <strong>Deep</strong>: full SHA256 hash — slower but accurate.</p>`,

  results: `<h2 style="color:var(--accent);margin-bottom:12px">📊 Results</h2>
<p>See all discovered files. Use the search box to filter by filename.</p>`,

  rules: `<h2 style="color:var(--accent);margin-bottom:12px">📁 Rules</h2>
<p>Rules decide what happens to each file. Files are matched in <strong>priority order</strong> — first match wins.</p>
<h3 style="margin-top:16px;color:var(--text)">Adding Rules</h3>
<p>Click <strong>+ Common Rules Library</strong> to browse preset bundles. Check the ones you want, click <strong>Add Selected</strong>.</p>
<h3 style="margin-top:16px;color:var(--text)">Actions</h3>
<p><strong>Move</strong>: move to destination. <strong>Skip</strong>: leave file as-is. <strong>Delete</strong>: move to trash.</p>`,

  preview: `<h2 style="color:var(--accent);margin-bottom:12px">👁 Preview</h2>
<p>See exactly what will happen before anything changes. Each file shows <strong>which rule matched</strong> and <strong>where it will go</strong>.</p>`,

  execute: `<h2 style="color:var(--accent);margin-bottom:12px">⚡ Execute</h2>
<div style="background:#f59e0b20;border:1px solid #f59e0b;border-radius:8px;padding:12px;margin-bottom:16px">⚠ <strong>Dry Run is ON</strong> — no files modified. Turn OFF to apply changes.</div>
<p><strong>Rename</strong>: adds _1, _2 if file exists. <strong>Skip</strong>: leave existing. <strong>Overwrite</strong>: replace.</p>
<p>Every run creates an <strong>undo snapshot</strong> — restore from Execute page history.</p>`,

  crosspath: `<h2 style="color:var(--accent);margin-bottom:12px">🔀 Cross-Path</h2>
<p>Scan <strong>multiple folders</strong> at once. Finds duplicates across different locations.</p>`,

  structure: `<h2 style="color:var(--accent);margin-bottom:12px">🗂 Structure</h2>
<p>See folder tree and structural issues. Deep nesting and empty folders are flagged.</p>`,

  duplicates: `<h2 style="color:var(--accent);margin-bottom:12px">🔁 Duplicates</h2>
<p><strong>Exact</strong>: same SHA256 hash. <strong>Likely</strong>: same name + size. <strong>Similar</strong>: similar name + size. Click a file path to reveal in Finder.</p>`,

  unknown: `<h2 style="color:var(--accent);margin-bottom:12px">⚠ Unknown</h2>
<p>Files with no recognized extension. Review before executing. Click <strong>Keep</strong> (safe folder) or <strong>Delete</strong> (trash).</p>`,

  settings: `<h2 style="color:var(--accent);margin-bottom:12px">⚙ Settings</h2>
<p><strong>Protected Folders</strong>: paths that File Organizer will never touch. Add folders you want to keep completely safe.</p>`,

  mockdata: `<h2 style="color:var(--accent);margin-bottom:12px">🧪 Mock Data</h2>
<p>Generate a synthetic test workspace. All files are <strong>sparse</strong> — claim disk space but use almost none.</p>
<ul style="margin-top:8px">
<li>Choose size: 1–2000 GB fake</li>
<li>Pick categories: images, videos, code, etc.</li>
<li>Files are created at the chosen path</li>
<li>Auto-fills scan path when done</li>
</ul>`,

  profiles: `<h2 style="color:var(--accent);margin-bottom:12px">🏷 Run Profiles</h2>
<p>Pre-configured rule bundles for specific goals. Select on the Scan page before scanning.</p>
<ul style="margin-top:8px">
<li><strong>Generic</strong>: scan only, no rules</li>
<li><strong>Images</strong>: photo + screenshot + camera rules</li>
<li><strong>Videos</strong>: video file rules</li>
<li><strong>Documents</strong>: PDF, Word, spreadsheet rules</li>
<li><strong>Duplicates</strong>: duplicate detection focus</li>
<li><strong>Code</strong>: source code file rules</li>
</ul>`
};

function showHelpSection(id) {
    var content = document.getElementById("help-content");
    if (!content) return;
    content.innerHTML = helpSections[id] || "<p>Coming soon.</p>";
    document.querySelectorAll(".help-toc-item").forEach(function(el) { el.classList.remove("active"); });
    if (event && event.target) event.target.classList.add("active");
}

// Patch navigate to init help page
var _orig_navigate = navigate;
navigate = function(page) {
    _orig_navigate(page);
    if (page === "help") {
        showHelpSection("scan");
        var first = document.querySelector(".help-toc-item");
        if (first) first.classList.add("active");
    }
};

