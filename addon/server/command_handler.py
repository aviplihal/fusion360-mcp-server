"""
Fusion360 Command Handler

Executes commands using the Fusion 360 API.  Every method in this class
is called on the **main thread** (via EventBridge), so Fusion API access
is safe.
"""

import ast
import base64
import io
import math
import os
import tempfile
import time
import traceback
from contextlib import redirect_stdout

import adsk.cam
import adsk.core
import adsk.fusion

from . import assembly_math as _asm
from . import get_logger
from . import hints as _hints
from . import hole_geometry as _hole_geom
from . import joint_values as _joint_vals
from . import occurrence_refs as _occ_refs
from . import parameter_units as _param_units
from . import robot_rules as _rules
from . import timeline_rows as _tl_rows

log = get_logger("handler")


class CommandHandler:
    """Runs Fusion API operations.  Instantiated once; reused across requests."""

    def __init__(self):
        self.app = adsk.core.Application.get()
        self.ui = self.app.userInterface
        # Sketch from the last create_sketch; may live in a sub-component.
        self._last_sketch_obj = None

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    _COMMANDS = None  # populated lazily

    # Canonical camera presets, (eye_dir, up_vec) in Fusion's Z-up world.
    # Shared by render_view and export_view_sheet.
    _VIEW_DIRS = {
        "iso": ((1.0, -1.0, 1.0), (0.0, 0.0, 1.0)),
        "iso_ne": ((1.0, 1.0, 1.0), (0.0, 0.0, 1.0)),
        "iso_nw": ((-1.0, 1.0, 1.0), (0.0, 0.0, 1.0)),
        "iso_sw": ((-1.0, -1.0, 1.0), (0.0, 0.0, 1.0)),
        "front": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
        "back": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        "top": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
        "bottom": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
        "right": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        "left": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    }

    # Commands that can change body mass / bbox / body count.  Only these
    # get before/after snapshots so agents can sanity-check without a render.
    _MUTATION_COMMANDS = frozenset(
        {
            # feature ops
            "extrude",
            "revolve",
            "sweep",
            "loft",
            "fillet",
            "chamfer",
            "shell",
            "mirror",
            "create_hole",
            "rectangular_pattern",
            "circular_pattern",
            "create_thread",
            "draft_faces",
            "split_body",
            "split_face",
            "offset_faces",
            "scale_body",
            "suppress_feature",
            "unsuppress_feature",
            # body ops
            "move_body",
            "boolean_operation",
            # primitives
            "create_box",
            "create_cylinder",
            "create_sphere",
            "create_torus",
            # assembly placement
            "insert_part",
            "move_occurrence",
            "set_joint_value",
            # surface / sheet metal (can produce / thicken bodies)
            "thicken_surface",
            "patch_surface",
            "stitch_surfaces",
            "ruled_surface",
            "trim_surface",
            "create_flange",
            "create_bend",
            "flat_pattern",
            "unfold",
            # scene-wide
            "delete_all",
            "undo",
            # parametric & agent-authored changes
            "set_parameter",
            "execute_code",
            # sketch constraint mutation
            "auto_constrain",
            # construction geometry / appearance
            "create_ucs",
            "set_color",
        }
    )

    def execute_command(self, command: dict) -> dict:
        """Route *command* to the correct handler; return a response dict."""
        if self._COMMANDS is None:
            self.__class__._COMMANDS = {
                # scene / query
                "get_scene_info": self.get_scene_info,
                "get_object_info": self.get_object_info,
                "get_bounding_box": self.get_bounding_box,
                "list_components": self.list_components,
                # sketch
                "create_sketch": self.create_sketch,
                "draw_rectangle": self.draw_rectangle,
                "draw_circle": self.draw_circle,
                "draw_line": self.draw_line,
                "draw_arc": self.draw_arc,
                "draw_spline": self.draw_spline,
                "create_polygon": self.create_polygon,
                "add_constraint": self.add_constraint,
                "auto_constrain": self.auto_constrain,
                "add_dimension": self.add_dimension,
                "offset_curve": self.offset_curve,
                "trim_curve": self.trim_curve,
                "extend_curve": self.extend_curve,
                "project_geometry": self.project_geometry,
                # features
                "extrude": self.extrude,
                "revolve": self.revolve,
                "sweep": self.sweep,
                "loft": self.loft,
                "fillet": self.fillet,
                "chamfer": self.chamfer,
                "shell": self.shell,
                "mirror": self.mirror,
                "create_hole": self.create_hole,
                "rectangular_pattern": self.rectangular_pattern,
                "circular_pattern": self.circular_pattern,
                "create_thread": self.create_thread,
                "draft_faces": self.draft_faces,
                "split_body": self.split_body,
                "split_face": self.split_face,
                "offset_faces": self.offset_faces,
                "scale_body": self.scale_body,
                "suppress_feature": self.suppress_feature,
                "unsuppress_feature": self.unsuppress_feature,
                # body operations
                "move_body": self.move_body,
                "rename_body": self.rename_body,
                "export_stl": self.export_stl,
                "export_step": self.export_step,
                "export_f3d": self.export_f3d,
                "export_view_sheet": self.export_view_sheet,
                "export": self.export,
                "import_mesh": self.import_mesh,
                "create_box_parametric": self.create_box_parametric,
                "boolean_operation": self.boolean_operation,
                "delete_all": self.delete_all,
                "undo": self.undo,
                # direct primitives
                "create_box": self.create_box,
                "create_cylinder": self.create_cylinder,
                "create_sphere": self.create_sphere,
                "create_torus": self.create_torus,
                # construction geometry
                "create_construction_plane": self.create_construction_plane,
                "create_construction_axis": self.create_construction_axis,
                "create_ucs": self.create_ucs,
                # assembly
                "create_component": self.create_component,
                "add_joint": self.add_joint,
                "create_as_built_joint": self.create_as_built_joint,
                "create_rigid_group": self.create_rigid_group,
                "ground_occurrence": self.ground_occurrence,
                "find_holes": self.find_holes,
                "list_faces": self.list_faces,
                "move_occurrence": self.move_occurrence,
                "insert_part": self.insert_part,
                "join_on_holes": self.join_on_holes,
                "list_joints": self.list_joints,
                "get_bom": self.get_bom,
                "check_robot_rules": self.check_robot_rules,
                # documents
                "list_documents": self.list_documents,
                "new_document": self.new_document,
                "open_document": self.open_document,
                "activate_document": self.activate_document,
                "save_document": self.save_document,
                "close_document": self.close_document,
                "set_joint_value": self.set_joint_value,
                "get_timeline": self.get_timeline,
                # inspection / analysis
                "measure_distance": self.measure_distance,
                "measure_angle": self.measure_angle,
                "get_physical_properties": self.get_physical_properties,
                "create_section_analysis": self.create_section_analysis,
                "check_interference": self.check_interference,
                "compare_meshes": self.compare_meshes,
                # appearance
                "set_appearance": self.set_appearance,
                "set_color": self.set_color,
                # parameters
                "get_parameters": self.get_parameters,
                "create_parameter": self.create_parameter,
                "set_parameter": self.set_parameter,
                "delete_parameter": self.delete_parameter,
                # surface operations
                "patch_surface": self.patch_surface,
                "stitch_surfaces": self.stitch_surfaces,
                "thicken_surface": self.thicken_surface,
                "ruled_surface": self.ruled_surface,
                "trim_surface": self.trim_surface,
                # sheet metal
                "create_flange": self.create_flange,
                "create_bend": self.create_bend,
                "flat_pattern": self.flat_pattern,
                "unfold": self.unfold,
                # code execution
                "execute_code": self.execute_code,
                # CAM
                "cam_list_setups": self.cam_list_setups,
                "cam_list_operations": self.cam_list_operations,
                "cam_get_operation_info": self.cam_get_operation_info,
                "cam_create_setup": self.cam_create_setup,
                "cam_create_operation": self.cam_create_operation,
                "cam_generate_toolpath": self.cam_generate_toolpath,
                "cam_post_process": self.cam_post_process,
                # health
                "ping": self.ping,
                # design type safety
                "get_design_type": self.get_design_type,
                "set_design_type": self.set_design_type,
                # perception
                "render_view": self.render_view,
            }

        cmd_type = command.get("type")
        params = command.get("params", {})

        handler = self._COMMANDS.get(cmd_type)
        if handler is None:
            # Infrastructure-level failure (not an application error) —
            # keep the legacy error envelope so the client raises.
            return {
                "status": "error",
                "error_kind": "UNKNOWN_COMMAND",
                "message": f"Unknown command: {cmd_type}",
            }

        is_mutation = cmd_type in self._MUTATION_COMMANDS
        snap_before = self._snapshot() if is_mutation else None

        try:
            t0 = time.monotonic()
            result = handler(**params)
            elapsed = time.monotonic() - t0
            log.debug("%s completed in %.3fs", cmd_type, elapsed)
        except Exception as exc:
            log.error("%s raised: %s", cmd_type, exc)
            error_kind, hint_list = _hints.classify(exc)
            return {
                "status": "success",
                "result": {
                    "ok": False,
                    "error_kind": error_kind,
                    "error_message": str(exc) or exc.__class__.__name__,
                    "hints": hint_list,
                    "traceback": traceback.format_exc(),
                },
            }

        if not isinstance(result, dict):
            result = {"value": result}
        result.setdefault("ok", True)

        # Deltas across a document switch compare two different designs.
        if (
            is_mutation
            and snap_before is not None
            and not result.get("document_changed")
        ):
            snap_after = self._snapshot()
            if snap_after is not None:
                result["deltas"] = self._compute_deltas(snap_before, snap_after)

        return {"status": "success", "result": result}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _design(self):
        """The active document's Design product.

        Prefer the explicit DesignProductType lookup: when the Manufacture
        (or another) workspace is active, ``app.activeProduct`` returns the
        CAM product instead of the design, which breaks every handler that
        assumes a fusion.Design.
        """
        doc = self.app.activeDocument
        if doc is not None:
            try:
                design = doc.products.itemByProductType("DesignProductType")
                if design is not None:
                    return design
            except Exception:
                pass
        d = self.app.activeProduct
        if d is None or not hasattr(d, "rootComponent"):
            raise RuntimeError("No active design")
        return d

    def _root(self):
        return self._design().rootComponent

    def _last_sketch(self):
        """The sketch from the last create_sketch while it is still valid in
        the active design; otherwise the last sketch in root."""
        design = self._design()
        s = self._last_sketch_obj
        if s is not None and s.isValid and s.parentComponent.parentDesign == design:
            return s
        root = design.rootComponent
        if root.sketches.count == 0:
            raise RuntimeError("No sketch available — create one first")
        return root.sketches.item(root.sketches.count - 1)

    def _sketch_by_name(self, name: str):
        """Sketch by name in root first, then in every other component."""
        design = self._design()
        for comp in [design.rootComponent, *design.allComponents]:
            s = comp.sketches.itemByName(name)
            if s is not None:
                return s
        raise RuntimeError(f"Sketch '{name}' not found")

    def _target_component(self, component: str = None):
        """Component to build in: the one behind occurrence *component*, or root."""
        return self._occurrence(component).component if component else self._root()

    @staticmethod
    def _native(body):
        """(native body, its component). A body inside a component comes back
        from _body_by_name as an assembly proxy; features on it are built in
        its own component from native entities, in component coordinates."""
        if body.assemblyContext:
            body = body.nativeObject
        return body, body.parentComponent

    def _body_by_name(self, name: str):
        root = self._root()
        # Search root bodies first
        for i in range(root.bRepBodies.count):
            b = root.bRepBodies.item(i)
            if b.name == name:
                return b
        # Search bodies inside components via occurrence proxies (assembly design)
        # Returns proxy body in root coordinate space for correct boolean ops
        for occ in root.allOccurrences:
            for i in range(occ.bRepBodies.count):
                b = occ.bRepBodies.item(i)
                if b.name == name:
                    return b
        raise RuntimeError(f"Body '{name}' not found")

    def _component_by_name(self, name: str):
        """Component by component name (unique in Fusion) or occurrence name."""
        design = self._design()
        if design.rootComponent.name == name:
            return design.rootComponent
        for comp in design.allComponents:
            if comp.name == name:
                return comp
        try:
            return self._occurrence(name).component
        except RuntimeError:
            raise RuntimeError(f"Component '{name}' not found") from None

    def _occurrence(self, name: str):
        """Occurrence (root-context proxy) by path, occurrence or component name.

        Raises with the candidate list when a component name is shared by
        several occurrences (four copies of the same channel).
        """
        occs = list(self._root().allOccurrences)
        rows = [(o.fullPathName, o.component.name) for o in occs]
        return occs[_occ_refs.pick_occurrence(name, rows)]

    @staticmethod
    def _occ_info(occ) -> dict:
        return {"occurrence": occ.fullPathName, "component": occ.component.name}

    def _resolve_ref(self, ref: str):
        """Face or edge (root-context proxy) for a ref like 'Channel:2/b0/f37'."""
        occ_path, body_i, kind, idx = _occ_refs.parse_ref(ref)
        bodies = (
            self._occurrence(occ_path).bRepBodies
            if occ_path
            else self._root().bRepBodies
        )
        if body_i >= bodies.count:
            raise RuntimeError(f"Ref '{ref}': body index {body_i} out of range")
        body = bodies.item(body_i)
        items = body.faces if kind == "face" else body.edges
        if idx >= items.count:
            raise RuntimeError(f"Ref '{ref}': {kind} index {idx} out of range")
        return items.item(idx)

    @staticmethod
    def _bbox_union(bodies):
        """(min, max) over *bodies*, or None. Use body proxies for assembly
        coordinates — Component.boundingBox is stale for moved occurrences."""
        boxes = []
        for b in bodies:
            bb = b.boundingBox
            boxes.append(
                (
                    [bb.minPoint.x, bb.minPoint.y, bb.minPoint.z],
                    [bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z],
                )
            )
        return _occ_refs.union_bbox(boxes)

    def _all_bodies(self, occ=None):
        """Body proxies in root coordinates: the whole design, or *occ* and
        everything nested under it."""
        root = self._root()
        if occ is None:
            bodies = list(root.bRepBodies)
            prefix = None
        else:
            bodies = list(occ.bRepBodies)
            prefix = occ.fullPathName + "+"
        for o in root.allOccurrences:
            if prefix is None or o.fullPathName.startswith(prefix):
                bodies.extend(o.bRepBodies)
        return bodies

    def _construction_plane(self, plane: str, comp=None):
        comp = comp or self._root()
        m = {
            "xy": comp.xYConstructionPlane,
            "yz": comp.yZConstructionPlane,
            "xz": comp.xZConstructionPlane,
        }
        p = m.get(plane)
        if p is None:
            raise RuntimeError(f"Unknown plane '{plane}' — use xy, yz, or xz")
        return p

    def _construction_axis(self, axis: str, comp=None):
        comp = comp or self._root()
        m = {
            "x": comp.xConstructionAxis,
            "y": comp.yConstructionAxis,
            "z": comp.zConstructionAxis,
        }
        a = m.get(axis)
        if a is None:
            raise RuntimeError(f"Unknown axis '{axis}' — use x, y, or z")
        return a

    @staticmethod
    def _operation_type(name: str):
        m = {
            "new_body": adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
            "join": adsk.fusion.FeatureOperations.JoinFeatureOperation,
            "cut": adsk.fusion.FeatureOperations.CutFeatureOperation,
            "intersect": adsk.fusion.FeatureOperations.IntersectFeatureOperation,
        }
        t = m.get(name)
        if t is None:
            raise RuntimeError(
                f"Unknown operation '{name}' — use new_body/join/cut/intersect"
            )
        return t

    def _select_edges(self, body, selection: str):
        """Return an ObjectCollection of edges based on *selection*."""
        coll = adsk.core.ObjectCollection.create()
        bbox = body.boundingBox

        if selection == "all":
            for edge in body.edges:
                coll.add(edge)
        elif selection == "top":
            threshold = bbox.maxPoint.z - 0.001
            for edge in body.edges:
                mid = edge.pointOnEdge
                if mid.z > threshold:
                    coll.add(edge)
        elif selection == "bottom":
            threshold = bbox.minPoint.z + 0.001
            for edge in body.edges:
                mid = edge.pointOnEdge
                if mid.z < threshold:
                    coll.add(edge)
        elif selection == "vertical":
            for edge in body.edges:
                sp = edge.startVertex.geometry
                ep = edge.endVertex.geometry
                if abs(sp.x - ep.x) < 0.001 and abs(sp.y - ep.y) < 0.001:
                    coll.add(edge)
        else:
            raise RuntimeError(
                f"Unknown edge_selection '{selection}' — use all/top/bottom/vertical"
            )

        if coll.count == 0:
            raise RuntimeError(f"No edges matched selection '{selection}'")
        return coll

    def _select_faces(self, body, selection: str):
        """Return an ObjectCollection of faces based on *selection*."""
        coll = adsk.core.ObjectCollection.create()
        bbox = body.boundingBox

        if selection == "all":
            for face in body.faces:
                coll.add(face)
        elif selection == "top":
            threshold = bbox.maxPoint.z - 0.001
            for face in body.faces:
                if face.boundingBox.maxPoint.z > threshold:
                    coll.add(face)
        elif selection == "bottom":
            threshold = bbox.minPoint.z + 0.001
            for face in body.faces:
                if face.boundingBox.minPoint.z < threshold:
                    coll.add(face)
        elif selection == "vertical":
            for face in body.faces:
                # Check if face normal is roughly horizontal (vertical face)
                try:
                    _, normal_vec = face.evaluator.getNormalAtPoint(face.pointOnFace)
                    if abs(normal_vec.z) < 0.1:
                        coll.add(face)
                except Exception:
                    pass
        else:
            raise RuntimeError(
                f"Unknown face_selection '{selection}' — use all/top/bottom/vertical"
            )

        if coll.count == 0:
            raise RuntimeError(f"No faces matched selection '{selection}'")
        return coll

    # ------------------------------------------------------------------
    # Scene / Query
    # ------------------------------------------------------------------

    def get_scene_info(self):
        design = self._design()
        root = self._root()

        bodies = []
        for i in range(root.bRepBodies.count):
            b = root.bRepBodies.item(i)
            bodies.append(
                {
                    "name": b.name,
                    "volume": b.volume,
                    "area": b.area,
                    "material": b.material.name if b.material else None,
                    "is_visible": b.isVisible,
                }
            )

        sketches = []
        for i in range(root.sketches.count):
            s = root.sketches.item(i)
            sketches.append(
                {
                    "name": s.name,
                    "profile_count": s.profiles.count,
                    "is_visible": s.isVisible,
                }
            )

        return {
            "design_name": design.parentDocument.name,
            "design_type": design.productType,
            "bodies": bodies,
            "sketches": sketches,
            "bodies_count": root.bRepBodies.count,
            "sketches_count": root.sketches.count,
            "features_count": root.features.count,
            "timeline_count": (
                design.timeline.count if hasattr(design, "timeline") else 0
            ),
            "camera": self._camera_info(),
        }

    def get_object_info(self, name: str):
        root = self._root()

        # bodies
        for i in range(root.bRepBodies.count):
            b = root.bRepBodies.item(i)
            if b.name == name:
                return {
                    "found": True,
                    "type": "body",
                    "name": name,
                    "volume": b.volume,
                    "area": b.area,
                    "material": b.material.name if b.material else None,
                    "is_visible": b.isVisible,
                    "faces_count": b.faces.count,
                    "edges_count": b.edges.count,
                    "vertices_count": b.vertices.count,
                    "bounding_box": self._bbox_dict(b.boundingBox),
                }

        # sketches
        for i in range(root.sketches.count):
            s = root.sketches.item(i)
            if s.name == name:
                return {
                    "found": True,
                    "type": "sketch",
                    "name": name,
                    "is_visible": s.isVisible,
                    "profile_count": s.profiles.count,
                    "curve_count": s.sketchCurves.count,
                }

        return {"found": False, "name": name}

    def list_components(self, depth: int = None):
        """Occurrence tree. To save tokens, grounded appears only when true,
        visible only when false, axis/angle only when rotated, and each
        component's part_number/source once under "parts"."""
        root = self._root()
        group, attr_name = self._IMPORT_SOURCE_ATTR
        per_comp = {}  # component name -> {part_number?, source?}

        def _comp_fields(comp):
            fields = per_comp.get(comp.name)
            if fields is None:
                fields = {}
                if comp.partNumber and comp.partNumber != comp.name:
                    fields["part_number"] = comp.partNumber
                attr = comp.attributes.itemByName(group, attr_name)
                if attr is not None:
                    fields["source"] = attr.value
                per_comp[comp.name] = fields
            return fields

        def _node(occ, level):
            comp = occ.component
            _comp_fields(comp)
            n = {"occurrence": occ.fullPathName, "component": comp.name}
            # isGrounded raises on sub-component occurrences.
            if occ.assemblyContext is None and occ.isGrounded:
                n["grounded"] = True
            if not occ.isVisible:
                n["visible"] = False
            m = occ.transform2
            t = m.translation
            n["translation"] = self._r((t.x, t.y, t.z))
            rot = _asm.axis_angle(_asm.matrix_rows(m.asArray()))
            if rot is not None:
                n["axis"] = self._r(rot[0])
                n["angle"] = round(rot[1], 3)
            kids = occ.childOccurrences
            if kids.count:
                if depth is None or level < depth:
                    n["children"] = [_node(k, level + 1) for k in kids]
                else:
                    n["child_count"] = kids.count
            return n

        tree = [_node(o, 1) for o in root.occurrences]
        return {
            "root": root.name,
            "root_bodies": root.bRepBodies.count,
            "count": root.allOccurrences.count,
            "components": tree,
            "parts": {k: v for k, v in per_comp.items() if v},
        }

    def get_bounding_box(self, name: str):
        """Axis-aligned bounding box for a body or component. Values in cm."""

        def _payload(obj_type, mn, mx):
            return {
                "found": True,
                "type": obj_type,
                "name": name,
                "min": mn,
                "max": mx,
                "size": [mx[i] - mn[i] for i in range(3)],
                "center": [(mn[i] + mx[i]) / 2 for i in range(3)],
            }

        # Try body first (covers root bodies + bodies inside components)
        try:
            body = self._body_by_name(name)
            bb = body.boundingBox
            return _payload(
                "body",
                [bb.minPoint.x, bb.minPoint.y, bb.minPoint.z],
                [bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z],
            )
        except RuntimeError:
            pass

        # Whole design, or one occurrence and everything nested under it.
        # Unions body proxies so moved occurrences are in assembly coordinates.
        if name in ("root", self._root().name):
            obj_type, bodies = "assembly", self._all_bodies()
        else:
            try:
                occ = self._occurrence(name)
            except RuntimeError as exc:
                if "matches" in str(exc):
                    raise
                return {"found": False, "name": name}
            obj_type, bodies = "occurrence", self._all_bodies(occ)

        box = self._bbox_union(bodies)
        if box is None:
            return {"found": True, "type": obj_type, "name": name, "empty": True}
        result = _payload(obj_type, *box)
        if obj_type == "assembly":
            # FTC size limits are in inches.
            result["size_in"] = [round(s / 2.54, 3) for s in result["size"]]
        return result

    # ------------------------------------------------------------------
    # Sketch
    # ------------------------------------------------------------------

    def create_sketch(
        self, plane: str = "xy", z_offset: float = None, component: str = None
    ):
        comp = self._target_component(component)

        if z_offset is not None and z_offset != 0:
            # Create an offset construction plane
            planes = comp.constructionPlanes
            plane_input = planes.createInput()
            offset_val = adsk.core.ValueInput.createByReal(z_offset)
            plane_input.setByOffset(self._construction_plane(plane, comp), offset_val)
            cp = planes.add(plane_input)
            sketch = comp.sketches.add(cp)
        else:
            sketch = comp.sketches.add(self._construction_plane(plane, comp))
        self._last_sketch_obj = sketch

        return {
            "sketch_name": sketch.name,
            "plane": plane,
            "z_offset": z_offset,
            "component": comp.name,
        }

    def draw_rectangle(
        self,
        width: float,
        height: float,
        origin_x: float = 0,
        origin_y: float = 0,
        origin_z: float = 0,
    ):
        sketch = self._last_sketch()
        p1 = adsk.core.Point3D.create(origin_x, origin_y, origin_z)
        p2 = adsk.core.Point3D.create(origin_x + width, origin_y + height, origin_z)
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(p1, p2)
        return {"sketch": sketch.name, "width": width, "height": height}

    def draw_circle(
        self,
        radius: float,
        center_x: float = 0,
        center_y: float = 0,
        center_z: float = 0,
    ):
        sketch = self._last_sketch()
        c = adsk.core.Point3D.create(center_x, center_y, center_z)
        sketch.sketchCurves.sketchCircles.addByCenterRadius(c, radius)
        return {
            "sketch": sketch.name,
            "radius": radius,
            "center": [center_x, center_y, center_z],
        }

    def draw_line(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        start_z: float = 0,
        end_z: float = 0,
    ):
        sketch = self._last_sketch()
        sp = adsk.core.Point3D.create(start_x, start_y, start_z)
        ep = adsk.core.Point3D.create(end_x, end_y, end_z)
        sketch.sketchCurves.sketchLines.addByTwoPoints(sp, ep)
        return {
            "sketch": sketch.name,
            "start": [start_x, start_y, start_z],
            "end": [end_x, end_y, end_z],
        }

    def draw_arc(
        self,
        center_x: float,
        center_y: float,
        start_x: float,
        start_y: float,
        sweep_angle: float,
        center_z: float = 0,
        start_z: float = 0,
    ):
        sketch = self._last_sketch()
        center = adsk.core.Point3D.create(center_x, center_y, center_z)
        start = adsk.core.Point3D.create(start_x, start_y, start_z)
        sweep_rad = math.radians(sweep_angle)
        sketch.sketchCurves.sketchArcs.addByCenterStartSweep(center, start, sweep_rad)
        return {"sketch": sketch.name, "sweep_angle": sweep_angle}

    def draw_spline(self, spline_type: str, points: list, degree: int = 3):
        sketch = self._last_sketch()
        pts = adsk.core.ObjectCollection.create()
        for p in points:
            z = p[2] if len(p) > 2 else 0
            pts.add(adsk.core.Point3D.create(p[0], p[1], z))

        if spline_type == "fit_points":
            sketch.sketchCurves.sketchFittedSplines.add(pts)
        else:  # control_points
            sketch.sketchCurves.sketchControlPointSplines.add(pts, degree)
        return {
            "sketch": sketch.name,
            "spline_type": spline_type,
            "points_count": len(points),
        }

    def create_polygon(
        self,
        sides: int,
        radius: float,
        center_x: float = 0,
        center_y: float = 0,
        center_z: float = 0,
    ):
        sketch = self._last_sketch()
        # Draw inscribed polygon
        for i in range(sides):
            angle1 = 2 * math.pi * i / sides
            angle2 = 2 * math.pi * (i + 1) / sides
            p1 = adsk.core.Point3D.create(
                center_x + radius * math.cos(angle1),
                center_y + radius * math.sin(angle1),
                center_z,
            )
            p2 = adsk.core.Point3D.create(
                center_x + radius * math.cos(angle2),
                center_y + radius * math.sin(angle2),
                center_z,
            )
            sketch.sketchCurves.sketchLines.addByTwoPoints(p1, p2)
        return {"sketch": sketch.name, "sides": sides, "radius": radius}

    def add_constraint(
        self,
        constraint_type: str,
        entity_one: int = None,
        entity_two: int = None,
        symmetry_line: int = None,
        sketch_name: str = None,
    ):
        sketch = (
            self._sketch_by_name(sketch_name) if sketch_name else self._last_sketch()
        )
        constraints = sketch.geometricConstraints
        curves = list(sketch.sketchCurves)

        e1 = curves[entity_one] if entity_one is not None else None
        e2 = curves[entity_two] if entity_two is not None else None

        constraint_map = {
            "coincident": lambda: constraints.addCoincident(e1, e2),
            "parallel": lambda: constraints.addParallel(e1, e2),
            "perpendicular": lambda: constraints.addPerpendicular(e1, e2),
            "tangent": lambda: constraints.addTangent(e1, e2),
            "equal": lambda: constraints.addEqual(e1, e2),
            "fix": lambda: constraints.addFix(e1),
            "horizontal": lambda: constraints.addHorizontal(e1),
            "vertical": lambda: constraints.addVertical(e1),
            "concentric": lambda: constraints.addConcentric(e1, e2),
            "collinear": lambda: constraints.addCollinear(e1, e2),
            "smooth": lambda: constraints.addSmooth(e1, e2),
            "midpoint": lambda: constraints.addMidPoint(
                sketch.sketchPoints.item(entity_one), e2
            ),
            "symmetry": lambda: constraints.addSymmetry(e1, e2, curves[symmetry_line]),
        }

        if constraint_type not in constraint_map:
            raise RuntimeError(f"Unknown constraint type: {constraint_type}")

        constraint_map[constraint_type]()
        return {"sketch": sketch.name, "constraint_type": constraint_type}

    def auto_constrain(
        self,
        sketch_name: str = None,
        result_option: int = 1,
    ):
        """Auto-constrain a sketch using Fusion's AutoConstrain (Jan 2026+).

        result_option: 1 = thorough (default), 2 = fast,
        3 = may move geometry within tolerance.
        """
        sketch = (
            self._sketch_by_name(sketch_name) if sketch_name else self._last_sketch()
        )

        option_map = {
            1: adsk.fusion.AutoConstrainResultTypes.Option1AutoConstrainResultType,
            2: adsk.fusion.AutoConstrainResultTypes.Option2AutoConstrainResultType,
            3: adsk.fusion.AutoConstrainResultTypes.Option3AutoConstrainResultType,
        }
        option = option_map.get(result_option)
        if option is None:
            raise RuntimeError(
                f"Invalid result_option {result_option} — use 1 (thorough), "
                "2 (fast), or 3 (may adjust geometry within tolerance)."
            )

        ac_input = sketch.createAutoConstrainInput()
        ac_input.resultOption = option
        result = sketch.autoConstrain(ac_input)
        if result is None:
            # Option 3 returns null when the sketch is not eligible for
            # geometry adjustment.
            raise RuntimeError(
                "autoConstrain returned no result — the sketch is not "
                "eligible for geometry adjustment. Retry with "
                "result_option 1 or 2."
            )

        return {
            "sketch": sketch.name,
            "is_fully_constrained": result.isFullyConstrained,
            "constraints_added": len(result.addedConstraints),
            "dimensions_added": len(result.addedDimensions),
            "entities_moved": len(result.movedGeometry),
            "result_option": result_option,
        }

    def add_dimension(
        self,
        dimension_type: str,
        value: float,
        entity_one: int = None,
        entity_two: int = None,
        sketch_name: str = None,
    ):
        sketch = (
            self._sketch_by_name(sketch_name) if sketch_name else self._last_sketch()
        )
        dims = sketch.sketchDimensions
        curves = list(sketch.sketchCurves)

        e1 = curves[entity_one] if entity_one is not None else None
        e2 = curves[entity_two] if entity_two is not None else None
        text_pt = adsk.core.Point3D.create(0, 0, 0)

        if dimension_type == "distance":
            dim = dims.addDistanceDimension(
                e1.startSketchPoint,
                e2.startSketchPoint,
                adsk.fusion.DimensionOrientations.AlignedDimensionOrientation,
                text_pt,
            )
        elif dimension_type == "horizontal":
            dim = dims.addDistanceDimension(
                e1.startSketchPoint,
                e2.startSketchPoint,
                adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation,
                text_pt,
            )
        elif dimension_type == "vertical":
            dim = dims.addDistanceDimension(
                e1.startSketchPoint,
                e2.startSketchPoint,
                adsk.fusion.DimensionOrientations.VerticalDimensionOrientation,
                text_pt,
            )
        elif dimension_type == "angular":
            dim = dims.addAngularDimension(e1, e2, text_pt)
        elif dimension_type == "radial":
            dim = dims.addRadialDimension(e1, text_pt)
        elif dimension_type == "diameter":
            dim = dims.addDiameterDimension(e1, text_pt)
        else:
            raise RuntimeError(f"Unknown dimension type: {dimension_type}")

        dim.parameter.value = value
        return {"sketch": sketch.name, "dimension_type": dimension_type, "value": value}

    def offset_curve(
        self,
        curve_index: int,
        offset_distance: float,
        direction_x: float = 1,
        direction_y: float = 0,
        sketch_name: str = None,
    ):
        sketch = (
            self._sketch_by_name(sketch_name) if sketch_name else self._last_sketch()
        )
        curves = list(sketch.sketchCurves)
        curve = curves[curve_index]
        direction_pt = adsk.core.Point3D.create(direction_x, direction_y, 0)

        coll = adsk.core.ObjectCollection.create()
        coll.add(curve)
        sketch.offset(coll, direction_pt, offset_distance)
        return {"sketch": sketch.name, "offset_distance": offset_distance}

    def trim_curve(
        self, curve_index: int, point_x: float, point_y: float, sketch_name: str = None
    ):
        sketch = (
            self._sketch_by_name(sketch_name) if sketch_name else self._last_sketch()
        )
        curves = list(sketch.sketchCurves)
        curve = curves[curve_index]
        point = adsk.core.Point3D.create(point_x, point_y, 0)
        curve.trim(point)
        return {"sketch": sketch.name, "trimmed": True}

    def extend_curve(
        self, curve_index: int, point_x: float, point_y: float, sketch_name: str = None
    ):
        sketch = (
            self._sketch_by_name(sketch_name) if sketch_name else self._last_sketch()
        )
        curves = list(sketch.sketchCurves)
        curve = curves[curve_index]
        point = adsk.core.Point3D.create(point_x, point_y, 0)
        curve.extend(point)
        return {"sketch": sketch.name, "extended": True}

    def project_geometry(
        self, source_name: str, is_linked: bool = True, sketch_name: str = None
    ):
        sketch = (
            self._sketch_by_name(sketch_name) if sketch_name else self._last_sketch()
        )
        body = self._body_by_name(source_name)

        projected = []
        for edge in body.edges:
            proj = sketch.project(edge)
            projected.append(proj.count)

        return {
            "sketch": sketch.name,
            "source": source_name,
            "projected_curves": sum(projected),
        }

    # ------------------------------------------------------------------
    # Features
    # ------------------------------------------------------------------

    def extrude(
        self,
        height: float,
        profile_index: int = 0,
        operation: str = "new_body",
        direction: str = "positive",
    ):
        sketch = self._last_sketch()
        if sketch.profiles.count == 0:
            raise RuntimeError("No profiles in sketch")
        profile = sketch.profiles.item(profile_index)

        comp = sketch.parentComponent
        ext_feats = comp.features.extrudeFeatures
        ext_input = ext_feats.createInput(profile, self._operation_type(operation))
        dist = adsk.core.ValueInput.createByReal(height)
        if direction == "symmetric":
            ext_input.setSymmetricExtent(dist, True)
        else:
            ext_input.setDistanceExtent(direction == "negative", dist)

        feat = ext_feats.add(ext_input)
        return {
            "feature_name": feat.name,
            "height": height,
            "operation": operation,
            "direction": direction,
            "component": comp.name,
        }

    def revolve(
        self,
        angle: float,
        profile_index: int = 0,
        axis_origin_x: float = 0,
        axis_origin_y: float = 0,
        axis_origin_z: float = 0,
        axis_direction_x: float = 1,
        axis_direction_y: float = 0,
        axis_direction_z: float = 0,
        operation: str = "new_body",
    ):
        sketch = self._last_sketch()
        if sketch.profiles.count == 0:
            raise RuntimeError("No profiles in sketch")
        profile = sketch.profiles.item(profile_index)
        comp = sketch.parentComponent

        # Determine axis entity first (required for createInput)
        axis_entity = None
        is_x = abs(axis_direction_x) > 0.99 and abs(axis_direction_y) < 0.01
        is_y = abs(axis_direction_y) > 0.99 and abs(axis_direction_x) < 0.01
        is_z = abs(axis_direction_z) > 0.99 and abs(axis_direction_x) < 0.01
        if is_x and abs(axis_direction_z) < 0.01:
            axis_entity = comp.xConstructionAxis
        elif is_y and abs(axis_direction_z) < 0.01:
            axis_entity = comp.yConstructionAxis
        elif is_z and abs(axis_direction_y) < 0.01:
            axis_entity = comp.zConstructionAxis
        else:
            # Create construction line in sketch
            origin = adsk.core.Point3D.create(
                axis_origin_x, axis_origin_y, axis_origin_z
            )
            end_pt = adsk.core.Point3D.create(
                axis_origin_x + axis_direction_x * 10,
                axis_origin_y + axis_direction_y * 10,
                axis_origin_z + axis_direction_z * 10,
            )
            line = sketch.sketchCurves.sketchLines.addByTwoPoints(origin, end_pt)
            line.isConstruction = True
            axis_entity = line

        rev_feats = comp.features.revolveFeatures
        rev_input = rev_feats.createInput(
            profile, axis_entity, self._operation_type(operation)
        )

        angle_val = adsk.core.ValueInput.createByString(f"{angle} deg")
        rev_input.setAngleExtent(False, angle_val)

        feat = rev_feats.add(rev_input)
        return {
            "feature_name": feat.name,
            "angle": angle,
            "operation": operation,
            "component": comp.name,
        }

    def sweep(
        self,
        profile_index: int,
        path_sketch_name: str,
        path_curve_index: int = 0,
        operation: str = "new_body",
    ):
        sketch = self._last_sketch()
        comp = sketch.parentComponent
        path_sketch = self._sketch_by_name(path_sketch_name)

        if sketch.profiles.count == 0:
            raise RuntimeError("No profiles in sketch")
        profile = sketch.profiles.item(profile_index)

        path_curves = list(path_sketch.sketchCurves)
        path_curve = path_curves[path_curve_index]

        path = comp.features.createPath(path_curve)

        sweep_feats = comp.features.sweepFeatures
        sweep_input = sweep_feats.createInput(
            profile, path, self._operation_type(operation)
        )
        feat = sweep_feats.add(sweep_input)
        return {
            "feature_name": feat.name,
            "operation": operation,
            "component": comp.name,
        }

    def loft(self, profile_sketch_names: list, operation: str = "new_body"):
        sketches = [self._sketch_by_name(n) for n in profile_sketch_names]
        comp = sketches[0].parentComponent if sketches else self._root()
        loft_feats = comp.features.loftFeatures
        loft_input = loft_feats.createInput(self._operation_type(operation))

        for sketch_name, sketch in zip(profile_sketch_names, sketches):
            if sketch.profiles.count == 0:
                raise RuntimeError(f"No profiles in sketch '{sketch_name}'")
            loft_input.loftSections.add(sketch.profiles.item(0))

        feat = loft_feats.add(loft_input)
        return {
            "feature_name": feat.name,
            "operation": operation,
            "profile_count": len(profile_sketch_names),
            "component": comp.name,
        }

    def fillet(
        self,
        radius: float,
        body_name: str = None,
        body_index: int = 0,
        edge_selection: str = "all",
    ):
        root = self._root()
        body, comp = self._native(
            self._body_by_name(body_name)
            if body_name
            else root.bRepBodies.item(body_index)
        )
        edges = self._select_edges(body, edge_selection)

        fillets = comp.features.filletFeatures
        inp = fillets.createInput()
        inp.addConstantRadiusEdgeSet(
            edges, adsk.core.ValueInput.createByReal(radius), True
        )
        feat = fillets.add(inp)
        return {
            "feature_name": feat.name,
            "radius": radius,
            "edges_count": edges.count,
            "component": comp.name,
        }

    def chamfer(
        self,
        distance: float,
        body_name: str = None,
        body_index: int = 0,
        edge_selection: str = "all",
    ):
        root = self._root()
        body, comp = self._native(
            self._body_by_name(body_name)
            if body_name
            else root.bRepBodies.item(body_index)
        )
        edges = self._select_edges(body, edge_selection)

        chamfers = comp.features.chamferFeatures
        inp = chamfers.createInput(edges, True)
        inp.setToEqualDistance(adsk.core.ValueInput.createByReal(distance))
        feat = chamfers.add(inp)
        return {
            "feature_name": feat.name,
            "distance": distance,
            "edges_count": edges.count,
            "component": comp.name,
        }

    def shell(
        self,
        thickness: float,
        body_name: str = None,
        body_index: int = 0,
        face_selection: str = "top",
    ):
        root = self._root()
        body, comp = self._native(
            self._body_by_name(body_name)
            if body_name
            else root.bRepBodies.item(body_index)
        )

        faces = adsk.core.ObjectCollection.create()
        bbox = body.boundingBox

        if face_selection == "top":
            threshold = bbox.maxPoint.z - 0.001
            for face in body.faces:
                if face.boundingBox.maxPoint.z > threshold:
                    faces.add(face)
        elif face_selection == "bottom":
            threshold = bbox.minPoint.z + 0.001
            for face in body.faces:
                if face.boundingBox.minPoint.z < threshold:
                    faces.add(face)
        else:
            raise RuntimeError(
                f"Unknown face_selection '{face_selection}' — use top/bottom"
            )

        if faces.count == 0:
            raise RuntimeError(f"No faces matched '{face_selection}'")

        shells = comp.features.shellFeatures
        body_coll = adsk.core.ObjectCollection.create()
        body_coll.add(body)
        inp = shells.createInput(body_coll)
        inp.facesToRemove = faces
        inp.insideThickness = adsk.core.ValueInput.createByReal(thickness)
        feat = shells.add(inp)
        return {
            "feature_name": feat.name,
            "thickness": thickness,
            "faces_removed": faces.count,
            "component": comp.name,
        }

    def mirror(self, mirror_plane: str, body_name: str = None, body_index: int = 0):
        root = self._root()
        body, comp = self._native(
            self._body_by_name(body_name)
            if body_name
            else root.bRepBodies.item(body_index)
        )

        entities = adsk.core.ObjectCollection.create()
        entities.add(body)

        mirrors = comp.features.mirrorFeatures
        inp = mirrors.createInput(
            entities, self._construction_plane(mirror_plane, comp)
        )
        feat = mirrors.add(inp)
        return {
            "feature_name": feat.name,
            "mirror_plane": mirror_plane,
            "component": comp.name,
        }

    def create_hole(
        self,
        diameter: float,
        depth: float,
        body_name: str = None,
        body_index: int = 0,
        face_selection: str = "top",
        center_x: float = 0,
        center_y: float = 0,
    ):
        root = self._root()
        body, comp = self._native(
            self._body_by_name(body_name)
            if body_name
            else root.bRepBodies.item(body_index)
        )

        # Find the target face.
        # Comparing bounding boxes is not enough: the side faces of a box reach
        # the body's max Z too, so the first "hit" is usually a vertical face.
        # Require a near-horizontal planar face that points up (or down).
        if face_selection not in ("top", "bottom"):
            raise RuntimeError(f"Unknown face_selection '{face_selection}'")
        want_up = face_selection == "top"

        target_face = None
        best_key = None
        for face in body.faces:
            if adsk.core.Plane.cast(face.geometry) is None:
                continue
            # Use the evaluator: it reports the face's outward normal, whereas
            # the underlying plane's normal ignores the face's orientation.
            ok, normal = face.evaluator.getNormalAtPoint(face.pointOnFace)
            if not ok or not _hole_geom.is_horizontal_face(normal.z, want_up):
                continue
            # Rank on the face's own extreme Z, not on an arbitrary point on
            # it: within the tilt tolerance the two are not the same.
            fbox = face.boundingBox
            edge_z = fbox.maxPoint.z if want_up else fbox.minPoint.z
            key = _hole_geom.face_rank_key(edge_z, face.area, want_up)
            if best_key is None or key > best_key:
                best_key, target_face = key, face

        if target_face is None:
            raise RuntimeError(
                f"No near-horizontal {face_selection}-facing planar face on "
                f"'{body.name}'"
            )

        # Place the hole centre. center_x / center_y are model-space XY, so the
        # caller does not have to know the sketch's own coordinate system. Solve
        # the face's plane for Z rather than reusing an arbitrary point on it.
        plane = adsk.core.Plane.cast(target_face.geometry)
        n, o = plane.normal, plane.origin
        center_z = _hole_geom.plane_z_at(
            (n.x, n.y, n.z), (o.x, o.y, o.z), center_x, center_y
        )
        sketch = comp.sketches.add(target_face)
        sketch_pt = sketch.sketchPoints.add(
            sketch.modelToSketchSpace(
                adsk.core.Point3D.create(center_x, center_y, center_z)
            )
        )

        # createSimpleInput() takes the DIAMETER -- "A ValueInput object that
        # defines the diameter of the hole" -- not the radius.
        holes = comp.features.holeFeatures
        hole_input = holes.createSimpleInput(
            adsk.core.ValueInput.createByReal(diameter)
        )
        hole_input.setPositionBySketchPoint(sketch_pt)
        hole_input.setDistanceExtent(adsk.core.ValueInput.createByReal(depth))
        # Without this the hole cuts every body it happens to intersect.
        # The property takes a plain list, not an ObjectCollection.
        hole_input.participantBodies = [body]

        feat = holes.add(hole_input)
        return {
            "feature_name": feat.name,
            "diameter": diameter,
            "depth": depth,
            "actual_diameter": feat.holeDiameter.value,
            "cut_bodies": [b.name for b in feat.bodies],
            # Where the request resolved to, not a measurement of the feature.
            "resolved_center": [center_x, center_y, center_z],
            "component": comp.name,
        }

    def rectangular_pattern(
        self,
        body_name: str,
        x_count: int = 1,
        x_spacing: float = 1.0,
        y_count: int = 1,
        y_spacing: float = 1.0,
    ):
        body, comp = self._native(self._body_by_name(body_name))

        bodies = adsk.core.ObjectCollection.create()
        bodies.add(body)

        patterns = comp.features.rectangularPatternFeatures
        inp = patterns.createInput(
            bodies,
            comp.xConstructionAxis,
            adsk.core.ValueInput.createByReal(x_count),
            adsk.core.ValueInput.createByReal(x_spacing),
            adsk.fusion.PatternDistanceType.SpacingPatternDistanceType,
        )
        inp.setDirectionTwo(
            comp.yConstructionAxis,
            adsk.core.ValueInput.createByReal(y_count),
            adsk.core.ValueInput.createByReal(y_spacing),
        )
        feat = patterns.add(inp)
        return {
            "feature_name": feat.name,
            "x_count": x_count,
            "y_count": y_count,
            "component": comp.name,
        }

    def circular_pattern(
        self, body_name: str, count: int, axis: str = "z", total_angle: float = 360
    ):
        body, comp = self._native(self._body_by_name(body_name))

        bodies = adsk.core.ObjectCollection.create()
        bodies.add(body)

        patterns = comp.features.circularPatternFeatures
        inp = patterns.createInput(bodies, self._construction_axis(axis, comp))
        inp.quantity = adsk.core.ValueInput.createByReal(count)
        inp.totalAngle = adsk.core.ValueInput.createByString(f"{total_angle} deg")
        feat = patterns.add(inp)
        return {
            "feature_name": feat.name,
            "count": count,
            "total_angle": total_angle,
            "component": comp.name,
        }

    def create_thread(
        self,
        body_name: str,
        face_index: int,
        is_internal: bool = False,
        thread_type: str = "ISO Metric profile",
        thread_designation: str = "M10x1.5",
        thread_class: str = "6g",
        is_modeled: bool = False,
        is_full_length: bool = True,
        thread_length: float = None,
    ):
        body, comp = self._native(self._body_by_name(body_name))
        face = body.faces.item(face_index)

        threads = comp.features.threadFeatures
        thread_data = threads.threadDataQuery
        thread_data.threadType = thread_type

        inp = threads.createInput(face, thread_data)
        inp.isModeled = is_modeled
        inp.isFullLength = is_full_length
        if not is_full_length and thread_length:
            inp.threadLength = adsk.core.ValueInput.createByReal(thread_length)

        feat = threads.add(inp)
        return {
            "feature_name": feat.name,
            "thread_type": thread_type,
            "component": comp.name,
        }

    def draft_faces(
        self,
        body_name: str,
        angle: float,
        face_selection: str = "vertical",
        pull_direction_plane: str = "xy",
        is_tangent_chain: bool = True,
    ):
        body, comp = self._native(self._body_by_name(body_name))
        faces = self._select_faces(body, face_selection)

        drafts = comp.features.draftFeatures
        # createInput wants a BRepFace array and three arguments; the angle is
        # set on the input object afterwards, not passed in.
        inp = drafts.createInput(
            [faces.item(i) for i in range(faces.count)],
            self._construction_plane(pull_direction_plane, comp),
            is_tangent_chain,
        )
        inp.setSingleAngle(False, adsk.core.ValueInput.createByString(f"{angle} deg"))
        feat = drafts.add(inp)
        return {
            "feature_name": feat.name,
            "angle": angle,
            "face_count": faces.count,
            "component": comp.name,
        }

    def split_body(
        self,
        body_name: str,
        splitting_plane: str = "xy",
        splitting_body: str = None,
        extend_tool: bool = True,
    ):
        body, comp = self._native(self._body_by_name(body_name))

        splits = comp.features.splitBodyFeatures
        if splitting_body:
            tool, _ = self._native(self._body_by_name(splitting_body))
            inp = splits.createInput(body, tool, extend_tool)
        else:
            inp = splits.createInput(
                body, self._construction_plane(splitting_plane, comp), extend_tool
            )
        feat = splits.add(inp)
        return {
            "feature_name": feat.name,
            "splitting_plane": splitting_plane,
            "component": comp.name,
        }

    def split_face(
        self,
        body_name: str,
        face_indices: list = None,
        splitting_plane: str = "xy",
        extend_tool: bool = True,
    ):
        body, comp = self._native(self._body_by_name(body_name))

        faces = adsk.core.ObjectCollection.create()
        if face_indices:
            for idx in face_indices:
                faces.add(body.faces.item(idx))
        else:
            for face in body.faces:
                faces.add(face)

        splits = comp.features.splitFaceFeatures
        inp = splits.createInput(
            faces, self._construction_plane(splitting_plane, comp), extend_tool
        )
        feat = splits.add(inp)
        return {"feature_name": feat.name, "component": comp.name}

    def offset_faces(
        self,
        body_name: str,
        distance: float,
        face_selection: str = "top",
        face_indices: list = None,
    ):
        body, comp = self._native(self._body_by_name(body_name))

        if face_indices:
            faces = adsk.core.ObjectCollection.create()
            for idx in face_indices:
                faces.add(body.faces.item(idx))
        else:
            faces = self._select_faces(body, face_selection)

        offsets = comp.features.offsetFeatures
        inp = offsets.createInput(
            faces,
            adsk.core.ValueInput.createByReal(distance),
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
        )
        feat = offsets.add(inp)
        return {"feature_name": feat.name, "distance": distance, "component": comp.name}

    def scale_body(
        self,
        body_name: str,
        scale: float,
        scale_x: float = None,
        scale_y: float = None,
        scale_z: float = None,
        anchor_x: float = 0,
        anchor_y: float = 0,
        anchor_z: float = 0,
    ):
        body, comp = self._native(self._body_by_name(body_name))

        bodies = adsk.core.ObjectCollection.create()
        bodies.add(body)

        anchor = adsk.core.Point3D.create(anchor_x, anchor_y, anchor_z)

        scales = comp.features.scaleFeatures
        if scale_x is not None and scale_y is not None and scale_z is not None:
            inp = scales.createInput(
                bodies,
                anchor,
                adsk.core.ValueInput.createByReal(scale_x),
                adsk.core.ValueInput.createByReal(scale_y),
                adsk.core.ValueInput.createByReal(scale_z),
            )
        else:
            inp = scales.createInput(
                bodies, anchor, adsk.core.ValueInput.createByReal(scale)
            )
        feat = scales.add(inp)
        return {"feature_name": feat.name, "scale": scale, "component": comp.name}

    def suppress_feature(self, feature_name: str):
        design = self._design()
        for i in range(design.timeline.count):
            item = design.timeline.item(i)
            has_entity = hasattr(item, "entity") and item.entity
            if has_entity and item.entity.name == feature_name:
                item.isSuppressed = True
                return {"suppressed": True, "feature": feature_name}
        raise RuntimeError(f"Feature '{feature_name}' not found in timeline")

    def unsuppress_feature(self, feature_name: str):
        design = self._design()
        for i in range(design.timeline.count):
            item = design.timeline.item(i)
            has_entity = hasattr(item, "entity") and item.entity
            if has_entity and item.entity.name == feature_name:
                item.isSuppressed = False
                return {"unsuppressed": True, "feature": feature_name}
        raise RuntimeError(f"Feature '{feature_name}' not found in timeline")

    # ------------------------------------------------------------------
    # Body Operations
    # ------------------------------------------------------------------

    def rename_body(self, body_name: str, new_name: str):
        body = self._body_by_name(body_name)
        old_name = body.name
        body.name = new_name
        return {"renamed": True, "old_name": old_name, "new_name": new_name}

    def move_body(self, body_name: str, x: float = 0, y: float = 0, z: float = 0):
        body, comp = self._native(self._body_by_name(body_name))

        move_feats = comp.features.moveFeatures
        bodies = adsk.core.ObjectCollection.create()
        bodies.add(body)

        transform = adsk.core.Matrix3D.create()
        transform.translation = adsk.core.Vector3D.create(x, y, z)

        inp = move_feats.createInput(bodies, transform)
        feat = move_feats.add(inp)
        return {
            "feature_name": feat.name,
            "body": body_name,
            "translation": [x, y, z],
            "component": comp.name,
        }

    def export_stl(self, body_name: str, file_path: str = None):
        body = self._body_by_name(body_name)

        if file_path is None:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            file_path = os.path.join(desktop, f"{body_name}.stl")

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        export_mgr = self._design().exportManager
        occ = body.assemblyContext  # None if body is at root

        if occ is None:
            stl_opts = export_mgr.createSTLExportOptions(body, file_path)
            stl_opts.meshRefinement = (
                adsk.fusion.MeshRefinementSettings.MeshRefinementMedium
            )
            export_mgr.execute(stl_opts)
            return {"exported": True, "body": body_name, "file_path": file_path}

        # Body lives in a component occurrence: hide siblings so the
        # occurrence export only contains the target body. Identify
        # siblings by entityToken, not name, to handle same-name bodies.
        target_token = body.entityToken
        hidden = []
        for i in range(occ.bRepBodies.count):
            sibling = occ.bRepBodies.item(i)
            if sibling.entityToken != target_token and sibling.isVisible:
                sibling.isVisible = False
                hidden.append(sibling)

        try:
            stl_opts = export_mgr.createSTLExportOptions(occ, file_path)
            stl_opts.meshRefinement = (
                adsk.fusion.MeshRefinementSettings.MeshRefinementMedium
            )
            export_mgr.execute(stl_opts)
        finally:
            for sibling in hidden:
                sibling.isVisible = True

        return {"exported": True, "body": body_name, "file_path": file_path}

    def export_step(self, body_name: str, file_path: str = None):
        body = self._body_by_name(body_name)

        if file_path is None:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            file_path = os.path.join(desktop, f"{body_name}.step")

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        export_mgr = self._design().exportManager
        occ = body.assemblyContext  # None if body is at root

        if occ is None:
            step_opts = export_mgr.createSTEPExportOptions(file_path, body)
            export_mgr.execute(step_opts)
            return {"exported": True, "body": body_name, "file_path": file_path}

        # Body lives in a component occurrence: hide siblings so the
        # occurrence export only contains the target body. Identify
        # siblings by entityToken, not name, to handle same-name bodies.
        target_token = body.entityToken
        hidden = []
        for i in range(occ.bRepBodies.count):
            sibling = occ.bRepBodies.item(i)
            if sibling.entityToken != target_token and sibling.isVisible:
                sibling.isVisible = False
                hidden.append(sibling)

        try:
            step_opts = export_mgr.createSTEPExportOptions(file_path, occ)
            export_mgr.execute(step_opts)
        finally:
            for sibling in hidden:
                sibling.isVisible = True

        return {"exported": True, "body": body_name, "file_path": file_path}

    def export_f3d(self, file_path: str = None):
        design = self._design()
        doc_name = design.parentDocument.name

        if file_path is None:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            file_path = os.path.join(desktop, f"{doc_name}.f3d")

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        export_mgr = design.exportManager
        f3d_opts = export_mgr.createFusionArchiveExportOptions(file_path)
        export_mgr.execute(f3d_opts)

        return {"exported": True, "file_path": file_path}

    # ── view sheet ─────────────────────────────────────────────────────
    # Render canonical views (iso/front/top/right/...) as PNGs and emit
    # a self-contained HTML page suitable for print-to-PDF. Intended
    # audience: mechanical engineers who want a quick sense of the part.

    def _scene_center_and_radius(self):
        """Return (center, radius) covering all visible root bodies."""
        root = self._root()
        minp = [float("inf")] * 3
        maxp = [float("-inf")] * 3
        found = False

        def _grow(bb):
            nonlocal found
            for j, coord in enumerate(("x", "y", "z")):
                minp[j] = min(minp[j], getattr(bb.minPoint, coord))
                maxp[j] = max(maxp[j], getattr(bb.maxPoint, coord))
            found = True

        for i in range(root.bRepBodies.count):
            b = root.bRepBodies.item(i)
            if b.isVisible:
                _grow(b.boundingBox)
        for i in range(root.occurrences.count):
            occ = root.occurrences.item(i)
            if not occ.isVisible:
                continue
            for j in range(occ.bRepBodies.count):
                b = occ.bRepBodies.item(j)
                if b.isVisible:
                    _grow(b.boundingBox)

        if not found:
            return (0.0, 0.0, 0.0), 10.0
        center = tuple((minp[i] + maxp[i]) / 2 for i in range(3))
        span = max(maxp[i] - minp[i] for i in range(3))
        return center, max(span, 1.0)

    def _apply_view(self, view_name: str, center, radius: float):
        """Point the active viewport camera at *center* from *view_name*."""
        dir_vec, up_vec = self._VIEW_DIRS[view_name]
        length = math.sqrt(sum(c * c for c in dir_vec))
        dist = radius * 3.0  # give fit() headroom
        eye = tuple(center[i] + dir_vec[i] / length * dist for i in range(3))
        vp = self.app.activeViewport
        cam = vp.camera
        cam.isSmoothTransition = False
        cam.cameraType = adsk.core.CameraTypes.OrthographicCameraType
        cam.eye = adsk.core.Point3D.create(*eye)
        cam.target = adsk.core.Point3D.create(*center)
        cam.upVector = adsk.core.Vector3D.create(*up_vec)
        cam.isFitView = True
        vp.camera = cam
        vp.refresh()
        adsk.doEvents()

    def export_view_sheet(
        self,
        title: str = None,
        notes: str = "",
        views: list = None,
        image_size: list = None,
        output_dir: str = None,
    ):
        """Render canonical views as PNGs + a shareable HTML sheet.

        Args:
            title: heading on the sheet (default: document name).
            notes: free-form text rendered below the views (newlines
                preserved; HTML is escaped).
            views: ordered list of view names. Valid: iso, iso_ne,
                iso_nw, iso_sw, front, back, top, bottom, right, left.
                Default: ["iso", "front", "top", "right"].
            image_size: [width, height] in pixels (default [1200, 900]).
            output_dir: destination folder
                (default: ~/Desktop/<doc>_views_<timestamp>).
        """
        import base64
        import html
        import json as _json

        design = self._design()
        doc_name = design.parentDocument.name
        sheet_title = title or doc_name
        views = views or ["iso", "front", "top", "right"]
        image_size = image_size or [1200, 900]
        width, height = int(image_size[0]), int(image_size[1])

        unknown = [v for v in views if v not in self._VIEW_DIRS]
        if unknown:
            raise RuntimeError(
                f"Unknown views: {unknown}. Valid: {sorted(self._VIEW_DIRS)}"
            )

        if output_dir is None:
            ts = time.strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join(
                os.path.expanduser("~"),
                "Desktop",
                f"{doc_name}_views_{ts}",
            )
        os.makedirs(output_dir, exist_ok=True)

        vp = self.app.activeViewport
        orig = vp.camera
        orig_state = {
            "eye": (orig.eye.x, orig.eye.y, orig.eye.z),
            "target": (orig.target.x, orig.target.y, orig.target.z),
            "up": (orig.upVector.x, orig.upVector.y, orig.upVector.z),
            "type": orig.cameraType,
        }

        center, radius = self._scene_center_and_radius()

        rendered = []
        try:
            for view_name in views:
                self._apply_view(view_name, center, radius)
                png_path = os.path.join(output_dir, f"{view_name}.png")
                vp.saveAsImageFile(png_path, width, height)
                rendered.append({"view": view_name, "path": png_path})
        finally:
            cam = vp.camera
            cam.isSmoothTransition = False
            cam.cameraType = orig_state["type"]
            cam.eye = adsk.core.Point3D.create(*orig_state["eye"])
            cam.target = adsk.core.Point3D.create(*orig_state["target"])
            cam.upVector = adsk.core.Vector3D.create(*orig_state["up"])
            vp.camera = cam
            vp.refresh()

        # Build self-contained HTML with base64-embedded PNGs.
        figures = []
        for r in rendered:
            with open(r["path"], "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            label = r["view"].replace("_", " ").upper()
            figures.append(
                "<figure>"
                f'<img src="data:image/png;base64,{b64}" alt="{label}">'
                f"<figcaption>{label}</figcaption>"
                "</figure>"
            )

        notes_block = ""
        if notes:
            notes_block = (
                '<section class="notes"><h2>Notes</h2>'
                f"<pre>{html.escape(notes)}</pre></section>"
            )

        timestamp = time.strftime("%Y-%m-%d %H:%M")
        html_doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>{html.escape(sheet_title)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
           sans-serif; color: #111; max-width: 1400px;
           margin: 2rem auto; padding: 0 2rem; }}
  header {{ border-bottom: 1px solid #d0d0d0; padding-bottom: .75rem;
            margin-bottom: 2rem; }}
  header h1 {{ margin: 0; font-weight: 500; font-size: 1.6rem; }}
  header .meta {{ color: #666; font-size: .85rem; margin-top: .25rem; }}
  .views {{ display: grid; grid-template-columns: 1fr 1fr;
            gap: 1.25rem; }}
  figure {{ margin: 0; border: 1px solid #e0e0e0; padding: .5rem;
            background: #fafafa; }}
  figure img {{ width: 100%; display: block; background: #fff; }}
  figcaption {{ text-align: center; font-size: .75rem; color: #555;
                margin-top: .35rem; letter-spacing: .15em; }}
  .notes {{ margin-top: 2rem; padding-top: 1rem;
            border-top: 1px solid #e0e0e0; }}
  .notes h2 {{ font-size: 1rem; font-weight: 500; margin: 0 0 .5rem; }}
  .notes pre {{ font-family: inherit; white-space: pre-wrap;
                margin: 0; color: #333; }}
  @media print {{
    body {{ max-width: none; margin: 0; padding: 1cm; }}
    .views {{ gap: .5cm; }}
    figure {{ break-inside: avoid; }}
  }}
</style>
</head><body>
<header>
  <h1>{html.escape(sheet_title)}</h1>
  <div class="meta">{html.escape(doc_name)} * {timestamp}</div>
</header>
<section class="views">{"".join(figures)}</section>
{notes_block}
</body></html>
"""
        html_path = os.path.join(output_dir, "view_sheet.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_doc)

        # Sidecar manifest - machine-readable record of what was emitted.
        manifest = {
            "title": sheet_title,
            "document": doc_name,
            "views": rendered,
            "html_path": html_path,
            "image_size": [width, height],
        }
        with open(os.path.join(output_dir, "manifest.json"), "w") as f:
            _json.dump(manifest, f, indent=2)

        return {
            "html_path": html_path,
            "output_dir": output_dir,
            "views": rendered,
            "title": sheet_title,
            "image_size": [width, height],
        }

    def export(self, format: str = None, body_name: str = None, file_path: str = None):
        """Unified export — dispatches to export_stl/export_step/export_f3d."""
        fmt = format.lower() if format else None
        if not fmt and file_path:
            fmt = os.path.splitext(file_path)[1].lstrip(".").lower()
        if not fmt:
            raise RuntimeError(
                "Specify format (stl/step/f3d) or file_path with extension"
            )

        if fmt == "stl":
            if not body_name:
                raise RuntimeError("body_name required for STL export")
            return self.export_stl(body_name, file_path)
        if fmt in ("step", "stp"):
            if not body_name:
                raise RuntimeError("body_name required for STEP export")
            return self.export_step(body_name, file_path)
        if fmt == "f3d":
            return self.export_f3d(file_path)

        raise RuntimeError(f"Unknown format: {fmt}. Expected: stl, step, f3d")

    def import_mesh(
        self, file_path: str, component_name: str = None, units: str = "mm"
    ):
        """Import mesh file (STL/OBJ/3MF) as mesh body. Values returned in cm."""
        if not os.path.exists(file_path):
            raise RuntimeError(f"Mesh file not found: {file_path}")

        target = (
            self._component_by_name(component_name) if component_name else self._root()
        )

        unit_map = {
            "mm": adsk.fusion.MeshUnits.MillimeterMeshUnit,
            "cm": adsk.fusion.MeshUnits.CentimeterMeshUnit,
            "m": adsk.fusion.MeshUnits.MeterMeshUnit,
            "in": adsk.fusion.MeshUnits.InchMeshUnit,
            "ft": adsk.fusion.MeshUnits.FootMeshUnit,
        }
        if units not in unit_map:
            raise RuntimeError(
                f"Unknown units '{units}'. Expected one of: {sorted(unit_map)}"
            )

        try:
            # MeshBodies.add(fullFilename, units) — the current API.
            # Returns a MeshBodyList (a file can contain several bodies).
            mesh_list = target.meshBodies.add(file_path, unit_map[units])
        except AttributeError:
            # Pre-2025 builds exposed this as addByFile returning one body.
            mesh_list = None
            mesh_body = target.meshBodies.addByFile(file_path, unit_map[units])
        if mesh_list is not None:
            if mesh_list.count == 0:
                raise RuntimeError(f"No mesh bodies imported from {file_path}")
            mesh_body = mesh_list.item(0)

        bb = mesh_body.boundingBox
        return {
            "imported": True,
            "file_path": file_path,
            "mesh_name": mesh_body.name,
            "component": target.name,
            "units": units,
            "bounding_box": {
                "min": [bb.minPoint.x, bb.minPoint.y, bb.minPoint.z],
                "max": [bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z],
                "size": [
                    bb.maxPoint.x - bb.minPoint.x,
                    bb.maxPoint.y - bb.minPoint.y,
                    bb.maxPoint.z - bb.minPoint.z,
                ],
            },
        }

    def boolean_operation(
        self, target_body: str, tool_body: str, operation: str = "join"
    ):
        target = self._body_by_name(target_body)
        tool = self._body_by_name(tool_body)
        native_target, comp = self._native(target)
        native_tool, tool_comp = self._native(tool)
        if tool_comp == comp:
            target, tool = native_target, native_tool
        else:
            # Across components: proxies in root (Fusion files the feature
            # under the target's component).
            comp = self._root()

        combine_feats = comp.features.combineFeatures
        tool_coll = adsk.core.ObjectCollection.create()
        tool_coll.add(tool)

        op_map = {
            "join": adsk.fusion.FeatureOperations.JoinFeatureOperation,
            "cut": adsk.fusion.FeatureOperations.CutFeatureOperation,
            "intersect": adsk.fusion.FeatureOperations.IntersectFeatureOperation,
        }
        op = op_map.get(operation)
        if op is None:
            raise RuntimeError(
                f"Unknown boolean op '{operation}' — use join/cut/intersect"
            )

        inp = combine_feats.createInput(target, tool_coll)
        inp.operation = op
        feat = combine_feats.add(inp)
        return {
            "feature_name": feat.name,
            "operation": operation,
            "target": target_body,
            "tool": tool_body,
            "component": feat.parentComponent.name,
        }

    def delete_all(self):
        """Clear the active design: unwind the timeline, then sweep leftovers.

        Returns counts of what was removed plus any per-item failures.  Raises
        if the design is *not* empty afterwards — a caller that believes this
        succeeded will happily build on a dirty document.
        """
        design = self._design()
        root = design.rootComponent
        deleted = {
            "timeline": 0,
            "joints": 0,
            "occurrences": 0,
            "construction": 0,
            "bodies": 0,
            "sketches": 0,
        }
        errors = []

        def _sweep(collection, stage, counter):
            """Delete every item of *collection*, newest-first."""
            for i in range(collection.count - 1, -1, -1):
                name = "?"
                try:
                    item = collection.item(i)
                    name = getattr(item, "name", "?")
                    item.deleteMe()
                    deleted[counter] += 1
                except Exception as exc:
                    errors.append(
                        {
                            "stage": stage,
                            "index": i,
                            "name": name,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

        # Parametric: unwind newest-first.  NOTE: TimelineObject has no
        # deleteMe() — that method lives on the *entity* it wraps.  Calling it
        # on the TimelineObject raises AttributeError on every item.
        tl = getattr(design, "timeline", None)
        if tl is not None and tl.count > 0:
            for i in range(tl.count - 1, -1, -1):
                name = "?"
                try:
                    item = tl.item(i)
                    name = item.name
                    entity = item.entity
                    if entity is None:
                        errors.append(
                            {
                                "stage": "timeline",
                                "index": i,
                                "name": name,
                                "error": "timeline item exposes no entity",
                            }
                        )
                        continue
                    entity.deleteMe()
                    deleted["timeline"] += 1
                except Exception as exc:
                    errors.append(
                        {
                            "stage": "timeline",
                            "index": i,
                            "name": name,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

        # Direct mode has no timeline; the sweeps below also catch anything
        # the timeline pass could not remove.  Joints go before occurrences
        # because they reference them.
        _sweep(root.rigidGroups, "rigid_group", "joints")
        _sweep(root.asBuiltJoints, "as_built_joint", "joints")
        _sweep(root.joints, "joint", "joints")
        # Deleting an occurrence removes the component it references,
        # including its bodies and sketches.
        _sweep(root.occurrences, "occurrence", "occurrences")
        _sweep(root.constructionPlanes, "construction_plane", "construction")
        _sweep(root.constructionAxes, "construction_axis", "construction")
        _sweep(root.constructionPoints, "construction_point", "construction")

        for i in range(root.bRepBodies.count - 1, -1, -1):
            name = "?"
            try:
                body = root.bRepBodies.item(i)
                name = body.name
                body.deleteMe()
                deleted["bodies"] += 1
            except Exception as exc:
                errors.append(
                    {
                        "stage": "body",
                        "index": i,
                        "name": name,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        for i in range(root.sketches.count - 1, -1, -1):
            name = "?"
            try:
                sk = root.sketches.item(i)
                name = sk.name
                sk.deleteMe()
                deleted["sketches"] += 1
            except Exception as exc:
                errors.append(
                    {
                        "stage": "sketch",
                        "index": i,
                        "name": name,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        remaining = {
            "bodies": root.bRepBodies.count,
            "sketches": root.sketches.count,
            "occurrences": root.occurrences.count,
            "joints": (
                root.joints.count + root.asBuiltJoints.count + root.rigidGroups.count
            ),
            "construction": (
                root.constructionPlanes.count
                + root.constructionAxes.count
                + root.constructionPoints.count
            ),
            "timeline": tl.count if tl is not None else 0,
        }

        if any(v for k, v in remaining.items() if k != "timeline"):
            raise RuntimeError(
                f"delete_all did not clear the design — remaining: {remaining}. "
                f"Deleted: {deleted}. Failures: {errors}"
            )

        return {"deleted": deleted, "remaining": remaining, "errors": errors}

    def undo(self):
        design = self._design()
        type_before = design.designType

        cmd_def = self.ui.commandDefinitions.itemById("UndoCommand")
        if cmd_def is None:
            raise RuntimeError(
                "Undo command is not available in the current workspace. "
                "The design was NOT modified — delete the failed feature "
                "explicitly instead."
            )
        cmd_def.execute()

        # Check if undo silently switched design type (Parametric → Direct)
        adsk.doEvents()  # let Fusion process the undo
        type_after = design.designType
        if type_before != type_after:
            # Undo the undo — redo to restore original state
            redo_def = self.ui.commandDefinitions.itemById("RedoCommand")
            if redo_def:
                redo_def.execute()
                adsk.doEvents()
            parametric = adsk.fusion.DesignTypes.ParametricDesignType
            raise RuntimeError(
                f"Undo aborted: would have changed design type from "
                f"{'Parametric' if type_before == parametric else 'Direct'} to "
                f"{'Parametric' if type_after == parametric else 'Direct'}. "
                f"The undo was automatically reversed (redo). "
                f"Delete the failed feature explicitly instead."
            )

        return {"undone": True, "design_type": type_after}

    # ------------------------------------------------------------------
    # Direct Primitives (via TemporaryBRepManager)
    # ------------------------------------------------------------------

    def create_box(
        self,
        length: float,
        width: float,
        height: float,
        center_x: float = 0,
        center_y: float = 0,
        center_z: float = 0,
        component: str = None,
    ):
        comp = self._target_component(component)
        temp_brep = adsk.fusion.TemporaryBRepManager.get()

        # Box orientation matrix
        orient = adsk.core.OrientedBoundingBox3D.create(
            adsk.core.Point3D.create(center_x, center_y, center_z + height / 2),
            adsk.core.Vector3D.create(1, 0, 0),
            adsk.core.Vector3D.create(0, 1, 0),
            length,
            width,
            height,
        )

        box_body = temp_brep.createBox(orient)
        base_feat = comp.features.baseFeatures.add()
        base_feat.startEdit()
        comp.bRepBodies.add(box_body, base_feat)
        base_feat.finishEdit()

        return {
            "created": True,
            "length": length,
            "width": width,
            "height": height,
            "component": comp.name,
        }

    def create_box_parametric(
        self,
        length,
        width,
        height,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
        origin_z: float = 0.0,
        plane: str = "xy",
        component_name: str = None,
        body_name: str = None,
    ):
        """Parametric box: sketch rectangle + dimensions + extrude.

        length/width/height may be numeric (cm) or string expressions
        (e.g. 'boxL', '56 mm'). Expressions are applied via Fusion's
        parameter system so later changes to User Parameters propagate.
        """
        comp = (
            self._component_by_name(component_name) if component_name else self._root()
        )

        base_plane = self._construction_plane(plane, comp)
        if origin_z != 0:
            plane_input = comp.constructionPlanes.createInput()
            offset_val = adsk.core.ValueInput.createByReal(origin_z)
            plane_input.setByOffset(base_plane, offset_val)
            sketch_plane = comp.constructionPlanes.add(plane_input)
        else:
            sketch_plane = base_plane
        sketch = comp.sketches.add(sketch_plane)

        def _initial(val):
            return float(val) if isinstance(val, (int, float)) else 1.0

        p1 = adsk.core.Point3D.create(origin_x, origin_y, 0)
        p2 = adsk.core.Point3D.create(
            origin_x + _initial(length), origin_y + _initial(width), 0
        )
        rect = sketch.sketchCurves.sketchLines.addTwoPointRectangle(p1, p2)

        dims = sketch.sketchDimensions
        text_pt = adsk.core.Point3D.create(0, 0, 0)

        def _set_dim(dim, value):
            if isinstance(value, (int, float)):
                dim.parameter.value = float(value)
            else:
                dim.parameter.expression = str(value)

        bottom = rect.item(0)
        length_dim = dims.addDistanceDimension(
            bottom.startSketchPoint,
            bottom.endSketchPoint,
            adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation,
            text_pt,
        )
        _set_dim(length_dim, length)

        right = rect.item(1)
        width_dim = dims.addDistanceDimension(
            right.startSketchPoint,
            right.endSketchPoint,
            adsk.fusion.DimensionOrientations.VerticalDimensionOrientation,
            text_pt,
        )
        _set_dim(width_dim, width)

        if sketch.profiles.count == 0:
            raise RuntimeError("Rectangle sketch produced no profile")
        profile = sketch.profiles.item(0)

        ext_feats = comp.features.extrudeFeatures
        ext_input = ext_feats.createInput(
            profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        if isinstance(height, (int, float)):
            h_vi = adsk.core.ValueInput.createByReal(float(height))
        else:
            h_vi = adsk.core.ValueInput.createByString(str(height))
        ext_input.setDistanceExtent(False, h_vi)
        feat = ext_feats.add(ext_input)

        body = feat.bodies.item(0)
        if body_name:
            body.name = body_name

        return {
            "created": True,
            "body_name": body.name,
            "feature_name": feat.name,
            "sketch_name": sketch.name,
            "length": length,
            "width": width,
            "height": height,
            "origin": [origin_x, origin_y, origin_z],
            "plane": plane,
            "component": comp.name,
        }

    def create_cylinder(
        self,
        radius: float,
        height: float,
        base_x: float = 0,
        base_y: float = 0,
        base_z: float = 0,
        axis: str = "z",
        component: str = None,
    ):
        comp = self._target_component(component)
        temp_brep = adsk.fusion.TemporaryBRepManager.get()

        base_pt = adsk.core.Point3D.create(base_x, base_y, base_z)
        axis_vec = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis]
        top_pt = adsk.core.Point3D.create(
            base_x + axis_vec[0] * height,
            base_y + axis_vec[1] * height,
            base_z + axis_vec[2] * height,
        )

        cyl_body = temp_brep.createCylinderOrCone(base_pt, radius, top_pt, radius)

        base_feat = comp.features.baseFeatures.add()
        base_feat.startEdit()
        comp.bRepBodies.add(cyl_body, base_feat)
        base_feat.finishEdit()

        return {
            "created": True,
            "radius": radius,
            "height": height,
            "component": comp.name,
        }

    def create_sphere(
        self,
        radius: float,
        center_x: float = 0,
        center_y: float = 0,
        center_z: float = 0,
        component: str = None,
    ):
        comp = self._target_component(component)
        temp_brep = adsk.fusion.TemporaryBRepManager.get()

        center = adsk.core.Point3D.create(center_x, center_y, center_z)
        sphere_body = temp_brep.createSphere(center, radius)

        base_feat = comp.features.baseFeatures.add()
        base_feat.startEdit()
        comp.bRepBodies.add(sphere_body, base_feat)
        base_feat.finishEdit()

        return {"created": True, "radius": radius, "component": comp.name}

    def create_torus(
        self,
        major_radius: float,
        minor_radius: float,
        center_x: float = 0,
        center_y: float = 0,
        center_z: float = 0,
        axis: str = "z",
        component: str = None,
    ):
        comp = self._target_component(component)
        temp_brep = adsk.fusion.TemporaryBRepManager.get()

        center = adsk.core.Point3D.create(center_x, center_y, center_z)
        axis_vec = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis]
        axis_vector = adsk.core.Vector3D.create(*axis_vec)

        torus_body = temp_brep.createTorus(
            center, axis_vector, major_radius, minor_radius
        )

        base_feat = comp.features.baseFeatures.add()
        base_feat.startEdit()
        comp.bRepBodies.add(torus_body, base_feat)
        base_feat.finishEdit()

        return {
            "created": True,
            "major_radius": major_radius,
            "minor_radius": minor_radius,
            "component": comp.name,
        }

    # ------------------------------------------------------------------
    # Construction Geometry
    # ------------------------------------------------------------------

    def create_construction_plane(
        self,
        method: str,
        plane: str = None,
        offset: float = None,
        angle: float = None,
        edge_name: str = None,
        plane_one: str = None,
        plane_two: str = None,
        point_one: list = None,
        point_two: list = None,
        point_three: list = None,
    ):
        root = self._root()
        planes = root.constructionPlanes
        inp = planes.createInput()

        if method == "offset":
            inp.setByOffset(
                self._construction_plane(plane),
                adsk.core.ValueInput.createByReal(offset),
            )
        elif method == "angle":
            inp.setByAngle(
                self._construction_axis(edge_name or "x"),
                adsk.core.ValueInput.createByString(f"{angle} deg"),
                self._construction_plane(plane),
            )
        elif method == "midplane":
            inp.setByTwoPlanes(
                self._construction_plane(plane_one), self._construction_plane(plane_two)
            )
        elif method == "three_points":
            p1 = adsk.core.Point3D.create(*point_one)
            p2 = adsk.core.Point3D.create(*point_two)
            p3 = adsk.core.Point3D.create(*point_three)
            inp.setByThreePoints(p1, p2, p3)
        elif method == "tangent":
            raise RuntimeError("Tangent plane needs face selection—use execute_code")
        else:
            raise RuntimeError(f"Unknown method: {method}")

        plane_obj = planes.add(inp)
        return {"created": True, "name": plane_obj.name, "method": method}

    def create_construction_axis(
        self,
        method: str,
        point_one: list = None,
        point_two: list = None,
        plane_one: str = None,
        plane_two: str = None,
        body_name: str = None,
        edge_index: int = None,
    ):
        root = self._root()
        axes = root.constructionAxes
        inp = axes.createInput()

        if method == "two_points":
            p1 = adsk.core.Point3D.create(*point_one)
            p2 = adsk.core.Point3D.create(*point_two)
            inp.setByTwoPoints(p1, p2)
        elif method == "intersection":
            inp.setByTwoPlanes(
                self._construction_plane(plane_one), self._construction_plane(plane_two)
            )
        elif method == "edge":
            body = self._body_by_name(body_name)
            edge = body.edges.item(edge_index)
            inp.setByEdge(edge)
        elif method == "perpendicular_at_point":
            p1 = adsk.core.Point3D.create(*point_one)
            inp.setByPerpendicularAtPoint(self._construction_plane(plane_one), p1)
        else:
            raise RuntimeError(f"Unknown method: {method}")

        axis_obj = axes.add(inp)
        return {"created": True, "name": axis_obj.name, "method": method}

    def create_ucs(
        self,
        name: str = None,
        x: float = 0,
        y: float = 0,
        z: float = 0,
        angle_x: float = 0,
        angle_y: float = 0,
        angle_z: float = 0,
    ):
        """Create a User Coordinate System at (x, y, z), angles in degrees.

        The UCS API (May 2026, preview) is entity-based: the anchor must be
        a sketch point / vertex / construction point.  This creates a hidden
        reference sketch (``UCS_<name>_ref``) holding the anchor point; the
        UCS stays parametrically linked to it, so don't delete that sketch.
        (ConstructionPoint anchors are rejected by current builds, hence the
        sketch-point route.)
        """
        root = self._root()

        if z:
            plane_in = root.constructionPlanes.createInput()
            plane_in.setByOffset(
                root.xYConstructionPlane, adsk.core.ValueInput.createByReal(z)
            )
            base_plane = root.constructionPlanes.add(plane_in)
        else:
            base_plane = root.xYConstructionPlane

        sk = root.sketches.add(base_plane)
        pt = sk.sketchPoints.add(adsk.core.Point3D.create(x, y, 0))
        ref_name = f"UCS_{name or 'unnamed'}_ref"
        sk.name = ref_name
        sk.isVisible = False

        geom = adsk.fusion.UserCoordinateSystemGeometry_createByPoint(pt)
        inp = root.userCoordinateSystems.createInput(geom)
        if angle_x:
            inp.angleX = adsk.core.ValueInput.createByReal(math.radians(angle_x))
        if angle_y:
            inp.angleY = adsk.core.ValueInput.createByReal(math.radians(angle_y))
        if angle_z:
            inp.angleZ = adsk.core.ValueInput.createByReal(math.radians(angle_z))

        ucs = root.userCoordinateSystems.add(inp)
        if name:
            try:
                ucs.name = name
            except Exception:
                pass
        return {
            "name": ucs.name,
            "origin": [x, y, z],
            "angles_deg": [angle_x, angle_y, angle_z],
            "reference_sketch": ref_name,
        }

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def create_component(self, name: str, parent_name: str = None):
        parent_occ = self._occurrence(parent_name) if parent_name else None
        parent = parent_occ.component if parent_occ else self._root()

        occ = parent.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        occ.component.name = name
        if parent_occ is not None:
            occ = occ.createForAssemblyContext(parent_occ)
        # Fusion makes component names unique ("Part" -> "Part (1)"), so
        # report what it actually used.
        return {"created": True, "name": occ.component.name, **self._occ_info(occ)}

    _JOINT_MOTIONS = {
        "rigid": lambda inp, d: inp.setAsRigidJointMotion(),
        "revolute": lambda inp, d: inp.setAsRevoluteJointMotion(d.ZAxisJointDirection),
        "slider": lambda inp, d: inp.setAsSliderJointMotion(d.ZAxisJointDirection),
        "cylindrical": lambda inp, d: inp.setAsCylindricalJointMotion(
            d.ZAxisJointDirection
        ),
        "pin_slot": lambda inp, d: inp.setAsPinSlotJointMotion(
            d.ZAxisJointDirection, d.XAxisJointDirection
        ),
        "planar": lambda inp, d: inp.setAsPlanarJointMotion(d.ZAxisJointDirection),
        "ball": lambda inp, d: inp.setAsBallJointMotion(
            d.ZAxisJointDirection, d.XAxisJointDirection
        ),
    }

    def _set_joint_motion(self, inp, joint_type: str):
        """Motion about the joint's Z axis (a hole's axis, a face's normal)."""
        setter = self._JOINT_MOTIONS.get(joint_type)
        if setter is None:
            raise RuntimeError(
                f"Unknown joint type: {joint_type} — use one of "
                f"{', '.join(self._JOINT_MOTIONS)}"
            )
        setter(inp, adsk.fusion.JointDirections)

    def _joint_geometry(self, spec: dict):
        """(JointGeometry, occurrence) for {"ref": ..., "keypoint": ...}.

        Planar faces default to their center, other faces (holes, shafts)
        to their start end, edges to their center.
        """
        kp_types = adsk.fusion.JointKeyPointTypes
        keypoints = {
            "start": kp_types.StartKeyPoint,
            "end": kp_types.EndKeyPoint,
            "middle": kp_types.MiddleKeyPoint,
            "center": kp_types.CenterKeyPoint,
        }
        entity = self._resolve_ref(spec["ref"])
        occ = entity.assemblyContext
        if occ is None:
            raise RuntimeError(
                f"Ref '{spec['ref']}' is a root-component body — joints need "
                "geometry on an occurrence"
            )
        kp = spec.get("keypoint")
        if kp is not None and kp not in keypoints:
            raise RuntimeError(
                f"Unknown keypoint '{kp}' — use start, end, middle or center"
            )
        jg = adsk.fusion.JointGeometry
        if isinstance(entity, adsk.fusion.BRepEdge):
            return jg.createByCurve(entity, keypoints[kp or "center"]), occ
        if entity.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
            return jg.createByPlanarFace(entity, None, keypoints[kp or "center"]), occ
        return jg.createByNonPlanarFace(entity, keypoints[kp or "start"]), occ

    @staticmethod
    def _release_from_parent(occ):
        """Clear isGroundToParent, which is True by default and stops joints
        between copies of one component from solving ("conflicts with
        assembly relationships")."""
        if occ.assemblyContext is None and occ.isGroundToParent:
            occ.isGroundToParent = False

    @staticmethod
    def _joint_health(joint) -> dict:
        """A joint that can't solve is still created; Fusion only flags it."""
        tl = joint.timelineObject
        if tl is None:
            return {"health": "ok"}
        names = {0: "ok", 1: "warning", 2: "error"}
        result = {"health": names.get(tl.healthState, str(tl.healthState))}
        if tl.healthState != 0:
            result["warning"] = (tl.errorOrWarningMessage or "").split("\n")[0][:200]
        return result

    def add_joint(
        self,
        component_one: str = None,
        component_two: str = None,
        joint_type: str = "rigid",
        geometry_one: dict = None,
        geometry_two: dict = None,
        offset: float = 0,
        angle: float = 0,
        flip: bool = False,
    ):
        """Joint occurrence one onto two (one moves).  Each side is a face or
        edge ref + keypoint, or else the occurrence's origin."""
        sides = []
        for name, spec in (
            (component_one, geometry_one),
            (component_two, geometry_two),
        ):
            if spec:
                sides.append(self._joint_geometry(spec))
            elif name:
                occ = self._occurrence(name)
                origin = occ.component.originConstructionPoint
                point = origin.createForAssemblyContext(occ)
                sides.append((adsk.fusion.JointGeometry.createByPoint(point), occ))
            else:
                raise RuntimeError(
                    "Each side needs component_one/two (origin) or "
                    "geometry_one/two ({ref, keypoint})"
                )
        (geo1, occ1), (geo2, occ2) = sides
        for occ in (occ1, occ2):
            self._release_from_parent(occ)

        root = self._root()
        inp = root.joints.createInput(geo1, geo2)
        self._set_joint_motion(inp, joint_type)
        if offset:
            inp.offset = adsk.core.ValueInput.createByReal(offset)
        if angle:
            inp.angle = adsk.core.ValueInput.createByString(f"{angle} deg")
        inp.isFlipped = bool(flip)
        joint = root.joints.add(inp)

        box = self._bbox_union(self._all_bodies(occ1))
        return {
            "created": True,
            "joint_name": joint.name,
            "joint_type": joint_type,
            "occurrence_one": occ1.fullPathName,
            "occurrence_two": occ2.fullPathName,
            **self._joint_health(joint),
            "moved_bbox": {"min": box[0], "max": box[1]} if box else None,
        }

    def create_as_built_joint(
        self,
        component_one: str,
        component_two: str,
        joint_type: str = "rigid",
        geometry: dict = None,
    ):
        root = self._root()
        occ1 = self._occurrence(component_one)
        occ2 = self._occurrence(component_two)
        geo = None
        if geometry:
            geo, _ = self._joint_geometry(geometry)
        elif joint_type != "rigid":
            raise RuntimeError(
                f"A {joint_type} as-built joint needs 'geometry' "
                "({ref, keypoint}) to define its axis"
            )
        for occ in (occ1, occ2):
            self._release_from_parent(occ)

        inp = root.asBuiltJoints.createInput(occ1, occ2, geo)
        self._set_joint_motion(inp, joint_type)
        joint = root.asBuiltJoints.add(inp)
        return {
            "created": True,
            "joint_name": joint.name,
            "joint_type": joint_type,
            "occurrence_one": occ1.fullPathName,
            "occurrence_two": occ2.fullPathName,
            **self._joint_health(joint),
        }

    def create_rigid_group(self, component_names: list, include_children: bool = True):
        root = self._root()
        occs = adsk.core.ObjectCollection.create()
        names = []
        for name in component_names:
            occ = self._occurrence(name)
            occs.add(occ)
            names.append(occ.fullPathName)

        if occs.count < 2:
            raise RuntimeError("Need at least 2 components for rigid group")

        group = root.rigidGroups.add(occs, include_children)
        return {
            "created": True,
            "rigid_group_name": group.name,
            "component_count": occs.count,
            "occurrences": names,
        }

    def _faces_with_refs(self, occ):
        """Yield (ref, face proxy) for *occ* and every occurrence under it."""
        prefix = occ.fullPathName + "+"
        occs = [occ] + [
            o for o in self._root().allOccurrences if o.fullPathName.startswith(prefix)
        ]
        for o in occs:
            for bi in range(o.bRepBodies.count):
                faces = o.bRepBodies.item(bi).faces
                for fi in range(faces.count):
                    yield (
                        _occ_refs.make_ref(o.fullPathName, bi, "face", fi),
                        faces.item(fi),
                    )

    @staticmethod
    def _r(values, nd: int = 4) -> list:
        return [round(v, nd) for v in values]

    def find_holes(
        self,
        occurrence: str,
        diameter: float = None,
        tolerance: float = 0.01,
        near: list = None,
        limit: int = 50,
    ):
        """Concave cylindrical faces of an occurrence, in assembly coordinates.

        start/end are the exact points add_joint's start/end keypoints use.
        """
        occ = self._occurrence(occurrence)
        jg = adsk.fusion.JointGeometry
        kp = adsk.fusion.JointKeyPointTypes
        cyl = adsk.core.SurfaceTypes.CylinderSurfaceType
        rows, seen, by_d = [], set(), {}
        for ref, face in self._faces_with_refs(occ):
            g = face.geometry
            if g.surfaceType != cyl:
                continue
            p = face.pointOnFace
            _, n = face.evaluator.getNormalAtPoint(p)
            if not _hole_geom.is_concave_cylinder(
                (n.x, n.y, n.z),
                (p.x, p.y, p.z),
                (g.origin.x, g.origin.y, g.origin.z),
                (g.axis.x, g.axis.y, g.axis.z),
            ):
                continue
            d = round(2 * g.radius, 4)
            if diameter is not None and abs(d - diameter) > tolerance:
                continue
            s = jg.createByNonPlanarFace(face, kp.StartKeyPoint).origin
            e = jg.createByNonPlanarFace(face, kp.EndKeyPoint).origin
            start, end = self._r((s.x, s.y, s.z)), self._r((e.x, e.y, e.z))
            # A hole split into two half-faces shows up twice.
            key = (d, tuple(start), tuple(end))
            if key in seen:
                continue
            seen.add(key)
            length = max(sum((end[i] - start[i]) ** 2 for i in range(3)) ** 0.5, 1e-9)
            rows.append(
                {
                    "ref": ref,
                    "d": d,
                    "start": start,
                    "end": end,
                    "axis": self._r([(end[i] - start[i]) / length for i in range(3)]),
                    "length": round(length, 4),
                }
            )
            by_d[d] = by_d.get(d, 0) + 1

        rows = _hole_geom.sort_near(rows, near, "start")
        return {
            "occurrence": occ.fullPathName,
            "count": len(rows),
            "by_diameter": {str(k): v for k, v in sorted(by_d.items())},
            "holes": rows[:limit],
            "truncated": len(rows) > limit,
        }

    def list_faces(
        self,
        occurrence: str,
        type: str = "planar",
        near: list = None,
        limit: int = 50,
    ):
        """Planar and/or cylindrical faces with refs, in assembly coordinates.

        Planar faces are largest-first unless *near* is given.
        """
        if type not in ("planar", "cylindrical", "all"):
            raise RuntimeError("type must be planar, cylindrical or all")
        occ = self._occurrence(occurrence)
        st = adsk.core.SurfaceTypes
        rows = []
        for ref, face in self._faces_with_refs(occ):
            g = face.geometry
            p = face.pointOnFace
            if g.surfaceType == st.PlaneSurfaceType and type in ("planar", "all"):
                _, n = face.evaluator.getNormalAtPoint(p)
                c = face.centroid
                rows.append(
                    {
                        "ref": ref,
                        "type": "planar",
                        "normal": self._r((n.x, n.y, n.z)),
                        "center": self._r((c.x, c.y, c.z)),
                        "area": round(face.area, 4),
                    }
                )
            elif g.surfaceType == st.CylinderSurfaceType and type in (
                "cylindrical",
                "all",
            ):
                _, n = face.evaluator.getNormalAtPoint(p)
                o = g.origin
                rows.append(
                    {
                        "ref": ref,
                        "type": "cylindrical",
                        "d": round(2 * g.radius, 4),
                        "axis": self._r((g.axis.x, g.axis.y, g.axis.z)),
                        "center": self._r((o.x, o.y, o.z)),
                        "concave": _hole_geom.is_concave_cylinder(
                            (n.x, n.y, n.z),
                            (p.x, p.y, p.z),
                            (o.x, o.y, o.z),
                            (g.axis.x, g.axis.y, g.axis.z),
                        ),
                        "area": round(face.area, 4),
                    }
                )
        if near is None:
            rows.sort(key=lambda r: -r["area"])
        else:
            rows = _hole_geom.sort_near(rows, near, "center")
        return {
            "occurrence": occ.fullPathName,
            "count": len(rows),
            "faces": rows[:limit],
            "truncated": len(rows) > limit,
        }

    def ground_occurrence(self, occurrence: str, grounded: bool = True):
        occ = self._occurrence(occurrence)
        occ.isGrounded = bool(grounded)
        return {**self._occ_info(occ), "grounded": occ.isGrounded}

    def _joint_by_name(self, name: str):
        """Joint or as-built joint anywhere in the design, by name."""
        root = self._root()
        joints = list(root.allJoints) + list(root.allAsBuiltJoints)
        found = [j for j in joints if j.name == name]
        if not found:  # "revolute1" finds Fusion's "Revolute 1"
            key = name.replace(" ", "").lower()
            found = [j for j in joints if j.name.replace(" ", "").lower() == key]
        if len(found) == 1:
            return found[0]
        if found:
            raise RuntimeError(
                f"{len(found)} joints are named '{name}' (in different "
                "components) — rename one"
            )
        names = [j.name for j in joints]
        listed = ", ".join(names[:8]) + (", …" if len(names) > 8 else "")
        raise RuntimeError(f"Joint '{name}' not found. Joints: {listed or 'none'}")

    @staticmethod
    def _dof_axis(motion, prefix: str):
        """JointDirections value a degree of freedom moves along/about."""
        if prefix == "slide" and hasattr(motion, "slideDirection"):
            return motion.slideDirection
        return motion.rotationAxis  # cylindrical slides along its rotation axis

    def set_joint_value(
        self,
        joint: str,
        value: float = None,
        value2: float = None,
        limits: dict = None,
        limits2: dict = None,
        persist: bool = False,
    ):
        """Drive a joint: rotation in degrees, slide in cm.

        Temporary (default): the joint's motion value, like dragging it.
        Fusion resets it to 0 on the next recompute (any modeling call).
        persist=True writes the joint's angle/offset parameters instead,
        which survive recompute; motion values and limits then count from
        that new zero.
        """
        j = self._joint_by_name(joint)
        m = j.jointMotion
        jtype = _joint_vals.joint_type_name(m.jointType)
        steps = _joint_vals.plan(jtype, value, value2, limits, limits2)
        z_axis = adsk.fusion.JointDirections.ZAxisJointDirection
        is_as_built = j.objectType == adsk.fusion.AsBuiltJoint.classType()

        # Limits first: editing a limit resets the motion value to 0.
        for prefix, unit, _, lim in steps:
            if lim is None:
                continue
            jl = getattr(m, prefix + "Limits")
            for stem, enabled, v in _joint_vals.limit_updates(lim, unit):
                setattr(jl, f"is{stem}ValueEnabled", enabled)
                if enabled:
                    setattr(jl, f"{stem[0].lower()}{stem[1:]}Value", v)

        warnings = []
        for prefix, unit, v, _ in steps:
            if v is None:
                continue
            if persist:
                if is_as_built:
                    raise RuntimeError(
                        "As-built joints have no angle/offset to persist — "
                        "use persist=false, or rebuild it with add_joint"
                    )
                if self._dof_axis(m, prefix) != z_axis:
                    raise RuntimeError(
                        f"Can't persist the {prefix} of '{j.name}': it isn't "
                        "along the joint's Z axis — use persist=false"
                    )
                param = j.angle if prefix == "rotation" else j.offset
                param.value = _joint_vals.to_api(v, unit)
                setattr(m, prefix + "Value", 0.0)
            else:
                setattr(m, prefix + "Value", _joint_vals.to_api(v, unit))
                got = _joint_vals.from_api(getattr(m, prefix + "Value"), unit)
                if abs(got - v) > 1e-3:
                    warnings.append(
                        f"{prefix} {v} {unit} rejected (outside limits?); "
                        f"it stays at {got} {unit}"
                    )

        # Report every degree of freedom: motion value, plus the persistent
        # angle/offset when it acts along the same axis.
        values, limits_out = {}, {}
        for prefix, unit in _joint_vals.DOFS[jtype]:
            motion_v = getattr(m, prefix + "Value")
            base = 0.0
            if not is_as_built and self._dof_axis(m, prefix) == z_axis:
                param = j.angle if prefix == "rotation" else j.offset
                base = param.value if param is not None else 0.0
            values[f"{prefix}_{unit}"] = _joint_vals.from_api(base + motion_v, unit)
            jl = getattr(m, prefix + "Limits")
            lim = _joint_vals.limits_dict(
                {
                    "min": jl.isMinimumValueEnabled,
                    "max": jl.isMaximumValueEnabled,
                    "rest": jl.isRestValueEnabled,
                },
                {
                    "min": jl.minimumValue,
                    "max": jl.maximumValue,
                    "rest": jl.restValue,
                },
                unit,
            )
            if lim:
                limits_out[prefix] = lim

        occ1 = j.occurrenceOne
        box = self._bbox_union(self._all_bodies(occ1)) if occ1 else None
        result = {
            "joint": j.name,
            "type": jtype,
            "occurrence_one": occ1.fullPathName if occ1 else None,
            "occurrence_two": j.occurrenceTwo.fullPathName if j.occurrenceTwo else None,
            "values": values,
            "persisted": bool(persist),
            **self._joint_health(j),
            "moved_bbox": {"min": box[0], "max": box[1]} if box else None,
        }
        if limits_out:
            result["limits"] = limits_out
        if warnings:
            result["warnings"] = warnings
        return result

    def get_timeline(self, offset: int = 0, limit: int = 100, errors_only=False):
        """Compact timeline rows; collapsed groups are one row."""
        tl = self._design().timeline

        def raw(t, i):
            ent = t.entity
            return _tl_rows.row(
                i,
                t.name,
                ent.objectType if ent is not None else None,
                t.isSuppressed,
                t.healthState,
                t.errorOrWarningMessage if t.healthState in (1, 2) else None,
            )

        rows = []
        for i in range(tl.count):
            t = tl.item(i)
            if t.isGroup:
                g = adsk.fusion.TimelineGroup.cast(t)
                kids = []
                for k in range(g.count):
                    kid = raw(g.item(k), i)
                    kid["k"] = k
                    kids.append(kid)
                rows.append(_tl_rows.group_row(i, t.name, t.isSuppressed, kids))
            else:
                rows.append(raw(t, i))

        selected, matching = _tl_rows.page(rows, offset, limit, errors_only)
        return {
            "count": tl.count,
            "marker_position": tl.markerPosition,
            "problems": sum(1 for r in rows if _tl_rows.is_problem(r)),
            "items": selected,
            "truncated": offset + len(selected) < matching,
        }

    @staticmethod
    def _placement(translation=None, axis=None, angle: float = 0):
        """Matrix: rotate *angle* deg about *axis* through the origin, then
        translate (cm)."""
        m = adsk.core.Matrix3D.create()
        if angle:
            ax = adsk.core.Vector3D.create(*(axis or [0, 0, 1]))
            m.setToRotation(math.radians(angle), ax, adsk.core.Point3D.create(0, 0, 0))
        if translation:
            m.translation = adsk.core.Vector3D.create(*translation)
        return m

    @staticmethod
    def _transform_dict(m) -> dict:
        t = m.translation
        return {"translation": [round(t.x, 6), round(t.y, 6), round(t.z, 6)]}

    def _attached(self, occ) -> list:
        """Joint / rigid-group names that reference *occ* or anything under it."""
        root = self._root()
        path = occ.fullPathName

        def _hits(o):
            if o is None:
                return False
            p = o.fullPathName
            return p == path or p.startswith(path + "+")

        names = []
        for j in list(root.allJoints) + list(root.allAsBuiltJoints):
            if _hits(j.occurrenceOne) or _hits(j.occurrenceTwo):
                names.append(j.name)
        for g in root.allRigidGroups:
            if any(_hits(o) for o in g.occurrences):
                names.append(g.name)
        return names

    def _parametric(self) -> bool:
        return self._design().designType == adsk.fusion.DesignTypes.ParametricDesignType

    def _add_existing(self, parent_comp, comp, matrix):
        """New occurrence of *comp* at *matrix* (native, in *parent_comp*)."""
        occ = parent_comp.occurrences.addExistingComponent(comp, matrix)
        if not self._parametric():
            # Direct designs compose *matrix* with the first occurrence's
            # transform; set it explicitly.
            occ.transform2 = matrix
        return occ

    def _place(self, occ, matrix):
        """Give *occ* a lasting transform; returns the (possibly new) occurrence.

        Parametric designs reset Occurrence.transform2 on the next recompute
        (design.snapshots.add() resets it too), so there the occurrence is
        re-inserted at *matrix* and the old one deleted.  That renumbers the
        occurrence (Plate:1 -> Plate:2) and would drop joints, so callers
        check _attached() first.
        """
        native = occ.nativeObject or occ
        if not self._parametric():
            native.transform2 = matrix
            return occ

        parent_ctx = occ.assemblyContext
        if parent_ctx is None:
            grounded = native.isGrounded
            new = self._root().occurrences.addExistingComponent(
                native.component, matrix
            )
            native.deleteMe()
            new.isGrounded = grounded
            return new
        # isGrounded is unavailable on sub-component occurrences.
        new = parent_ctx.component.occurrences.addExistingComponent(
            native.component, matrix
        )
        native.deleteMe()
        return new.createForAssemblyContext(parent_ctx)

    def move_occurrence(
        self,
        occurrence: str,
        translation: list = None,
        axis: list = None,
        angle: float = 0,
        relative: bool = False,
    ):
        occ = self._occurrence(occurrence)
        attached = self._attached(occ)
        if attached:
            raise RuntimeError(
                f"Occurrence '{occ.fullPathName}' is held by "
                f"{', '.join(attached)} — joints position it; delete or "
                "edit those instead of moving it"
            )

        native = occ.nativeObject or occ
        if relative:
            # Rotate about the occurrence's own origin, then shift.
            m = native.transform2.copy()
            if angle:
                rot = adsk.core.Matrix3D.create()
                rot.setToRotation(
                    math.radians(angle),
                    adsk.core.Vector3D.create(*(axis or [0, 0, 1])),
                    m.translation.asPoint(),
                )
                m.transformBy(rot)
            if translation:
                m.transformBy(self._placement(translation))
        else:
            m = self._placement(translation, axis, angle)

        previous = occ.fullPathName
        occ = self._place(occ, m)
        box = self._bbox_union(self._all_bodies(occ))
        return {
            **self._occ_info(occ),
            "previous_occurrence": previous,
            **self._transform_dict((occ.nativeObject or occ).transform2),
            "bbox": {"min": box[0], "max": box[1]} if box else None,
        }

    _IMPORT_SOURCE_ATTR = ("fusion360mcp", "source")

    def insert_part(
        self,
        file_path: str,
        name: str = None,
        parent: str = None,
        translation: list = None,
        axis: list = None,
        angle: float = 0,
    ):
        """Insert a STEP/f3d file as an occurrence; reuse it if already imported."""
        path = os.path.abspath(os.path.expanduser(file_path))
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".step", ".stp", ".f3d"):
            raise RuntimeError(
                f"Unsupported file type '{ext}' — insert_part takes .step, "
                ".stp or .f3d (use import_mesh for STL/OBJ/3MF)"
            )
        if not os.path.exists(path):
            raise RuntimeError(f"File not found: {path}")

        design = self._design()
        parent_occ = self._occurrence(parent) if parent else None
        parent_comp = parent_occ.component if parent_occ else self._root()
        matrix = self._placement(translation, axis, angle)

        group, attr_name = self._IMPORT_SOURCE_ATTR
        comp = None
        for c in design.allComponents:
            attr = c.attributes.itemByName(group, attr_name)
            if attr is not None and attr.value == path:
                comp = c
                break

        if comp is not None:
            occ = self._add_existing(parent_comp, comp, matrix)
            reused = True
        else:
            im = self.app.importManager
            opts = (
                im.createFusionArchiveImportOptions(path)
                if ext == ".f3d"
                else im.createSTEPImportOptions(path)
            )
            imported = im.importToTarget2(opts, parent_comp)
            if imported is None or imported.count == 0:
                raise RuntimeError(f"Import produced no occurrence: {path}")
            occ = imported.item(0)
            comp = occ.component
            stem = os.path.splitext(os.path.basename(path))[0]
            # Fusion-exported STEP files come in as "(Unsaved) (n)".
            if name:
                comp.name = name
            elif comp.name.startswith("(Unsaved)"):
                comp.name = stem
            comp.partNumber = stem
            comp.attributes.add(group, attr_name, path)
            reused = False

        # importToTarget2 already returns a proxy in the parent's context.
        if parent_occ is not None and occ.assemblyContext is None:
            occ = occ.createForAssemblyContext(parent_occ)
        # An import always lands at identity; reuse was placed on insert.
        if not reused and not matrix.isEqualTo(adsk.core.Matrix3D.create()):
            occ = self._place(occ, matrix)

        box = self._bbox_union(self._all_bodies(occ))
        return {
            **self._occ_info(occ),
            "reused": reused,
            "part_number": comp.partNumber,
            "bodies": comp.bRepBodies.count,
            "child_occurrences": occ.childOccurrences.count,
            "bbox": {"min": box[0], "max": box[1]} if box else None,
        }

    # Interference below this (cm³) is meshing noise, not a real overlap.
    _INTERFERENCE_EPS = 1e-5

    def _hole_face(self, ref: str, occ):
        """Cylindrical face for *ref*, checked to belong to *occ*."""
        face = self._resolve_ref(ref)
        if not isinstance(face, adsk.fusion.BRepFace) or (
            face.geometry.surfaceType != adsk.core.SurfaceTypes.CylinderSurfaceType
        ):
            raise RuntimeError(f"'{ref}' is not a hole — use a ref from find_holes")
        ctx = face.assemblyContext
        path = occ.fullPathName
        if ctx is None or not (
            ctx.fullPathName == path or ctx.fullPathName.startswith(path + "+")
        ):
            raise RuntimeError(f"Hole '{ref}' is not on occurrence '{path}'")
        return face

    @staticmethod
    def _hole_ends(face):
        """(start, end) keypoints of a hole face in assembly coordinates."""
        jg, kp = adsk.fusion.JointGeometry, adsk.fusion.JointKeyPointTypes
        s = jg.createByNonPlanarFace(face, kp.StartKeyPoint).origin
        e = jg.createByNonPlanarFace(face, kp.EndKeyPoint).origin
        return (s.x, s.y, s.z), (e.x, e.y, e.z)

    def _pair_interference(self, occ_a, occ_b) -> float:
        """Total overlap volume (cm³) between two occurrences' bodies."""
        bodies = adsk.core.ObjectCollection.create()
        paths_a = set()
        for b in self._all_bodies(occ_a):
            bodies.add(b)
            paths_a.add(b.assemblyContext.fullPathName)
        for b in self._all_bodies(occ_b):
            bodies.add(b)
        if bodies.count < 2:
            return 0.0
        design = self._design()
        inp = design.createInterferenceInput(bodies)
        inp.areCoincidentFacesIncluded = False
        results = design.analyzeInterference(inp)
        total = 0.0
        for i in range(results.count if results is not None else 0):
            r = results.item(i)
            # Skip overlaps inside one part (two bodies of a multi-body STEP).
            sides = {
                (e.assemblyContext.fullPathName in paths_a)
                for e in (r.entityOne, r.entityTwo)
                if e.assemblyContext is not None
            }
            if len(sides) == 1:
                continue
            total += r.interferenceBody.volume
        return total

    def join_on_holes(
        self,
        occ_a: str,
        hole_a: str,
        occ_b: str,
        hole_b: str,
        rotation: float = 0,
        joint_type: str = "rigid",
        flip: bool = False,
        offset: float = 0,
    ):
        """Bolt occ_a (moves) to occ_b (fixed) hole-to-hole, outside occ_b."""
        mover = self._occurrence(occ_a)
        fixed = self._occurrence(occ_b)
        if mover.fullPathName == fixed.fullPathName:
            raise RuntimeError("occ_a and occ_b are the same occurrence")
        face_a = self._hole_face(hole_a, mover)
        face_b = self._hole_face(hole_b, fixed)
        mover_box = self._bbox_union(self._all_bodies(mover))
        fixed_box = self._bbox_union(self._all_bodies(fixed))
        sides = _asm.pick_join_sides(
            self._hole_ends(face_b), fixed_box, self._hole_ends(face_a), mover_box
        )

        kp = adsk.fusion.JointKeyPointTypes
        keypoints = {"start": kp.StartKeyPoint, "end": kp.EndKeyPoint}
        jg = adsk.fusion.JointGeometry
        for occ in (mover, fixed):
            self._release_from_parent(occ)
        root = self._root()

        def _add(flipped: bool):
            inp = root.joints.createInput(
                jg.createByNonPlanarFace(face_a, keypoints[sides["mover"]]),
                jg.createByNonPlanarFace(face_b, keypoints[sides["fixed"]]),
            )
            self._set_joint_motion(inp, joint_type)
            if offset:
                inp.offset = adsk.core.ValueInput.createByReal(offset)
            if rotation:
                inp.angle = adsk.core.ValueInput.createByString(f"{rotation} deg")
            inp.isFlipped = flipped
            return root.joints.add(inp)

        joint = _add(sides["flip"] != bool(flip))
        volume = self._pair_interference(mover, fixed)
        auto_flipped = False
        if volume > self._INTERFERENCE_EPS:
            # Joint.isFlipped can't be edited without rolling the timeline
            # back, so replace the joint with a flipped one.
            was_flipped = joint.isFlipped
            joint.deleteMe()
            joint = _add(not was_flipped)
            flipped_volume = self._pair_interference(mover, fixed)
            if flipped_volume < volume:
                volume, auto_flipped = flipped_volume, True
            else:
                joint.deleteMe()
                joint = _add(was_flipped)

        box = self._bbox_union(self._all_bodies(mover))
        return {
            "joint": joint.name,
            "joint_type": joint_type,
            "moved": mover.fullPathName,
            "fixed": fixed.fullPathName,
            "keypoints": {"moved": sides["mover"], "fixed": sides["fixed"]},
            "side_from": sides["reason"],
            "flipped": joint.isFlipped,
            "auto_flipped": auto_flipped,
            **self._joint_health(joint),
            "moved_bbox": {"min": self._r(box[0]), "max": self._r(box[1])}
            if box
            else None,
            "interference_volume": round(volume, 6),
        }

    # JointTypes enum value -> the joint_type names the tools take.
    _JOINT_TYPE_NAMES = {
        0: "rigid",
        1: "revolute",
        2: "slider",
        3: "cylindrical",
        4: "pin_slot",
        5: "planar",
        6: "ball",
    }

    def _joint_row(self, j, as_built: bool) -> dict:
        m = j.jointMotion
        jt = self._JOINT_TYPE_NAMES.get(m.jointType, str(m.jointType))
        one, two = j.occurrenceOne, j.occurrenceTwo
        row = {
            "name": j.name,
            "type": jt,
            "one": one.fullPathName if one else None,
            "two": two.fullPathName if two else None,
        }
        if as_built:
            row["as_built"] = True
        rot = jt in ("revolute", "cylindrical", "pin_slot")
        slide = jt in ("slider", "cylindrical", "pin_slot")
        values = []
        if rot:
            values.append(round(math.degrees(m.rotationValue), 3))
        if slide:
            values.append(round(m.slideValue, 4))
        if values:
            row["value"] = values[0] if len(values) == 1 else values
        limits = {}
        for kind, lim in (
            ("rotation", m.rotationLimits if rot else None),
            ("slide", m.slideLimits if slide else None),
        ):
            if lim is None:
                continue
            to_unit = math.degrees if kind == "rotation" else float
            ends = {}
            if lim.isMinimumValueEnabled:
                ends["min"] = round(to_unit(lim.minimumValue), 4)
            if lim.isMaximumValueEnabled:
                ends["max"] = round(to_unit(lim.maximumValue), 4)
            if ends:
                limits[kind] = ends
        if limits:
            row["limits"] = limits
        row["suppressed"] = bool(j.isSuppressed)
        row.update(self._joint_health(j))
        return row

    def list_joints(self):
        """Joints and as-built joints. Values: revolute deg, slider cm,
        cylindrical/pin_slot [deg, cm]."""
        root = self._root()
        rows = [self._joint_row(j, False) for j in root.allJoints]
        rows += [self._joint_row(j, True) for j in root.allAsBuiltJoints]
        return {"count": len(rows), "joints": rows}

    @staticmethod
    def _own_mass_kg(comp) -> float:
        """Mass of a component's own bodies (not its sub-occurrences)."""
        acc = adsk.fusion.CalculationAccuracy.LowCalculationAccuracy
        if comp.occurrences.count == 0:
            return comp.getPhysicalProperties(acc).mass
        return sum(b.getPhysicalProperties(acc).mass for b in comp.bRepBodies)

    def get_bom(self):
        """Occurrences grouped by component; mass computed once per component."""
        root = self._root()
        groups = {}
        for occ in root.allOccurrences:
            comp = occ.component
            groups.setdefault(comp.name, [comp, []])[1].append(occ.fullPathName)

        classes = _asm.part_classes()
        class_counts = {c: 0 for c in classes}
        rows, total_g, total_count = [], 0.0, 0
        if root.bRepBodies.count:
            g = self._own_mass_kg(root) * 1000
            total_g += g
            rows.append({"component": root.name, "count": 1, "mass_g": round(g, 1)})
        for name, (comp, paths) in groups.items():
            if comp.bRepBodies.count == 0:
                continue
            g = self._own_mass_kg(comp) * 1000
            row = {"component": name}
            if comp.partNumber and comp.partNumber != name:
                row["part_number"] = comp.partNumber
            row["count"] = len(paths)
            row["mass_g"] = round(g, 1)
            cls = _asm.classify_part(comp.partNumber, name, classes)
            if cls:
                row["class"] = cls
                class_counts[cls] += len(paths)
            if len(paths) <= 5:
                row["occurrences"] = paths
            rows.append(row)
            total_g += g * len(paths)
            total_count += len(paths)
        rows.sort(key=lambda r: (-r["count"], r["component"]))
        return {
            "parts": rows,
            "unique": len(rows),
            "total_count": total_count,
            "total_mass_g": round(total_g, 1),
            **{f"{c}_count": n for c, n in class_counts.items()},
        }

    def _class_counts(self, occs) -> dict:
        """{"motor": n, "servo": n} over occurrences (each copy counts)."""
        counts = {}
        for occ in occs:
            comp = occ.component
            cls = _asm.classify_part(comp.partNumber, comp.name)
            if cls:
                counts[cls] = counts.get(cls, 0) + 1
        return counts

    def check_robot_rules(
        self,
        subsystem: str = None,
        envelope: dict = None,
        budget: dict = None,
        up: str = "z",
        rules: dict = None,
    ):
        """Size and actuator rules for the whole robot, or one subsystem."""
        root = self._root()
        checks = []
        if subsystem is None:
            lim = _rules.limits_from(rules or _rules.load_constraints())
            box = self._bbox_union(self._all_bodies())
            if box is None:
                raise RuntimeError("The design has no bodies to check")
            size = [box[1][i] - box[0][i] for i in range(3)]
            for name, key, vertical in (
                ("starting", "starting_box", None),
                ("expansion", "expansion_box", lim["expansion_vertical"]),
            ):
                if lim[key]:
                    res = _rules.fits_box(size, lim[key], up, vertical)
                    checks.append(
                        {
                            "rule": lim[f"{name}_rule"],
                            "check": f"fits {name} box {lim[key]} cm",
                            **res,
                        }
                    )
            counts = self._class_counts(root.allOccurrences)
            for cls in ("motor", "servo"):
                limit = lim[f"max_{cls}s"]
                if limit is not None:
                    n = counts.get(cls, 0)
                    checks.append(
                        {
                            "rule": lim["actuator_rule"],
                            "check": f"{cls}s ≤ {limit}",
                            "ok": n <= limit,
                            "value": n,
                        }
                    )
            scope = {"scope": "robot", "season": lim["season"]}
        else:
            occ = self._occurrence(subsystem)
            box = self._bbox_union(self._all_bodies(occ))
            if box is None:
                raise RuntimeError(f"'{subsystem}' has no bodies to check")
            size = [box[1][i] - box[0][i] for i in range(3)]
            if envelope:
                checks.append(
                    {"check": "inside envelope", **_rules.envelope_check(box, envelope)}
                )
            # Interference only with top-level neighbours whose box touches ours.
            top = occ
            while top.assemblyContext is not None:
                top = top.assemblyContext
            near = []
            for other in root.occurrences:
                if other.fullPathName == top.fullPathName:
                    continue
                obox = self._bbox_union(self._all_bodies(other))
                if obox is not None and _rules.boxes_overlap(box, obox):
                    near.append(other.fullPathName)
            hits = []
            if near:
                res = self.check_interference([occ.fullPathName, *near])
                mine = occ.fullPathName
                for hit in res["interferences"]:
                    paths = hit["occurrences"]
                    if any(p.startswith(mine) for p in paths) and any(
                        not p.startswith(mine) for p in paths
                    ):
                        hits.append(
                            {"occurrences": paths, "volume": round(hit["volume"], 4)}
                        )
            checks.append(
                {
                    "check": "no interference with other top-level components",
                    "ok": not hits,
                    "checked": near,
                    **({"hits": hits} if hits else {}),
                }
            )
            if budget:
                counts = self._class_counts([occ, *occ.component.allOccurrences])
                checks.extend(_rules.count_check(counts, budget))
            scope = {"scope": "subsystem", **self._occ_info(occ)}
        return {
            **scope,
            # Not "ok": that key is the response envelope's success flag.
            "passed": all(c["ok"] for c in checks),
            "checks": checks,
            "size_cm": [round(s, 2) for s in size],
            "size_in": [round(s / 2.54, 2) for s in size],
            "note": "Sizes are for the current joint pose.",
        }

    # ------------------------------------------------------------------
    # Inspection / Analysis
    # ------------------------------------------------------------------

    def measure_distance(self, entity_one: str, entity_two: str):
        root = self._root()

        def get_entity(name):
            # Try as body
            for i in range(root.bRepBodies.count):
                b = root.bRepBodies.item(i)
                if b.name == name:
                    return b
            # Try as point (x,y,z format)
            if "," in name:
                coords = [float(x.strip()) for x in name.split(",")]
                return adsk.core.Point3D.create(*coords)
            raise RuntimeError(f"Entity '{name}' not found")

        e1 = get_entity(entity_one)
        e2 = get_entity(entity_two)

        measure = self.app.measureManager
        result = measure.measureMinimumDistance(e1, e2)
        return {
            "distance": result.value,
            "point_one": [
                result.pointOnEntityOne.x,
                result.pointOnEntityOne.y,
                result.pointOnEntityOne.z,
            ],
            "point_two": [
                result.pointOnEntityTwo.x,
                result.pointOnEntityTwo.y,
                result.pointOnEntityTwo.z,
            ],
        }

    def measure_angle(self, entity_one: str, entity_two: str):
        root = self._root()

        def get_entity(name):
            for i in range(root.bRepBodies.count):
                b = root.bRepBodies.item(i)
                if b.name == name:
                    return b.faces.item(0)  # First face
            raise RuntimeError(f"Entity '{name}' not found")

        e1 = get_entity(entity_one)
        e2 = get_entity(entity_two)

        measure = self.app.measureManager
        result = measure.measureAngle(e1, e2)
        return {"angle_degrees": math.degrees(result.value)}

    def get_physical_properties(self, body_name: str, accuracy: str = "medium"):
        body = self._body_by_name(body_name)

        accuracy_map = {
            "low": adsk.fusion.CalculationAccuracy.LowCalculationAccuracy,
            "medium": adsk.fusion.CalculationAccuracy.MediumCalculationAccuracy,
            "high": adsk.fusion.CalculationAccuracy.HighCalculationAccuracy,
            "very_high": adsk.fusion.CalculationAccuracy.VeryHighCalculationAccuracy,
        }
        acc = accuracy_map.get(accuracy, accuracy_map["medium"])

        props = body.getPhysicalProperties(acc)
        return {
            "mass": props.mass,
            "volume": props.volume,
            "area": props.area,
            "density": props.density,
            "center_of_mass": [
                props.centerOfMass.x,
                props.centerOfMass.y,
                props.centerOfMass.z,
            ],
        }

    def create_section_analysis(self, plane: str = "yz", offset: float = 0):
        root = self._root()
        analyses = root.analyses

        inp = analyses.createInput()
        inp.plane = self._construction_plane(plane)
        if offset != 0:
            inp.distance = adsk.core.ValueInput.createByReal(offset)

        analyses.add(inp)
        return {"created": True, "plane": plane, "offset": offset}

    def check_interference(
        self, component_names: list, include_coincident_faces: bool = False
    ):
        bodies = adsk.core.ObjectCollection.create()
        # (body name, bbox, occurrence path) per input body. Interference
        # results are temporary bodies with no assembly context, so they are
        # mapped back to occurrences whose body box contains the overlap.
        inputs = []
        for name in component_names:
            for b in self._all_bodies(self._occurrence(name)):
                bodies.add(b)
                inputs.append(
                    (b.name, self._bbox_union([b]), b.assemblyContext.fullPathName)
                )

        if bodies.count < 2:
            raise RuntimeError("Need at least 2 components with bodies")

        # Interference analysis is a Design-level API.  Component has no
        # interfere() method at all, so the previous call raised
        # AttributeError for every caller.
        design = self._design()
        inp = design.createInterferenceInput(bodies)
        inp.areCoincidentFacesIncluded = bool(include_coincident_faces)
        interference = design.analyzeInterference(inp)

        results = []
        if interference is not None:
            for i in range(interference.count):
                result = interference.item(i)
                one, two = result.entityOne, result.entityTwo
                overlap = self._bbox_union([result.interferenceBody])
                occs = sorted(
                    {
                        path
                        for body_name, box, path in inputs
                        if body_name in (one.name, two.name)
                        and _occ_refs.box_contains(box, overlap)
                    }
                )
                results.append(
                    {
                        "body_one": one.name,
                        "body_two": two.name,
                        "occurrences": occs,
                        "volume": result.interferenceBody.volume,
                    }
                )

        return {"interferences": results, "count": len(results)}

    def compare_meshes(self, mesh_name_a: str, mesh_name_b: str):
        """Compare two mesh bodies; report per-node deviation statistics.

        Uses PolygonMesh.compareWith (Fusion 2026): for every node in mesh A,
        the signed distance to the closest point on mesh B (cm).  Positive
        means the node lies on the surface-normal side of B.
        """
        design = self._design()
        root = design.rootComponent

        def _mesh_body_by_name(name):
            for i in range(root.meshBodies.count):
                mb = root.meshBodies.item(i)
                if mb.name == name:
                    return mb
            raise RuntimeError(
                f"Mesh body '{name}' not found in root component. "
                "Use get_scene_info to list mesh bodies."
            )

        body_a = _mesh_body_by_name(mesh_name_a)
        body_b = _mesh_body_by_name(mesh_name_b)

        mesh_a = body_a.mesh or body_a.displayMesh
        mesh_b = body_b.mesh or body_b.displayMesh
        if mesh_a is None or mesh_b is None:
            raise RuntimeError("Could not obtain polygon mesh data")

        deviations = list(mesh_a.compareWith(mesh_b))
        if not deviations:
            raise RuntimeError("compareWith returned no deviation data")

        abs_dev = [abs(d) for d in deviations]
        n = len(deviations)
        mean_abs = sum(abs_dev) / n
        rms = math.sqrt(sum(d * d for d in deviations) / n)
        return {
            "mesh_a": mesh_name_a,
            "mesh_b": mesh_name_b,
            "node_count": n,
            "min_deviation": min(deviations),
            "max_deviation": max(deviations),
            "mean_abs_deviation": mean_abs,
            "rms_deviation": rms,
            "max_abs_deviation": max(abs_dev),
            "units": "cm",
        }

    # ------------------------------------------------------------------
    # Appearance
    # ------------------------------------------------------------------

    def set_appearance(
        self,
        target_name: str,
        appearance_name: str,
        target_type: str = "body",
        face_index: int = None,
    ):
        # Find appearance in library — try both known library names
        app_lib = self.app.materialLibraries.itemByName("Fusion Appearance Library")
        if app_lib is None:
            app_lib = self.app.materialLibraries.itemByName(
                "Fusion 360 Appearance Library"
            )
        if app_lib is None:
            # Fall back to searching all libraries
            for i in range(self.app.materialLibraries.count):
                lib = self.app.materialLibraries.item(i)
                if lib.appearances.count > 0:
                    app_lib = lib
                    break
        if app_lib is None:
            raise RuntimeError("No appearance library found")

        appearance = None
        for i in range(app_lib.appearances.count):
            app = app_lib.appearances.item(i)
            if app.name == appearance_name:
                appearance = app
                break

        if not appearance:
            raise RuntimeError(f"Appearance '{appearance_name}' not found")

        # Library appearances must be copied into the design before
        # assignment — assigning a library appearance directly is
        # version-dependent and known to fail on recent Fusion builds.
        design = self._design()
        local = design.appearances.itemByName(appearance.name)
        if local is None:
            local = design.appearances.addByCopy(appearance, appearance.name)
        if local is None:
            raise RuntimeError(
                f"Could not copy appearance '{appearance_name}' into the design"
            )

        if target_type == "body":
            body = self._body_by_name(target_name)
            body.appearance = local
        elif target_type == "component":
            comp = self._component_by_name(target_name)
            comp.appearance = local
        elif target_type == "face":
            body = self._body_by_name(target_name)
            face = body.faces.item(face_index)
            face.appearance = local

        return {"applied": True, "target": target_name, "appearance": appearance_name}

    def set_color(
        self,
        body_name: str,
        red: int,
        green: int,
        blue: int,
        opacity: float = 1.0,
    ):
        """Assign a flat RGB color to a body via a design-local appearance.

        Uses the Appearances.add + Appearance.color API (July 2026), so no
        library copy is needed.  Appearances are reused when the same color
        is requested again.  opacity 1.0 = fully opaque, 0.0 = invisible.
        """
        body = self._body_by_name(body_name)
        design = self._design()

        red = max(0, min(255, int(red)))
        green = max(0, min(255, int(green)))
        blue = max(0, min(255, int(blue)))
        alpha = max(0, min(255, round(opacity * 255)))

        color_name = f"MCP_{red}_{green}_{blue}_{alpha}"
        appearance = design.appearances.itemByName(color_name)
        if appearance is None:
            appearance = design.appearances.add(color_name)
            appearance.color = adsk.core.Color.create(red, green, blue, alpha)

        body.appearance = appearance
        return {
            "body": body_name,
            "color": [red, green, blue],
            "opacity": alpha / 255.0,
            "appearance": color_name,
        }

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def get_parameters(self):
        design = self._design()
        params = []
        for param in design.userParameters:
            params.append(
                {
                    "name": param.name,
                    "value": param.value,
                    "expression": param.expression,
                    "unit": param.unit,
                    "comment": param.comment,
                }
            )
        return {"parameters": params, "count": len(params)}

    def create_parameter(self, name: str, value: float, unit: str, comment: str = None):
        design = self._design()
        params = design.userParameters
        unit = _param_units.normalise_unit(unit)
        # createByReal() is read in internal units (cm, radians), so a caller
        # asking for 1000 mm would get 1000 cm labelled "mm".
        value_input = _param_units.build_value_input(
            value,
            unit,
            adsk.core.ValueInput.createByString,
            adsk.core.ValueInput.createByReal,
        )
        param = params.add(name, value_input, unit, comment or "")
        return {
            "created": True,
            "name": name,
            "value": value,
            "unit": unit,
            "expression": param.expression,
        }

    def set_parameter(self, name: str, value: float):
        design = self._design()
        param = design.userParameters.itemByName(name)
        if not param:
            raise RuntimeError(f"Parameter '{name}' not found")
        # Assigning .value would be read in internal units, silently rescaling
        # any parameter whose unit is not the internal one. Write the
        # expression, in the unit the parameter already declares.
        unit = _param_units.normalise_unit(param.unit)
        param.expression = _param_units.expression_for(value, unit)
        return {
            "updated": True,
            "name": name,
            "value": value,
            "unit": unit,
            "expression": param.expression,
        }

    def delete_parameter(self, name: str):
        design = self._design()
        param = design.userParameters.itemByName(name)
        if not param:
            raise RuntimeError(f"Parameter '{name}' not found")
        param.deleteMe()
        return {"deleted": True, "name": name}

    # ------------------------------------------------------------------
    # Surface Operations
    # ------------------------------------------------------------------

    def patch_surface(
        self, sketch_name: str, profile_index: int = 0, continuity: str = "connected"
    ):
        sketch = self._sketch_by_name(sketch_name)
        comp = sketch.parentComponent

        if sketch.profiles.count == 0:
            raise RuntimeError("No profiles in sketch")
        profile = sketch.profiles.item(profile_index)

        patches = comp.features.patchFeatures
        inp = patches.createInput(
            profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )

        sct = adsk.fusion.SurfaceContinuityTypes
        cont_map = {
            "connected": sct.ConnectedSurfaceContinuityType,
            "tangent": sct.TangentSurfaceContinuityType,
            "curvature": sct.CurvatureSurfaceContinuityType,
        }
        inp.boundaryContinuity = cont_map.get(continuity, cont_map["connected"])

        feat = patches.add(inp)
        return {
            "feature_name": feat.name,
            "continuity": continuity,
            "component": comp.name,
        }

    def stitch_surfaces(self, body_names: list, tolerance: float = 0.01):
        comp = self._root()
        bodies = adsk.core.ObjectCollection.create()
        for name in body_names:
            body, comp = self._native(self._body_by_name(name))
            bodies.add(body)

        stitches = comp.features.stitchFeatures
        inp = stitches.createInput(
            bodies,
            adsk.core.ValueInput.createByReal(tolerance),
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
        )
        feat = stitches.add(inp)
        return {
            "feature_name": feat.name,
            "body_count": len(body_names),
            "component": comp.name,
        }

    def thicken_surface(
        self, body_name: str, thickness: float, direction: str = "symmetric"
    ):
        body, comp = self._native(self._body_by_name(body_name))

        faces = adsk.core.ObjectCollection.create()
        for face in body.faces:
            faces.add(face)

        thickens = comp.features.thickenFeatures
        inp = thickens.createInput(
            faces,
            adsk.core.ValueInput.createByReal(thickness),
            False,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
            direction == "symmetric",
        )
        feat = thickens.add(inp)
        return {
            "feature_name": feat.name,
            "thickness": thickness,
            "component": comp.name,
        }

    def ruled_surface(
        self,
        body_name: str,
        edge_index: int,
        distance: float = 1.0,
        rule_type: str = "normal",
    ):
        body, comp = self._native(self._body_by_name(body_name))
        edge = body.edges.item(edge_index)

        ruled = comp.features.ruledSurfaceFeatures
        inp = ruled.createInput(edge, adsk.core.ValueInput.createByReal(distance))
        feat = ruled.add(inp)
        return {"feature_name": feat.name, "distance": distance, "component": comp.name}

    def trim_surface(self, body_name: str, tool_name: str):
        body, comp = self._native(self._body_by_name(body_name))
        tool, _ = self._native(self._body_by_name(tool_name))

        trims = comp.features.trimFeatures
        inp = trims.createInput(body, tool)
        feat = trims.add(inp)
        return {"feature_name": feat.name, "component": comp.name}

    # ------------------------------------------------------------------
    # Sheet Metal
    # ------------------------------------------------------------------

    def create_flange(
        self,
        body_name: str,
        edge_index: int,
        height: float = 1.0,
        angle: float = 90,
        bend_radius: float = None,
    ):
        body, comp = self._native(self._body_by_name(body_name))
        edge = body.edges.item(edge_index)

        flanges = comp.features.flangeFeatures
        inp = flanges.createInput(edge, True)
        inp.angle = adsk.core.ValueInput.createByString(f"{angle} deg")
        inp.height = adsk.core.ValueInput.createByReal(height)
        if bend_radius:
            inp.bendRadius = adsk.core.ValueInput.createByReal(bend_radius)

        feat = flanges.add(inp)
        return {
            "feature_name": feat.name,
            "height": height,
            "angle": angle,
            "component": comp.name,
        }

    def create_bend(
        self,
        body_name: str,
        bend_line_sketch: str = None,
        angle: float = 90,
        bend_radius: float = None,
    ):
        body, comp = self._native(self._body_by_name(body_name))

        if bend_line_sketch:
            sketch = self._sketch_by_name(bend_line_sketch)
            bend_line = sketch.sketchCurves.sketchLines.item(0)

            bends = comp.features.bendFeatures
            inp = bends.createInput(body, bend_line, True)
            inp.bendAngle = adsk.core.ValueInput.createByString(f"{angle} deg")
            if bend_radius:
                inp.bendRadius = adsk.core.ValueInput.createByReal(bend_radius)

            feat = bends.add(inp)
            return {"feature_name": feat.name, "angle": angle, "component": comp.name}
        else:
            raise RuntimeError("bend_line_sketch is required")

    def flat_pattern(self, body_name: str):
        body, comp = self._native(self._body_by_name(body_name))

        flat_patterns = comp.features.flatPatternFeatures
        inp = flat_patterns.createInput(body)
        feat = flat_patterns.add(inp)
        return {"feature_name": feat.name, "component": comp.name}

    def unfold(self, body_name: str, bend_indices: list = None):
        body, comp = self._native(self._body_by_name(body_name))

        unfolds = comp.features.unfoldFeatures

        bends = adsk.core.ObjectCollection.create()
        if bend_indices:
            for idx in bend_indices:
                # Get bend faces from sheet metal body
                bends.add(body.faces.item(idx))
        else:
            # Unfold all bends
            for face in body.faces:
                bends.add(face)

        # Find stationary face (first planar face)
        stationary = None
        for face in body.faces:
            if face.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
                stationary = face
                break

        if not stationary:
            raise RuntimeError("No planar face found for stationary face")

        inp = unfolds.createInput(bends, stationary)
        feat = unfolds.add(inp)
        return {"feature_name": feat.name, "component": comp.name}

    # ------------------------------------------------------------------
    # CAM
    # ------------------------------------------------------------------

    def _get_cam(self):
        """Get the CAM product from the active document.

        On recent Fusion builds the CAM product is only instantiated once
        the Manufacture workspace has been activated for the document, so
        activate it on demand instead of failing outright.  Note:
        itemByProductType *raises* when the product doesn't exist yet.
        """
        doc = self.app.activeDocument

        def _find_cam_product():
            try:
                return doc.products.itemByProductType("CAMProductType")
            except Exception:
                return None

        cam_product = _find_cam_product()
        if cam_product is None:
            ws = self.ui.workspaces.itemById("CAMEnvironment")
            if ws is not None:
                try:
                    ws.activate()
                    adsk.doEvents()
                except Exception as exc:
                    log.warning("Manufacture workspace activation failed: %s", exc)
                cam_product = _find_cam_product()

        if cam_product is None:
            raise RuntimeError(
                "No CAM workspace found. Open the Manufacturing workspace "
                "in Fusion 360 at least once to initialise it."
            )
        return cam_product

    def _find_setup(self, cam, name: str):
        for i in range(cam.setups.count):
            s = cam.setups.item(i)
            if s.name == name:
                return s
        raise RuntimeError(f"Setup '{name}' not found")

    def _find_operation(self, setup, name: str):
        for i in range(setup.operations.count):
            op = setup.operations.item(i)
            if op.name == name:
                return op
        raise RuntimeError(f"Operation '{name}' not found in setup '{setup.name}'")

    def cam_list_setups(self):
        cam = self._get_cam()
        result = []
        for i in range(cam.setups.count):
            setup = cam.setups.item(i)
            ops = []
            for j in range(setup.operations.count):
                ops.append(setup.operations.item(j).name)
            result.append(
                {
                    "name": setup.name,
                    "operations": ops,
                    "is_valid": setup.isValid,
                }
            )
        return {"setups": result, "count": len(result)}

    def cam_list_operations(self, setup_name: str):
        cam = self._get_cam()
        setup = self._find_setup(cam, setup_name)
        result = []
        for i in range(setup.operations.count):
            op = setup.operations.item(i)
            result.append(
                {
                    "name": op.name,
                    "has_toolpath": op.hasToolpath,
                    "is_valid": op.isValid,
                }
            )
        return {"setup": setup_name, "operations": result, "count": len(result)}

    def cam_get_operation_info(self, setup_name: str, operation_name: str):
        cam = self._get_cam()
        setup = self._find_setup(cam, setup_name)
        op = self._find_operation(setup, operation_name)

        info = {
            "name": op.name,
            "is_valid": op.isValid,
            "has_toolpath": op.hasToolpath,
        }

        if hasattr(op, "tool") and op.tool:
            tool = op.tool
            desc = tool.description if hasattr(tool, "description") else str(tool)
            info["tool"] = {"description": desc}

        if hasattr(op, "parameters"):
            params = {}
            for param in op.parameters:
                try:
                    params[param.name] = param.expression
                except Exception:
                    pass
            info["parameters"] = params

        return info

    def cam_create_setup(
        self,
        body_name: str,
        name: str = None,
        operation_type: str = "milling",
        stock_mode: str = "relative_box",
        stock_offset_sides: float = 0,
        stock_offset_top: float = 0,
        stock_offset_bottom: float = 0,
    ):
        cam = self._get_cam()
        body = self._body_by_name(body_name)

        op_type_map = {
            "milling": adsk.cam.OperationTypes.MillingOperation,
            "turning": adsk.cam.OperationTypes.TurningOperation,
            "cutting": adsk.cam.OperationTypes.JetOperation,
        }
        op_type = op_type_map.get(operation_type)
        if op_type is None:
            raise RuntimeError(
                f"Unknown operation_type '{operation_type}' "
                "— use milling/turning/cutting"
            )

        setup_input = cam.setups.createInput(op_type)
        setup_input.models = [body]

        if name:
            setup_input.name = name

        setup = cam.setups.add(setup_input)

        # Stock parameters live on the created setup, not the input.
        # Names/enumeration values verified against Fusion 2705: the
        # "Relative size box" UI choice has the id 'default'.
        stock_mode_map = {
            "relative_box": "default",
            "fixed_box": "fixedbox",
            "relative_cylinder": "relativecylinder",
            "fixed_cylinder": "fixedcylinder",
            "from_solid": "solid",
        }
        applied_stock = {}
        failed_stock = {}
        if stock_mode:
            mode_id = stock_mode_map.get(stock_mode, stock_mode)
            if self._set_cam_parameter(setup, "job_stockMode", mode_id, by_string=True):
                applied_stock["stock_mode"] = mode_id
            else:
                failed_stock["stock_mode"] = stock_mode
        for param_name, value in (
            ("job_stockOffset", stock_offset_sides),
            ("job_stockOffsetTop", stock_offset_top),
            ("job_stockOffsetBottom", stock_offset_bottom),
        ):
            if value:
                if self._set_cam_parameter(setup, param_name, value):
                    applied_stock[param_name] = value
                else:
                    failed_stock[param_name] = value

        result = {
            "name": setup.name,
            "body": body_name,
            "operation_type": operation_type,
        }
        if applied_stock:
            result["stock_applied"] = applied_stock
        if failed_stock:
            result["stock_failed"] = failed_stock
            result["warning"] = (
                "Some stock parameters could not be applied — parameter "
                "names vary by Fusion build; inspect via cam_get_operation_info"
            )
        return result

    @staticmethod
    def _set_cam_parameter(target, param_name, value, by_string=False):
        """Set a CAM parameter on a setup or operation. Returns success.

        CAMParameter.value is read-only on current Fusion builds — values
        must be assigned via the ``expression`` property.  Enum parameters
        (e.g. tool_coolant) take quoted lowercase strings ('flood').
        """
        try:
            params = getattr(target, "parameters", None)
            if params is None:
                return False
            p = params.itemByName(param_name)
            if p is None:
                return False
            p.expression = f"'{value}'" if by_string else str(value)
            return True
        except Exception as exc:
            log.debug("CAM parameter %s=%r failed: %s", param_name, value, exc)
            return False

    def cam_create_operation(
        self,
        setup_name: str,
        strategy: str,
        name: str = None,
        tool_number: int = None,
        tool_diameter: float = None,
        stepdown: float = None,
        stepover: float = None,
        feed_rate: float = None,
        spindle_speed: float = None,
        coolant: str = "flood",
    ):
        cam = self._get_cam()
        setup = self._find_setup(cam, setup_name)

        if tool_diameter is not None:
            raise RuntimeError(
                "tool_diameter cannot be set on an operation — tool geometry "
                "comes from a tool in the CAM tool library. Select the tool "
                "via tool_number instead."
            )

        op_input = setup.operations.createInput(strategy)
        if name:
            op_input.name = name

        op = setup.operations.add(op_input)
        if op is None:
            raise RuntimeError(
                f"Fusion rejected strategy '{strategy}' for setup '{setup_name}'"
            )

        # Operation parameters (stepdown, feeds, speeds...) only exist on
        # the created operation, keyed by strategy-dependent names.
        applied = {}
        failed = {}
        for param_name, value, by_string in (
            ("tool_number", tool_number, False),
            ("maximumStepdown", stepdown, False),
            ("maximumStepover", stepover, False),
            ("tool_feedCutting", feed_rate, False),
            ("tool_spindleSpeed", spindle_speed, False),
            ("tool_coolant", coolant, True),
        ):
            if value is None:
                continue
            if self._set_cam_parameter(op, param_name, value, by_string):
                applied[param_name] = value
            else:
                failed[param_name] = value

        result = {"name": op.name, "setup": setup_name, "strategy": strategy}
        if applied:
            result["parameters_applied"] = applied
        if failed:
            result["parameters_failed"] = failed
            result["warning"] = (
                "Some parameters are not available for this strategy — "
                "check available names via cam_get_operation_info"
            )
        return result

    @staticmethod
    def _wait_future(future, timeout: float = 25.0):
        """Wait for a CAM generation future, bounded so a runaway
        generation fails as a structured error instead of freezing the
        main thread past the bridge timeout."""
        is_completed = getattr(future, "isCompleted", None)
        if is_completed is None:
            future.wait()
            return
        deadline = time.monotonic() + timeout
        while not future.isCompleted:
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"Toolpath generation did not finish within {timeout}s. "
                    "The operation may still complete in the background — "
                    "check with cam_list_operations before regenerating."
                )
            time.sleep(0.1)

    def cam_generate_toolpath(
        self,
        setup_name: str = None,
        operation_name: str = None,
        generate_all: bool = False,
    ):
        cam = self._get_cam()

        if generate_all:
            future = cam.generateAllToolpaths(False)
            self._wait_future(future)
            return {"generated": True, "scope": "all"}

        if operation_name and setup_name:
            setup = self._find_setup(cam, setup_name)
            op = self._find_operation(setup, operation_name)
            future = cam.generateToolpath(op)
            self._wait_future(future)
            return {
                "generated": True,
                "scope": "operation",
                "operation": operation_name,
            }

        if setup_name:
            setup = self._find_setup(cam, setup_name)
            ops = adsk.core.ObjectCollection.create()
            for i in range(setup.operations.count):
                ops.add(setup.operations.item(i))
            future = cam.generateToolpath(ops)
            self._wait_future(future)
            return {"generated": True, "scope": "setup", "setup": setup_name}

        raise RuntimeError("Provide setup_name, operation_name, or generate_all=true")

    def cam_post_process(
        self,
        setup_name: str,
        operation_name: str = None,
        post_processor: str = "fanuc",
        output_folder: str = None,
        output_units: str = "mm",
    ):
        cam = self._get_cam()
        setup = self._find_setup(cam, setup_name)

        if not output_folder:
            output_folder = os.path.join(os.path.expanduser("~"), "Desktop")

        # Accept a full path to a .cps file, or resolve a short name against
        # the legacy local post folder when the build still provides one.
        if post_processor.endswith(".cps") or os.path.sep in post_processor:
            post_config = post_processor
        else:
            post_folder = getattr(cam, "genericPostFolder", None)
            if not post_folder:
                raise RuntimeError(
                    "This Fusion build has no local generic post folder "
                    "(posts are cloud-library based). Pass the full path to "
                    "the .cps file in 'post_processor' instead of a short "
                    "name."
                )
            post_config = os.path.join(post_folder, f"{post_processor}.cps")

        if not os.path.isfile(post_config):
            raise RuntimeError(f"Post processor not found: {post_config}")

        units = (
            adsk.cam.PostOutputUnitOptions.MillimetersOutput
            if output_units == "mm"
            else adsk.cam.PostOutputUnitOptions.InchesOutput
        )

        post_input = adsk.cam.PostProcessInput.create(
            setup_name, post_config, output_folder, units
        )
        post_input.isOpenInEditor = False

        if operation_name:
            op = self._find_operation(setup, operation_name)
            cam.postProcess(op, post_input)
        else:
            cam.postProcess(setup, post_input)

        return {
            "setup": setup_name,
            "post_processor": post_processor,
            "output_folder": output_folder,
            "units": output_units,
        }

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def _doc_info(self, doc):
        return {
            "name": doc.name,
            "active": doc == self.app.activeDocument,
            "saved": doc.isSaved,
            "modified": doc.isModified,
        }

    def _document(self, name: str = None):
        """Open document by name (exact, then case-insensitive); active if None."""
        if name is None:
            doc = self.app.activeDocument
            if doc is None:
                raise RuntimeError("No active document")
            return doc
        docs = list(self.app.documents)
        for match in (
            lambda d: d.name == name,
            lambda d: d.name.lower() == name.lower(),
        ):
            hits = [d for d in docs if match(d)]
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                raise RuntimeError(
                    f"'{name}' matches {len(hits)} open documents — save them "
                    "under distinct names or activate one with the UI"
                )
        names = ", ".join(d.name for d in docs[:12])
        raise RuntimeError(f"Document '{name}' is not open. Open documents: {names}")

    def list_documents(self):
        docs = [self._doc_info(d) for d in self.app.documents]
        return {"count": len(docs), "documents": docs}

    def new_document(self, design_type: str = "parametric"):
        doc = self.app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(
            doc.products.itemByProductType("DesignProductType")
        )
        design.designType = (
            adsk.fusion.DesignTypes.DirectDesignType
            if design_type == "direct"
            else adsk.fusion.DesignTypes.ParametricDesignType
        )
        return {**self._doc_info(doc), "design_type": design_type}

    _CLOUD_SEARCH_DEPTH = 4
    _CLOUD_SEARCH_FILES = 500

    def _find_cloud_file(self, name: str):
        """Breadth-first search of the active project for a design by name."""
        project = self.app.data.activeProject
        queue, seen, loose = [(project.rootFolder, 0)], 0, None
        while queue:
            folder, depth = queue.pop(0)
            for df in folder.dataFiles:
                seen += 1
                if df.name == name:
                    return df
                if loose is None and df.name.lower() == name.lower():
                    loose = df
                if seen >= self._CLOUD_SEARCH_FILES:
                    return loose
            if depth < self._CLOUD_SEARCH_DEPTH:
                queue.extend((f, depth + 1) for f in folder.dataFolders)
        return loose

    def open_document(self, name: str = None, file_path: str = None):
        if bool(name) == bool(file_path):
            raise RuntimeError("Pass exactly one of 'name' or 'file_path'")
        if file_path:
            path = os.path.abspath(os.path.expanduser(file_path))
            if not path.lower().endswith(".f3d"):
                raise RuntimeError(
                    "open_document takes a .f3d file — use insert_part for STEP"
                )
            if not os.path.exists(path):
                raise RuntimeError(f"File not found: {path}")
            im = self.app.importManager
            doc = im.importToNewDocument(im.createFusionArchiveImportOptions(path))
            return {**self._doc_info(doc), "source": "file"}
        for doc in self.app.documents:
            if doc.name == name:
                doc.activate()
                return {**self._doc_info(doc), "source": "already_open"}
        df = self._find_cloud_file(name)
        if df is None:
            project = self.app.data.activeProject.name
            raise RuntimeError(
                f"No design named '{name}' in project '{project}' (searched "
                f"{self._CLOUD_SEARCH_DEPTH} folder levels)"
            )
        doc = self.app.documents.open(df, True)
        return {**self._doc_info(doc), "source": "cloud"}

    def activate_document(self, name: str):
        doc = self._document(name)
        doc.activate()
        return self._doc_info(doc)

    def _cloud_folder(self, path: str):
        """Folder under the active project's root from "FTC/2026", created
        if missing."""
        folder = self.app.data.activeProject.rootFolder
        for part in [p for p in (path or "").replace("\\", "/").split("/") if p]:
            sub = folder.dataFolders.itemByName(part)
            folder = sub if sub is not None else folder.dataFolders.add(part)
        return folder

    def save_document(
        self,
        name: str = None,
        folder: str = None,
        description: str = "Saved by MCP",
        document: str = None,
    ):
        doc = self._document(document)
        project = self.app.data.activeProject.name
        if doc.isSaved and not name:
            if not doc.save(description):
                raise RuntimeError(f"Saving '{doc.name}' failed")
            return {**self._doc_info(doc), "project": project, "new_version": True}
        if not name:
            raise RuntimeError(
                f"'{doc.name}' has never been saved — pass 'name' (and "
                "optionally 'folder')"
            )
        target = self._cloud_folder(folder)
        if not doc.saveAs(name, target, description, ""):
            raise RuntimeError(f"saveAs '{name}' failed")
        return {
            **self._doc_info(doc),
            "project": project,
            "folder": folder or "",
            "new_version": False,
        }

    def close_document(
        self, name: str = None, save: bool = False, discard_changes: bool = False
    ):
        doc = self._document(name)
        doc_name = doc.name
        if save:
            if not doc.isSaved:
                raise RuntimeError(
                    f"'{doc_name}' has never been saved — call save_document "
                    "with a name first"
                )
        elif doc.isModified and not discard_changes:
            raise RuntimeError(
                f"'{doc_name}' has unsaved changes — pass save=true or "
                "discard_changes=true"
            )
        doc.close(bool(save))
        active = self.app.activeDocument
        return {
            "closed": doc_name,
            "saved": bool(save),
            "active": active.name if active is not None else None,
        }

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def ping(self):
        return {"pong": True}

    # ------------------------------------------------------------------
    # Design type safety
    # ------------------------------------------------------------------

    def get_design_type(self):
        """Return current design type: 'parametric' or 'direct'."""
        design = self._design()
        dt = design.designType
        is_parametric = dt == adsk.fusion.DesignTypes.ParametricDesignType
        return {
            "design_type": "parametric" if is_parametric else "direct",
            "design_type_id": dt,
        }

    def set_design_type(self, design_type: str):
        """Switch design type. Use 'parametric' to recover from accidental
        direct-mode switches (equivalent to UI 'Capture Design History')."""
        design = self._design()
        current = design.designType

        if design_type == "parametric":
            target = adsk.fusion.DesignTypes.ParametricDesignType
            if current == target:
                return {
                    "changed": False,
                    "design_type": "parametric",
                    "message": "Already in parametric mode",
                }
            design.designType = target
            adsk.doEvents()
            # Verify it actually changed
            if design.designType != target:
                raise RuntimeError(
                    "Failed to switch to parametric mode. "
                    "Try 'Capture Design History' in the Fusion UI."
                )
            return {"changed": True, "design_type": "parametric"}

        elif design_type == "direct":
            target = adsk.fusion.DesignTypes.DirectDesignType
            if current == target:
                return {
                    "changed": False,
                    "design_type": "direct",
                    "message": "Already in direct mode",
                }
            design.designType = target
            adsk.doEvents()
            return {"changed": True, "design_type": "direct"}

        else:
            raise RuntimeError(
                f"Invalid design_type '{design_type}'. Use 'parametric' or 'direct'."
            )

    # ------------------------------------------------------------------
    # Code execution (REPL-style)
    # ------------------------------------------------------------------

    def execute_code(self, code: str):
        design = self._design()
        type_before = design.designType

        ns = {
            "adsk": adsk,
            "app": self.app,
            "ui": self.ui,
            "design": design,
            "component": self._root(),
            "math": math,
        }

        buf = io.StringIO()

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            raise RuntimeError(f"SyntaxError: {exc}")

        last_expr_value = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last_node = tree.body.pop()
            if tree.body:
                with redirect_stdout(buf):
                    exec(
                        compile(
                            ast.Module(body=tree.body, type_ignores=[]), "<mcp>", "exec"
                        ),
                        ns,
                    )
            expr_code = compile(ast.Expression(body=last_node.value), "<mcp>", "eval")
            with redirect_stdout(buf):
                last_expr_value = eval(expr_code, ns)
        else:
            with redirect_stdout(buf):
                exec(compile(tree, "<mcp>", "exec"), ns)

        output = buf.getvalue()
        result = last_expr_value if last_expr_value is not None else output

        # The code may have closed or switched the document (S11): the old
        # design is then a deleted object and must not be touched.
        try:
            document_changed = not design.isValid or self._design() != design
        except RuntimeError:  # no design is active any more
            document_changed = True
        design_type_warning = None
        type_after = type_before if document_changed else design.designType
        if type_before != type_after:
            parametric = adsk.fusion.DesignTypes.ParametricDesignType
            design_type_warning = (
                f"WARNING: Design type changed from "
                f"{'parametric' if type_before == parametric else 'direct'} to "
                f"{'parametric' if type_after == parametric else 'direct'} "
                f"during code execution. Use set_design_type to recover."
            )
            log.warning(design_type_warning)
        if result is not None:
            try:
                import json as _json

                _json.dumps(result)
            except (TypeError, ValueError):
                result = str(result)

        response = {"executed": True, "result": result, "output": output}
        if document_changed:
            response["document_changed"] = True
        if design_type_warning:
            response["design_type_warning"] = design_type_warning
        return response

    # ------------------------------------------------------------------
    # Camera helper
    # ------------------------------------------------------------------

    def _camera_info(self):
        try:
            cam = self.app.activeViewport.camera
            return {
                "eye": [cam.eye.x, cam.eye.y, cam.eye.z],
                "target": [cam.target.x, cam.target.y, cam.target.z],
                "up_vector": [cam.upVector.x, cam.upVector.y, cam.upVector.z],
            }
        except Exception:
            return None

    @staticmethod
    def _bbox_dict(bbox):
        return {
            "min": [bbox.minPoint.x, bbox.minPoint.y, bbox.minPoint.z],
            "max": [bbox.maxPoint.x, bbox.maxPoint.y, bbox.maxPoint.z],
        }

    # ------------------------------------------------------------------
    # Mutation snapshot (before/after deltas for feedback)
    # ------------------------------------------------------------------

    def _snapshot(self) -> dict | None:
        """Capture body_count, overall bbox, and total mass of the design.

        Best-effort — returns None if the design isn't readable yet.  Mass
        is reported in grams; bbox in cm (Fusion's internal unit).
        """
        try:
            design = self.app.activeProduct
            if design is None or not hasattr(design, "rootComponent"):
                return None
            root = design.rootComponent

            # Collect body proxies recursively (root + occurrences).
            bodies = list(root.bRepBodies)
            try:
                for occ in design.rootComponent.allOccurrences:
                    bodies.extend(occ.bRepBodies)
            except Exception:
                pass  # allOccurrences can fail on empty designs
            body_count = len(bodies)

            # root.boundingBox is stale for moved occurrences; union the
            # proxies instead (they are in assembly coordinates).
            bbox_dict = None
            if body_count > 0:
                try:
                    box = self._bbox_union(bodies)
                    if box is not None:
                        bbox_dict = {"min": box[0], "max": box[1]}
                except Exception:
                    bbox_dict = None

            mass_g = 0.0
            if body_count > 0:
                try:
                    # physicalProperties.mass is in kg.  Sum occurrence
                    # bodies explicitly so mass_g stays consistent with
                    # body_count (which includes occurrence bodies).
                    mass_kg = float(root.physicalProperties.mass)
                    for occ in root.allOccurrences:
                        try:
                            mass_kg += float(occ.physicalProperties.mass)
                        except Exception:
                            pass
                    mass_g = mass_kg * 1000.0
                except Exception:
                    mass_g = 0.0

            return {
                "body_count": body_count,
                "bbox": bbox_dict,
                "mass_g": mass_g,
            }
        except Exception as exc:
            log.debug("snapshot failed: %s", exc)
            return None

    @staticmethod
    def _compute_deltas(before: dict, after: dict) -> dict:
        """Return a diff suitable for an agent: counts + masses + bboxes."""
        return {
            "body_count_before": before.get("body_count", 0),
            "body_count_after": after.get("body_count", 0),
            "body_count_delta": after.get("body_count", 0)
            - before.get("body_count", 0),
            "mass_g_before": before.get("mass_g", 0.0),
            "mass_g_after": after.get("mass_g", 0.0),
            "mass_g_delta": after.get("mass_g", 0.0) - before.get("mass_g", 0.0),
            "bbox_before": before.get("bbox"),
            "bbox_after": after.get("bbox"),
        }

    # ------------------------------------------------------------------
    # Viewport render (perception)
    # ------------------------------------------------------------------

    def render_view(
        self,
        view: str = "current",
        width: int = 1024,
        height: int = 768,
        fit: bool = True,
    ):
        """Save the active viewport to a PNG and return base64-encoded bytes.

        * ``view`` — ``"current"`` keeps the existing camera, or one of
          ``_VIEW_DIRS`` keys (iso, front, top, ...) to reposition first.
        * ``width``/``height`` — pixel dimensions.
        * ``fit`` — call viewport.fit() before capture so the model frames.

        If ``view != "current"``, the camera is restored to its prior state
        before returning so the user's view isn't disturbed.
        """
        viewport = self.app.activeViewport
        if viewport is None:
            raise RuntimeError("No active viewport")

        # Clamp dimensions — an oversized capture would stall the main
        # thread and produce an enormous base64 payload.
        width = max(16, min(int(width), 4096))
        height = max(16, min(int(height), 4096))

        repositioned = view != "current"
        if repositioned:
            spec = self._VIEW_DIRS.get(view)
            if spec is None:
                raise RuntimeError(
                    f"Unknown view '{view}'. "
                    f"Expected: current, {', '.join(self._VIEW_DIRS)}"
                )
            orig = viewport.camera
            orig_state = {
                "eye": (orig.eye.x, orig.eye.y, orig.eye.z),
                "target": (orig.target.x, orig.target.y, orig.target.z),
                "up": (orig.upVector.x, orig.upVector.y, orig.upVector.z),
                "type": orig.cameraType,
            }
            self._orient_camera(viewport, spec)

        try:
            if fit:
                try:
                    viewport.fit()
                except Exception:
                    pass  # fit() can fail on empty designs; keep going

            # saveAsImageFile requires a real path; write to a tempfile.
            fd, path = tempfile.mkstemp(suffix=".png", prefix="fusion_render_")
            os.close(fd)
            try:
                ok = viewport.saveAsImageFile(path, int(width), int(height))
                if not ok or not os.path.exists(path):
                    raise RuntimeError("saveAsImageFile returned false")
                with open(path, "rb") as f:
                    data = f.read()
            finally:
                try:
                    os.remove(path)
                except Exception:
                    pass
        finally:
            if repositioned:
                cam = viewport.camera
                cam.isSmoothTransition = False
                cam.cameraType = orig_state["type"]
                cam.eye = adsk.core.Point3D.create(*orig_state["eye"])
                cam.target = adsk.core.Point3D.create(*orig_state["target"])
                cam.upVector = adsk.core.Vector3D.create(*orig_state["up"])
                viewport.camera = cam
                try:
                    viewport.refresh()
                except Exception:
                    pass

        return {
            "view": view,
            "width": width,
            "height": height,
            "image_format": "png",
            "image_base64": base64.b64encode(data).decode("ascii"),
            "bytes": len(data),
        }

    def _orient_camera(self, viewport, spec):
        """Position the camera at a canonical view relative to the model.

        ``spec`` is ``(eye_dir, up_vec)`` from ``_VIEW_DIRS``.
        """
        eye_dir, up_vec = spec
        design = self.app.activeProduct
        root = design.rootComponent if design is not None else None

        # Target is the model centroid (or origin if no bodies).
        target = adsk.core.Point3D.create(0.0, 0.0, 0.0)
        distance = 20.0
        if root is not None and root.bRepBodies.count > 0:
            try:
                bbox = root.boundingBox
                if bbox is not None:
                    cx = (bbox.minPoint.x + bbox.maxPoint.x) * 0.5
                    cy = (bbox.minPoint.y + bbox.maxPoint.y) * 0.5
                    cz = (bbox.minPoint.z + bbox.maxPoint.z) * 0.5
                    target = adsk.core.Point3D.create(cx, cy, cz)
                    dx = bbox.maxPoint.x - bbox.minPoint.x
                    dy = bbox.maxPoint.y - bbox.minPoint.y
                    dz = bbox.maxPoint.z - bbox.minPoint.z
                    distance = max(dx, dy, dz, 1.0) * 2.5
            except Exception:
                pass

        eye = adsk.core.Point3D.create(
            target.x + eye_dir[0] * distance,
            target.y + eye_dir[1] * distance,
            target.z + eye_dir[2] * distance,
        )
        up = adsk.core.Vector3D.create(up_vec[0], up_vec[1], up_vec[2])

        cam = viewport.camera
        cam.eye = eye
        cam.target = target
        cam.upVector = up
        cam.isSmoothTransition = False
        viewport.camera = cam
