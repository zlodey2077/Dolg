# NE555 internal astable schematic generation report

Generated through `Dolg_APP.services.schematic_operations.apply_schematic_operations`.

- Operations: 98
- Components: 40
- Connections: 58
- Operations rejected: 0
- DRC ok: True
- Topology ok: True
- Connected parts: 1
- Has ground: True
- Has source: True

Artifacts:

- `ne555_internal_astable_operations.json` - operation log for the programmatic mode.
- `ne555_internal_astable_scheme.json` - importable `scheme_data` package with DRC/topology report.
- `ne555_internal_astable_preview.svg` - external simulator-style SVG preview with fixed NE555 pins, rails and orthogonal wiring.
- `ne555_internal_astable_simulator_preview.png` - raster preview of the same external sheet.
- `ne555_internal_block_preview.svg` - internal NE555 functional subcircuit sheet.
- `ne555_internal_block_preview.png` - raster preview of the internal sheet.
- `ne555_internal_astable_hierarchical_scheme.json` - hierarchical `sheets/subcircuits` scheme data used for automated quality checks.
- `ne555_internal_astable_quality_report.json` - self-check output from `schematic_layout_quality`.

Modeling note: this is a functional NE555 internal schematic, not a manufacturer-specific transistor-level die netlist.

Layout note: the first generated graph preview was intentionally replaced. A readable schematic needs a schematic-layout layer, not a generic node-link graph layout.

Latest layout quality self-check:

- scopes: 2 (`sheet:external_astable_load`, `subcircuit:NE555_FUNC`)
- components: 37
- connections: 52
- diagonal segments: 0
- direct diagonal connections: 0
- wire crossings: 0
- component overlaps: 0
- missing coordinates: 0
- warnings: 0
