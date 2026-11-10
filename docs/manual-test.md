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

- [ ] **Probe.** Install `probe/nut_api_probe.py` (version 0.7.0 or later). Its output is
  shown in the "Nut probe" tab; it prints nothing unless you run step 7.

  Runs 1 to 5 are done and recorded in `docs/probe-log.txt`. They showed that importing
  numpy raised about 120 permission prompts. Probe 0.7.0 asks Orca once, while it loads,
  for read access to Python's library folders. What is left:

  1. Install 0.7.0 and restart Orca. Expect **one** permission request listing folders
     under the OrcaSlicer app and its data folder. Answer Yes.
  2. Open the project with the part and `NUT_M3SQ`.
  3. Run "Nut probe 5: import numpy (may prompt)". No prompt, or a flood? If it floods,
     stop here and report.
  4. Run "Nut probe 6: mesh arrays", "7: print test" and "8: notification test". Note
     any prompt, and whether a notification appeared in the 3D view.
  5. Slice and export G-code. Note any prompt.
  6. Open the "Nut probe" tab, press Refresh, Select all, copy, and append the text to
     `docs/probe-log.txt`. Save the exported file as `tests/data/sample.gcode`.

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
