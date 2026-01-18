import json
import os
import queue
import socket
import sys
import tempfile
import threading
import time
import traceback
import importlib.util

_EARLY_LOG_PATH = None


def _write_early_log(message):
    global _EARLY_LOG_PATH
    if not _EARLY_LOG_PATH:
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            _EARLY_LOG_PATH = os.path.join(base_dir, "FusionRPCAddIn_debug.log")
        except Exception:
            return
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(_EARLY_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


_write_early_log("FusionRPCAddIn: module import start")
try:
    import adsk.core
    import adsk.fusion
    _write_early_log("FusionRPCAddIn: adsk imports complete")
except Exception:
    _write_early_log("FusionRPCAddIn: adsk import failed:\n" + traceback.format_exc())
    raise

CUSTOM_EVENT_ID = "com.justin.fusion_rpc"
DEFAULT_PORT = 8766

_app = None
_ui = None
_server_thread = None
_server_stop = threading.Event()
_server_socket = None
_request_queue = queue.Queue()
_handlers = []
_log_path = None
_log_dir = None
_command_registry = {}
_command_modules = []
_commands_loaded = False


def _log(message):
    if not _log_path:
        _write_early_log(message)
        return
    try:
        with open(_log_path, "a", encoding="utf-8") as fh:
            fh.write(message + "\n")
    except Exception:
        pass


def _format_exception():
    return traceback.format_exc()


def _find_body(root_comp, body_name=None):
    for body in root_comp.bRepBodies:
        try:
            if not body.isVisible or not body.isSolid:
                continue
        except Exception:
            continue
        if body_name:
            if body.name == body_name:
                return body
        else:
            return body
    return None


def _convert_mm(units_mgr, value):
    try:
        return units_mgr.convert(value, units_mgr.internalUnits, "mm")
    except Exception:
        # Internal units are cm; fallback conversion.
        return value * 10.0


def _commands_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "commands")


def _load_command_modules():
    registry = {}
    modules = []
    cmd_dir = _commands_dir()
    if not os.path.isdir(cmd_dir):
        _log(f"Commands directory missing: {cmd_dir}")
        return registry, modules
    for filename in os.listdir(cmd_dir):
        if not filename.endswith(".py"):
            continue
        if filename.startswith("_") or filename == "__init__.py":
            continue
        cmd_name = filename[:-3]
        module_name = f"fusion_rpc_cmds.{cmd_name}"
        module_path = os.path.join(cmd_dir, filename)
        try:
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if not spec or not spec.loader:
                _log(f"Failed to load command module: {module_path}")
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:
            _log("Error loading command module:\n" + _format_exception())
            continue
        command = getattr(module, "COMMAND", None)
        handler = getattr(module, "handle", None)
        if not command or not callable(handler):
            _log(f"Command module missing COMMAND/handle: {module_path}")
            continue
        requires_design = bool(getattr(module, "REQUIRES_DESIGN", False))
        registry[command] = {
            "handle": handler,
            "requires_design": requires_design,
            "module": module_name,
        }
        modules.append(module_name)
    return registry, modules


def _reload_commands():
    global _command_registry, _command_modules, _commands_loaded
    for module_name in list(_command_modules):
        try:
            if module_name in sys.modules:
                del sys.modules[module_name]
        except Exception:
            pass
    registry, modules = _load_command_modules()
    _command_registry = registry
    _command_modules = modules
    _commands_loaded = True
    return {"ok": True, "commands": sorted(_command_registry.keys())}


def _ensure_commands_loaded():
    global _commands_loaded
    if _commands_loaded:
        return
    registry, modules = _load_command_modules()
    _command_registry.update(registry)
    _command_modules.extend(modules)
    _commands_loaded = True


class RpcEventHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            while True:
                request, done_event, response_holder = _request_queue.get_nowait()
                response = _handle_request(request)
                response_holder["response"] = response
                done_event.set()
        except queue.Empty:
            return
        except Exception:
            _log("Handler error:\n" + _format_exception())


def _get_custom_event(app, event_id):
    if hasattr(app, "customEvent"):
        try:
            return app.customEvent(event_id)
        except Exception:
            return None
    if hasattr(app, "customEvents"):
        try:
            return app.customEvents.itemById(event_id)
        except Exception:
            return None
    return None


def _register_custom_event(app, event_id, handler):
    if hasattr(app, "customEvents"):
        try:
            custom_event = app.customEvents.itemById(event_id)
        except Exception:
            custom_event = None
        if not custom_event:
            custom_event = app.customEvents.add(event_id)
        custom_event.add(handler)
        return True
    if hasattr(app, "addCustomEventHandler"):
        if hasattr(app, "registerCustomEvent"):
            app.registerCustomEvent(event_id)
        app.addCustomEventHandler(event_id, handler)
        return True
    if hasattr(app, "registerCustomEvent"):
        custom_event = app.registerCustomEvent(event_id)
        if custom_event:
            custom_event.add(handler)
            return True
    custom_event = _get_custom_event(app, event_id)
    if custom_event:
        custom_event.add(handler)
        return True
    return False


def _unregister_custom_event(app, event_id):
    if hasattr(app, "customEvents"):
        try:
            custom_event = app.customEvents.itemById(event_id)
        except Exception:
            custom_event = None
        if custom_event:
            try:
                app.customEvents.remove(custom_event)
            except Exception:
                pass
        return
    if hasattr(app, "removeCustomEventHandler"):
        try:
            app.removeCustomEventHandler(event_id)
        except Exception:
            pass
        return
    if hasattr(app, "unregisterCustomEvent"):
        try:
            app.unregisterCustomEvent(event_id)
        except Exception:
            pass


def _handle_request(request):
    response = {"ok": False}
    if isinstance(request, dict) and "id" in request:
        response["id"] = request.get("id")

    try:
        cmd = request.get("cmd")
        if cmd == "help":
            _ensure_commands_loaded()
            commands = sorted(_command_registry.keys())
            commands.extend(["help", "reload_commands"])
            response.update({"ok": True, "commands": sorted(set(commands))})
            return response
        if cmd == "reload_commands":
            response.update(_reload_commands())
            return response

        _ensure_commands_loaded()
        handler_entry = _command_registry.get(cmd)
        if not handler_entry:
            response.update({"ok": False, "error": f"Unknown command: {cmd}"})
            return response

        design = adsk.fusion.Design.cast(_app.activeProduct)
        if handler_entry.get("requires_design"):
            if not design:
                response.update({"ok": False, "error": "No active Fusion design."})
                return response
            root_comp = design.rootComponent
            units_mgr = design.unitsManager
        else:
            root_comp = None
            units_mgr = None

        context = {
            "app": _app,
            "ui": _ui,
            "design": design,
            "root_comp": root_comp,
            "units_mgr": units_mgr,
            "log": _log,
            "find_body": _find_body,
            "convert_mm": _convert_mm,
        }
        result = handler_entry["handle"](request, context)
        if isinstance(result, dict):
            response.update(result)
        else:
            response.update({"ok": True, "result": result})
        return response
    except Exception:
        response.update({"ok": False, "error": _format_exception()})
        return response


def _server_loop(port):
    global _server_socket
    _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server_socket.bind(("127.0.0.1", port))
    _server_socket.listen(5)
    _server_socket.settimeout(0.5)
    _log(f"FusionRPCAddIn listening on 127.0.0.1:{port}")

    while not _server_stop.is_set():
        try:
            conn, _addr = _server_socket.accept()
        except socket.timeout:
            continue
        except Exception:
            break
        with conn:
            conn.settimeout(1.0)
            try:
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                if not data:
                    continue
                request = json.loads(data.decode("utf-8"))
                _log("FusionRPCAddIn: received request: {}".format(request))
                done_event = threading.Event()
                response_holder = {}
                _request_queue.put((request, done_event, response_holder))
                fired = False
                try:
                    fired = _app.fireCustomEvent(CUSTOM_EVENT_ID)
                except Exception:
                    _log("FusionRPCAddIn: fireCustomEvent failed:\n" + _format_exception())
                _log("FusionRPCAddIn: fireCustomEvent returned {}".format(fired))
                if done_event.wait(10.0):
                    response = response_holder.get("response", {"ok": False, "error": "No response"})
                    _log("FusionRPCAddIn: response ready")
                else:
                    _log("FusionRPCAddIn: timeout waiting for Fusion API response")
                    response = {"ok": False, "error": "Timeout waiting for Fusion API"}
                conn.sendall(json.dumps(response).encode("utf-8"))
            except Exception:
                err = {"ok": False, "error": _format_exception()}
                try:
                    conn.sendall(json.dumps(err).encode("utf-8"))
                except Exception:
                    pass

    try:
        _server_socket.close()
    except Exception:
        pass


def run(context):
    global _app, _ui, _server_thread, _log_path
    _write_early_log("FusionRPCAddIn: run() entered")
    _app = adsk.core.Application.get()
    _ui = _app.userInterface
    _write_early_log("FusionRPCAddIn: got app/ui")
    try:
        custom_attrs = [name for name in dir(_app) if "custom" in name.lower()]
        _write_early_log("FusionRPCAddIn: app custom attrs: " + ", ".join(custom_attrs))
    except Exception:
        _write_early_log("FusionRPCAddIn: failed to inspect app custom attrs")

    port = int(os.environ.get("FUSION_RPC_PORT", DEFAULT_PORT))
    global _log_dir
    try:
        user_root = _app.userDataFolder
        _log_dir = os.path.join(user_root, "FusionRPCAddInLogs")
        _write_early_log(f"FusionRPCAddIn: userDataFolder={user_root}")
    except Exception:
        _log_dir = os.path.join(tempfile.gettempdir(), "FusionRPCAddInLogs")
        _write_early_log("FusionRPCAddIn: using temp log dir")
    try:
        os.makedirs(_log_dir, exist_ok=True)
    except Exception:
        _write_early_log("FusionRPCAddIn: failed to create log dir")
        pass
    _log_path = os.path.join(_log_dir, "fusion_rpc_addin.log")
    _log("FusionRPCAddIn run() starting")
    _log(f"Log path: {_log_path}")

    _write_early_log("FusionRPCAddIn: registering custom event")
    handler = RpcEventHandler()
    try:
        _unregister_custom_event(_app, CUSTOM_EVENT_ID)
        _write_early_log("FusionRPCAddIn: unregistered prior custom event (if any)")
        ok = _register_custom_event(_app, CUSTOM_EVENT_ID, handler)
        if not ok:
            raise RuntimeError("Custom event registration returned False.")
        _handlers.append(handler)
        _write_early_log("FusionRPCAddIn: custom event registered")
    except Exception:
        err = _format_exception()
        _write_early_log("FusionRPCAddIn: custom event registration failed:\n" + err)
        if _ui:
            _ui.messageBox("FusionRPCAddIn failed to register custom event:\n{}".format(err))
        return

    _server_stop.clear()
    _write_early_log("FusionRPCAddIn: starting server thread")
    _server_thread = threading.Thread(target=_server_loop, args=(port,), daemon=True)
    _server_thread.start()
    _write_early_log("FusionRPCAddIn: server thread started")

    _write_early_log("FusionRPCAddIn: showing messageBox")
    _ui.messageBox(f"Fusion RPC Add-In started on 127.0.0.1:{port}\nLog: {_log_path}")
    _write_early_log("FusionRPCAddIn: run() completed")


def stop(context):
    try:
        _log("FusionRPCAddIn stop() called")
        _server_stop.set()
        if _server_socket:
            try:
                _server_socket.close()
            except Exception:
                pass
        if _server_thread:
            _server_thread.join(timeout=2.0)
        if _app:
            _unregister_custom_event(_app, CUSTOM_EVENT_ID)
    except Exception:
        if _ui:
            _ui.messageBox("FusionRPCAddIn stop failed:\n{}".format(_format_exception()))
