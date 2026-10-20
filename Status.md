# Status

## Assembly tools (goal: build a full FTC robot without execute_code)

Plan with spike results: [docs/plans/assembly-tools.md](docs/plans/assembly-tools.md). Branch: `feat/assembly-tools`.

### PR 1: occurrence names + ground_occurrence (code done, not committed)

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

Still needed: restart the add-in in Fusion so the running code picks up the changes, then commit and open the PR.

Open item for PR 3: an origin-to-origin rigid joint gets created but doesn't move the part, even after computeAll. Spike 2's hole-face joint did move it. Check this when replacing origin joints with face geometry.

### Next: PR 2, `insert_part` + `move_occurrence`

Spike the placement options first (see plan #2 and #4).
