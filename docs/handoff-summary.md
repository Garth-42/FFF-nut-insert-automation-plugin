# Nut insertion plugin (OrcaSlicer 2.5): decisions as of 2026-11-10

Full architecture and build brief: https://claude.ai/artifact/X7YaFwZtnkSDpdWhpqLLAU

## Goal

An OrcaSlicer 2.5 Python plugin for a toolchanging printer. It finds bodies named `NUT_<key>` (for example `NUT_M3SQ`), measures the pocket each one sits in, checks the pocket against a nut library, reports placement points, shows a preview tab, and writes an insert block per nut at export.

## Decisions

- Geometry source: triangle meshes in the Prepare tab, not STEP or Design-tab solids. The plugin API exposes only meshes, and flat faces tessellate exactly, so centre, size and angle match the CAD values.
- Nut bodies stay in the model as modifiers and are the persistent record. The plugin stores nothing per project.
- The modifier type is set by hand, because the plugin API is read-only. Export is blocked if the G-code shows plastic inside a pocket.
- Body names survive STEP import into Orca (confirmed by Garth, 2026-11-10).
- Name rule: a part is a nut when its name contains `NUT_<key>`, ignoring case, with a non-alphanumeric boundary before `NUT_` and after the key; the longest library key wins. Fusion 360 is the reference CAD; other CAD is covered by this tolerance, and a nut can be named by hand.
- Orientation classes: `FLAT` (thread axis within 0.5 degrees of Z), `EDGE` (axis horizontal, standing on a flat), `CORNER` (axis horizontal, standing on a corner; allowed per Garth, 2026-11-10). `TILTED` and `ROLLED` are unsupported: warning, no insert. Any rotation about Z is allowed. Each nut type can switch each class on or off.
- Placement point, in bed coordinates: the centre of the nut after it is settled onto its seat faces and centred between the side walls. X and Y therefore come from the pocket. At export, heights snap to the printed layers.
- Nut library entry per key: nut size, per-class pocket ranges (flat, edge, corner), max roof span, tool reach, feeder. Stored in the plugin's own settings (the slicing capability's config) and edited in a docked panel.
- Firmware: all three supported through editable templates, chosen from the profile's G-code flavor. Klipper: `INSERT_NUT KEY=.. CLASS=.. X=.. Y=.. Z=.. Z_LOW=.. YAW=.. FEEDER=.. TOOL=..`. RepRapFirmware: `M98 P"insert_nut.g" K".." C".." X.. Y.. Z.. L.. A.. F.. S..` (value letters avoid G, M, N, T and P). Marlin: the user's own inline lines with values filled in, because M810-M819 macros take no parameters.
- The plugin only writes the insert block; the printer macro does the tool change, pick, place, return and re-prime.
- Structure: package `nutcore` (plain Python 3.12 + numpy, no Orca imports) and package `nut_inserter` (the Orca plugin, the wheel's entry package). Outputs are a docked panel, a "Nuts" plugin tab (wireframe on a 2D canvas), a slice gate and an export step.

## Limits of the first build

- Square nuts only; plate 1 only; print order by layer; no support material in pockets; the Modifier step stays manual.

## OrcaSlicer 2.5 plugin API facts (docs read 2026-11-10)

- Registration: `@orca.plugin` on one class deriving `orca.base`; `register_capabilities()` calls `orca.register_capability(cls)`.
- Capability bases: `orca.script.ScriptPluginCapabilityBase`, `orca.pages.PagesPluginCapabilityBase`, `orca.slicing.SlicingPipelineCapabilityBase`.
- Readable: part names, part meshes (numpy, mm, part-local frame), part and instance transform matrices.
- Not available: changing the model, reading a part's type, STEP or B-rep data, the selection, plate information, drawing in Orca's own 3D view.
- Available: docked HTML panels (shown on Prepare and Preview), plugin tabs, lifecycle events through `on_lifecycle_event`, per-capability settings through `get_config` / `save_config`, slicing-pipeline steps. A failure returned by a slicing step is raised as a slicing error. The `psGCodePostProcess` step edits the exported G-code.
- Packaging: single `.py` with a PEP 723 header, or a pure-Python wheel; numpy must be declared. Local plugins live in their own folder under `orca_plugins` in Orca's data folder. Output from `print` goes to `log/python_*.log`.
- Permission prompts appear for threads, network, processes and files outside Orca's data folder and the G-code folder.
- Orca says the plugin API may still change.

## Still to test in Orca

The API probe plugin in milestone 0 of the build brief collects all of these.

1. May a slicing step read the model from its worker thread?
2. How do bed coordinates map to G-code coordinates on plates after the first?
3. A real exported G-code file with a nut pocket, for parser tests.
4. The setting keys for G-code flavor and print order.

## Build handoff

The doc's "Build brief" sections are written for Claude Code in an empty repository: scope and rules, repository layout and tooling, Orca API contract with a plugin skeleton, data contracts, algorithm details and constants, G-code contract, tests, milestones 0-6 and manual checks. Export the doc as Markdown and save it as `docs/SPEC.md` in the repository.
