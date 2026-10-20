# Status

## Assembly tools (goal: build a full FTC robot without execute_code)

Plan with spike results: [docs/plans/assembly-tools.md](docs/plans/assembly-tools.md). Branch: `feat/assembly-tools`.

### PR 1: occurrence names + ground_occurrence (done)

Done:
- `addon/server/occurrence_refs.py` (no adsk, unit-tested in `tests/test_occurrence_refs.py`): `pick_occurrence` (path / occurrence name / unique component name; an ambiguous name lists the candidates), `parse_ref`/`make_ref` (`Channel:2/b0/f37`), `union_bbox`.
- Handler helpers: `_occurrence`, `_occ_info`, `_resolve_ref`, `_bbox_union`, `_all_bodies`. `_component_by_name` matches the exact component name first, then occurrence names.
- `add_joint`, `create_as_built_joint`, `create_rigid_group`, `check_interference` look parts up by occurrence and return occurrence names.
- `create_component` returns the real (uniquified) name + occurrence; `parent_name` takes an occurrence.
- `list_components` adds `occurrence` and `is_grounded`.
- `get_bounding_box` handles `root` (adds `size_in`) and occurrences (subtree), using body proxies. `_snapshot` deltas use the same union (root.boundingBox was stale).
- New tool `ground_occurrence`. tools.py, mock.py, tests, AGENTS.md and README are updated. 394 tests pass and ruff check is clean.

Live-tested in Fusion on 2026-10-19 (handler reloaded inside execute_code, throwaway document). Every changed tool works. The live test also turned up and fixed:
- `add_joint` had always been broken (`createByPoint(occ, point)` takes one argument in this Fusion). It now passes an origin proxy created with `createForAssemblyContext`.
- `check_interference` results are temporary bodies with no assembly context, so occurrences are matched by body name + bbox overlap (`occurrences` list per hit).
- New hint `JOINT_GROUNDED_FIRST`: the first occurrence of a joint is the one that moves.

Committed and pushed on `feat/assembly-tools` (add-in restarted and smoke-tested). PR: https://github.com/aviplihal/fusion360-mcp-server/pull/1 (awaiting review).

Open item for PR 3: an origin-to-origin rigid joint gets created but doesn't move the part, even after computeAll. Spike 2's hole-face joint did move it. Check this when replacing origin joints with face geometry.

### PR 2: insert_part + move_occurrence (same branch; merge with PR 1)

Done (2026-10-19), live-tested in parametric and direct designs, including a real STEP plate from ~/Downloads:
- `insert_part(file_path, name?, parent?, translation?, axis?, angle?)`: .step/.stp/.f3d via `importToTarget2`. The source path is stored as a component attribute, so inserting the same file again reuses the component (3 ms vs ~0.2–0.4 s to import), including in later sessions. `partNumber` = file stem; "(Unsaved)" names are replaced by the stem.
- `move_occurrence(occurrence, translation?, axis?, angle?, relative?)`: direct designs set transform2. Parametric designs re-insert and delete (transform2 doesn't last there), which renumbers the occurrence, so the tool returns `occurrence` + `previous_occurrence`. It refuses when joints, as-built joints or rigid groups reference the occurrence. Keeps grounded state (top level only).
- Both are in the mutation sets (deltas). 399 tests pass.

Commit status: committed and pushed on `feat/assembly-tools` (PR #1, now covering PR 1 + PR 2). The add-in needs a restart to run it.

### PR 3: find_holes + list_faces + joint geometry + create_as_built_joint fix (same branch)

Done (2026-10-20). **Tier 0 acceptance passed** using only MCP handlers in Fusion: a real STEP plate (grounded) plus 3 copies of a bracket STEP, bolted hole to hole (rigid, rigid at 90°, revolute with 0.05 cm offset). Zero interference, all joints healthy after computeAll.
- `find_holes(occurrence, diameter?, tolerance, near?, limit)`: concave cylinders (pure `is_concave_cylinder` in hole_geometry.py), start/end = the exact JointGeometry keypoint origins, deduped, `by_diameter` summary. 0.02 s on a 64-face plate.
- `list_faces(occurrence, type, near?, limit)`: planar (normal, center, area) and cylindrical (d, axis, concave).
- `add_joint`: optional `geometry_one/two` = {ref, keypoint}, plus offset, angle, flip. All 7 joint types now set their motion (previously only rigid did). Returns `health` (+ `warning`) and `moved_bbox`.
- `create_as_built_joint`: `joint_type` is now honoured, with `geometry` required for non-rigid types.
- Joints clear `isGroundToParent` on both occurrences. It's True by default and made joints between copies of one component fail silently (this was PR 1's open item).
- `check_interference` attributes a hit to the occurrences whose body box *contains* the overlap (it previously also listed parts that merely touched).

Keypoint rule (in the add_joint description): moving `end` → fixed `start` puts the mover on the fixed hole's start side; `start` → `end` puts it on the end side.

Commit status: committed and pushed on `feat/assembly-tools` (PR #1). Restart the add-in to run it.

### PR 4–6 (same branch; built by three parallel agents in worktrees, merged 2026-10-20)

- **PR 4: `component` parameter (#1).** `create_sketch` and the primitives take `component`. Sketch features build in the sketch's component, and body features build in the body's own component with native entities (spike S17). `_last_sketch` uses the sketch from the last `create_sketch`. Fixed: `create_box_parametric` was using root's plane. Coordinates for a body inside a component (e.g. `create_hole` centers) are now component-local.
- **PR 5: `join_on_holes`, `list_components` tree, `list_joints`, `get_bom` (#9, #10, #13).**
  - **join_on_holes:** the side is picked by `pick_join_sides` (pure, in `addon/server/assembly_math.py`) and was correct in 11/11 live joints. It falls back to re-adding the joint flipped when interference is above 0.
  - **list_components:** part numbers and sources appear once per component under `parts`, to keep the output short.
  - **get_bom:** reads motor/servo prefixes from `addon/server/part_classes.json`. The servo prefixes are unverified.
- **PR 6: `set_joint_value`, `get_timeline` (#11, #15).** Joint motion values reset on any recompute. `persist=true` writes `joint.angle`/`offset` instead. Collapsed timeline groups report their worst child's health.
- **Fixed during the merge:** `insert_part(parent=…)` on a fresh import. `importToTarget2` already returns a proxy, so it no longer calls `createForAssemblyContext` again.
- **Results:** 465 tests pass and ruff is clean. A smoke test of the merged code in Fusion passed (nested insert, join, set value, list_joints, BOM, tree, component sketch, timeline). Tool count is 103.

Commit status: merged and pushed on `feat/assembly-tools` (PR #1). Restart the add-in to run it.

### Next
- #14 document handling plus the S11 fix (execute_code fails if user code closes the active document). Test it on its own, since it switches documents.
- #17 pattern occurrences.
- #18 `check_robot_rules`, whole robot and one subsystem (requirements in the plan).
- Check `part_classes.json` servo prefixes.
- `list_joints` may not include a persisted `angle`/`offset`.
- Test `join_on_holes` on a real goBILDA channel STEP.
