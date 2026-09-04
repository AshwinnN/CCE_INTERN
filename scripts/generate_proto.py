#!/usr/bin/env python3
"""Generate Python protobuf/gRPC code from backend/proto into backend/src/cce/gen."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PROTO_ROOT = BACKEND / "proto"
OUT = BACKEND / "src" / "cce" / "gen"


def main() -> int:
    proto_files = [str(path) for path in (PROTO_ROOT / "cce" / "v1").glob("*.proto")]
    if not proto_files:
        print("No proto files found under %s" % PROTO_ROOT, file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        "-I",
        str(PROTO_ROOT),
        "--python_out",
        str(OUT),
        "--grpc_python_out",
        str(OUT),
        *proto_files,
    ]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
