"""The Nuts tab: a wireframe preview and the report list.

One self-contained HTML page kept as a Python string. The 3D view is drawn on
a 2D canvas, so it needs no WebGL and no libraries.
"""

PREVIEW_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Nuts</title>
<style>
  :root {
    --bg: var(--orca-bg, #ffffff); --fg: var(--orca-fg, #262e30);
    --muted: var(--orca-muted, #6b7478); --accent: var(--orca-accent, #009688);
    --accent-fg: var(--orca-accent-fg, #ffffff); --border: var(--orca-border, #d0d5d7);
    --ok: #2e9e5b; --warn: #c98a00; --err: #d6453d;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body { margin: 0; display: flex; background: var(--bg); color: var(--fg); overflow: hidden;
         font: 13px/1.45 var(--orca-font, system-ui, sans-serif); }
  #view { flex: 1; position: relative; min-width: 0; }
  canvas { position: absolute; inset: 0; width: 100%; height: 100%; cursor: grab; }
  #hint { position: absolute; left: 10px; bottom: 8px; color: var(--muted); pointer-events: none; }
  #side { width: 360px; max-width: 45%; border-left: 1px solid var(--border); display: flex;
          flex-direction: column; }
  #bar { padding: 8px 10px; display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
         border-bottom: 1px solid var(--border); }
  button { font: inherit; color: var(--fg); background: transparent; border: 1px solid var(--border);
           border-radius: 4px; padding: 4px 10px; cursor: pointer; }
  button.primary { background: var(--accent); color: var(--accent-fg); border-color: var(--accent); }
  .banner { border-left: 4px solid var(--warn); padding: 6px 10px; }
  .banner.error { border-left-color: var(--err); }
  #list { flex: 1; overflow: auto; }
  .nut { padding: 6px 10px; border-bottom: 1px solid var(--border); cursor: pointer; }
  .nut.selected { background: color-mix(in srgb, var(--accent) 14%, transparent); }
  .nut .head { font-weight: 600; }
  .icon { display: inline-block; width: 1.3em; font-weight: 700; }
  .ok { color: var(--ok); } .warning { color: var(--warn); } .error { color: var(--err); }
  .sub { color: var(--muted); margin-left: 1.3em; }
  #detail { border-top: 1px solid var(--border); padding: 8px 10px; max-height: 45%; overflow: auto; }
  #detail table { border-collapse: collapse; width: 100%; }
  #detail td { padding: 1px 8px 1px 0; vertical-align: top; }
  #detail td:first-child { color: var(--muted); white-space: nowrap; }
  .finding { margin-top: 4px; }
  #export { position: absolute; inset: 24px; background: var(--bg); border: 1px solid var(--border);
            border-radius: 6px; padding: 10px; display: flex; flex-direction: column; gap: 8px; }
  #export textarea { flex: 1; font: 12px ui-monospace, Consolas, monospace; color: var(--fg);
                     background: var(--bg); border: 1px solid var(--border); }
  .hidden { display: none !important; }
  .muted { color: var(--muted); }
</style>
</head>
<body>
<div id="view">
  <canvas id="canvas"></canvas>
  <div id="hint">Drag to orbit · Shift-drag to pan · Scroll to zoom · Click a box to select</div>
  <div id="export" class="hidden">
    <div class="muted">Select all and copy. The plugin writes no files.</div>
    <textarea id="export-text" readonly spellcheck="false"></textarea>
    <div><button id="export-close">Close</button></div>
  </div>
</div>
<div id="side">
  <div id="bar">
    <button class="primary" id="check">Check nuts</button>
    <button id="fit">Fit view</button>
    <button id="json">JSON</button>
    <button id="csv">CSV</button>
    <span class="muted" id="count"></span>
  </div>
  <div id="stale" class="banner hidden">The model changed. This report is out of date; checking again…</div>
  <div id="error" class="banner error hidden"></div>
  <div id="list"></div>
  <div id="detail" class="hidden"></div>
</div>

<script>
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var canvas = $('canvas'), ctx = canvas.getContext('2d');
  var report = null, edges = [], selected = -1, isStale = false;
  var cam = {target: [0, 0, 0], yaw: -1.0, pitch: 0.6, dist: 200};
  var ICON = {ok: '✓', warning: '!', error: '✕'};

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

  // --- Camera ------------------------------------------------------------------------------
  function basis() {
    var cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
    var cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
    var back = [cp * cy, cp * sy, sp];                       // from the target to the camera
    return {
      eye: [cam.target[0] + cam.dist * back[0], cam.target[1] + cam.dist * back[1],
            cam.target[2] + cam.dist * back[2]],
      right: [-sy, cy, 0], up: [-sp * cy, -sp * sy, cp], fwd: [-back[0], -back[1], -back[2]]};
  }
  function projector() {
    var b = basis(), w = canvas.clientWidth, h = canvas.clientHeight, scale = h * 1.3;
    return function (p) {
      var x = p[0] - b.eye[0], y = p[1] - b.eye[1], z = p[2] - b.eye[2];
      var depth = x * b.fwd[0] + y * b.fwd[1] + z * b.fwd[2];
      if (depth < 0.5) { return null; }
      return [w / 2 + scale * (x * b.right[0] + y * b.right[1]) / depth,
              h / 2 - scale * (x * b.up[0] + y * b.up[1] + z * b.up[2]) / depth];
    };
  }

  // --- Geometry of a nut record ------------------------------------------------------------
  function boxCorners(box) {
    var out = [];
    for (var i = 0; i < 8; i++) {
      var s = [(i & 1) ? 1 : -1, (i & 2) ? 1 : -1, (i & 4) ? 1 : -1], p = box.centre.slice();
      for (var a = 0; a < 3; a++) {
        for (var k = 0; k < 3; k++) { p[k] += s[a] * box.half[a] * box.axes[a][k]; }
      }
      out.push(p);
    }
    return out;
  }
  var BOX_EDGES = [[0, 1], [2, 3], [4, 5], [6, 7], [0, 2], [1, 3], [4, 6], [5, 7],
                   [0, 4], [1, 5], [2, 6], [3, 7]];
  function line(project, a, b) {
    var p = project(a), q = project(b);
    if (p && q) { ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); }
  }
  function add(p, v, s) { return [p[0] + v[0] * s, p[1] + v[1] * s, p[2] + v[2] * s]; }

  // --- Drawing -----------------------------------------------------------------------------
  function draw() {
    var ratio = window.devicePixelRatio || 1;
    var w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * ratio) || canvas.height !== Math.round(h * ratio)) {
      canvas.width = Math.round(w * ratio); canvas.height = Math.round(h * ratio);
    }
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, w, h);
    var project = projector();

    ctx.strokeStyle = css('--muted') || '#888'; ctx.globalAlpha = 0.55; ctx.lineWidth = 1;
    ctx.beginPath();
    for (var i = 0; i < edges.length; i++) {
      var e = edges[i];
      line(project, [e[0], e[1], e[2]], [e[3], e[4], e[5]]);
    }
    ctx.stroke();
    ctx.globalAlpha = 1;

    if (!report) { return; }
    report.nuts.forEach(function (n, index) {
      if (!n.box) { return; }
      var colour = css('--' + (n.status === 'ok' ? 'ok' : n.status === 'warning' ? 'warn' : 'err'));
      var corners = boxCorners(n.box);
      ctx.strokeStyle = colour; ctx.fillStyle = colour;
      ctx.lineWidth = index === selected ? 3 : 1.5;
      ctx.beginPath();
      BOX_EDGES.forEach(function (pair) { line(project, corners[pair[0]], corners[pair[1]]); });
      ctx.stroke();

      if (n.placement) {
        // Crosshair at the placement point and an arrow along the thread axis.
        ctx.lineWidth = 1.5; ctx.beginPath();
        [[1, 0, 0], [0, 1, 0], [0, 0, 1]].forEach(function (axis) {
          line(project, add(n.placement, axis, -1.5), add(n.placement, axis, 1.5));
        });
        var tip = add(n.placement, n.axis, 5);
        line(project, n.placement, tip);
        ctx.stroke();
        var p = project(n.placement), q = project(tip);
        if (p && q) {
          var angle = Math.atan2(q[1] - p[1], q[0] - p[0]);
          ctx.beginPath(); ctx.moveTo(q[0], q[1]);
          ctx.lineTo(q[0] - 9 * Math.cos(angle - 0.4), q[1] - 9 * Math.sin(angle - 0.4));
          ctx.lineTo(q[0] - 9 * Math.cos(angle + 0.4), q[1] - 9 * Math.sin(angle + 0.4));
          ctx.closePath(); ctx.fill();
        }
      }
      var c = project(n.box.centre);
      if (c) {
        ctx.font = '600 13px ' + (css('--orca-font') || 'system-ui, sans-serif');
        ctx.fillText(ICON[n.status] + ' #' + n.index, c[0] + 10, c[1] - 10);
      }
    });
  }
  var pending = false;
  function redraw() {
    if (pending) { return; }
    pending = true;
    requestAnimationFrame(function () { pending = false; draw(); });
  }

  // --- Camera moves ------------------------------------------------------------------------
  function fit() {
    var lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    function grow(p) { for (var k = 0; k < 3; k++) { lo[k] = Math.min(lo[k], p[k]); hi[k] = Math.max(hi[k], p[k]); } }
    edges.forEach(function (e) { grow([e[0], e[1], e[2]]); grow([e[3], e[4], e[5]]); });
    if (report) { report.nuts.forEach(function (n) { if (n.box) { boxCorners(n.box).forEach(grow); } }); }
    if (lo[0] === Infinity) { return; }
    cam.target = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2];
    var radius = Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2;
    cam.dist = Math.max(20, radius * 3.2);
    redraw();
  }
  function flyTo(point, dist) {
    var from = cam.target.slice(), fromDist = cam.dist, start = null;
    function step(now) {
      if (start === null) { start = now; }
      var t = Math.min(1, (now - start) / 350), s = t * t * (3 - 2 * t);
      for (var k = 0; k < 3; k++) { cam.target[k] = from[k] + (point[k] - from[k]) * s; }
      cam.dist = fromDist + (dist - fromDist) * s;
      draw();
      if (t < 1) { requestAnimationFrame(step); }
    }
    requestAnimationFrame(step);
  }

  // --- List and detail ---------------------------------------------------------------------
  function fmt(v, d) { return v == null ? '–' : v.toFixed(d == null ? 3 : d); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text != null) { node.textContent = text; }
    return node;
  }
  function select(index, fly) {
    selected = index;
    var rows = $('list').children;
    for (var i = 0; i < rows.length; i++) { rows[i].classList.toggle('selected', i === index); }
    if (index >= 0 && rows[index]) { rows[index].scrollIntoView({block: 'nearest'}); }
    renderDetail();
    var n = report && report.nuts[index];
    if (fly && n && n.box) { flyTo(n.box.centre, 45); } else { redraw(); }
  }
  function renderList() {
    var list = $('list');
    list.textContent = '';
    $('count').textContent = report ? report.nuts.length + ' nut(s): ' + report.summary.ok + ' ok, ' +
      report.summary.warning + ' warning, ' + report.summary.error + ' error' : 'No report yet';
    if (!report) { return; }
    if (!report.nuts.length) {
      list.appendChild(el('div', 'sub', 'No bodies named NUT_<key> in this project.'));
    }
    report.nuts.forEach(function (n, index) {
      var row = el('div', 'nut' + (index === selected ? ' selected' : ''));
      var head = el('div', 'head');
      head.appendChild(el('span', 'icon ' + n.status, ICON[n.status]));
      head.appendChild(el('span', '', '#' + n.index + ' ' + n.name));
      row.appendChild(head);
      var angle = n.cls === 'FLAT' ? 'yaw ' + fmt(n.yaw_deg, 1) + '°' :
        (n.cls === 'EDGE' || n.cls === 'CORNER') ? 'heading ' + fmt(n.yaw_deg, 1) + '°' :
        n.cls === 'TILTED' ? 'tilt ' + fmt(n.tilt_deg, 1) + '°' :
        n.cls === 'ROLLED' ? 'roll ' + fmt(n.roll_deg, 1) + '°' : '';
      row.appendChild(el('div', 'sub', (n.cls || 'not measured') + (angle ? ', ' + angle : '') +
        ' · object ' + n.object + ', copy ' + n.instance));
      if (n.findings.length) {
        row.appendChild(el('div', 'sub', n.findings.map(function (f) { return f.code; }).join(', ')));
      }
      row.addEventListener('click', function () { select(index, true); });
      list.appendChild(row);
    });
  }
  function renderDetail() {
    var host = $('detail'), n = report && report.nuts[selected];
    host.classList.toggle('hidden', !n);
    host.textContent = '';
    if (!n) { return; }
    var table = el('table');
    function row(name, value) {
      var tr = el('tr'); tr.appendChild(el('td', '', name)); tr.appendChild(el('td', '', value));
      table.appendChild(tr);
    }
    function xyz(p) { return p ? 'X ' + fmt(p[0]) + '  Y ' + fmt(p[1]) + '  Z ' + fmt(p[2]) : '–'; }
    row('Nut', '#' + n.index + ', ' + n.name + ', object ' + n.object + ', copy ' + n.instance);
    row('Pocket centre', n.box ? xyz(n.box.centre) : '–');
    row('Placement', xyz(n.placement) + (n.z_low != null ? ', lowest point ' + fmt(n.z_low) : ''));
    if (n.pocket) {
      var sizes = (n.pocket.width || []).map(function (w) { return fmt(w, 2); });
      if (n.pocket.thickness != null) { sizes.unshift(fmt(n.pocket.thickness, 2)); }
      if (n.pocket.depth != null) { sizes.push(fmt(n.pocket.depth, 2)); }
      row('Pocket measured', sizes.length ? sizes.join(' × ') + ' mm' : '–');
    }
    if (n.window) {
      row('Insert window', 'Z ' + fmt(n.window[0]) + (n.window[1] != null ? ' to ' + fmt(n.window[1]) : ' and up'));
    }
    if (n.export && n.export.layer_z != null) {
      row('Exported', 'after layer ' + n.export.layer + ', Z ' + fmt(n.export.layer_z));
    }
    host.appendChild(table);
    if (!n.findings.length) { host.appendChild(el('div', 'finding ok', 'OK')); }
    n.findings.forEach(function (f) {
      var d = el('div', 'finding');
      d.appendChild(el('b', f.level, f.level + ' ' + f.code + ': '));
      d.appendChild(document.createTextNode(f.message));
      host.appendChild(d);
    });
  }

  // --- Mouse -------------------------------------------------------------------------------
  var drag = null;
  canvas.addEventListener('pointerdown', function (ev) {
    drag = {x: ev.clientX, y: ev.clientY, moved: false, pan: ev.shiftKey || ev.button !== 0};
    canvas.setPointerCapture(ev.pointerId);
  });
  canvas.addEventListener('pointermove', function (ev) {
    if (!drag) { return; }
    var dx = ev.clientX - drag.x, dy = ev.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) { drag.moved = true; }
    if (!drag.moved) { return; }
    drag.x = ev.clientX; drag.y = ev.clientY;
    if (drag.pan) {
      var b = basis(), k = cam.dist / (canvas.clientHeight * 1.3);
      for (var i = 0; i < 3; i++) { cam.target[i] += (-dx * b.right[i] + dy * b.up[i]) * k; }
    } else {
      cam.yaw -= dx * 0.008;
      cam.pitch = Math.max(-1.5, Math.min(1.5, cam.pitch + dy * 0.008));
    }
    redraw();
  });
  canvas.addEventListener('pointerup', function (ev) {
    if (drag && !drag.moved && report) {
      var rect = canvas.getBoundingClientRect(), project = projector();
      var best = -1, bestDist = 28;
      report.nuts.forEach(function (n, index) {
        var p = n.box && project(n.box.centre);
        if (!p) { return; }
        var d = Math.hypot(p[0] - (ev.clientX - rect.left), p[1] - (ev.clientY - rect.top));
        if (d < bestDist) { bestDist = d; best = index; }
      });
      if (best >= 0) { select(best, false); }
    }
    drag = null;
  });
  canvas.addEventListener('contextmenu', function (ev) { ev.preventDefault(); });
  canvas.addEventListener('wheel', function (ev) {
    ev.preventDefault();
    cam.dist = Math.max(3, Math.min(5000, cam.dist * Math.exp(ev.deltaY * 0.0012)));
    redraw();
  }, {passive: false});
  window.addEventListener('resize', redraw);

  // --- Messages ----------------------------------------------------------------------------
  function showError(text) {
    $('error').textContent = text || '';
    $('error').classList.toggle('hidden', !text);
  }
  function setStale(value) {
    isStale = value;
    $('stale').classList.toggle('hidden', !value);
  }
  function send(message) {
    try { window.orca.postMessage(message); } catch (e) { showError('Cannot reach OrcaSlicer: ' + e); }
  }
  function showExport(text) {
    $('export-text').value = text;
    $('export').classList.remove('hidden');
    $('export-text').select();
  }
  var firstEdges = true;
  function handle(m) {
    if (typeof m === 'string') { try { m = JSON.parse(m); } catch (e) { return; } }
    if (!m || !m.type) { return; }
    if (m.type === 'report') {
      report = m.report;
      setStale(!!(report && report.stale));
      showError('');
      if (report && selected >= report.nuts.length) { selected = -1; }
      renderList(); renderDetail(); redraw();
      send({type: 'get_edges'});
    } else if (m.type === 'edges') {
      edges = m.segments || [];
      if (firstEdges && edges.length) { firstEdges = false; fit(); } else { redraw(); }
    } else if (m.type === 'stale') {
      setStale(true);
      if (document.visibilityState === 'visible') { send({type: 'check'}); }
    } else if (m.type === 'csv') {
      showExport(m.text);
    } else if (m.type === 'error') {
      showError(m.message);
    }
  }

  $('check').addEventListener('click', function () { send({type: 'check'}); });
  $('fit').addEventListener('click', fit);
  $('json').addEventListener('click', function () { showExport(JSON.stringify(report, null, 2)); });
  $('csv').addEventListener('click', function () { send({type: 'get_csv'}); });
  $('export-close').addEventListener('click', function () { $('export').classList.add('hidden'); });
  document.addEventListener('visibilitychange', function () {
    // Ask for the current report each time the tab is shown again.
    if (document.visibilityState === 'visible' && window.orca) {
      send({type: isStale ? 'check' : 'ready'});
    }
  });

  function boot() {
    if (!window.orca) { setTimeout(boot, 100); return; }
    window.orca.onMessage(handle);
    send({type: 'ready'});
  }
  boot();
  redraw();
})();
</script>
</body>
</html>
"""
