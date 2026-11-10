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

- [ ] **Probe.** Install `probe/nut_api_probe.py` (version 0.3.0 or later). It opens no
  files and prints nothing, because in OrcaSlicer 2.5.0 each of those raised a permission
  prompt. Its output is shown in its own tab instead.

  1. Open a project with a two-body STEP: a part plus `NUT_M3SQ`.
  2. Run "Nut API probe: 1 API" from the Plugins window. Note whether any prompt appears.
  3. Run "Nut API probe: 2 model". Note whether any prompt appears.
  4. Move the object, slice, and export G-code.
  5. Open the "Nut probe" tab, press Refresh, Select all, copy, and save the text as
     `docs/probe-log.txt`.
  6. Save the exported G-code file as `tests/data/sample.gcode`.

  Then fill `docs/api-facts.md` from the lines that start with `NUTPROBE`.

  Result:

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
