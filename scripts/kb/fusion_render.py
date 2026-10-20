"""Per-mechanism renders from a robot STEP, run inside Fusion via execute_code.

Load once per session, then call the helpers stored on `sys.kb`:

    exec(open("<repo>/scripts/kb/fusion_render.py").read()); sys.kb.open(step_path)
    kb = sys.kb; kb.tree(2)                       # names + bbox (cm) of occurrences
    kb.shoot([occ, ...], out_png)                 # show only these, iso view, save
    kb.close()                                    # close the throwaway doc

Positions match Onshape (cm, Z up). Occurrence names keep Onshape's instance names.
"""

import re
import sys
import types

import adsk.core
import adsk.fusion

HW = ("Button", "Socket", "Countersunk", "Locknut", "Nylon", "Set Screw")
kb = types.SimpleNamespace()


def _app():
    return adsk.core.Application.get()


def base(o):
    """Occurrence name without Fusion's ':n' and Onshape's ' <n>'."""
    return re.sub(r"\s*<\d+>$", "", o.name.rsplit(":", 1)[0].strip())


def is_hw(o):
    return base(o).startswith(HW)


def open_step(path):
    app = _app()
    kb.prev = app.activeDocument
    kb.doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    des = adsk.fusion.Design.cast(app.activeProduct)
    des.designType = adsk.fusion.DesignTypes.DirectDesignType
    opts = app.importManager.createSTEPImportOptions(path)
    app.importManager.importToTarget(opts, des.rootComponent)
    kb.root = des.rootComponent
    kb.top = kb.root.occurrences.item(0)
    return kb.top.childOccurrences.count


def children(occ=None):
    return [o for o in (occ or kb.top).childOccurrences if not is_hw(o)]


def find(name, occ=None):
    """First child occurrence whose base name starts with `name`."""
    return next(o for o in children(occ) if base(o).startswith(name))


def box(occs):
    xs, ys, zs = [], [], []
    for o in occs:
        b = o.boundingBox
        xs += [b.minPoint.x, b.maxPoint.x]
        ys += [b.minPoint.y, b.maxPoint.y]
        zs += [b.minPoint.z, b.maxPoint.z]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def tree(depth=1, occ=None, indent=0, min_parts=0):
    """Compact listing: name ×count [zmin..zmax] (y range) per distinct child."""
    out, seen = [], {}
    for o in children(occ):
        k = base(o)
        seen.setdefault(k, []).append(o)
    for k, os in seen.items():
        (x0, y0, z0), (x1, y1, z1) = box(os)
        n = sum(1 for _ in os)
        out.append(
            f"{'  ' * indent}{k[:45]}{f' ×{n}' if n > 1 else ''}  "
            f"x[{x0:.0f},{x1:.0f}] y[{y0:.0f},{y1:.0f}] z[{z0:.0f},{z1:.0f}]"
        )
        if depth > 1 and os[0].childOccurrences.count:
            out += tree(depth - 1, os[0], indent + 1)
    return out


def show(occs):
    """Light-bulb only `occs` (any depth) and their ancestors."""
    keep = {o.fullPathName for o in occs}
    anc = set()
    for o in occs:
        p = o.assemblyContext
        while p:
            anc.add(p.fullPathName)
            p = p.assemblyContext

    def rec(parent):
        # Bodies that sit directly in a partly shown assembly aren't in `occs`.
        for body in parent.component.bRepBodies:
            body.isLightBulbOn = False
        for c in parent.childOccurrences:
            if c.fullPathName in keep:
                c.isLightBulbOn = True
            elif c.fullPathName in anc:
                c.isLightBulbOn = True
                rec(c)
            else:
                c.isLightBulbOn = False

    for o in kb.root.occurrences:
        o.isLightBulbOn = o.fullPathName == kb.top.fullPathName
    for body in kb.root.bRepBodies:
        body.isLightBulbOn = False
    rec(kb.top)


def show_all():
    def rec(parent):
        for body in parent.component.bRepBodies:
            body.isLightBulbOn = True
        for c in parent.childOccurrences:
            c.isLightBulbOn = True
            rec(c)

    rec(kb.top)


def shoot(occs, out, eye=(1.0, -1.0, 0.8), w=600, h=450):
    """Render only `occs`; `eye` is the view direction from the target (Z up)."""
    show(occs)
    (x0, y0, z0), (x1, y1, z1) = box(occs)
    c = adsk.core.Point3D.create((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    vp = _app().activeViewport
    cam = vp.camera
    cam.isSmoothTransition = False
    cam.target = c
    cam.eye = adsk.core.Point3D.create(
        c.x + 100 * eye[0], c.y + 100 * eye[1], c.z + 100 * eye[2]
    )
    cam.upVector = adsk.core.Vector3D.create(0, 0, 1)
    vp.camera = cam
    vp.fit()
    vp.saveAsImageFile(out, w, h)
    show_all()
    return out


def close():
    """Close the throwaway doc. execute_code then reports a deleted-object error."""
    prev = kb.prev
    kb.doc.close(False)
    if prev and prev.isValid:
        prev.activate()


kb.open, kb.children, kb.find, kb.box, kb.tree = open_step, children, find, box, tree
kb.show, kb.show_all, kb.shoot, kb.close, kb.base = show, show_all, shoot, close, base
sys.kb = kb
