# Manual checks in OrcaSlicer

These are the steps only a person with OrcaSlicer 2.5 can do. Tick each one and write
the result under it, then commit this file.

## Installing a plugin

Give each plugin its own folder under `orca_plugins` in OrcaSlicer's data folder,
holding exactly one entry file: the `.py` or the `.whl`. The Plugins window also has
"Install local plugin". Restart Orca after replacing a file. Plugin output goes to the
newest `python_*.log` in the data folder's `log` directory.

Build the wheel with:

```bash
uv build
```

## Checks

- [ ] **Probe.** Install `probe/nut_api_probe.py` (version 0.6.0 or later). It opens no
  files and prints nothing; its output is shown in the "Nut probe" tab. Its script
  actions are numbered from harmless to "may raise permission prompts". In OrcaSlicer
  2.5.0 some model calls raise about a hundred prompts in a row; hold Return or Esc to
  clear them.

  1. Open a project with a two-body STEP: a part plus `NUT_M3SQ`.
  2. Run "Nut probe 1: signatures", then "Nut probe 2: model names and types", then
     "Nut probe 3: mesh without arrays". Stop at the first one that floods prompts.
  3. Open the "Nut probe" tab, press Refresh, Select all, copy, and append the text to
     `docs/probe-log.txt`. Every call is logged before it is made, so the last `call`
     line names the one Orca objected to.
  4. Steps 4, 5 and 6 only when asked.
  5. Slicing and export: slice, export G-code, Refresh the tab and copy again. Save the
     exported file as `tests/data/sample.gcode`.

  Then fill `docs/api-facts.md` from the lines that start with `NUTPROBE`.

  Result so far (10 Nov 2026): runs 1 and 2 recorded in `docs/probe-log.txt`.

- [ ] **A, Check nuts.** Install the wheel and run Check nuts from the Plugins window.
  Expect a result line with the nut count. Rotate the part 20° about X and expect a
  warning notification.

  Result:

- [ ] **B, Panel.** Narrow the flat pocket width range until the test part fails, save,
  and see the error state the measured width. Restart Orca and confirm the change was
  kept.

  Result:

- [ ] **C, Preview.** Open the Nuts tab and find the part's edges, one box per pocket,
  and a crosshair at each placement point. Move the part in Prepare and confirm the tab
  follows.

  Result:

- [ ] **D, Export.** With the nut body still a normal part, export and expect a slicing
  error naming the nut. Set it to Modifier, export again, and find one insert block
  after the last layer below the pocket roof, in your firmware's syntax.

  Result:

- [ ] **Corner.** Repeat A and D with a part whose nut stands on a corner in a V slot.

  Result:

- [ ] **E, Dry run.** On the printer, run the file once with the insert macro replaced
  by a pause, before the first real insert.

  Result:

## If something does not work

The plugin has only run against a stand-in `orca` module. If Orca rejects a call, the
traceback is in the Python log. Every Orca call is in `src/nut_inserter/adapter.py` and
`src/nut_inserter/__init__.py`; the first thing to try for a blank panel or tab is
flipping `POST_AS_JSON_STRING` in `adapter.py`.
