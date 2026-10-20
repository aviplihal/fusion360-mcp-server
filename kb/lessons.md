# Lessons

Loaded every session. Short, one lesson per bullet. Cap ~150 lines: merge or delete old lessons before adding. Infrastructure notes go in Claude.md, not here.

## Fusion modeling and assembly
- Units are cm everywhere in the tools. Robot frame: origin at the footprint centre on the tiles, +x right, +y front, +z up (see the robot's design file).
- Each subsystem lives in its own top-level component. Work only inside that component.
- In parametric designs, moving a part (moving an occurrence) is temporary: a recompute or snapshot snaps it back. Get lasting positions from the insert position or from joints. In direct designs moves stick, but joints don't move parts.
- A joint moves the first part onto the second, so the first can't be the grounded part.
- Joints between two copies of the same component can fail silently (created with a warning, nothing moves). Always check joint health with `list_joints`.
- Hole joints: moving part's hole `end` → fixed hole's `start` stacks the mover on the fixed hole's start side; `start` → `end` stacks it on the end side.
- Bounding boxes: trust per-body boxes (or the tool's union of them), not the root component's box, which can be stale.
- Patterns work on occurrences; moves don't.
- Imported STEP parts arrive with names like "(Unsaved) (n)"; rename them right away.
- Re-inserting a part to fix its position renumbers it (Plate:1 → Plate:2); refresh your references.

## Design
- Check the actuator budget (8 motors, 8 servos for the whole robot) before choosing a concept, not after building it.
- Give the stowed envelope and the extended envelope separately; R102 applies stowed, R105 extended.

## Workflow
- Never use `execute_code` in a design session; if a tool is missing, note it for the tool lane instead.
