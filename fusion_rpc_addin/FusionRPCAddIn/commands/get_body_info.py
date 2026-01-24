COMMAND = "get_body_info"
REQUIRES_DESIGN = True


def _entity_id(entity):
    for attr in ("tempId", "entityToken", "entityId"):
        try:
            value = getattr(entity, attr)
        except Exception:
            continue
        if value is not None:
            return str(value)
    return None


def _list_bodies(root_comp, include_hidden):
    bodies = []
    for body in root_comp.bRepBodies:
        try:
            if not body.isSolid:
                continue
            if not include_hidden and not body.isVisible:
                continue
            bodies.append(body)
        except Exception:
            continue
    return bodies


def _resolve_body(root_comp, body_name, include_hidden):
    bodies = _list_bodies(root_comp, include_hidden)
    if body_name:
        for body in bodies:
            if body.name == body_name:
                return body, bodies
        return None, bodies
    if len(bodies) == 1:
        return bodies[0], bodies
    return None, bodies


def _point_mm(convert_mm, units_mgr, point):
    return {
        "x": convert_mm(units_mgr, point.x),
        "y": convert_mm(units_mgr, point.y),
        "z": convert_mm(units_mgr, point.z),
    }


def _collection_count(collection):
    try:
        return int(collection.count)
    except Exception:
        try:
            return len(list(collection))
        except Exception:
            return 0


def _length_factor_mm(units_mgr, convert_mm):
    try:
        return float(convert_mm(units_mgr, 1.0))
    except Exception:
        return 10.0


def _physical_props(body, units_mgr, convert_mm):
    try:
        props = body.physicalProperties
    except Exception:
        props = None

    if not props:
        return {
            "volume_mm3": None,
            "area_mm2": None,
            "density_kg_m3": None,
            "mass_kg": None,
        }

    length_factor = _length_factor_mm(units_mgr, convert_mm)
    volume_mm3 = None
    area_mm2 = None
    density_kg_m3 = None
    mass_kg = None

    try:
        volume_mm3 = props.volume * (length_factor ** 3)
    except Exception:
        volume_mm3 = None
    try:
        area_mm2 = props.area * (length_factor ** 2)
    except Exception:
        area_mm2 = None
    try:
        mass_kg = props.mass
    except Exception:
        mass_kg = None
    try:
        density_kg_m3 = props.density * 1_000_000.0
    except Exception:
        density_kg_m3 = None

    return {
        "volume_mm3": volume_mm3,
        "area_mm2": area_mm2,
        "density_kg_m3": density_kg_m3,
        "mass_kg": mass_kg,
    }


def handle(request, context):
    root_comp = context["root_comp"]
    units_mgr = context["units_mgr"]
    convert_mm = context["convert_mm"]

    body_name = request.get("body_name")
    include_hidden = bool(request.get("include_hidden", False))
    units = request.get("units", "mm")

    if units != "mm":
        return {"ok": False, "error": f"Unsupported units: {units}. Only 'mm' is supported."}

    body, bodies = _resolve_body(root_comp, body_name, include_hidden)
    if not body:
        candidates = sorted([b.name for b in bodies])
        if body_name:
            return {
                "ok": False,
                "error": f"Body not found: {body_name}. Candidates: {candidates}",
                "candidates": candidates,
            }
        if not candidates:
            return {"ok": False, "error": "No solid bodies found.", "candidates": []}
        return {
            "ok": False,
            "error": "Multiple bodies found; specify body_name.",
            "candidates": candidates,
        }

    try:
        bbox = getattr(body, "worldBoundingBox", None) or body.boundingBox
    except Exception:
        bbox = None
    if not bbox:
        return {"ok": False, "error": "Failed to read body bounding box."}

    min_pt = _point_mm(convert_mm, units_mgr, bbox.minPoint)
    max_pt = _point_mm(convert_mm, units_mgr, bbox.maxPoint)
    size_pt = {
        "x": max_pt["x"] - min_pt["x"],
        "y": max_pt["y"] - min_pt["y"],
        "z": max_pt["z"] - min_pt["z"],
    }

    data = {
        "body": {"name": body.name, "id": _entity_id(body)},
        "counts": {
            "faces": _collection_count(body.faces),
            "edges": _collection_count(body.edges),
            "vertices": _collection_count(body.vertices),
        },
        "bbox_mm": {
            "min": min_pt,
            "max": max_pt,
            "size": size_pt,
        },
        "physical_mm": _physical_props(body, units_mgr, convert_mm),
        "transform": {"is_identity": True},
        "units": "mm",
    }

    return {"ok": True, "error": None, "data": data}
