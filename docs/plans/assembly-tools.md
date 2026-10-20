# Plan: assembly tools (build a full FTC robot without execute_code)

Goal: Claude inserts COTS parts (goBILDA/REV STEP files) and custom parts, places them, and joins them at the right holes, all through MCP tools.

**Tier 0 is done when** Claude inserts a goBILDA channel and a plate and bolts them together at named holes using only MCP tools.

Work on branch `feat/assembly-tools`. Every tool follows the checklist in `.claude/CLAUDE.md`: handler → `tools.py` → `mock.py` → `tests/test_tools.py` + `tests/test_mock.py`, then the AGENTS.md catalog. Before writing each real handler, spike its Fusion calls through `execute_code` in a throwaway document (`app.documents.add(...)`, then `doc.close(False)`).

Legend: ✅ checked by a spike on 2026-10-19 (Fusion 2705.1.15) · ❓ still to spike · ❌ spike showed it doesn't work

---

## Spike results (2026-10-19)

All the API calls the plans below need exist in this build: `Occurrence.transform2/activate/isGrounded`, `Design.activeComponent/activateRootComponent/findEntityByToken`, `ImportManager.importToTarget2/createSTEPImportOptions/createFusionArchiveImportOptions`, `Occurrences.addExistingComponent`, `JointGeometry.createByPlanarFace/createByNonPlanarFace/createByCurve`, `JointInput.offset/angle/isFlipped`, `AsBuiltJointInput.setAsRevoluteJointMotion`, `RevoluteJointMotion.rotationValue/rotationLimits`, `SliderJointMotion.slideValue`, `Component.partNumber`, `TimelineObject.healthState/errorOrWarningMessage`.

What the spikes showed:

| # | Finding | Affects |
|---|---|---|
| S1 | `occ.activate()` works, and `design.activeComponent` follows it. Building through `comp.sketches` / `comp.features` puts features in that component. ✅ | #1 |
| S2 | STEP `importToTarget2(opts, root)` returns an `ObjectCollection` holding one `Occurrence` and takes about 0.3 s for a simple part. The component comes in named `"(Unsaved) (1)"`, and `partNumber` is a timestamp, so we must rename it. A STEP import adds a `Group1` timeline item. ✅ | #2 |
| S3 | `addExistingComponent(comp, matrix)` takes 4 ms and names the new occurrence `Part:2`. **Placing at insert time keeps the position** after `computeAll()`. ✅ | #2, #4 |
| S4 | ❌ **In a parametric design, `occ.transform2 = m` moves the part, but the move is lost.** Both `design.snapshots.add()` and `computeAll()` reset the transform to identity, and calling the snapshot in a separate main-thread tick didn't help. Grounding after the move also reverts. **In a direct design the move sticks.** `moveFeatures.createInput2` rejects occurrences ("invalid argument inputEntities"). | #4 |
| S5 | ❌ **`root.boundingBox` is stale or ignores occurrences.** It reported max x = 4 while the occurrence's body was at x = 20–24, even in a direct design. `occ.boundingBox` returned 0..0. Taking the union of the occurrence's **body proxy** bounding boxes (`occ.bRepBodies.item(i).boundingBox`) is correct. | #11, `_snapshot` deltas |
| S6 | A face reached through `occ.bRepBodies` is already a proxy in assembly coordinates. Cylinder `origin/axis/radius` come back in root space. `entityToken` round-trips through `findEntityByToken` and returns a proxy, **but it's 388 characters long**, which costs too many tokens to list per hole. A body index plus a face index is stable and short. ✅ | #5, #6 |
| S7 | A rigid joint built from `createByNonPlanarFace(holeFace, Start/EndKeyPoint)` on both sides snapped hole to hole. ✅ **The first occurrence is the one that moves.** Fusion refuses if it's grounded ("First component to move is grounded"). An origin-to-origin rigid joint was created but didn't move the part. ❓ Stacking direction. | #6, #9 |
| S8 | `rectangularPatternFeatures` **accepts occurrences.** Patterning an occurrence 3× made new occurrences `Part:3…`. ✅ | #16 |
| S9 | Fusion forces component names to be unique (the second `"Part"` became `"Part (1)"`). Today `create_component` returns the name that was *requested*, not the one Fusion actually used. | #3 |
| S10 | Timeline names for occurrence items have a leading space (`" Part:1"`). `healthState` is an int enum. | #15 |
| S12 | ✅ Re-insert (`addExistingComponent` at the target, then `deleteMe` the old one) lasts through computeAll in parametric designs, rotation included. It also works on an import's original occurrence, and the component survives. Cost: the occurrence is renumbered and two timeline items are added. ❌ `SnapshotCmd` executed from the API doesn't capture. | #2, #4 |
| S13 | Direct designs: `addExistingComponent(comp, m)` composes *m* with the first occurrence's transform, so `transform2 = m` is set afterwards. `isGrounded` raises on sub-component occurrences. | #2, #4 |
| S14 | ❌→✅ Joints between two copies of one component fail silently (timeline warning "conflicts with assembly relationships", nothing moves) because `isGroundToParent` defaults to True. Setting it False on both fixes it. Copies joined to a different component work regardless. Direct designs don't move parts for joints. | #6, #9 |
| S15 | ✅ Hole keypoints: start/end = the two circular edge centers, read exactly via `JointGeometry.origin`. Concave test (normal vs radial) separates holes from bosses. Mover `end` → fixed `start` stacks on the start side; `start` → `end` on the end side (zero interference in the live test). All 7 joint motions accept `setAs*JointMotion(ZAxis[, XAxis])`. As-built joints take `JointGeometry` for non-rigid types. | #5, #6, #7, #9 |
| S16 | Tier 0 acceptance passed (2026-10-20): real STEP plate + 3 bracket copies, rigid/rigid@90°/revolute+offset, zero interference after computeAll. `undo` doesn't remove a just-added joint within one execute call. | #9 |
| S11 | `execute_code` raises "refers to a deleted Object" when the user code closes the active document, because it reads `design.designType` after running the code. | #14 |
| S17 | ✅ (2026-10-20) A fillet on a proxy body works three ways: `root.features` + proxy edges, `comp.features` + proxy edges, `comp.features` + native edges. All three land in the body's component (Fusion re-parents the feature). A cross-component combine (root tool, component target, proxies, `root.features`) also lands in the target's component. `comp.features.baseFeatures` works in a non-active component; primitive coordinates are component-local. `comp.sketches.modelToSketchSpace` takes component coordinates. | #1 |

---

## Shared pieces (build these first, as part of #3)

Helpers in `command_handler.py`:

- **`_occurrence(name)`** accepts an occurrence name (`Channel:2`), a full path (`Drivetrain:1+Channel:2`), or a component name *if exactly one occurrence uses it*. When the name is ambiguous it raises `RuntimeError("'Channel' matches 4 occurrences: Channel:1, Channel:2, … — pass the occurrence name")` so Claude can correct itself in one step.
- **`_occ_info(occ)`** returns the compact dict every tool sends back for a part: `{"occurrence": occ.fullPathName, "component": occ.component.name}`.
- **Face/edge ref format: `"<occurrence path>/b<body>/f<face>"`**, for example `Channel:2/b0/f37`, and `.../e<edge>` for edges. `_resolve_ref(ref)` resolves it through `_occurrence(...).bRepBodies.item(b).faces.item(f)`, which already returns a proxy (S6). A ref stays valid as long as the part's geometry doesn't change, which holds for COTS parts. A ref for a root-level body is written `/b0/f3`.
- **`_bbox_union(bodies)`**: one helper for the body-proxy union (S5). `get_bounding_box`, `_snapshot` and `get_bom` all use it.
- Pure math goes in an adsk-free module (as `hole_geometry.py` does) so it can be unit tested: hole detection, choosing the keypoint, and building matrices from axis/angle.

---

## Tier 0: blockers

### #1 Model inside a component (`component` parameter)

**Decision:** stateless rather than `activate_component`. Add an optional `component` (occurrence name) to `create_sketch` and the primitives. Every feature tool then takes its component from its input: `sketch.parentComponent` or `body.nativeObject.parentComponent`. This adds no hidden state that can go stale between calls or sessions. (`activate_component` can come later if wanted; S1 shows it works.)

- **Handler changes**
  - `create_sketch(plane, z_offset, component=None)`: `comp = _occurrence(component).component if component else root`, and use `comp.xYConstructionPlane` and `comp.sketches`. Store the sketch: `self._last_sketch_obj = sketch`.
  - `_last_sketch()`: return `self._last_sketch_obj` if it is still valid (`isValid`). Otherwise fall back to the last sketch in `root`. Today it only looks in root, so a sketch made in a component would be missed.
  - `_sketch_by_name` searches `design.allComponents`.
  - `_construction_plane(plane, comp=None)` and `_construction_axis(axis, comp=None)` take the component.
  - `extrude`, `revolve`, `sweep`, `loft`, `create_hole`: replace `root.features` with `sketch.parentComponent.features`.
  - `fillet`, `chamfer`, `shell`, `mirror`, `split_*`, `offset_faces`, `draft_faces`, patterns: `comp = body.nativeObject.parentComponent if body.assemblyContext else root`, then pass native entities (body, edges and faces through `.nativeObject`). ✅ S17: both work; native was chosen so planes, axes and selections use the component's own coordinates.
  - `create_box`, `create_cylinder`, `create_sphere`, `create_torus` get `component=None`.
- **Return** `"component": comp.name` on create_sketch and on every feature tool.
- **Tests:** schema has `component`; the mock echoes it. Add an AST guard in `test_addon_api_usage.py` that `extrude` no longer references `root.features`.
- **Size:** M. It's mostly mechanical, but it touches about 25 handlers. Do it in one PR.

### #2 `insert_part(file_path, name?, parent?, transform?)`

- **Schema:** `file_path` (required; .step/.stp/.f3d), `name` (component name; default is the file stem), `parent` (occurrence, default root), `transform` (`{"translation":[x,y,z] cm, "axis":[x,y,z], "angle": deg}`).
- **Handler:**
  1. **Reuse:** look through `design.allComponents` for attribute `("fusion360mcp","source") == abspath(file_path)`. If found, call `parent.occurrences.addExistingComponent(comp, matrix)` and return. (Attributes save with the document, so reuse still works in a later session, unlike an in-memory cache.)
  2. **Import:** `opts = createSTEPImportOptions(path)` or `createFusionArchiveImportOptions(path)`, then `occ = importToTarget2(opts, parent_comp).item(0)` (S2). Set `comp.name = name`, `comp.partNumber = file stem` (goBILDA file names are SKUs), and `comp.attributes.add("fusion360mcp","source", path)`.
  3. **Placement:** a fresh import lands at identity, and setting `transform2` doesn't stick in parametric designs (S4). ❓ Spike: after importing, `addExistingComponent(comp, matrix)` at the target and then `occ.deleteMe()` the original. Check that the component and the `Group1` import body survive. If not, use the S4 fallback (see #4).
- **Returns:** `{occurrence, component, reused: bool, bodies, child_occurrences, bbox}`. Leave it out of `_MUTATION_COMMANDS` deltas, or keep it; check speed (see "Performance").
- **Errors:** file not found; unsupported extension; the hint suggests `import_mesh` for STL.
- ❓ Spike with a real goBILDA STEP (for example 1120-0001-0336 channel and a 5203 motor). Check the time per import, whether the result has nested occurrences, and whether units come in right.
- **Size:** M.

### #3 Tell identical parts apart (occurrence names everywhere)

- Add the helpers from "Shared pieces".
- **Lookup by occurrence:** `add_joint`, `create_as_built_joint`, `create_rigid_group`, `check_interference`, `get_bounding_box`, `import_mesh(component_name)`, `create_component(parent_name)`. Keep the existing parameter names, but resolve them through `_occurrence()`, which still accepts unique component names, so current callers keep working.
- **Return occurrence names:** `create_component` returns `{occurrence: occ.name, component: occ.component.name}`, the real names (S9). `list_components` is covered in #10. `check_interference` reports `occ.fullPathName` for each body (`entityOne.assemblyContext`).
- **Tests:** mock returns `occurrence`. Unit test the ambiguity error message (pure helper).
- **Size:** S.

### #4 `move_occurrence(occurrence, translation, axis?, angle?, mode="absolute"|"relative")`

- **Matrix:** `m = Matrix3D.create()`, `m.setToRotation(rad, Vector3D(axis), Point3D(0,0,0))`, `m.translation = …`. For relative moves, `m.transformBy(...)` onto `occ.transform2`.
- **Direct design:** `occ.transform2 = m` (✅ works).
- **Parametric design:** S4 shows `transform2` doesn't persist. Options, in the order to spike them:
  1. ❓ The UI command `SnapshotCmd` (`ui.commandDefinitions.itemById("SnapshotCmd").execute()`) after setting `transform2`. That's the "Capture Position" button.
  2. ❓ Re-insert: `addExistingComponent(comp, m)`, move the children's names across, then `occ.deleteMe()`. Only allowed when the occurrence has no joints, so check `occ.joints.count == 0`.
  3. Otherwise set `transform2`, return `"persisted": false` with a hint: "position is temporary in parametric designs; ground it or join it". Joints place parts anyway, so for a robot this is mostly for initial placement before a joint.
- **Returns:** `{occurrence, transform: {translation, axis, angle}, persisted}`.
- **Size:** S to M, depending on how the spike goes.

### #5 `find_holes(occurrence, diameter?, tolerance=0.01, near?, limit=50)` + `list_faces(occurrence, type="planar"|"cylindrical"|"all", limit=50)`

- **find_holes:** for every body proxy and every face where `geometry.surfaceType == CylinderSurfaceType`, **keep only concave faces**. A hole's surface normal points toward its axis, while a boss or rounded edge points away. Test this with `face.evaluator.getNormalAtPoint(face.pointOnFace)` against the vector from the axis. Put the check in a pure helper with a unit test.
- Get the hole's axis span from the cylinder edges' circle centers (the two keypoints). Report `start` and `end` points in assembly space, so Claude can see which side is which.
- **Row format (compact):** `{"ref":"Channel:2/b0/f37","d":0.4,"start":[x,y,z],"end":[x,y,z],"axis":[0,0,1]}`, rounded to 4 decimals. With no filter, group by diameter in the summary: `{"by_diameter":{"0.4":112,"1.4":6}}`. Filters keep a goBILDA channel (more than 100 holes) from flooding the context: `near` sorts by distance to a point and `limit` caps the count.
- **list_faces:** for planar faces `{ref, normal, center, area}`, and for cylindrical faces the same as a hole plus `concave`.
- **Read-only + idempotent annotations.**
- **Size:** M. The concave test is the hard part.

### #6 Real joint geometry in `add_joint`

- **New schema:** `one` and `two` are each `{"occurrence"?, "ref": "Channel:2/b0/f37", "keypoint": "center"|"start"|"end"|"middle"}`, plus `joint_type`, `offset` (cm), `angle` (deg), `flip` (bool). If a side has only `occurrence` and no ref, fall back to the origin point (today's behavior).
- **Geometry from the ref type:**
  - planar face → `createByPlanarFace(face, None, keypoint)`
  - cylindrical/conical face → `createByNonPlanarFace(face, keypoint)` (✅ S7)
  - edge → `createByCurve(edge, keypoint)`
- **Joint motion:** `rigid` → `setAsRigidJointMotion()`. `revolute` → `setAsRevoluteJointMotion(JointDirections.ZAxisJointDirection)`, where Z is the hole axis. `slider` → `setAsSliderJointMotion(...)`, and so on. Set `inp.offset = ValueInput.createByReal(offset)`, `inp.angle = createByString(f"{angle} deg")` and `inp.isFlipped = flip`.
- **Returns:** `{joint: j.name, joint_type, moved: occurrence name, gap/overlap check}`. ❓ Spike S7 again with one part grounded to learn which side moves.
- **Size:** M.

### #7 Bug: `create_as_built_joint` ignores `joint_type`

- **Fix rather than remove.** Add an optional `geometry` ref with the same `{ref, keypoint}` shape as in #6. `inp = as_built.createInput(occ1, occ2, geo)`, where geometry is required for anything except rigid (raise a clear error if it's missing). Then call the matching `inp.setAs<Type>JointMotion(direction)`. `AsBuiltJointInput.setAsRevoluteJointMotion` exists ✅.
- **Tests:** an AST guard that `create_as_built_joint` calls `setAs*JointMotion`.
- **Size:** S.

---

## Tier 1: needed for a whole robot

### #9 `join_on_holes(occ_a, hole_a, occ_b, hole_b, rotation=0, joint_type="rigid", flip=False)`

The main FTC helper. It's #6 with good defaults.

- `hole_a` and `hole_b` are refs from `find_holes`. It builds a joint using `createByNonPlanarFace` on both holes.
- **Choosing the end:** use the end of hole A that lies on A's *outer* planar face nearest to B, and the same for B. ❓ Spike. If the heuristic is unreliable, fall back to this: build the joint, run `analyzeInterference` on just those two occurrences, and if the overlap volume is above 0, set `isFlipped` and try again. Report `"auto_flipped": true`.
- `rotation` → `inp.angle` (turns a channel around the bolt axis). On hole grids Claude usually needs 0/90/180.
- **Returns:** `{joint, moved, auto_flipped, interference_volume}`.
- **Size:** M (after #5 and #6).

### #10 Assembly tree in `list_components` + `list_joints`

- **`list_components(depth=None)`:** walk `root.occurrences` recursively. Each node is `{occurrence, component, part_number, source?, grounded, visible, translation, children:[…]}`. Report the translation only (rotation as axis/angle only when it isn't identity) to save tokens. Bump the response shape. The mock and test change.
- **`list_joints()`:** `root.allJoints` + `root.allAsBuiltJoints` → `{name, type, one: occ path, two: occ path, value (deg or cm), limits, suppressed, health}`.
- **Size:** S.

### #11 `set_joint_value(joint, value, limits?)`

- Find it with `root.allJoints` and `allAsBuiltJoints` by name. `m = joint.jointMotion`. For revolute, `m.rotationValue = radians(value)`. For slider, `m.slideValue = value` cm. For cylindrical or pin-slot, pass two values.
- **`limits`:** `{"min","max","rest"}` → `m.rotationLimits.isMinimumValueEnabled=True; minimumValue=…`.
- ❓ Spike: does a joint value persist after `computeAll()` in a parametric design? It might revert the same way S4 does. For "show stowed vs extended" plus a size check, a temporary value is enough. Report `persisted`.
- **Size:** S.

### #12 Whole-robot bounding box

- **Confirmed broken in spirit:** `root.boundingBox` can't be trusted (S5). Also `_snapshot` (the deltas on every mutation) uses `root.boundingBox`, so its deltas are wrong for assemblies.
- **Fix:** add `_bbox_union` over `root.bRepBodies` + every `occ.bRepBodies` proxy. Use it in `get_bounding_box` when the name is the root, a component or an occurrence. For an occurrence name, union that occurrence's subtree only (`occ.bRepBodies` + `occ.allOccurrences`?). ❓ Check whether `occ.childOccurrences` bodies come back as root-space proxies.
- **Add `get_bounding_box(name="root")`.** It also returns `size_in` (inches), since FTC size limits are in inches.
- **Size:** S.

### #13 `get_bom()`

- Group `root.allOccurrences` by `occ.component` (the same object means the same part). For each group: `{component, part_number, count, mass_g, occurrences:[…] (only if count ≤ 5)}`. Compute mass **once per unique component** with `comp.getPhysicalProperties(Low)` to keep it fast. Add `total_mass_g`, `motor_count` and `servo_count` by matching part-number prefixes from a small table (goBILDA 5202/5203/5204 = motors, 2000-0025 = servo, REV HD Hex REV-41-1291, and so on). Keep that table in the knowledge base or a JSON file, not hard-coded in the handler.
- Skip components with no bodies (pure assembly groupings).
- **Size:** S.

### #14 Document handling: `list_documents`, `new_document`, `open_document`, `save_document`, `activate_document`, `close_document`

- `new_document(name?)`: `app.documents.add(FusionDesignDocumentType)`; set parametric.
- `open_document(name | file_path)`: for a cloud file, search `app.data.activeProject.rootFolder` (recursively, with a depth cap) for a `DataFile` by name, then `app.documents.open(dataFile)`. For a local `.f3d`, `importManager.importToNewDocument(createFusionArchiveImportOptions(path))`.
- `save_document(name?, folder?)`: if `doc.isSaved`, call `doc.save("mcp")`. Otherwise call `doc.saveAs(name, folder_obj, "", "")` with the folder resolved from a path such as `"FTC/2026"` under the active project (create it if missing). Saving to the cloud is outward-facing, so the description has to say so.
- `list_documents`: `[{name, saved, modified, active}]`. 12 documents were open during the spikes, so Claude needs this to stay oriented.
- **Infra:** leave these **out of** `_MUTATION_COMMANDS`, because a snapshot taken across a document switch is meaningless. Fix S11: in `execute_code`, wrap the code that runs after the user's code in `if design.isValid`.
- **Size:** M (cloud folder lookup).

### #15 `get_timeline(offset=0, limit=100, errors_only=False)`

- `design.timeline`: `{i, name: name.strip(), type: entity.objectType short name, suppressed, health: {0:"healthy",1:"warning",2:"error",…}, message: errorOrWarningMessage if health}`. Also return `count` and `marker_position`. Groups appear as a single row with `children` only when expanded. Keep it compact.
- **Read-only.** Size: S.

### #16 `ground_occurrence(occurrence, grounded=True)`

- `occ.isGrounded = grounded` (creates a `Pin1` timeline item ✅). Returns `{occurrence, grounded}`. **Size:** XS. Bundle it with #3.

---

## Tier 2: nice to have

### #17 Pattern occurrences

- ✅ S8: `rectangularPatternFeatures` accepts occurrences. Change `rectangular_pattern` and `circular_pattern` to accept `occurrence` as an alternative to `body_name`. Add a `direction` that takes `x|y|z` **or an edge ref** (along a channel's edge) and `circular_pattern(axis=ref)`. Return the new occurrence names by diffing `root.allOccurrences` before and after.
- **Size:** S.

### #18 `check_robot_rules`

- Lives on the knowledge-base side once #12 and #13 exist. `constraints.json` holds each season's values (starting size cube in inches, motor and servo limits). Don't hard-code the numbers, because they change by season. It calls `get_bounding_box("root")` and `get_bom()` and compares. It can be a prompt or resource in `server.py` rather than an add-in handler, since it needs no new Fusion calls.
- **Size:** S.

---

## Performance (CLAUDE.md: "keep it fast")

`_snapshot()` runs before and after **every** mutation and calls `occ.physicalProperties` for each occurrence. On a robot with 200+ occurrences this could add hundreds of ms per call. ❓ Measure it once there's a real robot. Fix: compute the mass per unique component and multiply by the count (the same grouping as `get_bom`), or skip mass above N occurrences.

## Build order

1. **PR 1:** #3 + #16 + shared helpers (the base everything else needs).
2. **PR 2:** #2 + #4 (spike the placement options first).
3. **PR 3:** #5 + #6 + #7, then the Tier 0 acceptance test: channel + plate joined at named holes.
4. **PR 4:** #1 (separate, because it touches about 25 handlers).
5. **PR 5:** #9 + #10 + #12 + #13 (the robot-scale tools).
6. **PR 6:** #11 + #14 + #15, then #17.

#1 comes after the joint work because the Tier 0 acceptance test uses COTS parts only. Custom parts can be built in root and then moved into a component later, if needed.
