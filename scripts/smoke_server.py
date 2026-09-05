#!/usr/bin/env python3
"""Smoke check for the CCE gRPC server health endpoint."""

import argparse
import sys

import grpc

from cce.gen.cce.v1 import health_pb2, health_pb2_grpc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="localhost:50051")
    args = parser.parse_args()

    with grpc.insecure_channel(args.target) as channel:
        stub = health_pb2_grpc.HealthServiceStub(channel)
        response = stub.Check(health_pb2.HealthCheckRequest(), timeout=10)

    status_name = health_pb2.HealthCheckResponse.ServingStatus.Name(response.status)
    print(f"Health status: {status_name}")
    return 0 if response.status == health_pb2.HealthCheckResponse.SERVING else 1


if __name__ == "__main__":
    sys.exit(main())
