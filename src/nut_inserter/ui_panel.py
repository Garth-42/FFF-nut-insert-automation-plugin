"""The docked panel: check summary, Modifier reminder, nut library editor and settings.

One self-contained HTML page kept as a Python string: inline CSS and JavaScript,
no external files. It talks to Python through window.orca (see state._handle).
"""

PANEL_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Nut inserter</title>
<style>
  :root {
    --bg: var(--orca-bg, #ffffff); --fg: var(--orca-fg, #262e30);
    --muted: var(--orca-muted, #6b7478); --accent: var(--orca-accent, #009688);
    --accent-fg: var(--orca-accent-fg, #ffffff); --border: var(--orca-border, #d0d5d7);
    --ok: #2e9e5b; --warn: #c98a00; --err: #d6453d;
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 10px 12px 24px; background: var(--bg); color: var(--fg);
         font: 13px/1.45 var(--orca-font, system-ui, sans-serif); }
  h2 { font-size: 13px; margin: 18px 0 6px; text-transform: uppercase; letter-spacing: .04em;
       color: var(--muted); }
  button { font: inherit; color: var(--fg); background: transparent; border: 1px solid var(--border);
           border-radius: 4px; padding: 4px 10px; cursor: pointer; }
  button.primary { background: var(--accent); color: var(--accent-fg); border-color: var(--accent); }
  button:disabled { opacity: .5; cursor: default; }
  input, select, textarea { font: inherit; color: var(--fg); background: var(--bg);
           border: 1px solid var(--border); border-radius: 4px; padding: 3px 6px; }
  input[type=number] { width: 70px; }
  textarea { width: 100%; font-family: ui-monospace, Consolas, monospace; font-size: 12px; }
  .row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .chips { display: flex; gap: 6px; margin: 8px 0; flex-wrap: wrap; }
  .chip { border: 1px solid var(--border); border-radius: 10px; padding: 1px 9px; }
  .chip.ok { color: var(--ok); } .chip.warning { color: var(--warn); } .chip.error { color: var(--err); }
  .banner { border: 1px solid var(--border); border-left-width: 4px; border-radius: 4px;
            padding: 6px 8px; margin: 8px 0; }
  .banner.stale { border-left-color: var(--warn); }
  .banner.error { border-left-color: var(--err); }
  .banner.info { border-left-color: var(--accent); }
  .nut { border-top: 1px solid var(--border); padding: 6px 0; }
  .nut .head { font-weight: 600; }
  .icon { display: inline-block; width: 1.3em; font-weight: 700; }
  .icon.ok { color: var(--ok); } .icon.warning { color: var(--warn); } .icon.error { color: var(--err); }
  .finding { margin: 3px 0 0 1.3em; color: var(--muted); }
  .finding b { color: var(--fg); font-weight: 600; }
  table { border-collapse: collapse; width: 100%; }
  td, th { text-align: left; padding: 3px 6px 3px 0; vertical-align: middle; }
  th { color: var(--muted); font-weight: 500; }
  tr.entry { cursor: pointer; } tr.entry.selected td { background: color-mix(in srgb, var(--accent) 14%, transparent); }
  .form label { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center;
                padding: 2px 0; }
  .form .group { font-weight: 600; margin-top: 10px; }
  .form .unit { color: var(--muted); }
  .muted { color: var(--muted); }
  details { margin: 6px 0; } summary { cursor: pointer; }
  .hidden { display: none; }
</style>
</head>
<body>
<div class="row">
  <button class="primary" id="check">Check nuts</button>
  <span class="muted" id="status">Waiting for OrcaSlicer…</span>
</div>
<div id="stale" class="banner stale hidden">The model changed. This report is out of date.
  Press Check nuts.</div>
<div id="error" class="banner error hidden"></div>
<div class="chips" id="chips"></div>
<div id="modifier" class="banner info hidden"></div>
<div id="nuts"></div>

<h2>Nut library</h2>
<p class="muted">Every pocket, slot, span and reach number is a placeholder until you replace it
with values from your own test prints.</p>
<table id="library"><thead><tr><th>Key</th><th>Across flats</th><th>Thickness</th><th>Classes</th>
</tr></thead><tbody></tbody></table>
<div class="row" style="margin-top:6px">
  <button id="add">Add</button><button id="duplicate">Duplicate</button>
  <button id="delete">Delete</button>
</div>
<div class="form" id="form"></div>

<h2>Settings</h2>
<div class="form" id="settings"></div>
<details><summary>What your printer macro must do</summary>
<p>The insert block starts with the print tool at the end of its last extrusion, hot and not
retracted. Your macro (Klipper <code>INSERT_NUT</code>, RepRapFirmware <code>insert_nut.g</code>)
or your Marlin lines must retract and park the print tool, place the nut, and bring the print tool
back to the same position, primed, with the positioning and extruder modes unchanged.</p>
<p>Placeholders: {index} {key} {cls} {x} {y} {z} {z_low} {z_high} {yaw} {feeder} {layer_z}
{tool} {rx} {ry} {rz}. Write a literal brace as {{ or }}.</p></details>

<div class="row" style="margin-top:10px">
  <button class="primary" id="save">Save</button>
  <button id="revert">Revert</button>
  <span class="muted" id="saved"></span>
</div>

<h2>Import and export</h2>
<p class="muted">Export shows the settings as JSON to copy. To import, paste JSON here and press
Import, then Save.</p>
<textarea id="json" rows="6" spellcheck="false"></textarea>
<div class="row" style="margin-top:6px">
  <button id="export">Export</button><button id="import">Import</button>
</div>

<script>
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var config = null;      // the settings being edited
  var saved = null;       // the settings as last received from Python
  var selected = 0;       // index of the nut entry being edited
  var ICON = {ok: '✓', warning: '!', error: '✕'};

  // Field lists: [path, label, kind]. kind: text, num, int, range, bool.
  var NUT_FIELDS = [
    ['key', 'Key (bodies named NUT_<key>)', 'text'], ['label', 'Label', 'text'],
    ['across_flats', 'Width across flats', 'num'], ['thickness', 'Thickness', 'num'],
    ['max_roof_span', 'Max roof span', 'num'], ['tool_reach', 'Tool reach', 'num'],
    ['feeder', 'Feeder', 'int'],
    [null, 'Flat (horizontal nut)'], ['flat.enabled', 'Enabled', 'bool'],
    ['flat.width', 'Pocket width', 'range'], ['flat.depth', 'Pocket depth', 'range'],
    [null, 'Edge (vertical nut on a flat)'], ['edge.enabled', 'Enabled', 'bool'],
    ['edge.thickness', 'Slot thickness', 'range'], ['edge.width', 'Slot width', 'range'],
    ['edge.height_min', 'Slot height, minimum', 'num'],
    [null, 'Corner (vertical nut on a corner)'], ['corner.enabled', 'Enabled', 'bool'],
    ['corner.thickness', 'Slot thickness', 'range'], ['corner.opening', 'Slot opening', 'range'],
    ['corner.seat_gap_max', 'Seat gap, maximum', 'num'],
    ['corner.height_min', 'Slot height, minimum', 'num']
  ];
  var SETTING_FIELDS = [
    ['axis_tolerance_deg', 'Angle window (degrees)', 'num'],
    ['body_tolerance_mm', 'Nut body tolerance', 'num'],
    ['min_top_clearance_mm', 'Clearance above the nut', 'num'],
    ['on_error', 'When a nut has an error', 'select',
      [['block', 'Block the slice'], ['skip', 'Skip the nut and continue']]],
    ['firmware', 'Firmware', 'select', [['auto', 'From the printer profile'],
      ['klipper', 'Klipper'], ['reprapfirmware', 'RepRapFirmware'], ['marlin', 'Marlin']]],
    ['templates.klipper', 'Klipper insert line', 'area'],
    ['templates.reprapfirmware', 'RepRapFirmware insert line', 'area'],
    ['templates.marlin', 'Marlin insert lines (your own)', 'area']
  ];

  function get(obj, path) {
    return path.split('.').reduce(function (o, k) { return o == null ? o : o[k]; }, obj);
  }
  function set(obj, path, value) {
    var keys = path.split('.');
    var last = keys.pop();
    keys.reduce(function (o, k) { return o[k]; }, obj)[last] = value;
  }
  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    if (text != null) { node.textContent = text; }
    return node;
  }
  function numberInput(value, onChange) {
    var input = el('input', {type: 'number', step: 'any'});
    input.value = value;
    input.addEventListener('change', function () { onChange(parseFloat(input.value)); });
    return input;
  }

  // Build a form for `target` from a field list.
  function buildForm(host, fields, target, afterChange) {
    host.textContent = '';
    fields.forEach(function (field) {
      var path = field[0], kind = field[2];
      if (path === null) { host.appendChild(el('div', {class: 'group'}, field[1])); return; }
      var row = el('label');
      row.appendChild(el('span', {}, field[1]));
      var value = get(target, path), control;
      var changed = function (v) { set(target, path, v); dirty(); if (afterChange) { afterChange(); } };
      if (kind === 'range') {
        control = el('span', {class: 'row'});
        control.appendChild(numberInput(value[0], function (v) { value[0] = v; dirty(); }));
        control.appendChild(el('span', {class: 'unit'}, 'to'));
        control.appendChild(numberInput(value[1], function (v) { value[1] = v; dirty(); }));
        control.appendChild(el('span', {class: 'unit'}, 'mm'));
      } else if (kind === 'num' || kind === 'int') {
        control = el('span', {class: 'row'});
        control.appendChild(numberInput(value, function (v) {
          changed(kind === 'int' ? Math.round(v) : v); }));
        if (kind === 'num' && path.indexOf('deg') < 0) {
          control.appendChild(el('span', {class: 'unit'}, 'mm'));
        }
      } else if (kind === 'bool') {
        control = el('input', {type: 'checkbox'});
        control.checked = !!value;
        control.addEventListener('change', function () { changed(control.checked); });
      } else if (kind === 'select') {
        control = el('select');
        field[3].forEach(function (option) {
          control.appendChild(el('option', {value: option[0]}, option[1]));
        });
        control.value = value;
        control.addEventListener('change', function () { changed(control.value); });
      } else if (kind === 'area') {
        row = el('div');
        row.appendChild(el('div', {class: 'muted', style: 'margin-top:6px'}, field[1]));
        control = el('textarea', {rows: path === 'templates.marlin' ? 5 : 3, spellcheck: 'false'});
        control.value = value;
        control.addEventListener('change', function () { changed(control.value); });
      } else {
        control = el('input', {type: 'text'});
        control.value = value == null ? '' : value;
        control.addEventListener('change', function () { changed(control.value); });
      }
      row.appendChild(control);
      host.appendChild(row);
    });
  }

  function dirty() { $('saved').textContent = 'Not saved yet'; }

  function renderLibrary() {
    var body = $('library').querySelector('tbody');
    body.textContent = '';
    if (!config) { return; }
    if (selected >= config.nuts.length) { selected = Math.max(0, config.nuts.length - 1); }
    config.nuts.forEach(function (nut, i) {
      var row = el('tr', {class: 'entry' + (i === selected ? ' selected' : '')});
      var classes = ['flat', 'edge', 'corner'].filter(function (c) { return nut[c].enabled; });
      [nut.key, nut.across_flats + ' mm', nut.thickness + ' mm', classes.join(', ') || 'none']
        .forEach(function (text) { row.appendChild(el('td', {}, text)); });
      row.addEventListener('click', function () { selected = i; renderLibrary(); });
      body.appendChild(row);
    });
    if (config.nuts.length) {
      buildForm($('form'), NUT_FIELDS, config.nuts[selected], function () {
        // Keep the table row in step without rebuilding the form under the cursor.
        var nut = config.nuts[selected];
        var cells = body.children[selected].children;
        cells[0].textContent = nut.key;
        cells[1].textContent = nut.across_flats + ' mm';
        cells[2].textContent = nut.thickness + ' mm';
        cells[3].textContent = ['flat', 'edge', 'corner'].filter(function (c) {
          return nut[c].enabled; }).join(', ') || 'none';
      });
    } else {
      $('form').textContent = '';
    }
    buildForm($('settings'), SETTING_FIELDS, config.settings);
  }

  function renderReport(report) {
    $('stale').classList.toggle('hidden', !(report && report.stale));
    var chips = $('chips'), list = $('nuts'), modifier = $('modifier');
    chips.textContent = ''; list.textContent = '';
    if (!report) { $('status').textContent = 'No check has run yet.'; return; }
    $('status').textContent = report.nuts.length + ' nut(s) found';
    ['ok', 'warning', 'error'].forEach(function (k) {
      chips.appendChild(el('span', {class: 'chip ' + k}, report.summary[k] + ' ' + k));
    });
    modifier.classList.toggle('hidden', report.nuts.length === 0);
    if (report.nuts.length) {
      var names = [];
      report.nuts.forEach(function (n) { if (names.indexOf(n.name) < 0) { names.push(n.name); } });
      modifier.textContent = 'One manual step: set every nut body to Modifier. Select ' +
        names.join(', ') + ' in the object list, right-click, Change type, Modifier. ' +
        'A nut body left as a normal part prints as plastic and fills its own pocket. ' +
        'Export is refused if that happens.';
    }
    report.nuts.forEach(function (n) {
      var box = el('div', {class: 'nut'});
      var head = el('div', {class: 'head'});
      head.appendChild(el('span', {class: 'icon ' + n.status}, ICON[n.status]));
      var where = n.placement ? '  X ' + n.placement[0].toFixed(3) + '  Y ' +
        n.placement[1].toFixed(3) + '  Z ' + n.placement[2].toFixed(3) : '';
      head.appendChild(el('span', {}, '#' + n.index + ' ' + n.name + (n.cls ? ' · ' + n.cls : '')));
      box.appendChild(head);
      if (where) { box.appendChild(el('div', {class: 'finding'}, where)); }
      n.findings.forEach(function (f) {
        var line = el('div', {class: 'finding'});
        line.appendChild(el('b', {}, f.level + ': '));
        line.appendChild(document.createTextNode(f.message));
        box.appendChild(line);
      });
      list.appendChild(box);
    });
  }

  function showError(text) {
    $('error').textContent = text || '';
    $('error').classList.toggle('hidden', !text);
  }

  function send(message) {
    try { window.orca.postMessage(message); } catch (e) { showError('Cannot reach OrcaSlicer: ' + e); }
  }

  function handle(m) {
    if (typeof m === 'string') { try { m = JSON.parse(m); } catch (e) { return; } }
    if (!m || !m.type) { return; }
    if (m.type === 'config') {
      saved = m.config;
      config = JSON.parse(JSON.stringify(m.config));
      $('saved').textContent = 'Saved';
      showError('');
      renderLibrary();
    } else if (m.type === 'report') {
      showError('');
      renderReport(m.report);
    } else if (m.type === 'stale') {
      $('stale').classList.remove('hidden');
    } else if (m.type === 'error') {
      showError(m.message);
    }
  }

  $('check').addEventListener('click', function () { send({type: 'check'}); });
  $('save').addEventListener('click', function () { send({type: 'save_config', config: config}); });
  $('revert').addEventListener('click', function () { if (saved) { handle({type: 'config', config: saved}); } });
  $('add').addEventListener('click', function () {
    config.nuts.push({key: 'NEW' + (config.nuts.length + 1), label: '', shape: 'square',
      across_flats: 5.5, thickness: 1.8, feeder: 1, max_roof_span: 6.0, tool_reach: 3.0,
      flat: {enabled: true, width: [5.7, 5.9], depth: [2.0, 2.6]},
      edge: {enabled: false, thickness: [2.0, 2.3], width: [5.7, 5.9], height_min: 5.7},
      corner: {enabled: false, thickness: [2.0, 2.3], opening: [7.98, 8.18], seat_gap_max: 0.2,
               height_min: 7.98}});
    selected = config.nuts.length - 1; dirty(); renderLibrary();
  });
  $('duplicate').addEventListener('click', function () {
    if (!config.nuts.length) { return; }
    var copy = JSON.parse(JSON.stringify(config.nuts[selected]));
    copy.key = copy.key + '_COPY';
    config.nuts.push(copy); selected = config.nuts.length - 1; dirty(); renderLibrary();
  });
  $('delete').addEventListener('click', function () {
    if (!config.nuts.length) { return; }
    config.nuts.splice(selected, 1); dirty(); renderLibrary();
  });
  $('export').addEventListener('click', function () {
    $('json').value = JSON.stringify(config, null, 2); $('json').select();
  });
  $('import').addEventListener('click', function () {
    try {
      var parsed = JSON.parse($('json').value);
      if (!parsed.settings || !Array.isArray(parsed.nuts)) { throw new Error('settings and nuts are required'); }
      config = parsed; selected = 0; dirty(); showError(''); renderLibrary();
    } catch (e) { showError('Import failed: ' + e.message); }
  });

  function boot() {
    if (!window.orca) { setTimeout(boot, 100); return; }
    window.orca.onMessage(handle);
    send({type: 'ready'});
  }
  boot();
})();
</script>
</body>
</html>
"""
