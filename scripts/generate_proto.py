#!/usr/bin/env python3
"""Generate Python protobuf/gRPC code from backend/proto into backend/src/cce/gen."""

import subprocess
import sys
from pathlib import Path

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
    import grpc_tools

    well_known = Path(grpc_tools.__file__).parent / "_proto"
    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        "-I",
        str(PROTO_ROOT),
        "-I",
        str(well_known),
        "--python_out",
        str(OUT),
        "--grpc_python_out",
        str(OUT),
        *proto_files,
    ]
    result = subprocess.call(cmd)
    if result != 0:
        return result
    _rewrite_generated_imports()
    return 0


def _rewrite_generated_imports() -> None:
    generated = (OUT / "cce" / "v1").glob("*_pb2*.py")
    for path in generated:
        text = path.read_text(encoding="utf-8")
        text = text.replace("from cce.v1 import", "from cce.gen.cce.v1 import")
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
