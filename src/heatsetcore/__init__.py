"""Heat-set inserts: the tool profile, detection and checks, the routine and its G-code.

The design is docs/HEATSET_GCODE_SPEC.md; docs/heatset-plan.md says how it fits the nut
plugin. Like nutcore this package never imports orca, and its tests run without Orca.
Nothing is imported here, so importing one module does not pull in numpy.
"""
