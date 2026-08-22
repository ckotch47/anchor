from __future__ import annotations

import ipaddress
import webbrowser
from typing import Any

import typer
from starlette.responses import HTMLResponse
from starlette.routing import Route

from anchor.container import build_container
from anchor.mcp_server import mcp_app

UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Anchor</title>
<style>
:root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#e6edf3;--text-dim:#8b949e;--accent:#58a6ff;--green:#3fb950;--orange:#d29922;--red:#f85149;--radius:8px;--font:ui-monospace,SFMono-Regular,SF Mono,Menlo,Consolas,monospace;--sidebar-w:220px}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font:14px/1.5 var(--font);overflow:hidden;height:100vh}
#app{display:flex;height:100vh}
#sidebar{width:var(--sidebar-w);background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
#sidebar .brand{padding:16px;font-size:16px;font-weight:700;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px}
#sidebar .brand span{color:var(--accent)}
#sidebar nav{flex:1;padding:8px 0;overflow-y:auto}
#sidebar nav a{display:flex;align-items:center;gap:10px;padding:10px 16px;color:var(--text-dim);text-decoration:none;cursor:pointer;border-left:3px solid transparent;transition:.15s}
#sidebar nav a:hover,#sidebar nav a.active{color:var(--text);background:rgba(88,166,255,.08)}
#sidebar nav a.active{border-left-color:var(--accent);color:var(--accent)}
#sidebar .status{padding:12px 16px;border-top:1px solid var(--border);font-size:12px;display:flex;align-items:center;gap:8px}
#sidebar .status-dot{width:8px;height:8px;border-radius:50%;background:var(--text-dim)}
#sidebar .status-dot.ok{background:var(--green)}
#sidebar .status-dot.err{background:var(--red)}
#main{flex:1;display:flex;flex-direction:column;min-width:0;overflow:hidden}
#topbar{display:flex;align-items:center;justify-content:space-between;padding:12px 24px;border-bottom:1px solid var(--border);background:var(--surface);flex-shrink:0}
#topbar h2{font-size:15px;font-weight:600}
#topbar .actions{display:flex;gap:8px}
#content{flex:1;padding:24px;overflow-y:auto}
.page{display:none}
.page.active{display:block}
input,textarea,select{background:var(--bg);border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:var(--radius);font:13px/1.5 var(--font);width:100%;outline:none;transition:border-color .15s}
input:focus,textarea:focus,select:focus{border-color:var(--accent)}
textarea{resize:vertical;min-height:80px}
button,.btn{background:var(--accent);color:#fff;border:none;padding:7px 16px;border-radius:var(--radius);cursor:pointer;font:13px/1.5 var(--font);transition:opacity .15s;white-space:nowrap}
button:hover,.btn:hover{opacity:.8}
.btn-secondary{background:var(--surface);color:var(--text);border:1px solid var(--border)}
.btn-secondary:hover{background:var(--border)}
.btn-danger{background:var(--red)}
.btn-sm{padding:4px 10px;font-size:12px}
.btn-icon{background:0 0;color:var(--text-dim);padding:4px;border:none;cursor:pointer;font-size:16px;line-height:1}
.btn-icon:hover{color:var(--text)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:12px}
.card h3{font-size:13px;font-weight:600;color:var(--text-dim);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px}
.row{display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap}
.row>*{flex:1;min-width:200px}
.gap-8{gap:8px}
.mt-8{margin-top:8px}
.mb-8{margin-bottom:8px}
.flex{display:flex}
.flex-1{flex:1}
.items-center{align-items:center}
.justify-between{justify-content:space-between}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--border)}
th{color:var(--text-dim);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.5px}
tr:hover td{background:rgba(88,166,255,.04)}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600}
.badge-green{background:rgba(63,185,80,.15);color:var(--green)}
.badge-orange{background:rgba(210,153,34,.15);color:var(--orange)}
.badge-red{background:rgba(248,81,69,.15);color:var(--red)}
.badge-blue{background:rgba(88,166,255,.15);color:var(--accent)}
.empty{text-align:center;padding:48px 0;color:var(--text-dim)}
.loading{text-align:center;padding:24px;color:var(--text-dim)}
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:100;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:24px;width:90vw;max-width:960px;max-height:85vh;display:flex;flex-direction:column}
.modal-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-shrink:0}
.modal-head h3{margin:0;font-size:16px}
.modal-close{background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:20px;padding:4px;line-height:1}
.modal-close:hover{color:var(--text)}
.modal-body{flex:1;overflow-y:auto;min-height:0}
.modal-body::-webkit-scrollbar{width:6px}
.modal-body::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.modal h3{font-size:15px;margin-bottom:16px}
.modal label{display:block;font-size:12px;color:var(--text-dim);margin-bottom:4px;margin-top:12px}
.modal label:first-child{margin-top:0}
.modal .btn-row{display:flex;gap:8px;justify-content:flex-end;margin-top:16px}
pre{background:var(--bg);padding:12px;border-radius:var(--radius);overflow-x:auto;font-size:12px;line-height:1.4}
.search-box{position:relative}
.search-box input{padding-left:32px}
.search-box::before{content:'\1F50D';position:absolute;left:10px;top:50%;transform:translateY(-50%);font-size:14px;opacity:.5}
.form-group{margin-bottom:12px}
.form-group label{display:block;font-size:12px;color:var(--text-dim);margin-bottom:4px}
.tool-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.tool-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px;cursor:pointer;transition:border-color .15s}
.tool-card:hover{border-color:var(--accent)}
.tool-card h4{font-size:13px;margin-bottom:4px;color:var(--accent)}
.tool-card p{font-size:12px;color:var(--text-dim)}
@media(max-width:768px){#sidebar{width:56px}#sidebar .brand span,#sidebar nav a span,#sidebar .status span{display:none}#sidebar nav a{justify-content:center;padding:12px}#content{padding:16px}.modal{min-width:auto}}
</style>
</head>
<body>
<div id="app">
<aside id="sidebar">
<div class="brand"><span>&#9670;</span> Anchor</div>
<nav>
<a class="active" data-page="dashboard">&#9679; Dashboard</a>
<a data-page="notes">&#128221; Notes</a>
<a data-page="tasks">&#9745; Tasks</a>
<a data-page="history">&#128214; History</a>
<a data-page="files">&#128196; Files</a>
<a data-page="projects">&#128202; Projects</a>
<a data-page="search">&#128269; Search</a>
<a data-page="tools">&#9881; Tools</a>
<a data-page="config">&#9878; Config</a>
</nav>
<div class="status"><span class="status-dot" id="statusDot"></span><span id="statusText">Connecting...</span></div>
</aside>
<div id="main">
<div id="topbar">
  <div style="display:flex;align-items:center;gap:12px">
    <h2 id="pageTitle">Dashboard</h2>
    <select id="projectFilter" style="width:auto;min-width:120px;font-size:12px;padding:4px 8px" onchange="onProjectChange()">
      <option value="">-- all projects --</option>
    </select>
  </div>
  <div class="actions" id="topActions"></div>
</div>
<div id="content">

<div class="page active" id="page-dashboard"></div>
<div class="page" id="page-notes"></div>
<div class="page" id="page-tasks"></div>
<div class="page" id="page-search"></div>
<div class="page" id="page-tools"></div>
<div class="page" id="page-config"></div>
<div class="page" id="page-task-view"></div>
<div class="page" id="page-note-view"></div>
<div class="page" id="page-history"></div>
<div class="page" id="page-files"></div>
<div class="page" id="page-projects"></div>

</div></div></div>

<div class="modal-overlay" id="modalOverlay"><div class="modal"><div class="modal-head"><h3 id="modalTitle">Task</h3><button class="modal-close" onclick="closeModal()">&times;</button></div><div class="modal-body" id="modalBody"></div></div></div>

<script>
const MCP_PROTOCOL_VERSION = '2025-11-25';
const BASE = window.location.origin;

let mcpPostUrl = null;
let mcpPending = new Map();
let mcpNextId = 1;
let mcpConnected = false;
let mcpEventSource = null;
let currentPage = 'dashboard';
let currentProject = '';

async function mcpRequest(method, params) {
  const id = mcpNextId++;
  await fetch(mcpPostUrl, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({jsonrpc:'2.0',id,method,params}) });
  return new Promise(resolve => { mcpPending.set(id, resolve); });
}

async function mcpCallTool(name, args) {
  const res = await mcpRequest('tools/call', { name, arguments: args || {} });
  if (res.error) throw new Error(res.error.message || JSON.stringify(res.error));
  const r = res.result;
  if (r.isError) {
    const sc = r.structuredContent || {};
    throw new Error(sc.error?.message || 'Tool error');
  }
  return r.structuredContent || r.content?.[0]?.text;
}

function withProject(args) {
  if (!currentProject) throw new Error('Select a project before using project-scoped tools');
  args.project = currentProject;
  return args;
}

async function loadProjects() {
  try {
    const data = await mcpCallTool('projects_list');
    const projects = data?.data?.projects || [];
    const sel = document.getElementById('projectFilter');
    sel.innerHTML = projects.map(p =>
      `<option value="${esc(p)}">${esc(p)}</option>`
    ).join('');
    if (!currentProject && projects.length) currentProject = projects[0];
    sel.value = currentProject;
  } catch(_) {}
}

async function connectMCP() {
  return new Promise((resolve, reject) => {
    mcpEventSource = new EventSource('/sse');
    mcpEventSource.addEventListener('endpoint', async e => {
      mcpPostUrl = BASE + e.data;
      try {
        const initRes = await mcpRequest('initialize', {
          protocolVersion: MCP_PROTOCOL_VERSION, capabilities: {},
          clientInfo: { name: 'anchor-web-ui', version: '1.0.0' }
        });
        if (initRes.error) throw new Error(initRes.error.message);
        await fetch(mcpPostUrl, { method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ jsonrpc:'2.0', method:'notifications/initialized' }) });
        mcpConnected = true;
        document.getElementById('statusDot').className = 'status-dot ok';
        document.getElementById('statusText').textContent = 'Connected';
        await loadProjects();
        resolve();
      } catch(err) { reject(err); }
    });
    mcpEventSource.addEventListener('message', e => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.id != null && mcpPending.has(msg.id)) { mcpPending.get(msg.id)(msg); mcpPending.delete(msg.id); }
      } catch(_) {}
    });
    mcpEventSource.onerror = () => {
      document.getElementById('statusDot').className = 'status-dot err';
      document.getElementById('statusText').textContent = 'Disconnected'; mcpConnected = false;
    };
    setTimeout(() => { if (!mcpConnected) reject(new Error('Connection timeout')); }, 10000);
  });
}

const pages = {};

function showPage(name) {
  currentPage = name;
  document.querySelectorAll('#sidebar nav a').forEach(a => a.classList.toggle('active', a.dataset.page === name || (name==='task-view' && a.dataset.page==='tasks') || (name==='note-view' && a.dataset.page==='notes')));
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === 'page-' + name));
  const titles = { dashboard:'Dashboard', notes:'Notes', tasks:'Tasks', history:'History', files:'Files', projects:'Projects', search:'Search', tools:'Tools', config:'Config', 'task-view':'Task', 'note-view':'Note' };
  document.getElementById('pageTitle').textContent = titles[name] || name;
  document.getElementById('topActions').innerHTML = '';
  if (pages[name] && name !== 'task-view' && name !== 'note-view') pages[name]();
}

function onProjectChange() {
  currentProject = document.getElementById('projectFilter').value;
  if (pages[currentPage]) pages[currentPage]();
}

document.querySelectorAll('#sidebar nav a').forEach(a => {
  a.addEventListener('click', () => showPage(a.dataset.page));
});

// ---- Dashboard ----
pages.dashboard = async function() {
  const el = document.getElementById('page-dashboard');
  el.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const data = await mcpCallTool('health');
    el.innerHTML = `
      <div class="row">
        <div class="card"><h3>Status</h3><div style="font-size:24px;font-weight:700;color:${data.ok?'var(--green)':'var(--red)'}">${data.ok?'OK':'ERROR'}</div></div>
        <div class="card"><h3>Database</h3><div style="font-size:13px;word-break:break-all">${esc(data.data?.database_path||'N/A')}</div></div>
      <div class="card"><h3>Project</h3><div style="font-size:13px">${esc(currentProject||'(none selected)')}</div></div>
      </div>
      <div class="card"><h3>Response</h3><pre>${esc(JSON.stringify(data.data||data, null, 2))}</pre></div>`;
  } catch(e) { el.innerHTML = `<div class="card"><h3>Error</h3><pre style="color:var(--red)">${esc(e.message)}</pre></div>`; }
};

// ---- Notes ----
pages.notes = async function() {
  document.getElementById('topActions').innerHTML = '<button onclick="showNoteForm()">+ New Note</button>';
  document.getElementById('page-notes').innerHTML = '<div class="loading">Loading...</div>';
  await renderNotes();
};

async function renderNotes(query) {
  const el = document.getElementById('page-notes');
  try {
    const args = withProject({ limit: 50 });
    const data = query ? await mcpCallTool('notes_search', Object.assign({ query }, args))
                       : await mcpCallTool('notes_list', args);
    const notes = data?.data?.notes || data?.data?.results?.map(r => r.note) || [];
    if (!notes.length) { el.innerHTML = '<div class="empty">No notes yet.</div>'; return; }
    el.innerHTML = `
      <div class="search-box mb-8"><input type="text" placeholder="Search notes..." oninput="clearTimeout(this._t);this._t=setTimeout(()=>renderNotes(this.value),300)"></div>
      <table><colgroup><col style="width:30%"><col style="width:35%"><col style="width:60px"><col style="width:120px"></colgroup>
      <thead><tr><th>Title</th><th>Body</th><th>Pinned</th><th></th></tr></thead><tbody>
      ${notes.map(n => `<tr>
        <td><strong>${esc(n.title||'Untitled')}</strong> <span style="color:var(--text-dim);font-size:11px">${esc(n.id?.slice(0,8)||'')}</span></td>
        <td style="color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc((n.body||'').slice(0,120))}</td>
        <td>${n.pinned?'<span class="badge badge-orange">Y</span>':''}</td>
        <td><button class="btn-sm" onclick="viewNote('${n.id}')">View</button> <button class="btn-sm btn-secondary" onclick="showNoteForm('${n.id}')">Edit</button> <button class="btn-sm btn-danger" onclick="deleteNote('${n.id}')">Del</button></td>
      </tr>`).join('')}
      </tbody></table>`;
  } catch(e) { el.innerHTML = `<div class="card"><pre style="color:var(--red)">${esc(e.message)}</pre></div>`; }
}

window.showNoteForm = async function(id) {
  let note = { title:'', body:'', pinned:false, source:'cli' };
  if (id) {
    try { const data = await mcpCallTool('notes_get', withProject({ note_id:id })); note = data.data.note; }
    catch(e) { alert('Error: '+e.message); return; }
  }
  const overlay = document.getElementById('modalOverlay');
  document.getElementById('modalBody').innerHTML = `
    <h3>${id?'Edit Note':'New Note'}</h3>
    <div class="form-group"><label>Title</label><input id="noteTitle" value="${esc(note.title)}"></div>
    <div class="form-group"><label>Body</label><textarea id="noteBody">${esc(note.body)}</textarea></div>
    <div class="form-group"><label><input type="checkbox" id="notePinned" ${note.pinned?'checked':''}> Pinned</label></div>
    <div class="btn-row"><button class="btn-secondary" onclick="closeModal()">Cancel</button><button onclick="saveNote('${id||''}')">Save</button></div>`;
  overlay.classList.add('open');
};

window.saveNote = async function(id) {
  const title = document.getElementById('noteTitle').value;
  const body = document.getElementById('noteBody').value;
  const pinned = document.getElementById('notePinned').checked;
  try {
    const args = withProject({ title, body, pinned, source:'cli' });
    if (id) await mcpCallTool('notes_update', Object.assign({ note_id:id }, args));
    else await mcpCallTool('notes_add', args);
    closeModal(); renderNotes();
  } catch(e) { alert('Error: '+e.message); }
};

window.deleteNote = async function(id) {
  if (!confirm('Delete?')) return;
  try { await mcpCallTool('notes_delete', withProject({ note_id:id })); renderNotes(); }
  catch(e) { alert('Error: '+e.message); }
};

window.viewNote = async function(id) {
  try {
    const el = document.getElementById('page-note-view');
    el.innerHTML = '<div class="loading">Loading...</div>';
    showPage('note-view');

    const data = await mcpCallTool('notes_get', withProject({ note_id:id }));
    const note = data.data.note;

    document.getElementById('pageTitle').textContent = esc(note.title);
    document.getElementById('topActions').innerHTML = '<button class="btn-secondary" onclick="showPage(\'notes\')">&larr; Back</button> <button class="btn-sm btn-secondary" onclick="showNoteForm(\''+id+'\')">Edit</button>';

    let html = '<div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center">' +
      '<span class="badge badge-blue">note</span>' +
      (note.pinned?'<span class="badge badge-orange">pinned</span>':'') +
      '<span style="color:var(--text-dim);font-size:12px">'+esc(note.id?.slice(0,8)||'')+'</span></div>';

    html += '<div style="font-size:16px;font-weight:600;line-height:1.4;margin-bottom:16px">'+esc(note.title)+'</div>';

    if (note.body) {
      html += '<div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:16px;font-size:13px;line-height:1.7;white-space:pre-wrap;margin-bottom:16px">'+esc(note.body)+'</div>';
    }

    html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:14px;font-size:12px;margin-bottom:16px">' +
      '<div><span style="color:var(--text-dim)">Created</span><br>'+esc(note.created_at?.slice(0,10)||'-')+'</div>' +
      '<div><span style="color:var(--text-dim)">Updated</span><br>'+esc(note.updated_at?.slice(0,10)||'-')+'</div>' +
      '<div><span style="color:var(--text-dim)">Source</span><br>'+esc(note.source||'—')+'</div>' +
      '<div><span style="color:var(--text-dim)">Project</span><br>'+esc(note.project||'—')+'</div>' +
      (note.correlation_id?'<div><span style="color:var(--text-dim)">Correlation</span><br>'+esc(note.correlation_id)+'</div>':'') +
    '</div>';

    // Linked entities
    const [outRes, inRes] = await Promise.all([
      mcpCallTool('links_list', withProject({ source_id:id })).catch(()=>({data:{links:[]}})),
      mcpCallTool('links_list', withProject({ target_id:id })).catch(()=>({data:{links:[]}})),
    ]);
    const allLinks = [...(outRes?.data?.links||[]), ...(inRes?.data?.links||[])];
    const seen = new Set();
    const entities = [];
    for (const link of allLinks) {
      const linkedId = link.source_id===id ? link.target_id : link.source_id;
      if (seen.has(linkedId)) continue;
      seen.add(linkedId);
      const results = await Promise.allSettled([
        mcpCallTool('notes_get', withProject({ note_id:linkedId })).then(r=>({type:'note', title:r.data.note.title})),
        mcpCallTool('tasks_get', withProject({ task_id:linkedId })).then(r=>({type:'task', title:r.data.task.title})),
      ]);
      for (const r of results) {
        if (r.status==='fulfilled') { entities.push(r.value); break; }
      }
    }

    if (entities.length) {
      html += '<div style="margin-bottom:12px"><div style="font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:.5px;font-weight:600;margin-bottom:6px">Linked</div>';
      for (const e of entities) {
        html += '<div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:10px;margin-bottom:6px">' +
          '<div style="font-size:13px">'+esc(e.title)+'</div>' +
          '<div style="display:flex;gap:6px;margin-top:4px;font-size:11px"><span class="badge badge-blue">'+esc(e.type)+'</span></div></div>';
      }
      html += '</div>';
    }

    el.innerHTML = html;
  } catch(e) { alert('Error: '+e.message); }
};

// ---- Tasks ----
pages.tasks = async function() {
  document.getElementById('topActions').innerHTML = '<button onclick="showTaskForm()">+ New Task</button>';
  document.getElementById('page-tasks').innerHTML = '<div class="loading">Loading...</div>';
  await renderTasks();
};

async function renderTasks(query) {
  const el = document.getElementById('page-tasks');
  try {
    const args = withProject({ limit: 50 });
    const data = query ? await mcpCallTool('tasks_search', Object.assign({ query }, args))
                       : await mcpCallTool('tasks_list', args);
    const tasks = data?.data?.tasks || data?.data?.results?.map(r => r.task) || [];
    if (!tasks.length) { el.innerHTML = '<div class="empty">No tasks yet.</div>'; return; }
    el.innerHTML = `
      <div class="search-box mb-8"><input type="text" placeholder="Search tasks..." oninput="clearTimeout(this._t);this._t=setTimeout(()=>renderTasks(this.value),300)"></div>
      <table><colgroup><col style="width:40%"><col style="width:80px"><col style="width:80px"><col style="width:160px"></colgroup>
      <thead><tr><th>Title</th><th>Priority</th><th>Status</th><th></th></tr></thead><tbody>
      ${tasks.map(t => `<tr>
        <td><strong style="${t.status==='done'?'text-decoration:line-through;opacity:.5':''}">${esc(t.title||'Untitled')}</strong> <span style="color:var(--text-dim);font-size:11px">${esc(t.id?.slice(0,8)||'')}</span></td>
        <td>${t.priority>=5?'<span class="badge badge-red">High</span>':t.priority>=2?'<span class="badge badge-orange">Med</span>':'<span class="badge badge-blue">Low</span>'}</td>
        <td>${t.status==='done'?'<span class="badge badge-green">Done</span>':'<span class="badge badge-orange">Open</span>'}</td>
        <td><button class="btn-sm" onclick="viewTask('${t.id}')">View</button> <button class="btn-sm btn-secondary" onclick="showTaskForm('${t.id}')">Edit</button> <button class="btn-sm btn-danger" onclick="deleteTask('${t.id}')">Del</button></td>
      </tr>`).join('')}
      </tbody></table>`;
  } catch(e) { el.innerHTML = `<div class="card"><pre style="color:var(--red)">${esc(e.message)}</pre></div>`; }
}

window.viewTask = async function(id) {
  try {
    const el = document.getElementById('page-task-view');
    el.innerHTML = '<div class="loading">Loading...</div>';
    showPage('task-view');

    const data = await mcpCallTool('tasks_get', withProject({ task_id:id, view:'full' }));
    const task = data.data.task;

    const [outRes, inRes, allTasksData] = await Promise.all([
      mcpCallTool('links_list', withProject({ source_id:id })).catch(()=>({data:{links:[]}})),
      mcpCallTool('links_list', withProject({ target_id:id })).catch(()=>({data:{links:[]}})),
      mcpCallTool('tasks_list', withProject({ limit:100, view:'full' })).catch(()=>({data:{tasks:[]}})),
    ]);

    const allLinks = [...(outRes?.data?.links||[]), ...(inRes?.data?.links||[])];
    const seen = new Set();
    const entities = [];

    for (const link of allLinks) {
      const linkedId = link.source_id===id ? link.target_id : link.source_id;
      if (seen.has(linkedId)) continue;
      seen.add(linkedId);
      const results = await Promise.allSettled([
        mcpCallTool('notes_get', withProject({ note_id:linkedId })).then(r=>({type:'note', title:r.data.note.title})),
        mcpCallTool('tasks_get', withProject({ task_id:linkedId })).then(r=>({type:'task', title:r.data.task.title})),
      ]);
      for (const r of results) {
        if (r.status==='fulfilled') { entities.push(r.value); break; }
      }
    }

    const all = allTasksData?.data?.tasks||[];
    const children = all.filter(t => t.parent_document_id === id);
    const blocker = task.blocked_by_document_id ? all.find(t => t.id === task.blocked_by_document_id) : null;
    const parent = task.parent_document_id ? all.find(t => t.id === task.parent_document_id) : null;

    // correlation_id — find related notes and history
    let relatedNotes = [], relatedHistory = [];
    if (task.correlation_id) {
      const [notesRes, histRes] = await Promise.all([
        mcpCallTool('notes_search', withProject({ query: task.correlation_id, limit:20 })).catch(()=>({data:{results:[]}})),
        mcpCallTool('history_search', withProject({ query: task.correlation_id, limit:20 })).catch(()=>({data:{results:[]}})),
      ]);
      relatedNotes = (notesRes?.data?.results||[]).filter(r => r.note?.correlation_id === task.correlation_id).map(r => r.note);
      relatedHistory = (histRes?.data?.results||[]).filter(r => r.history?.correlation_id === task.correlation_id).map(r => r.history);
    }

    const key = task.id?.slice(0,8);
    document.getElementById('pageTitle').textContent = `${esc(task.project||'?')}-${key}`;
    document.getElementById('topActions').innerHTML = `<button class="btn-secondary" onclick="showPage('tasks')">&larr; Back</button> <button onclick="viewTask('${id}')" class="btn-sm btn-secondary" style="border-color:var(--accent)">&#8635;</button>`;

    let left = '', right = '';

    // === LEFT: description + meta ===
    left += `<div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center">
      ${task.status==='done'?'<span class="badge badge-green">Done</span>':'<span class="badge badge-orange">Open</span>'}
      <span class="badge badge-blue">${esc(task.task_kind||'task')}</span>
      ${task.priority>=5?'<span class="badge badge-red">P'+task.priority+'</span>':task.priority>=2?'<span class="badge badge-orange">P'+task.priority+'</span>':'<span class="badge badge-blue">P'+task.priority+'</span>'}
    </div>`;

    left += task.body
      ? `<div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:14px;font-size:13px;line-height:1.7;white-space:pre-wrap;margin-bottom:16px">${esc(task.body)}</div>`
      : '';

    left += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:14px;font-size:12px;margin-bottom:16px">
      <div><span style="color:var(--text-dim)">Status</span><br>${task.status==='done'?'<span class="badge badge-green">Done</span>':'<span class="badge badge-orange">Open</span>'}</div>
      <div><span style="color:var(--text-dim)">Type</span><br><span class="badge badge-blue">${esc(task.task_kind||'task')}</span></div>
      <div><span style="color:var(--text-dim)">Priority</span><br>${task.priority>=5?'<span class="badge badge-red">High</span>':task.priority>=2?'<span class="badge badge-orange">Medium</span>':'<span class="badge badge-blue">Low</span>'}</div>
      <div><span style="color:var(--text-dim)">Project</span><br>${esc(task.project||'—')}</div>
      <div><span style="color:var(--text-dim)">Created</span><br>${esc(task.created_at?.slice(0,10)||'-')}</div>
      <div><span style="color:var(--text-dim)">Updated</span><br>${esc(task.updated_at?.slice(0,10)||'-')}</div>
      ${task.due_at?`<div><span style="color:var(--text-dim)">Due</span><br>${esc(task.due_at.slice(0,10))}</div>`:''}
      ${task.completed_at?`<div><span style="color:var(--text-dim)">Completed</span><br>${esc(task.completed_at.slice(0,10))}</div>`:''}
    </div>`;

    left += `<div style="display:flex;gap:8px;margin-bottom:16px">
      <button onclick="(async()=>{await mcpCallTool('tasks_done', withProject({task_id:'${id}'}));showPage('tasks');})()" class="btn-sm" style="background:var(--green)">Done</button>
      <button onclick="closeModal();showTaskForm('${id}')" class="btn-sm btn-secondary">Edit</button>
    </div>`;

    // === RIGHT: sub-tasks + linked + related ===
    const sections = [];

    if (parent) sections.push(`<div style="margin-bottom:12px"><div style="font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:.5px;font-weight:600;margin-bottom:6px">Parent</div>
      <div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:10px;cursor:pointer" onclick="viewTask('${parent.id}')">
        <div style="color:var(--accent);font-size:13px">${esc(parent.title)}</div>
        <div style="color:var(--text-dim);font-size:11px">${parent.status==='done'?'Done':'Open'} &middot; P${parent.priority}</div>
      </div></div>`);

    if (blocker) sections.push(`<div style="margin-bottom:12px"><div style="font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:.5px;font-weight:600;margin-bottom:6px">Blocked by</div>
      <div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:10px;cursor:pointer" onclick="viewTask('${blocker.id}')">
        <div style="color:var(--accent);font-size:13px">${esc(blocker.title)}</div>
        <div style="color:var(--text-dim);font-size:11px">${blocker.status==='done'?'Done':'Open'} &middot; P${blocker.priority}</div>
      </div></div>`);

    if (children.length) {
      sections.push(`<div style="margin-bottom:12px"><div style="display:flex;align-items:center;gap:6px;margin-bottom:6px"><span style="font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:.5px;font-weight:600">Sub-tasks</span><span class="badge badge-blue">${children.length}</span></div>
        ${children.map(t => `<div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:10px;margin-bottom:6px;cursor:pointer" onclick="viewTask('${t.id}')">
          <div style="color:var(--accent);font-size:13px">${esc(t.title||'Untitled')}</div>
          <div style="display:flex;gap:6px;margin-top:4px;font-size:11px;color:var(--text-dim)">
            ${t.priority>=5?'<span class="badge badge-red">H</span>':t.priority>=2?'<span class="badge badge-orange">M</span>':'<span class="badge badge-blue">L</span>'}
            ${t.status==='done'?'<span class="badge badge-green">Done</span>':'<span class="badge badge-orange">Open</span>'}
          </div>
        </div>`).join('')}
      </div>`);
    }

    if (entities.length) {
      sections.push(`<div style="margin-bottom:12px"><div style="display:flex;align-items:center;gap:6px;margin-bottom:6px"><span style="font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:.5px;font-weight:600">Linked</span><span class="badge badge-blue">${entities.length}</span></div>
        ${entities.map(e => `<div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:10px;margin-bottom:6px">
          <div style="font-size:13px">${esc(e.title)}</div>
          <div style="display:flex;gap:6px;margin-top:4px;font-size:11px"><span class="badge badge-blue">${esc(e.type)}</span><span style="color:var(--text-dim)">${esc(e.relation||'')}</span></div>
        </div>`).join('')}
      </div>`);
    }

    if (relatedNotes.length) {
      sections.push(`<div style="margin-bottom:12px"><div style="display:flex;align-items:center;gap:6px;margin-bottom:6px"><span style="font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:.5px;font-weight:600">Notes</span><span class="badge badge-blue">${relatedNotes.length}</span></div>
        ${relatedNotes.map(n => `<div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:10px;margin-bottom:6px">
          <div style="font-size:13px">${esc(n.title)}</div>
          <div style="color:var(--text-dim);font-size:11px;margin-top:2px">${esc((n.body||'').slice(0,80))}</div>
        </div>`).join('')}
      </div>`);
    }

    if (relatedHistory.length) {
      sections.push(`<div style="margin-bottom:12px"><div style="display:flex;align-items:center;gap:6px;margin-bottom:6px"><span style="font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:.5px;font-weight:600">History</span><span class="badge badge-blue">${relatedHistory.length}</span></div>
        ${relatedHistory.map(h => `<div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:10px;margin-bottom:6px">
          <div style="font-size:13px">${esc(h.entry_type||'entry')}</div>
          <div style="color:var(--text-dim);font-size:11px;margin-top:2px">${esc((h.payload||'').slice(0,80))}</div>
        </div>`).join('')}
      </div>`);
    }

    if (!sections.length) {
      sections.push(`<div style="padding:24px 0;text-align:center;color:var(--text-dim);font-size:13px">Nothing linked</div>`);
    }

    right = sections.join('');

    el.innerHTML = `
<div style="display:flex;gap:24px">
  <div style="flex:1;min-width:0">
    <div style="font-size:16px;font-weight:600;line-height:1.4;margin-bottom:16px">${esc(task.title)}</div>
    ${left}
  </div>
  <div style="width:340px;flex-shrink:0">
    ${right}
  </div>
</div>`;
  } catch(e) { alert('Error: '+e.message); }
};

window.showTaskForm = async function(id) {
  let task = { title:'', body:'', priority:0, task_kind:'task' };
  if (id) {
    try { const data = await mcpCallTool('tasks_get', withProject({ task_id:id })); task = data.data.task; }
    catch(e) { alert('Error: '+e.message); return; }
  }
  document.getElementById('modalBody').innerHTML = `
    <h3>${id?'Edit Task':'New Task'}</h3>
    <div class="form-group"><label>Title</label><input id="taskTitle" value="${esc(task.title)}"></div>
    <div class="form-group"><label>Body</label><textarea id="taskBody">${esc(task.body||'')}</textarea></div>
    <div class="row"><div class="form-group"><label>Priority</label><input type="number" id="taskPriority" value="${task.priority}" min="0" max="10"></div>
    <div class="form-group"><label>Kind</label><input id="taskKind" value="${esc(task.task_kind||'task')}"></div></div>
    <div class="btn-row"><button class="btn-secondary" onclick="closeModal()">Cancel</button><button onclick="saveTask('${id||''}')">Save</button></div>`;
  document.getElementById('modalOverlay').classList.add('open');
};

window.saveTask = async function(id) {
  const title = document.getElementById('taskTitle').value;
  const body = document.getElementById('taskBody').value;
  const priority = parseInt(document.getElementById('taskPriority').value)||0;
  const task_kind = document.getElementById('taskKind').value;
  try {
    const args = withProject({ title, body, priority, task_kind, source:'cli' });
    if (id) await mcpCallTool('tasks_update', Object.assign({ task_id:id }, args));
    else await mcpCallTool('tasks_add', args);
    closeModal(); renderTasks();
  } catch(e) { alert('Error: '+e.message); }
};

window.deleteTask = async function(id) {
  if (!confirm('Delete?')) return;
  try { await mcpCallTool('tasks_delete', withProject({ task_id:id })); renderTasks(); }
  catch(e) { alert('Error: '+e.message); }
};

// ---- History ----
pages.history = async function() {
  document.getElementById('page-history').innerHTML = `
    <div class="row">
      <div class="flex-1"><input type="text" id="historyQuery" placeholder="Search history..." onkeydown="if(event.key==='Enter')searchHistory()" value=""></div>
      <button onclick="searchHistory()">Search</button>
    </div>
    <div id="historyResults"></div>`;
};

window.searchHistory = async function() {
  const query = document.getElementById('historyQuery').value.trim();
  if (!query) return;
  const el = document.getElementById('historyResults');
  el.innerHTML = '<div class="loading">Searching...</div>';
  try {
    const data = await mcpCallTool('history_search', withProject({ query, limit:50 }));
    const results = data?.data?.results || data?.data?.hits || [];
    if (!results.length) { el.innerHTML = '<div class="empty">No results.</div>'; return; }
    el.innerHTML = '<div style="margin-bottom:8px;color:var(--text-dim);font-size:12px">'+results.length+' result(s)</div>' +
      '<table><colgroup><col style="width:80px"><col style="width:100px"><col style="width:60px"><col></colgroup>' +
      '<thead><tr><th>Type</th><th>Project</th><th>Actor</th><th>Payload</th></tr></thead><tbody>' +
      results.map(r => {
        const h = r.history || r;
        return '<tr>' +
          '<td><span class="badge badge-blue">'+esc(h.entry_type||'entry')+'</span></td>' +
          '<td>'+esc(h.project||'—')+'</td>' +
          '<td>'+esc(h.actor||'—')+'</td>' +
          '<td style="color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc((h.payload||'').slice(0,200))+'</td>' +
        '</tr>';
      }).join('') +
      '</tbody></table>';
  } catch(e) { el.innerHTML = '<div class="card"><pre style="color:var(--red)">'+esc(e.message)+'</pre></div>'; }
};

// ---- Files ----
pages.files = async function() {
  document.getElementById('topActions').innerHTML = '<button onclick="reindexFiles()">Re-index</button>';
  document.getElementById('page-files').innerHTML = '<div class="loading">Loading...</div>';
  await renderFiles();
};

async function renderFiles(query) {
  const el = document.getElementById('page-files');
  try {
    const args = withProject({ limit: 50 });
    const data = query ? await mcpCallTool('files_search', Object.assign({ query }, args))
                       : await mcpCallTool('files_list', args);
    const files = data?.data?.files || data?.data?.results?.map(r => r.file) || [];
    if (!files.length) { el.innerHTML = '<div class="empty">No files indexed yet. Click <strong>Re-index</strong> to index the current project.</div>'; return; }
    el.innerHTML = `
      <div class="search-box mb-8"><input type="text" placeholder="Search files..." oninput="clearTimeout(this._t);this._t=setTimeout(()=>renderFiles(this.value),300)"></div>
      <table><colgroup><col style="width:30%"><col style="width:15%"><col style="width:40%"><col style="width:60px"></colgroup>
      <thead><tr><th>Name</th><th>Language</th><th>Path</th><th></th></tr></thead><tbody>
      ${files.map(f => `<tr>
        <td><strong>${esc(f.name||f.path?.split('/').pop()||'Untitled')}</strong></td>
        <td>${f.language?'<span class="badge badge-blue">'+esc(f.language)+'</span>':''}</td>
        <td style="color:var(--text-dim);font-size:12px">${esc(f.path||'—')}</td>
        <td><button class="btn-sm btn-secondary" onclick="viewFile('${f.id}')">View</button> <button class="btn-sm btn-danger" onclick="deleteFile('${f.id}')">Del</button></td>
      </tr>`).join('')}
      </tbody></table>`;
  } catch(e) { el.innerHTML = '<div class="card"><pre style="color:var(--red)">'+esc(e.message)+'</pre></div>'; }
}

window.viewFile = async function(id) {
  try {
    const data = await mcpCallTool('files_get', withProject({ file_id:id }));
    const f = data.data.file;
    document.getElementById('modalBody').innerHTML = '<h3>'+esc(f.name||f.path||'File')+'</h3>' +
      '<div class="form-group"><label>Path</label><div style="font-size:13px">'+esc(f.path||'—')+'</div></div>' +
      (f.language?'<div class="form-group"><label>Language</label><div style="font-size:13px"><span class="badge badge-blue">'+esc(f.language)+'</span></div></div>':'') +
      (f.root?'<div class="form-group"><label>Root</label><div style="font-size:13px">'+esc(f.root)+'</div></div>':'') +
      '<div class="btn-row"><button class="btn-secondary" onclick="closeModal()">Close</button></div>';
    document.getElementById('modalOverlay').classList.add('open');
  } catch(e) { alert('Error: '+e.message); }
};

window.deleteFile = async function(id) {
  if (!confirm('Delete file from index?')) return;
  try { await mcpCallTool('files_delete', withProject({ file_id:id })); renderFiles(); }
  catch(e) { alert('Error: '+e.message); }
};

window.reindexFiles = async function() {
  try {
    await mcpCallTool('files_index', withProject({}));
    renderFiles();
  } catch(e) { alert('Error: '+e.message); }
};

// ---- Projects ----
pages.projects = async function() {
  const el = document.getElementById('page-projects');
  el.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const data = await mcpCallTool('projects_list', {});
    const projects = data?.data?.projects || [];
    if (!projects.length) { el.innerHTML = '<div class="empty">No projects configured.</div>'; return; }
    el.innerHTML = '<table><colgroup><col></colgroup><thead><tr><th>Project</th></tr></thead><tbody>' +
      projects.map(p => '<tr><td><strong>'+esc(p)+'</strong></td></tr>').join('') +
      '</tbody></table>';
  } catch(e) { el.innerHTML = '<div class="card"><pre style="color:var(--red)">'+esc(e.message)+'</pre></div>'; }
};

// ---- Search ----
pages.search = async function() {
  document.getElementById('page-search').innerHTML = `
    <div class="row">
      <div class="flex-1"><input type="text" id="searchQuery" placeholder="Search..." onkeydown="if(event.key==='Enter')doSearch()"></div>
      <button onclick="doSearch()">Search</button>
    </div>
    <div class="row">
      <label style="font-size:12px;color:var(--text-dim);display:flex;align-items:center;gap:8px"><input type="checkbox" id="sNotes" checked> Notes</label>
      <label style="font-size:12px;color:var(--text-dim);display:flex;align-items:center;gap:8px"><input type="checkbox" id="sTasks" checked> Tasks</label>
      <label style="font-size:12px;color:var(--text-dim);display:flex;align-items:center;gap:8px"><input type="checkbox" id="sHistory"> History</label>
      <label style="font-size:12px;color:var(--text-dim);display:flex;align-items:center;gap:8px"><input type="checkbox" id="sFiles"> Files</label>
    </div>
    <div id="searchResults"></div>`;
};

window.doSearch = async function() {
  const query = document.getElementById('searchQuery').value.trim();
  if (!query) return;
  const types = [];
  if (document.getElementById('sNotes').checked) types.push('notes');
  if (document.getElementById('sTasks').checked) types.push('tasks');
  if (document.getElementById('sHistory').checked) types.push('history');
  if (document.getElementById('sFiles').checked) types.push('files');
  const el = document.getElementById('searchResults');
  el.innerHTML = '<div class="loading">Searching...</div>';
  try {
    const data = await mcpCallTool('search', withProject({ query, types, limit:50 }));
    const results = data?.data?.results || [];
    if (!results.length) { el.innerHTML = '<div class="empty">No results.</div>'; return; }
    el.innerHTML = `<div style="margin-bottom:8px;color:var(--text-dim);font-size:12px">${results.length} result(s)</div>
      <table><colgroup><col style="width:80px"><col><col style="width:80px"></colgroup>
      <thead><tr><th>Type</th><th>Title</th><th>Score</th></tr></thead><tbody>
      ${results.map(r => {
        const item = r.note||r.task||r.history||r.file||{};
        const type = r.note?'Note':r.task?'Task':r.history?'History':r.file?'File':'?';
        return `<tr><td><span class="badge badge-blue">${type}</span></td><td>${esc(item.title||item.name||item.path||item.id||'')}</td><td>${r.score!=null?r.score.toFixed(3):'-'}</td></tr>`;
      }).join('')}
      </tbody></table>`;
  } catch(e) { el.innerHTML = `<div class="card"><pre style="color:var(--red)">${esc(e.message)}</pre></div>`; }
};

// ---- Tools ----
pages.tools = async function() {
  const el = document.getElementById('page-tools');
  el.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const tools = await mcpRequest('tools/list', {}).then(r => r.result?.tools||[]);
    el.innerHTML = `<div class="tool-grid">${tools.map(t => `
      <div class="tool-card" onclick="showToolDetail('${t.name}')">
        <h4>${esc(t.name)}</h4>
        <p>${esc(t.description||'')}</p>
      </div>`).join('')}</div>`;
  } catch(e) { el.innerHTML = `<div class="card"><pre style="color:var(--red)">${esc(e.message)}</pre></div>`; }
};

window.showToolDetail = async function(name) {
  const tools = await mcpRequest('tools/list', {}).then(r => r.result?.tools||[]);
  const tool = tools.find(t => t.name === name);
  if (!tool) return;
  document.getElementById('modalBody').innerHTML = `
    <h3>${esc(tool.name)}</h3>
    <p style="color:var(--text-dim);margin-bottom:12px">${esc(tool.description||'')}</p>
    <div class="form-group"><label>Schema</label><pre>${esc(JSON.stringify(tool.inputSchema, null, 2))}</pre></div>
    <div class="btn-row"><button class="btn-secondary" onclick="closeModal()">Close</button></div>`;
  document.getElementById('modalOverlay').classList.add('open');
};

// ---- Config ----
pages.config = async function() {
  const el = document.getElementById('page-config');
  el.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const data = await mcpCallTool('config_get');
    el.innerHTML = `<div class="card"><h3>Config</h3><pre>${esc(JSON.stringify(data.data||data, null, 2))}</pre></div>`;
  } catch(e) { el.innerHTML = `<div class="card"><pre style="color:var(--red)">${esc(e.message)}</pre></div>`; }
};

function esc(s) { if (!s&&s!==0) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
window.closeModal = function() { document.getElementById('modalOverlay').classList.remove('open'); };
document.getElementById('modalOverlay').addEventListener('click', e => { if (e.target===e.currentTarget) closeModal(); });

(async function() {
  try {
    await connectMCP();
    showPage('dashboard');
  } catch(e) {
    document.getElementById('statusDot').className = 'status-dot err';
    document.getElementById('statusText').textContent = 'Error: '+e.message;
    document.getElementById('page-dashboard').innerHTML = `<div class="card"><h3>Connection Error</h3><pre style="color:var(--red)">${esc(e.message)}</pre></div>`;
  }
})();
</script>
</body>
</html>
"""

def serve(
    host: str = "127.0.0.1",
    port: int = 9080,
    profile: str | None = None,
    open_browser: bool = True,
) -> None:
    validate_serve_host(host)
    try:
        build_container(profile=profile)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    mcp_app.settings.host = host
    mcp_app.settings.port = port

    async def ui_handler(request: Any) -> HTMLResponse:
        return HTMLResponse(UI_HTML)

    mcp_app._custom_starlette_routes.append(
        Route("/", endpoint=ui_handler, methods=["GET"])
    )

    url = f"http://{host}:{port}"
    typer.echo(f"Anchor Web UI running at {url}")

    if open_browser:
        webbrowser.open(url)

    mcp_app.run("sse")


def validate_serve_host(host: str) -> None:
    if host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise ValueError("Anchor serve supports loopback hosts only")
