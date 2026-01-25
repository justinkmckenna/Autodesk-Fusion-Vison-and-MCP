import math

import adsk.core


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


def _point_tuple_mm(convert_mm, units_mgr, point):
    return (
        convert_mm(units_mgr, point.x),
        convert_mm(units_mgr, point.y),
        convert_mm(units_mgr, point.z),
    )


def _bbox_mm(entity, units_mgr, convert_mm):
    bbox = None
    try:
        bbox = getattr(entity, "worldBoundingBox", None) or entity.boundingBox
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


def _normalize_vector(vector):
    try:
        length = math.sqrt(vector.x * vector.x + vector.y * vector.y + vector.z * vector.z)
    except Exception:
        return None
    if length <= 0.0:
        return None
    return {
        "x": vector.x / length,
        "y": vector.y / length,
        "z": vector.z / length,
    }


def _vector_dot(vector, axis):
    return vector.x * axis[0] + vector.y * axis[1] + vector.z * axis[2]


def _face_area_mm2(face, units_mgr, convert_mm):
    try:
        area = face.area
    except Exception:
        return None
    length_factor = _length_factor_mm(units_mgr, convert_mm)
    return area * (length_factor ** 2)


def _edge_length_mm(edge, units_mgr, convert_mm):
    try:
        length = edge.length
    except Exception:
        return None
    length_factor = _length_factor_mm(units_mgr, convert_mm)
    return length * length_factor


def _edge_midpoint(edge):
    try:
        evaluator = edge.evaluator
        ok, start, end = evaluator.getParameterExtents()
        if ok:
            ok2, point = evaluator.getPointAtParameter((start + end) * 0.5)
            if ok2:
                return point
    except Exception:
        pass
    try:
        start_pt = edge.startVertex.geometry
        end_pt = edge.endVertex.geometry
        return adsk.core.Point3D.create(
            (start_pt.x + end_pt.x) * 0.5,
            (start_pt.y + end_pt.y) * 0.5,
            (start_pt.z + end_pt.z) * 0.5,
        )
    except Exception:
        return None


def _edge_direction(edge):
    try:
        start_pt = edge.startVertex.geometry
        end_pt = edge.endVertex.geometry
        vec = adsk.core.Vector3D.create(
            end_pt.x - start_pt.x,
            end_pt.y - start_pt.y,
            end_pt.z - start_pt.z,
        )
        if vec.length <= 0.0:
            return None
        vec.normalize()
        return vec
    except Exception:
        return None


def _vertex_point(vertex):
    try:
        return vertex.geometry
    except Exception:
        return None


def _parse_face_selector(selector):
    if selector == "largest_planar":
        return {"type": "largest_planar"}
    if selector == "largest_area":
        return {"type": "largest_area"}
    if selector.startswith("normal_closest:"):
        axis = selector.split(":", 1)[1].strip()
        if axis in ("+X", "-X", "+Y", "-Y", "+Z", "-Z"):
            return {"type": "normal_closest", "axis": axis}
    if selector.startswith("max_bbox_"):
        axis = selector.split("_")[-1].lower()
        if axis in ("x", "y", "z"):
            return {"type": "max_bbox", "axis": axis}
    if selector.startswith("min_bbox_"):
        axis = selector.split("_")[-1].lower()
        if axis in ("x", "y", "z"):
            return {"type": "min_bbox", "axis": axis}
    return None


def _parse_edge_selector(selector):
    if selector == "longest_edge":
        return {"type": "longest_edge"}
    if selector.startswith("normal_closest:"):
        axis = selector.split(":", 1)[1].strip()
        if axis in ("+X", "-X", "+Y", "-Y", "+Z", "-Z"):
            return {"type": "normal_closest", "axis": axis}
    if selector == "closest_to_point":
        return {"type": "closest_to_point"}
    return None


def _parse_vertex_selector(selector):
    if selector == "closest_to_point":
        return {"type": "closest_to_point"}
    return None


def _select_face(body, selector, units_mgr, convert_mm):
    candidates = []
    for face in body.faces:
        if selector["type"] == "largest_planar" and not _is_planar(face):
            continue
        if selector["type"] == "normal_closest" and not _is_planar(face):
            continue

        try:
            centroid = face.centroid
        except Exception:
            centroid = None
        if not centroid:
            continue

        area_mm2 = _face_area_mm2(face, units_mgr, convert_mm)
        face_id = _entity_id(face) or ""
        centroid_tuple = _point_tuple_mm(convert_mm, units_mgr, centroid)

        score = None
        normal_out = None
        if selector["type"] in ("largest_planar", "largest_area"):
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
            score = _vector_dot(normal, axis)
            normal_out = _normalize_vector(normal)
        elif selector["type"] in ("max_bbox", "min_bbox"):
            bbox = _bbox_mm(face, units_mgr, convert_mm)
            if not bbox:
                continue
            axis = selector["axis"]
            max_coord = bbox["max"][axis]
            min_coord = bbox["min"][axis]
            if selector["type"] == "max_bbox":
                score = max_coord
            else:
                score = -min_coord
        else:
            continue

        candidates.append(
            {
                "face": face,
                "score": score,
                "area_mm2": area_mm2,
                "centroid": centroid,
                "centroid_tuple": centroid_tuple,
                "face_id": face_id,
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


def _select_edge(entity, selector, units_mgr, convert_mm, point_mm=None):
    edges = []
    try:
        for edge in entity.edges:
            edges.append(edge)
    except Exception:
        return None, 0

    candidates = []
    for edge in edges:
        edge_id = _entity_id(edge) or ""
        length_mm = _edge_length_mm(edge, units_mgr, convert_mm)
        midpoint = _edge_midpoint(edge)
        if not midpoint:
            continue
        midpoint_tuple = _point_tuple_mm(convert_mm, units_mgr, midpoint)

        score = None
        if selector["type"] == "longest_edge":
            if length_mm is None:
                continue
            score = length_mm
        elif selector["type"] == "normal_closest":
            direction = _edge_direction(edge)
            if not direction:
                continue
            axis = _axis_vector(selector["axis"])
            score = _vector_dot(direction, axis)
        elif selector["type"] == "closest_to_point":
            if not point_mm:
                continue
            dx = midpoint_tuple[0] - point_mm["x"]
            dy = midpoint_tuple[1] - point_mm["y"]
            dz = midpoint_tuple[2] - point_mm["z"]
            score = -(dx * dx + dy * dy + dz * dz)
        else:
            continue

        candidates.append(
            {
                "edge": edge,
                "score": score,
                "length_mm": length_mm,
                "midpoint": midpoint,
                "midpoint_tuple": midpoint_tuple,
                "edge_id": edge_id,
            }
        )

    if not candidates:
        return None, 0

    def _tie_key(item):
        length = item["length_mm"] if item["length_mm"] is not None else -1.0
        return (-item["score"], -length, item["midpoint_tuple"], item["edge_id"])

    candidates.sort(key=_tie_key)
    return candidates[0], len(candidates)


def _select_vertex(entity, selector, units_mgr, convert_mm, point_mm=None):
    vertices = []
    try:
        for vertex in entity.vertices:
            vertices.append(vertex)
    except Exception:
        return None, 0

    candidates = []
    for vertex in vertices:
        vertex_id = _entity_id(vertex) or ""
        point = _vertex_point(vertex)
        if not point:
            continue
        point_tuple = _point_tuple_mm(convert_mm, units_mgr, point)

        score = None
        if selector["type"] == "closest_to_point":
            if not point_mm:
                continue
            dx = point_tuple[0] - point_mm["x"]
            dy = point_tuple[1] - point_mm["y"]
            dz = point_tuple[2] - point_mm["z"]
            score = -(dx * dx + dy * dy + dz * dz)
        else:
            continue

        candidates.append(
            {
                "vertex": vertex,
                "score": score,
                "point": point,
                "point_tuple": point_tuple,
                "vertex_id": vertex_id,
            }
        )

    if not candidates:
        return None, 0

    def _tie_key(item):
        return (-item["score"], item["point_tuple"], item["vertex_id"])

    candidates.sort(key=_tie_key)
    return candidates[0], len(candidates)
