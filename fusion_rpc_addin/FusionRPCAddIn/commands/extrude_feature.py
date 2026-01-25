import importlib
import os
import sys
import time

import adsk.core
import adsk.fusion

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _selection_helpers as selection_helpers

importlib.reload(selection_helpers)

COMMAND = "extrude_feature"
REQUIRES_DESIGN = True

MAX_EXTRUDE_MM = 50.0
MAX_APPLY_MS = 1500.0
MAX_FACE_DELTA = 150
MAX_EDGE_DELTA = 300
MAX_BODY_DELTA = 1


def _entity_id(entity):
    for attr in ("entityToken", "tempId", "entityId"):
        try:
            value = getattr(entity, attr)
        except Exception:
            continue
        if value is not None:
            return str(value)
    return None


def _list_visible_bodies(root_comp):
    bodies = []
    for body in root_comp.bRepBodies:
        try:
            if not body.isSolid or not body.isVisible:
                continue
        except Exception:
            continue
        bodies.append(body)
    return bodies


def _resolve_body(root_comp, body_name):
    bodies = _list_visible_bodies(root_comp)
    if body_name:
        for body in bodies:
            if body.name == body_name:
                return body, bodies
        return None, bodies
    if len(bodies) == 1:
        return bodies[0], bodies
    return None, bodies


def _collection_count(collection):
    try:
        return int(collection.count)
    except Exception:
        try:
            return len(list(collection))
        except Exception:
            return 0


def _body_counts(body):
    return {
        "faces": _collection_count(body.faces),
        "edges": _collection_count(body.edges),
        "vertices": _collection_count(body.vertices),
    }


def _total_counts(bodies):
    totals = {"faces": 0, "edges": 0, "vertices": 0}
    for body in bodies:
        counts = _body_counts(body)
        totals["faces"] += counts["faces"]
        totals["edges"] += counts["edges"]
        totals["vertices"] += counts["vertices"]
    return totals


def _length_factor_mm(units_mgr, convert_mm):
    try:
        return float(convert_mm(units_mgr, 1.0))
    except Exception:
        return 10.0


def _point_mm(convert_mm, units_mgr, point):
    return {
        "x": convert_mm(units_mgr, point.x),
        "y": convert_mm(units_mgr, point.y),
        "z": convert_mm(units_mgr, point.z),
    }


def _bbox_mm(body, units_mgr, convert_mm):
    try:
        bbox = getattr(body, "worldBoundingBox", None) or body.boundingBox
    except Exception:
        bbox = None
    if not bbox:
        return None
    min_pt = _point_mm(convert_mm, units_mgr, bbox.minPoint)
    max_pt = _point_mm(convert_mm, units_mgr, bbox.maxPoint)
    return {
        "min": min_pt,
        "max": max_pt,
        "size": {
            "x": max_pt["x"] - min_pt["x"],
            "y": max_pt["y"] - min_pt["y"],
            "z": max_pt["z"] - min_pt["z"],
        },
    }


def _volume_mm3(body, units_mgr, convert_mm):
    try:
        props = body.physicalProperties
    except Exception:
        props = None
    if not props:
        return None
    length_factor = _length_factor_mm(units_mgr, convert_mm)
    try:
        return props.volume * (length_factor ** 3)
    except Exception:
        return None


def _body_measurement(body, units_mgr, convert_mm):
    return {
        "body_name": getattr(body, "name", None),
        "bbox_mm": _bbox_mm(body, units_mgr, convert_mm),
        "volume_mm3": _volume_mm3(body, units_mgr, convert_mm),
        "counts": _body_counts(body),
    }


def _normalize_vector(vector):
    try:
        length = (vector.x ** 2 + vector.y ** 2 + vector.z ** 2) ** 0.5
    except Exception:
        return None
    if length <= 0.0:
        return None
    return {
        "x": vector.x / length,
        "y": vector.y / length,
        "z": vector.z / length,
    }


def _face_area_mm2(face, units_mgr, convert_mm):
    try:
        area = face.area
    except Exception:
        return None
    length_factor = _length_factor_mm(units_mgr, convert_mm)
    return area * (length_factor ** 2)


def _parse_face_selector(selector):
    if selector == "largest_planar":
        return {"type": "largest_planar"}
    if selector.startswith("normal_closest:"):
        axis = selector.split(":", 1)[1].strip()
        if axis in ("+X", "-X", "+Y", "-Y", "+Z", "-Z"):
            return {"type": "normal_closest", "axis": axis}
    return None


def _axis_vector(axis):
    if axis == "+X":
        return (1.0, 0.0, 0.0)
    if axis == "-X":
        return (-1.0, 0.0, 0.0)
    if axis == "+Y":
        return (0.0, 1.0, 0.0)
    if axis == "-Y":
        return (0.0, -1.0, 0.0)
    if axis == "+Z":
        return (0.0, 0.0, 1.0)
    if axis == "-Z":
        return (0.0, 0.0, -1.0)
    return (0.0, 0.0, 0.0)


def _is_planar(face):
    try:
        geom = face.geometry
    except Exception:
        return False
    if not geom:
        return False
    try:
        if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
            return True
    except Exception:
        pass
    try:
        return bool(geom.isPlane)
    except Exception:
        return False


def _select_face(body, selector, units_mgr, convert_mm):
    candidates = []
    for face in body.faces:
        if not _is_planar(face):
            continue
        try:
            centroid = face.centroid
        except Exception:
            centroid = None
        if not centroid:
            continue

        area_mm2 = _face_area_mm2(face, units_mgr, convert_mm)
        face_id = _entity_id(face)
        centroid_tuple = (
            convert_mm(units_mgr, centroid.x),
            convert_mm(units_mgr, centroid.y),
            convert_mm(units_mgr, centroid.z),
        )

        score = None
        normal_out = None
        if selector["type"] == "largest_planar":
            if area_mm2 is None:
                continue
            score = area_mm2
        elif selector["type"] == "normal_closest":
            try:
                normal = face.geometry.normal
            except Exception:
                normal = None
            if not normal:
                continue
            axis = _axis_vector(selector["axis"])
            score = normal.x * axis[0] + normal.y * axis[1] + normal.z * axis[2]
            normal_out = _normalize_vector(normal)
        else:
            continue

        candidates.append(
            {
                "face": face,
                "score": score,
                "area_mm2": area_mm2,
                "centroid": centroid,
                "centroid_tuple": centroid_tuple,
                "face_id": face_id or "",
                "normal": normal_out,
            }
        )

    if not candidates:
        return None, 0

    def _tie_key(item):
        area = item["area_mm2"] if item["area_mm2"] is not None else -1.0
        return (-item["score"], -area, item["centroid_tuple"], item["face_id"])

    candidates.sort(key=_tie_key)
    return candidates[0], len(candidates)


def _mm_to_internal(units_mgr, value_mm):
    if not units_mgr:
        return value_mm
    try:
        return units_mgr.convert(value_mm, "mm", units_mgr.internalUnits)
    except Exception:
        return value_mm / 10.0


def _body_key(body):
    entity = selection_helpers._entity_id(body)
    if entity:
        return ("id", entity)
    return ("name", getattr(body, "name", ""))


def _apply_extrude(root_comp, face, operation, distance_mm, direction, units_mgr):
    extrudes = root_comp.features.extrudeFeatures
    ext_input = extrudes.createInput(face, operation)
    distance_internal = _mm_to_internal(units_mgr, distance_mm)
    distance_value = adsk.core.ValueInput.createByReal(distance_internal)
    ext_input.setDistanceExtent(False, distance_value)
    ext_input.isSolid = True

    if direction == "opposite":
        try:
            ext_input.isDirectionOpposite = True
        except Exception:
            try:
                distance_value = adsk.core.ValueInput.createByReal(-distance_internal)
                ext_input.setDistanceExtent(False, distance_value)
            except Exception:
                pass

    return extrudes.add(ext_input)


def handle(request, context):
    design = context.get("design")
    root_comp = context.get("root_comp")
    units_mgr = context.get("units_mgr")
    convert_mm = context.get("convert_mm")

    if not design or not root_comp:
        return {"ok": False, "error": "No active design."}

    body_name = request.get("body_name")
    face_selector = request.get("face_selector", "largest_planar")
    operation_name = request.get("operation", "new_body")
    distance_mm = request.get("distance_mm")
    direction = request.get("direction", "normal")
    preview = bool(request.get("preview", False))
    compute = bool(request.get("compute", True))
    units = request.get("units", "mm")

    tolerance_mm = request.get("verification_tolerance_mm", 0.1)
    tolerance_pct = request.get("verification_tolerance_pct", 1.0)

    if units != "mm":
        return {"ok": False, "error": f"Unsupported units: {units}. Only 'mm' is supported."}

    selector = selection_helpers._parse_face_selector(face_selector)
    if not selector:
        return {"ok": False, "error": f"Unsupported face_selector: {face_selector}"}

    operations = {
        "new_body": adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
        "join": adsk.fusion.FeatureOperations.JoinFeatureOperation,
        "cut": adsk.fusion.FeatureOperations.CutFeatureOperation,
        "intersect": adsk.fusion.FeatureOperations.IntersectFeatureOperation,
    }
    if operation_name not in operations:
        return {"ok": False, "error": f"Unsupported operation: {operation_name}"}

    if direction not in ("normal", "opposite"):
        return {"ok": False, "error": f"Unsupported direction: {direction}"}

    try:
        distance_mm = float(distance_mm)
    except Exception:
        return {"ok": False, "error": "distance_mm must be a number"}

    if distance_mm <= 0:
        return {"ok": False, "error": "distance_mm must be > 0"}
    if distance_mm > MAX_EXTRUDE_MM:
        return {"ok": False, "error": f"distance_mm exceeds MAX_EXTRUDE_MM ({MAX_EXTRUDE_MM})"}

    body, bodies = selection_helpers._resolve_body(root_comp, body_name)
    if not body:
        candidates = sorted([b.name for b in bodies])
        if body_name:
            return {
                "ok": False,
                "error": f"Body not found: {body_name}. Candidates: {candidates}",
                "candidates": candidates,
            }
        if not candidates:
            return {"ok": False, "error": "No visible solid body found.", "candidates": []}
        return {
            "ok": False,
            "error": "Multiple visible bodies; specify body_name.",
            "candidates": candidates,
        }

    selected, candidate_count = selection_helpers._select_face(body, selector, units_mgr, convert_mm)
    if not selected:
        return {"ok": False, "error": "No planar faces matched selector."}

    face = selected["face"]
    centroid_mm = selection_helpers._point_mm(convert_mm, units_mgr, selected["centroid"])
    normal = selected["normal"]
    if normal is None:
        try:
            normal = selection_helpers._normalize_vector(face.geometry.normal)
        except Exception:
            normal = None

    plan = {
        "body_name": body.name,
        "face": {
            "id": selected["face_id"],
            "selector": face_selector,
            "centroid_mm": centroid_mm,
            "normal": normal,
            "area_mm2": selected["area_mm2"],
        },
        "operation": operation_name,
        "distance_mm": distance_mm,
        "direction": direction,
    }

    if preview:
        return {
            "ok": True,
            "error": None,
            "data": {
                "preview": {"is_preview": True, "plan": plan},
                "apply": None,
                "measure_before": _body_measurement(body, units_mgr, convert_mm),
                "measure_after": None,
                "verify": None,
                "trace": {"candidates_considered": {"faces": candidate_count}},
            },
        }

    before_visible = selection_helpers._list_visible_bodies(root_comp)
    before_counts = _total_counts(before_visible)
    before_body_count = len(before_visible)
    measure_before = _body_measurement(body, units_mgr, convert_mm)

    start_time = time.time()
    feature = None
    compute_ran = False
    try:
        feature = _apply_extrude(
            root_comp,
            face,
            operations[operation_name],
            distance_mm,
            direction,
            units_mgr,
        )
        if compute:
            try:
                design.computeAll()
                compute_ran = True
            except Exception:
                raise RuntimeError("Design compute failed")
        timing_ms = (time.time() - start_time) * 1000.0
    except Exception as exc:
        if feature:
            try:
                feature.deleteMe()
            except Exception:
                pass
        return {"ok": False, "error": f"Extrude failed: {exc}", "data": {"preview": {"plan": plan}}}

    after_visible = selection_helpers._list_visible_bodies(root_comp)
    after_counts = _total_counts(after_visible)
    after_body_count = len(after_visible)

    face_delta = after_counts["faces"] - before_counts["faces"]
    edge_delta = after_counts["edges"] - before_counts["edges"]
    body_delta = after_body_count - before_body_count

    guardrail_error = None
    if timing_ms > MAX_APPLY_MS:
        guardrail_error = f"Apply exceeded MAX_APPLY_MS ({MAX_APPLY_MS} ms)"
    elif face_delta > MAX_FACE_DELTA:
        guardrail_error = f"face_count_delta exceeded MAX_FACE_DELTA ({MAX_FACE_DELTA})"
    elif edge_delta > MAX_EDGE_DELTA:
        guardrail_error = f"edge_count_delta exceeded MAX_EDGE_DELTA ({MAX_EDGE_DELTA})"
    elif body_delta > MAX_BODY_DELTA:
        guardrail_error = f"body_count_delta exceeded MAX_BODY_DELTA ({MAX_BODY_DELTA})"

    if guardrail_error:
        try:
            feature.deleteMe()
            if compute:
                design.computeAll()
        except Exception:
            pass
        return {
            "ok": False,
            "error": guardrail_error,
            "data": {"preview": {"plan": plan}},
        }

    new_body = None
    if operation_name == "new_body":
        before_keys = {_body_key(b) for b in before_visible}
        new_candidates = [b for b in after_visible if _body_key(b) not in before_keys]
        if len(new_candidates) == 1:
            new_body = new_candidates[0]
        elif len(new_candidates) > 1:
            try:
                feature.deleteMe()
                if compute:
                    design.computeAll()
            except Exception:
                pass
            return {
                "ok": False,
                "error": "Multiple bodies created; guardrail failure.",
                "data": {"preview": {"plan": plan}},
            }
        else:
            try:
                feature.deleteMe()
                if compute:
                    design.computeAll()
            except Exception:
                pass
            return {
                "ok": False,
                "error": "No new body created.",
                "data": {"preview": {"plan": plan}},
            }

    measure_after = _body_measurement(body, units_mgr, convert_mm)
    if new_body:
        measure_after = _body_measurement(new_body, units_mgr, convert_mm)
        measure_after["source_body"] = _body_measurement(body, units_mgr, convert_mm)

    warnings = []
    required_pass = True
    metrics_attempted = ["bbox", "volume"]

    def _has_bbox(measure):
        return bool(measure and measure.get("bbox_mm"))

    def _has_volume(measure):
        value = measure.get("volume_mm3") if measure else None
        return value is not None

    if not _has_bbox(measure_before) or not _has_bbox(measure_after):
        required_pass = False
        warnings.append("bbox measurement missing")

    require_volume = operation_name in ("join", "cut", "intersect")
    if require_volume and (not _has_volume(measure_before) or not _has_volume(measure_after)):
        required_pass = False
        warnings.append("volume measurement missing")
    elif not _has_volume(measure_before) or not _has_volume(measure_after):
        warnings.append("volume measurement missing (advisory)")

    if new_body and not measure_after.get("source_body"):
        required_pass = False
        warnings.append("source_body measurement missing for new_body operation")

    if new_body:
        if not _has_bbox(measure_after):
            required_pass = False
            warnings.append("new_body bbox missing")
        if require_volume and not _has_volume(measure_after):
            required_pass = False
            warnings.append("new_body volume missing")

    warnings.append("face_span not computed (no selector provided)")

    data = {
        "preview": {"is_preview": False, "plan": plan},
        "apply": {
            "feature": {
                "id": selection_helpers._entity_id(feature),
                "name": getattr(feature, "name", None),
            },
            "compute": {"ran": compute_ran},
            "timing_ms": timing_ms,
        },
        "measure_before": measure_before,
        "measure_after": measure_after,
        "verify": {
            "tolerances": {"mm": tolerance_mm, "pct": tolerance_pct},
            "required_pass": required_pass,
            "warnings": warnings,
            "metrics_attempted": metrics_attempted,
        },
        "trace": {"candidates_considered": {"faces": candidate_count}},
    }

    return {"ok": True, "error": None, "data": data}
