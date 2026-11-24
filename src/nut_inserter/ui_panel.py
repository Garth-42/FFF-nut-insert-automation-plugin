"""The docked panel: check summary, Modifier reminder, and three settings tabs: Nuts (the
nut library and the shared settings), Heat-set (how inserts are put in) and Machine settings
(the heat-set tool's measured values and motion).

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
  .form label > .row > .unit:last-child { display: inline-block; min-width: 3.2em; }
  .muted { color: var(--muted); }
  details { margin: 6px 0; } summary { cursor: pointer; }
  .tabs { display: flex; gap: 2px; margin: 18px 0 4px; border-bottom: 1px solid var(--border); }
  .tabs button { border: 1px solid transparent; border-bottom: none; border-radius: 4px 4px 0 0;
                 margin-bottom: -1px; }
  .tabs button.selected { border-color: var(--border); background: var(--bg); font-weight: 600; }
  .badge { font-size: 11px; padding: 0 5px; margin-left: 6px; border-radius: 8px;
           border: 1px solid var(--warn); color: var(--warn); cursor: pointer; }
  .problems { margin: 6px 0; color: var(--err); }
  .derived td:first-child { color: var(--muted); }
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

<div class="tabs" id="tabs">
  <button data-tab="nuts" class="selected">Nuts</button>
  <button data-tab="heatset">Heat-set</button>
  <button data-tab="machine">Machine settings</button>
</div>

<section id="tab-nuts">
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
<p>The insert block comes after the layer's last extrusion, the slicer's retract and wipe, and
the label that ends the object: the print tool is hot and normally retracted, and no object label
is open. Your macro (Klipper <code>INSERT_NUT</code>, RepRapFirmware <code>insert_nut.g</code>)
or your Marlin lines must park the print tool, place the nut, and bring the print tool back to the
same position, undoing any retraction the macro adds itself, with the positioning and extruder
modes unchanged.</p>
<p>Placeholders: {index} {key} {cls} {x} {y} {z} {z_low} {z_high} {yaw} {feeder} {layer_z}
{tool} {rx} {ry} {rz}. Write a literal brace as {{ or }}.</p></details>
</section>

<section id="tab-heatset" class="hidden">
<h2>Heat-set tool</h2>
<div class="row picker"></div>
<div class="banner stale hidden tbd"></div>
<div class="problems"></div>
<p class="muted">Bodies named HEATSET_&lt;key&gt; are inserts for the profile with that key. The
angle window, body tolerance and what happens on an error are the shared settings on the Nuts
tab.</p>
<div class="form" id="heatset-form"></div>
<h2>Derived, never typed</h2>
<table class="derived" id="derived"></table>
</section>

<section id="tab-machine" class="hidden">
<h2>Heat-set tool hardware</h2>
<div class="row picker"></div>
<div class="banner stale hidden tbd"></div>
<div class="problems"></div>
<p class="muted">Values marked TBD are placeholders until measured on the tool. Entering a value
marks it measured; click TBD to keep the placeholder as measured.</p>
<div class="form" id="machine-form"></div>
</section>

<div class="row" style="margin-top:10px">
  <button class="primary" id="save">Save</button>
  <button id="revert">Revert</button>
  <span class="muted" id="saved"></span>
</div>

<h2>Activity</h2>
<p class="muted">What the plugin did, newest last. Slicing and export steps report here.
Useful when something does not happen.</p>
<div class="row"><button id="log-refresh">Refresh</button></div>
<textarea id="log" rows="8" readonly spellcheck="false"></textarea>

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
  // Heat-set profile fields: [name, label, kind, unit or options]. docs/HEATSET_GCODE_SPEC.md.
  var HEATSET_FIELDS = [
    [null, 'Mode'],
    ['mode', 'Mode', 'select', [['normal', 'Normal'],
      ['rehearse', 'Rehearse: no heat, no contact, every move raised']]],
    ['rehearse_lift', 'Rehearse lift', 'num', 'mm'],
    [null, 'When'],
    ['timing', 'Insert', 'select', [['after_layer', 'After the layer that prints the hole rim'],
      ['end_of_print', 'At the end of the print']]],
    ['preheat_lead', 'Preheat this long before a block', 'num', 's'],
    ['preheat_layers', 'Or this many layers, without time estimates', 'int', 'layers'],
    [null, 'Temperature'],
    ['insert_temp', 'Insert temperature (blank: automatic)', 'temp', '°C'],
    ['insert_temp_offset', 'Automatic: print temperature plus', 'num', '°C'],
    ['filament_temps', 'Filament table, when the G-code has none', 'table', '°C'],
    ['temp_window', 'Allowed difference before a push', 'num', '°C'],
    [null, 'Process'],
    ['proud_after_hot', 'Proud after the hot push (g)', 'num', 'mm'],
    ['mouth_gap', 'Mouth above the surface in the push (h)', 'num', 'mm'],
    ['follower_retract', 'Follower back-off after each insert (r)', 'num', 'mm'],
    ['resist_wait', 'Wait when the insert resists', 'num', 's'],
    ['resist_retries', 'Waits before aborting', 'int', ''],
    ['press_dwell', 'Hold after the press', 'num', 's'],
    ['flush_tol', 'Flush tolerance', 'num', 'mm'],
    ['press_guard', 'Overpress guard', 'num', 'mm'],
    ['surface_tol', 'Probed surface against the model', 'num', 'mm'],
    ['on_proud', 'When an insert stays proud', 'select', [['warn', 'Warn and carry on'],
      ['pause', 'Pause the print']]],
    [null, 'Hole checks'],
    ['hole_d_min', 'Hole diameter, minimum', 'num', 'mm'],
    ['hole_d_max', 'Hole diameter, maximum', 'num', 'mm'],
    ['hole_extra_depth', 'Blind hole deeper than the insert by', 'num', 'mm'],
    ['min_wall', 'Wall around the hole, minimum', 'num', 'mm'],
    [null, 'Hold-down warning'],
    ['min_contact_area', 'Part on the bed, minimum area', 'num', 'mm²'],
    ['max_height_ratio', 'Height ÷ √area, maximum', 'num', '']
  ];
  var MACHINE_FIELDS = [
    [null, 'Tool'],
    ['name', 'Profile name', 'text'],
    ['tool', 'Tool number', 'int', 'T'],
    ['firmware', 'Firmware', 'select', [['reprapfirmware', 'RepRapFirmware'],
      ['klipper', 'Klipper (not built yet)']]],
    ['magazine_capacity', 'Magazine capacity', 'int', 'inserts'],
    [null, 'Insert'],
    ['insert_key', 'Key (bodies named HEATSET_<key>)', 'text'],
    ['insert_length', 'Insert length (Li)', 'num', 'mm'],
    ['insert_od', 'Insert diameter across the knurls', 'num', 'mm'],
    ['rest_recess', 'Rest recess above the mouth (e)', 'num', 'mm'],
    [null, 'Measured on the tool'],
    ['pad_dx', 'Pad offset X, pad minus mouth', 'num', 'mm'],
    ['pad_dy', 'Pad offset Y, pad minus mouth', 'num', 'mm'],
    ['pad_drop', 'Pad face below the mouth (p)', 'num', 'mm'],
    ['pad_d', 'Pad face diameter', 'num', 'mm'],
    ['tube_od', 'Tube tip diameter', 'num', 'mm'],
    ['block_r', 'Heater block radius around the mouth', 'num', 'mm'],
    ['block_clearance', 'Heater block underside above the mouth', 'num', 'mm'],
    ['trip_overtravel', 'Trip overtravel (δ)', 'num', 'mm'],
    ['float_travel', 'Float lift left after the trip', 'num', 'mm'],
    ['trip_force', 'Trip force', 'num', 'g'],
    [null, 'Motion'],
    ['push_step', 'Push step between float checks', 'num', 'mm'],
    ['push_speed', 'Push speed', 'num', 'mm/s'],
    ['unsheath_speed', 'Unsheath speed', 'num', 'mm/s'],
    ['retract_speed', 'Follower back-off speed', 'num', 'mm/s'],
    ['probe_start', 'Probing starts above the surface', 'num', 'mm'],
    ['probe_speed', 'Probe speed', 'num', 'mm/s'],
    ['press_speed', 'Press speed', 'num', 'mm/s'],
    ['travel_lift', 'Lift before the pad moves over', 'num', 'mm'],
    ['local_clear', 'Mouth clearance near a hole', 'num', 'mm'],
    ['safe_z_clear', 'Clearance over the print between inserts', 'num', 'mm'],
    ['xy_travel_speed', 'XY speed between inserts', 'num', 'mm/s'],
    ['xy_local_speed', 'XY speed near a hole', 'num', 'mm/s'],
    ['z_travel_speed', 'Z speed between inserts', 'num', 'mm/s'],
    ['z_local_speed', 'Z speed near a hole', 'num', 'mm/s']
  ];
  var DERIVED = [['L', 'Unsheath lift and follower feed (L = g − h)', 'mm'],
    ['push', 'Follower travel in the hot push (h + e + Li − g)', 'mm'],
    ['ticks', 'Float checks in the push, at most', ''],
    ['pad_face_in_push', 'Pad face above the surface in the push (h − p)', 'mm'],
    ['mouth_in_press', 'Mouth above the surface in the press (p)', 'mm']];
  var profileIndex = 0;   // the heat-set profile being edited
  var lastTemp = null;    // {value, source} from the last export

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

  // Build a form for `target` from a field list. A target with a "tbd" list (a heat-set
  // profile) shows a TBD badge on each placeholder; entering a value takes it off the list.
  function buildForm(host, fields, target, afterChange) {
    host.textContent = '';
    var tbd = Array.isArray(target.tbd) ? target.tbd : null;
    fields.forEach(function (field) {
      var path = field[0], kind = field[2], extra = field[3];
      if (path === null) { host.appendChild(el('div', {class: 'group'}, field[1])); return; }
      var row = el('label');
      var name = el('span', {}, field[1]);
      row.appendChild(name);
      var value = get(target, path), control, badge = null;
      var measured = function () {
        var at = tbd ? tbd.indexOf(path) : -1;
        if (at >= 0) { tbd.splice(at, 1); }
        if (badge) { badge.remove(); badge = null; }
      };
      var changed = function (v) {
        set(target, path, v); measured(); dirty();
        if (afterChange) { afterChange(path); }
      };
      var unit = typeof extra === 'string' ? extra :
        (kind === 'num' && path.indexOf('deg') < 0 ? 'mm' : '');
      if (kind === 'range') {
        control = el('span', {class: 'row'});
        control.appendChild(numberInput(value[0], function (v) { value[0] = v; dirty(); }));
        control.appendChild(el('span', {class: 'unit'}, 'to'));
        control.appendChild(numberInput(value[1], function (v) { value[1] = v; dirty(); }));
        control.appendChild(el('span', {class: 'unit'}, 'mm'));
      } else if (kind === 'num' || kind === 'int' || kind === 'temp') {
        control = el('span', {class: 'row'});
        var input = el('input', {type: 'number', step: 'any'});
        input.value = value == null ? '' : value;
        input.addEventListener('change', function () {
          if (kind === 'temp' && input.value.trim() === '') { changed(null); return; }
          var v = parseFloat(input.value);
          changed(kind === 'int' ? Math.round(v) : v);
        });
        if (kind === 'temp') { input.placeholder = 'auto'; }
        control.appendChild(input);
        if (unit || tbd) { control.appendChild(el('span', {class: 'unit'}, unit)); }
        if (kind === 'temp') {
          row = el('div');
          var line = el('label');
          line.appendChild(name);
          line.appendChild(control);
          row.appendChild(line);
          row.appendChild(el('div', {class: 'muted', id: 'auto-temp'}));
          host.appendChild(row);
          return;
        }
      } else if (kind === 'table') {
        control = el('span', {class: 'row'});
        var text = el('input', {type: 'text', size: 24});
        text.value = Object.keys(value || {}).map(function (k) { return k + ' ' + value[k]; })
          .join(', ');
        text.addEventListener('change', function () {
          var table = {};
          text.value.split(',').forEach(function (part) {
            var words = part.trim().split(/\s+/);
            if (words.length === 2 && words[0]) { table[words[0]] = parseFloat(words[1]); }
          });
          changed(table);
        });
        control.appendChild(text);
        control.appendChild(el('span', {class: 'unit'}, unit));
      } else if (kind === 'bool') {
        control = el('input', {type: 'checkbox'});
        control.checked = !!value;
        control.addEventListener('change', function () { changed(control.checked); });
      } else if (kind === 'select') {
        control = el('select');
        (extra || field[3]).forEach(function (option) {
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
      if (tbd && tbd.indexOf(path) >= 0) {
        badge = el('span', {class: 'badge', title: 'A placeholder, not measured yet. ' +
          'Enter the measured value, or click to keep this one as measured.'}, 'TBD');
        badge.addEventListener('click', function (ev) {
          ev.preventDefault(); measured(); dirty();
          if (afterChange) { afterChange(path); }
        });
        name.appendChild(badge);
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
    renderProfiles();
  }

  // --- Heat-set profiles: the Heat-set and Machine settings tabs ---------------------------
  function currentProfile() {
    var list = config && config.heatset && config.heatset.profiles;
    if (!list || !list.length) { return null; }
    if (profileIndex >= list.length) { profileIndex = list.length - 1; }
    return list[profileIndex];
  }

  function renderPicker(host) {
    host.textContent = '';
    var list = config.heatset.profiles;
    var select = el('select');
    list.forEach(function (p, i) {
      select.appendChild(el('option', {value: String(i)}, p.name + ', HEATSET_' + p.insert_key));
    });
    select.value = String(profileIndex);
    select.addEventListener('change', function () {
      profileIndex = parseInt(select.value, 10); renderProfiles();
    });
    var copy = el('button', {}, 'Duplicate'), remove = el('button', {}, 'Delete');
    remove.disabled = list.length < 2;
    copy.addEventListener('click', function () {
      var p = JSON.parse(JSON.stringify(list[profileIndex]));
      p.name = p.name + ' copy'; p.insert_key = p.insert_key + '_COPY';
      list.push(p); profileIndex = list.length - 1; dirty(); renderProfiles();
    });
    remove.addEventListener('click', function () {
      if (list.length < 2) { return; }
      list.splice(profileIndex, 1); dirty(); renderProfiles();
    });
    host.appendChild(el('span', {class: 'muted'}, 'Profile'));
    host.appendChild(select); host.appendChild(copy); host.appendChild(remove);
  }

  function renderTbd() {
    var p = currentProfile();
    var open = !!(p && p.tbd && p.tbd.length && p.mode !== 'rehearse');
    document.querySelectorAll('.tbd').forEach(function (box) {
      box.classList.toggle('hidden', !open);
      box.textContent = open ? 'Not measured yet: ' + p.tbd.join(', ') + '. In normal mode ' +
        'inserts are refused until these are entered (rule 5). Rehearse mode runs without them.' : '';
    });
  }

  function renderTemp() {
    var host = $('auto-temp'), p = currentProfile();
    if (!host || !p) { return; }
    var text = (p.insert_temp == null ? 'Automatic: ' : 'Automatic would be: ') +
      'the print temperature in the G-code + ' + p.insert_temp_offset + ' °C, or the filament ' +
      'table when the G-code sets none.';
    if (lastTemp) {
      text += ' Last export: ' + lastTemp.value + ' °C (' + lastTemp.source + ').';
    }
    host.textContent = text;
  }

  function renderDerived(values) {
    var table = $('derived');
    table.textContent = '';
    if (!values) {
      var tr = el('tr');
      tr.appendChild(el('td', {}, 'Shown once the profile breaks no rule.'));
      table.appendChild(tr);
      return;
    }
    DERIVED.forEach(function (d) {
      var row = el('tr'), v = values[d[0]];
      row.appendChild(el('td', {}, d[1]));
      row.appendChild(el('td', {}, (d[2] ? (+v).toFixed(3) + ' ' + d[2] : String(v))));
      table.appendChild(row);
    });
  }

  function checkProfile() {
    var p = currentProfile();
    if (p) { send({type: 'check_profile', profile: p}); }
  }

  function profileChanged(path) {
    if (path === 'name' || path === 'insert_key') {
      document.querySelectorAll('.picker').forEach(renderPicker);
    }
    renderTbd();
    renderTemp();
    checkProfile();
  }

  function renderProfiles() {
    var p = currentProfile();
    document.querySelectorAll('.picker').forEach(function (host) {
      if (p) { renderPicker(host); } else {
        host.textContent = 'No heat-set profile. Save to add the default one.';
      }
    });
    if (!p) {
      $('heatset-form').textContent = ''; $('machine-form').textContent = '';
      renderDerived(null); renderTbd();
      return;
    }
    buildForm($('heatset-form'), HEATSET_FIELDS, p, profileChanged);
    buildForm($('machine-form'), MACHINE_FIELDS, p, profileChanged);
    renderTemp(); renderTbd(); checkProfile();
  }

  function showTab(name) {
    Array.prototype.forEach.call($('tabs').children, function (button) {
      button.classList.toggle('selected', button.getAttribute('data-tab') === name);
    });
    ['nuts', 'heatset', 'machine'].forEach(function (tab) {
      $('tab-' + tab).classList.toggle('hidden', tab !== name);
    });
  }

  function renderReport(report) {
    $('stale').classList.toggle('hidden', !(report && report.stale));
    var chips = $('chips'), list = $('nuts'), modifier = $('modifier');
    chips.textContent = ''; list.textContent = '';
    if (!report) { $('status').textContent = 'No check has run yet.'; return; }
    var inserts = report.nuts.filter(function (n) { return n.kind === 'heatset'; }).length;
    $('status').textContent = (report.nuts.length - inserts) + ' nut(s)' +
      (inserts ? ', ' + inserts + ' heat-set insert(s)' : '') + ' found';
    ['ok', 'warning', 'error'].forEach(function (k) {
      chips.appendChild(el('span', {class: 'chip ' + k}, report.summary[k] + ' ' + k));
    });
    modifier.classList.toggle('hidden', report.nuts.length === 0);
    if (report.nuts.length) {
      var names = [];
      report.nuts.forEach(function (n) { if (names.indexOf(n.name) < 0) { names.push(n.name); } });
      modifier.textContent = 'One manual step: set every nut and insert body to Modifier. ' +
        'Select ' + names.join(', ') + ' in the object list, right-click, Change type, ' +
        'Modifier. A body left as a normal part prints as plastic and fills its own pocket ' +
        'or hole. Export is refused if that happens.';
    }
    var shown = {};         // profile problem -> the first insert it was written out for
    report.nuts.forEach(function (n) {
      var box = el('div', {class: 'nut'});
      var head = el('div', {class: 'head'});
      head.appendChild(el('span', {class: 'icon ' + n.status}, ICON[n.status]));
      var top = n.kind === 'heatset';      // an insert's height is its top, flush with the rim
      var where = n.placement ? '  X ' + n.placement[0].toFixed(3) + '  Y ' +
        n.placement[1].toFixed(3) + (top ? '  top Z ' + n.z_high.toFixed(3) :
        '  Z ' + n.placement[2].toFixed(3)) : '';
      head.appendChild(el('span', {}, '#' + n.index + ' ' + n.name + (n.cls ? ' · ' + n.cls : '')));
      box.appendChild(head);
      if (where) { box.appendChild(el('div', {class: 'finding'}, where)); }
      n.findings.forEach(function (f) {
        var line = el('div', {class: 'finding'});
        line.appendChild(el('b', {}, f.level + ': '));
        var prefix = n.name + ' #' + n.index + ': ', text = f.message;
        var shared = f.code === 'E_PROFILE' && text.indexOf(prefix) === 0 ?
          text.slice(prefix.length) : null;
        if (shared !== null && shown[shared]) {
          text = 'the heat-set profile problem given for #' + shown[shared] + ' above.';
        } else if (shared !== null) {
          shown[shared] = n.index;
        }
        line.appendChild(document.createTextNode(text));
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
      send({type: 'get_log'});
    } else if (m.type === 'log') {
      $('log').value = (m.lines || []).join('\n');
      $('log').scrollTop = $('log').scrollHeight;
    } else if (m.type === 'stale') {
      $('stale').classList.remove('hidden');
    } else if (m.type === 'profile_check') {
      document.querySelectorAll('.problems').forEach(function (box) {
        box.textContent = '';
        (m.problems || []).forEach(function (text) { box.appendChild(el('div', {}, text)); });
      });
      renderDerived(m.derived);
    } else if (m.type === 'insert_temp') {
      lastTemp = {value: m.value, source: m.source};
      renderTemp();
    } else if (m.type === 'error') {
      showError(m.message);
    }
  }

  Array.prototype.forEach.call($('tabs').children, function (button) {
    button.addEventListener('click', function () { showTab(button.getAttribute('data-tab')); });
  });

  $('check').addEventListener('click', function () { send({type: 'check'}); });
  $('log-refresh').addEventListener('click', function () { send({type: 'get_log'}); });
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
