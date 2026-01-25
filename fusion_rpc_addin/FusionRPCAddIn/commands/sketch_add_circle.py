import importlib
import os
import sys

import adsk.core
import adsk.fusion

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _selection_helpers as selection_helpers

importlib.reload(selection_helpers)

COMMAND = "sketch_add_circle"
REQUIRES_DESIGN = True


def _mm_to_internal(units_mgr, value_mm):
    if not units_mgr:
        return value_mm
    try:
        return units_mgr.convert(value_mm, "mm", units_mgr.internalUnits)
    except Exception:
        return value_mm / 10.0


def _find_sketch(root_comp, sketch_id):
    try:
        sketches = root_comp.sketches
    except Exception:
        return None
    try:
        count = int(sketches.count)
    except Exception:
        count = 0
    for idx in range(count):
        try:
            sketch = sketches.item(idx)
        except Exception:
            continue
        if selection_helpers._entity_id(sketch) == sketch_id:
            return sketch
    return None


def handle(request, context):
    root_comp = context.get("root_comp")
    units_mgr = context.get("units_mgr")

    if not root_comp:
        return {"ok": False, "error": "No active design."}

    sketch_id = request.get("sketch_id")
    center_mm = request.get("center_mm")
    radius_mm = request.get("radius_mm")
    preview = bool(request.get("preview", False))

    if not sketch_id:
        return {"ok": False, "error": "sketch_id is required"}
    if not isinstance(center_mm, dict):
        return {"ok": False, "error": "center_mm must be an object with x,y,z"}

    try:
        cx = float(center_mm.get("x", 0.0))
        cy = float(center_mm.get("y", 0.0))
        cz = float(center_mm.get("z", 0.0))
        radius_mm = float(radius_mm)
    except Exception:
        return {"ok": False, "error": "center_mm and radius_mm must be numeric"}

    if radius_mm <= 0:
        return {"ok": False, "error": "radius_mm must be > 0"}

    sketch = _find_sketch(root_comp, sketch_id)
    if not sketch:
        return {"ok": False, "error": f"sketch_id not found: {sketch_id}"}

    plan = {
        "sketch_id": sketch_id,
        "center_mm": {"x": cx, "y": cy, "z": cz},
        "radius_mm": radius_mm,
    }

    if preview:
        return {"ok": True, "error": None, "data": {"curve_id": None, "preview": {"is_preview": True, "plan": plan}}}

    center = adsk.core.Point3D.create(
        _mm_to_internal(units_mgr, cx),
        _mm_to_internal(units_mgr, cy),
        _mm_to_internal(units_mgr, cz),
    )
    radius_internal = _mm_to_internal(units_mgr, radius_mm)

    try:
        circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(center, radius_internal)
    except Exception as exc:
        return {"ok": False, "error": f"Failed to create circle: {exc}"}

    return {
        "ok": True,
        "error": None,
        "data": {
            "curve_id": selection_helpers._entity_id(circle),
            "preview": {"is_preview": False, "plan": plan},
        },
    }
