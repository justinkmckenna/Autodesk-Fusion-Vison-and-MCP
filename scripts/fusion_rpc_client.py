#!/usr/bin/env python3
import argparse
import json
import socket


def _send_request(host, port, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(data)
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks).decode("utf-8")
    return json.loads(raw) if raw else {"ok": False, "error": "Empty response"}


def main():
    parser = argparse.ArgumentParser(description="Fusion RPC client.")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("cmd")
    parser.add_argument("--body", type=str, default=None)
    parser.add_argument("--payload", type=str, default=None)
    parser.add_argument("--param", action="append", default=[])
    args = parser.parse_args()

    payload = {"cmd": args.cmd}
    if args.body:
        payload["body_name"] = args.body
    if args.payload:
        payload.update(json.loads(args.payload))
    for item in args.param:
        if "=" not in item:
            raise SystemExit(f"--param must be key=value, got: {item}")
        key, value = item.split("=", 1)
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
        payload[key] = value

    response = _send_request("127.0.0.1", args.port, payload, args.timeout)
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()
