COMMAND = "ping"
REQUIRES_DESIGN = False


def handle(_request, _context):
    return {"ok": True, "msg": "pong"}
