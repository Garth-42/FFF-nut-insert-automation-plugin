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

**Keep one copy installed.** Before installing a new wheel, remove the old one: delete its
folder (named after the old wheel file) from `orca_plugins`, or uninstall it in the
Plugins window. Two versions at once share one Python package name and break each other.

**Switch the slicing step on.** The check, panel and tab work as soon as the plugin is
installed. The slice gate and the export step only run once the plugin is added to the
process preset: in the process settings find **Slicing pipeline plugin**, enable it, click
**+ Add Plugin** and add Nut insert. The preset stores the wheel's file name, version
included, so expect to add it again after installing a newer wheel.

## Checks

- [x] **Probe, model part.** Runs 1 to 6 are recorded in `docs/probe-log.txt` and
  summarised in `docs/api-facts.md`. With the permission request granted, importing numpy
  and reading meshes raise no prompts.

- [ ] **Probe, slicing part.** With probe 0.7.0 installed, slice and export G-code. Note
  any prompt. Open the "Nut probe" tab, press Refresh, copy the text and append it to
  `docs/probe-log.txt`. Save the exported file as `tests/data/sample.gcode`.

  Result:

- [x] **A, Check nuts.** Remove the probe first, so only one plugin asks for permissions.
  Install the wheel (0.2.1 or later). Expect **one** permission request for read access
  to folders under the OrcaSlicer app and its data folder; answer Yes. Expect a
  notification asking you to restart OrcaSlicer, and no other prompts. Restart.
  Open the project. Expect the Nut inserter panel docked on the right, no prompts, and a
  report listing the nut. With the nut body still a normal part, expect the error
  `E_NOT_MODIFIER`. Run Check nuts from the Plugins window and expect a result line with
  the nut count. Rotate the part 20 degrees about X and expect a warning notification.

  Result (10 Nov 2026, wheel 0.2.0): passed. The panel docked, the check ran on load,
  the nut was found as FLAT at X 164.706 Y 158.320 Z 1.900 with `E_NOT_MODIFIER`, which
  cleared after the body was set to Modifier. Rotating about X raised a notification and
  undoing it cleared the finding. The install session flooded permission prompts and a
  restart ended them; 0.2.1 avoids the flood. Notifications stay on screen after the
  problem is fixed; 0.2.2 adds an "all clear". The script action from the Plugins window
  was not tried.

- [ ] **B, Panel.** Narrow the flat pocket width range until the test part fails, save,
  and see the error state the measured width. Restart Orca and confirm the change was
  kept.

  Result:

- [x] **C, Preview.** Open the Nuts tab and find the part's edges, one box per pocket,
  and a crosshair at each placement point. Move the part in Prepare and confirm the tab
  follows.

  Result (10 Nov 2026, wheel 0.2.0): the tab shows the part's edges, the pocket box, the
  list and the detail (pocket 5.80 x 5.80 x 2.00 mm, insert window Z 2.900 to 3.000).
  Moving the part and checking that the tab follows was not reported.

- [ ] **D, Export.** With the nut body still a normal part, slice and expect the slice to
  be blocked naming the nut. Set it to Modifier, export again, and find one insert block
  after the last layer below the pocket roof, in your firmware's syntax.

  Result (10 Nov 2026): the second half passed with wheel 0.2.3. One block, Klipper
  syntax, after the layer at Z 3.0 and before the layer change to Z 3.2; no permission
  prompt. See "The first working export" in `docs/api-facts.md`. Earlier attempts: 0.2.0
  wrote nothing because the plugin was not added to the process preset, then failed
  because two versions were installed. Still to do: the first half, a slice with the nut
  body still a normal part.

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
