# Status

**Version 1 goal, first-robot test and parallel lanes: [docs/plans/v1.md](docs/plans/v1.md).** **Fusion: Lane A (live tests of #14 documents + #18 check_robot_rules; Lane C paused and agreed). Lane C waits until A releases it.** Onshape calls: Lane C only.

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

## Knowledge base (goal: searchable past robots, mechanisms, ideas, parts and rules for designing FTC robots)

Plan with spike results: [docs/plans/knowledge-base.md](docs/plans/knowledge-base.md). Ingest brief: [docs/plans/robot-ingest-brief.md](docs/plans/robot-ingest-brief.md). Files only (docs/plans/, kb/, scripts/kb/), not committed; they don't depend on the assembly-tools changes.

Done:
- 2026-10-19: manual TU05 + `constraints.json`, spikes K1–K11, review page (private artifact https://claude.ai/artifact/PDXC2H15BL6hTJwngfY6e2) with the first robot approved. Manual split per rule (`scripts/kb/split_manual.py`).
- 2026-10-20, **ingest pilot**: `scripts/kb/build_queue.py` → `kb/ingest/queue.csv` (248 rows: 225 Onshape, 23 non-Onshape skipped). `scripts/kb/onshape_fetch.py` (fetch / tree / parts / render, logs to `kb/ingest/api_calls.csv`, run budget + yearly stop), `scripts/kb/ftcscout.py` (rating), `scripts/kb/queue_status.py`. **10 drafts written to the review page** (status `pending`): 3 BIOBUZZ (18365 robot + drivetrain) and 7 DECODE robots (18365 ×2, 13581, 4410, 23849 ×2, 23511, 25070). 7 entries failed with 403 (documents not public). 69 Onshape calls used (85 this year).

- 2026-10-20, **search code** on branch `feat/kb-search` (worktree `.worktrees/kb-search`, not committed): `src/fusion360_mcp/kb.py` indexes `kb/` into SQLite FTS5 at `kb/.index.sqlite`, rebuilt when a file or `INDEX_VERSION` changes. `kb_tools.py` adds `kb_search` + `kb_get`, handled inside the server (not in `tools.py`, no mock). `tests/test_kb.py` (21 tests, 388 total pass). Checked end to end over MCP stdio on the 149 manual files. Card frontmatter format for the export step is now fixed in the plan (one line per key, JSON for structured values).

- 2026-10-20, **export**: `scripts/kb/export_approved.py` writes approved review-page robots into `kb/robots/<id>/` (robot card + one card per mechanism + ~800 px JPEG renders) and `kb/ideas.csv` (deduplicated, `seen_in`). 7 robots, 34 mechanisms, 24 ideas exported and searchable. Review page v2 adds a per-mechanism Rating (bias). Search fixes committed on `feat/kb-search`.
- Review round 1 handled: 18365 25-26 Decode re-drafted per the note (drivetrain removed, biases set) and back to pending. Droid Force DECODE V2: the user said to drop that note (it was meant for another chat).

- 2026-10-20: `feat/kb-search` merged into local `main` (fast-forward to 4997f04). Not pushed to GitHub.

- 2026-10-20: `kb_feedback` tool on `feat/kb-search` (not yet in `main`): the user's verdicts on designs built from KB entries move those entries' rank (±0.1 each, 0.7–1.3×), stored in `kb/feedback.csv`.

- 2026-10-20, **Lane E done** (gm0): `feat/kb-gm0` @ ee6b6a7, not merged. `scripts/kb/ingest_gm0.py` (sparse clone of gm0 c81f4c44dc85 into gitignored `.cache/gm0`) → `kb/books/gm0/`: 182 sections (~43k words) from common-mechanisms, hardware-components, power-and-electronics, plus 104 ideas in `kb/books/gm0/ideas.csv`. Re-runs only rewrite changed pages. Follow-ups: ideas lack a link to their source section (needs an optional `ref` column), and some formulas keep `frac{...}`.

- 2026-10-20, **Lane F done** (subsystem workflow): `feat/kb-session` @ 5037144, not merged, 420 tests. New `kb_design.py`; tools `robot_design` (get/create/update_subsystem/add_note/resolve_note on `kb/designs/<robot>/design.md`, enforces ≤8/≤8 and the cube/R105 boxes) and `kb_save_design` (accepted subsystems → `kb/robots/ours-<robot>/`); resources kb://design-rules, kb://lessons, kb://constraints; prompts `work_on_subsystem`, `build_whole_robot`. Drafts `kb/design_rules.md` (all numbers unverified, 10 questions for the team) and `kb/lessons.md`. Plan updated: robot kickoff step assigns envelopes and actuator budgets up front.

- 2026-10-20, **Lane D done** (goBILDA parts): `feat/kb-parts` @ 2be4790, not merged, 440 tests. `scripts/kb/scrape_gobilda.py` (product JSON from 383 category pages, 10 s delay per robots.txt, cache gitignored) → `kb/parts/parts.csv`: 1,698 parts, 1,407 with STEP links, counts_as 43 motors / 52 servos. `kb_find_part` (exact filters + name; `download: true` → `~/.fusion-mcp/step-cache/<sku>.step`). BOM name → SKU matching resolves 778/832 goBILDA-style names (2 known wrong matches; 34 discontinued SKUs return nothing). Open: confirm Shark/Stingray servo gearboxes count as servos; join get_bom with counts_as (part_classes.json stays as fallback).

- 2026-10-20, **KB merged into local `main` (26adb4f)**: feat/kb-search + kb-gm0 + kb-session + kb-parts, plus the KB data (manual, 8 robots, ideas, ingest queue/api_calls/render_urls, scripts, plans). 463 tests; live MCP check of all 6 KB tools, 3 resources and 2 prompts passed. Not pushed to GitHub. The main checkout still has untracked copies of these files; 5e will merge main into feat/assembly-tools with a backup/restore step (instructions sent).

Next for the KB: the user's 10 design-rule answers; more robot reviews (40 approved needed for v1); small glue (get_bom → counts_as; gm0 idea → section link).

- 2026-10-20, **pilot review done**: 7 approved (18365 BIOBUZZ V1 + drivetrain, 13581, 4410, 23849 V2, 23511, 25070), 3 rejected (23849 V1, 18365 DECODE, 18365 Chain Reaction). 18365 BIOBUZZ V1 and Droid Force V2 were re-split with per-mechanism renders from STEP → Fusion (`onshape_fetch.py step`, `scripts/kb/fusion_render.py`). Split rules from the review are in the brief. 135 Onshape calls used in the run (151 this year).

- 2026-10-20, **export done**: 8 approved robots (incl. the Drizzy example) → `kb/robots/` (39 mechanism cards, 4 MB of JPEG renders) and `kb/ideas.csv` (32 ideas), via `scripts/kb/export_approved.py` (the other session's tested script). Renders come from each `kb/ingest/drafts/<id>/draft.json` `render_file`. kb_search on feat/kb-search finds them.

- 2026-10-20, **batch 2 paused** (user asked to stop): run budget 400, 230 calls used (381 this year). 26 robots fetched (31 failed on 403/404, 1 skipped as a field CAD). **16 drafts on the review page.** STEP + Fusion renders are done but not drafted for ORACLE 18603 (`fus-*.png` in its drafts folder) and 4410 ITD V2 (`fus-*.png`). Still to split from their STEP files: Caesar 24331, Clip Bot, NOVA, LSCC 2023, Centerstage 16460 v2, ITD 16460, leagues bot, 8404 ITD. Draft generators: scratchpad make_drafts2.py and make_drafts3.py (not in the repo). Render helper: `scripts/kb/fusion_render.py` (one mechanism per execute_code call keeps each under the 30 s timeout).

Next: Better splits and renders for 4410 and 25070 exist locally but weren't written (both were approved first). Then run batches of ~25 with the new split rules: `queue_status.py next 25`.
