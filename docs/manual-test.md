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

- [x] **Probe, model part.** Runs 1 to 6 are recorded in `docs/probe-log.txt` and
  summarised in `docs/api-facts.md`. With the permission request granted, importing numpy
  and reading meshes raise no prompts.

- [ ] **Probe, slicing part.** With probe 0.7.0 installed, slice and export G-code. Note
  any prompt. Open the "Nut probe" tab, press Refresh, copy the text and append it to
  `docs/probe-log.txt`. Save the exported file as `tests/data/sample.gcode`.

  Result:

- [ ] **A, Check nuts.** Remove the probe first, so only one plugin asks for permissions.
  Install the wheel (0.2.1 or later). Expect **one** permission request for read access
  to folders under the OrcaSlicer app and its data folder; answer Yes. Expect a
  notification asking you to restart OrcaSlicer, and no other prompts. Restart.
  Open the project. Expect the Nut inserter panel docked on the right, no prompts, and a
  report listing the nut. With the nut body still a normal part, expect the error
  `E_NOT_MODIFIER`. Run Check nuts from the Plugins window and expect a result line with
  the nut count. Rotate the part 20 degrees about X and expect a warning notification.

  Result so far (10 Nov 2026, wheel 0.2.0, install session): the panel docked, the check
  ran from `on_load`, the nut was found as FLAT at X 164.706 Y 158.320 Z 1.900 with
  `E_NOT_MODIFIER`, and the error notification appeared. The install session flooded
  permission prompts, which 0.2.1 avoids. Still to do: the session after a restart, the
  script action, and the rotation.

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
