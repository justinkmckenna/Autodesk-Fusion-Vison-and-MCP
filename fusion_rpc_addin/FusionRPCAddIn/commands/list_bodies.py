COMMAND = "list_bodies"
REQUIRES_DESIGN = True


def handle(_request, context):
    root_comp = context["root_comp"]
    bodies = []
    for body in root_comp.bRepBodies:
        try:
            if body.isVisible and body.isSolid:
                bodies.append(body.name)
        except Exception:
            continue
    return {"ok": True, "bodies": bodies}
