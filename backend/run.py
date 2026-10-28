import argparse
import json
import os
import socket
import sys
import uvicorn
from backend.config import RUNTIME


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def find_available_port(host: str, start_port: int = 8765, max_tries: int = 50) -> int:
    for port in range(start_port, start_port + max_tries):
        if is_port_available(host, port):
            return port
    raise RuntimeError(f"Could not find an available port in range {start_port}..{start_port + max_tries}")


def main():
    parser = argparse.ArgumentParser(description="Run ACE Timesheet Backend")
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Preferred port")
    args = parser.parse_args()

    host = args.host
    requested_port = int(os.environ.get("PORT") or args.port)

    if is_port_available(host, requested_port):
        port = requested_port
    else:
        port = find_available_port(host, requested_port + 1)
        print(f"[ACE] Port {requested_port} is occupied. Using available port {port} instead.")

    port_file = RUNTIME / "port.json"
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with port_file.open("w", encoding="utf-8") as f:
        json.dump({"port": port, "host": host}, f)

    print(f"[ACE] Server starting on http://{host}:{port}")
    try:
        uvicorn.run("backend.main:app", host=host, port=port, log_level="info")
    finally:
        try:
            # Another instance may have updated the shared discovery file.
            if port_file.exists() and json.loads(port_file.read_text(encoding="utf-8")) == {"port": port, "host": host}:
                port_file.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()
