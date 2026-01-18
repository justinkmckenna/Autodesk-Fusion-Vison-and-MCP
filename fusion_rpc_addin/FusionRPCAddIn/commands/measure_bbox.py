COMMAND = "measure_bbox"
REQUIRES_DESIGN = True


def handle(request, context):
    root_comp = context["root_comp"]
    units_mgr = context["units_mgr"]
    find_body = context["find_body"]
    convert_mm = context["convert_mm"]

    body_name = request.get("body_name")
    body = find_body(root_comp, body_name)
    if not body:
        return {"ok": False, "error": "No visible solid body found."}

    bbox = body.boundingBox
    min_pt = bbox.minPoint
    max_pt = bbox.maxPoint
    x_mm = convert_mm(units_mgr, max_pt.x - min_pt.x)
    y_mm = convert_mm(units_mgr, max_pt.y - min_pt.y)
    z_mm = convert_mm(units_mgr, max_pt.z - min_pt.z)
    return {
        "ok": True,
        "body": body.name,
        "x_mm": x_mm,
        "y_mm": y_mm,
        "z_mm": z_mm,
    }
