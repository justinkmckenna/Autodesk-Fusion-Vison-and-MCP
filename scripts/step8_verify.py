#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from agent_runner import (
    MCPClient,
    _ensure_dir,
    _get_region,
    _load_env,
    _load_calibration,
    _log_action,
    _looks_like_measure_panel,
    _now_stamp,
    _point_in_region,
    _shift_y_below_panel,
    _update_scale_from_capture,
    _find_dark_row_targets,
    _compute_silhouette_bbox,
    vision_client,
)


def _parse_connect(addr):
    host, port = addr.split(":")
    return host, int(port)


def _extract_distance(entries):
    best = None
    for entry in entries:
        metric = str(entry.get("metric", "")).lower()
        label = str(entry.get("label", "")).lower()
        units = str(entry.get("units", "")).lower()
        value = entry.get("value")
        if metric == "distance" or "distance" in label:
            try:
                value = float(value)
            except Exception:
                continue
            confidence = entry.get("confidence", 0.0)
            if units == "mm" and value > 0:
                confidence = 1.0
            best = {
                "value": value,
                "units": units,
                "confidence": confidence,
                "label": entry.get("label"),
                "metric": entry.get("metric"),
            }
            break
    return best


def main():
    _load_env()
    parser = argparse.ArgumentParser(description="Step 8 verify measurement run.")
    parser.add_argument("--connect", required=True, help="host:port for MCP server")
    args = parser.parse_args()

    host, port = _parse_connect(args.connect)
    client = MCPClient(connect_addr=(host, int(port)))
    calibration = _load_calibration()
    run_dir = os.path.join(ROOT_DIR, "logs", f"agent-run-{_now_stamp()}-step8-verify")
    _ensure_dir(run_dir)
    actions_log = os.path.join(run_dir, "actions.jsonl")

    _log_action(actions_log, {"tool": "precondition", "note": "Selection Filters assumed vertex-only."})

    # Focus + normalize view
    canvas = _get_region(calibration, "canvas")
    center_x = canvas["x"] + canvas["width"] * 0.5
    center_y = canvas["y"] + canvas["height"] * 0.5
    client.call_tool("mouse_click", {"x": int(round(center_x)), "y": int(round(center_y))})
    _log_action(actions_log, {"tool": "mouse_click", "region_name": "canvas", "target": "focus"})
    client.call_tool("key_press", {"keys": ["escape"]})
    client.call_tool("key_press", {"keys": ["escape"]})
    _log_action(actions_log, {"tool": "key_press", "keys": ["escape", "escape"]})
    client.call_tool("key_press", {"keys": ["f6"]})
    _log_action(actions_log, {"tool": "key_press", "keys": ["f6"]})
    client.call_tool("wait", {"milliseconds": 350})
    _log_action(actions_log, {"tool": "wait", "arguments": {"milliseconds": 350}})
    client.call_tool("key_press", {"keys": ["command", "6"]})
    _log_action(actions_log, {"tool": "key_press", "keys": ["command", "6"]})
    client.call_tool("wait", {"milliseconds": 350})
    _log_action(actions_log, {"tool": "wait", "arguments": {"milliseconds": 350}})
    client.call_tool("mouse_scroll", {"delta_y": -120, "steps": 6})
    _log_action(actions_log, {"tool": "mouse_scroll", "arguments": {"delta_y": -120, "steps": 6}})

    screen_info = client.call_tool("get_screen_info", {})
    _log_action(actions_log, {"tool": "get_screen_info", "result": screen_info})
    canvas_cap = client.call_tool("capture_screen", {"region_name": "canvas"})
    _log_action(actions_log, {"tool": "capture_screen", "region_name": "canvas", "result": canvas_cap})
    scale_factor, _ratio = _update_scale_from_capture(screen_info, canvas_cap)

    # Open Measure
    client.call_tool("key_press", {"keys": ["i"]})
    _log_action(actions_log, {"tool": "key_press", "keys": ["i"]})
    time.sleep(0.2)
    panel_check = client.call_tool("capture_screen", {"region_name": "measure_panel"})
    _log_action(actions_log, {"tool": "capture_screen", "region_name": "measure_panel_check", "result": panel_check})
    if not _looks_like_measure_panel(panel_check.get("image_path")):
        _log_action(actions_log, {"tool": "measure_panel_missing"})

    # Compute targets (row-scan preferred, then bbox mid-row)
    row_target = _find_dark_row_targets(canvas_cap.get("image_path"))
    bbox = _compute_silhouette_bbox(canvas_cap.get("image_path"))
    margin = 20
    if row_target:
        left_x = max(row_target["left"] + 5, 0)
        right_x = max(row_target["right"] - 5, left_x + 1)
        click_y = row_target["y"]
        reason = "row_scan_dark_pixels"
    elif bbox:
        left_x = max(bbox["left"] + margin, 0)
        right_x = min(bbox["right"] - margin, bbox["width"])
        click_y = int(bbox["top"] + (bbox["bottom"] - bbox["top"]) * 0.5)
        reason = "bbox_mid"
    else:
        left_x = int(canvas_cap.get("width", 800) * 0.2)
        right_x = int(canvas_cap.get("width", 800) * 0.8)
        click_y = int(canvas_cap.get("height", 600) * 0.6)
        reason = "fallback"

    abs_left_x = canvas["x"] + left_x * scale_factor
    abs_right_x = canvas["x"] + right_x * scale_factor
    abs_y = canvas["y"] + click_y * scale_factor
    panel = _get_region(calibration, "measure_panel")
    if _point_in_region(abs_left_x, abs_y, panel):
        abs_y = _shift_y_below_panel(abs_y, panel, canvas)
    if _point_in_region(abs_right_x, abs_y, panel):
        abs_y = _shift_y_below_panel(abs_y, panel, canvas)

    _log_action(
        actions_log,
        {
            "tool": "step8_targets",
            "reason": reason,
            "canvas_points": {"left_x": left_x, "right_x": right_x, "click_y": click_y},
            "abs_points": {"left_x": abs_left_x, "right_x": abs_right_x, "y": abs_y},
            "scale_factor": scale_factor,
        },
    )

    client.call_tool("mouse_click", {"x": int(round(abs_left_x)), "y": int(round(abs_y))})
    _log_action(actions_log, {"tool": "mouse_click", "region_name": "canvas", "target": "left_vertex"})
    time.sleep(0.2)
    client.call_tool("mouse_click", {"x": int(round(abs_right_x)), "y": int(round(abs_y))})
    _log_action(actions_log, {"tool": "mouse_click", "region_name": "canvas", "target": "right_vertex"})

    panel_post = client.call_tool("capture_screen", {"region_name": "measure_panel"})
    _log_action(actions_log, {"tool": "capture_screen", "region_name": "measure_panel", "result": panel_post})

    observation = vision_client(
        [panel_post.get("image_path")],
        "Extract measurement panel values only",
        focus="measure_panel",
    )
    entries = observation.get("extraction", {}).get("measurements", {}).get("entries", [])
    distance = _extract_distance(entries)
    success = distance is not None and distance["value"] > 0.05

    report = {
        "run_dir": run_dir,
        "canvas_region": canvas,
        "measure_panel_region": panel,
        "scale_factor": scale_factor,
        "targets": {
            "canvas": {"left_x": left_x, "right_x": right_x, "click_y": click_y},
            "absolute": {"left_x": abs_left_x, "right_x": abs_right_x, "y": abs_y},
        },
        "measure_panel_path": panel_post.get("image_path"),
        "distance": distance,
        "success": success,
    }

    report_path = os.path.join(run_dir, "step8-verify.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("## Step 8 Verify Report\n\n")
        fh.write(json.dumps(report, indent=2))
        fh.write("\n")

    print(json.dumps(report, indent=2))
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
