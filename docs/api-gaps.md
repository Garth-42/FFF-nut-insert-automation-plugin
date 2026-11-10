# API gaps

Calls the plugin wanted and OrcaSlicer 2.5's documented plugin API does not have, with
the fallback that was built. No `orca` call outside the spec's API table is used.

| Wanted | Why | Fallback built |
| --- | --- | --- |
| Set a part's type to Modifier | A nut body left as a part prints as plastic | Manual step, shown in the panel after every check |
| Read a part's type | Know whether the manual step was done | **Closed.** `is_modifier()` exists in 2.5.0 though the docs do not list it; `adapter.part_type()` uses it. The pocket proof at export stays as a second check |
| Plate of an object, plate offset | Export only the nuts on the exported plate | Plate 1 only. A nut with nothing printed around it is skipped (`N_NOT_ON_PLATE`) |
| Read the model from a slicing step | Re-measure at slice time | The report cached on the UI thread; a stale report fails the slice. `ctx.print.model()` exists for this and is not used yet |
| Stop a slice from an event handler | Block on errors early | The slicing step returns a failure at `posSlice` |
| Draw in Orca's 3D view, read the selection | Highlight pockets in place | The plugin's own Nuts tab with a canvas wireframe |
| Read a plugin's own data files | Ship the HTML pages as files | The pages are Python string constants |
| Save a file from a page | Export the report or the library | The page shows the text to copy |

## Not documented, assumed, and checked by the probe

- Whether page messages arrive and leave as objects or JSON strings. Incoming messages
  are accepted in both forms; outgoing form is one switch, `adapter.POST_AS_JSON_STRING`.
  The pages accept both.
- Whether `window.orca` exists when a page's script first runs. The pages wait for it.
- The arguments Orca passes to a dock panel's `on_close`. The handler accepts any.
- Whether `volume.name` is an attribute or a method. The adapter accepts both.
- How a wheel declares the plugin's display name and description. Only the single-file
  PEP 723 form is documented, so the wheel relies on the distribution name `nut-inserter`.
- Setting keys `gcode_flavor` and `print_sequence`. A failed lookup is treated as
  "unknown": firmware `auto` then asks you to pick one in the panel.
