import os

COMMAND = "status"
REQUIRES_DESIGN = True


def _safe_get(obj, attr, default=None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def _list_visible_solid_bodies(root_comp):
    bodies = []
    for body in root_comp.bRepBodies:
        try:
            if body.isVisible and body.isSolid:
                bodies.append(body)
        except Exception:
            continue
    return bodies


def handle(_request, context):
    app = context.get("app")
    design = context.get("design")
    root_comp = context.get("root_comp")
    units_mgr = context.get("units_mgr")

    if not design:
        return {"ok": False, "error": "No active design."}
    if not root_comp:
        return {"ok": False, "error": "No root component."}

    bodies = _list_visible_solid_bodies(root_comp)
    body_names = sorted([body.name for body in bodies])

    document = _safe_get(app, "activeDocument")
    document_name = _safe_get(document, "name")
    document_is_saved = _safe_get(document, "isSaved")
    document_path = _safe_get(document, "fullPath")

    design_name = _safe_get(design, "name")
    fusion_version = _safe_get(app, "productVersion")

    units = None
    try:
        units = units_mgr.defaultLengthUnits
    except Exception:
        units = None

    port = None
    try:
        port = int(os.environ.get("FUSION_RPC_PORT", ""))
    except Exception:
        port = None

    data = {
        "app": {"fusion_version": fusion_version},
        "document": {
            "name": document_name,
            "is_saved": document_is_saved,
            "path": document_path,
        },
        "design": {"is_active": True, "name": design_name},
        "units": {"default_length_units": units},
        "root_component": {"name": root_comp.name},
        "bodies": {"visible_solid_count": len(body_names), "names": body_names},
        "rpc": {"port": port},
    }

    return {"ok": True, "error": None, "data": data}
