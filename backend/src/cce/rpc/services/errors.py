"""Map service/request failures consistently; branch failures stay in QueryResponse."""
from functools import wraps
import grpc

def rpc_errors(function):
    @wraps(function)
    def call(self,request,context):
        try:return function(self,request,context)
        except PermissionError as exc:
            if context is None:raise
            context.abort(grpc.StatusCode.PERMISSION_DENIED,str(exc))
        except KeyError as exc:
            if context is None:raise
            context.abort(grpc.StatusCode.NOT_FOUND,str(exc))
        except ValueError as exc:
            if context is None:raise
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,str(exc))
        except Exception as exc:
            if context is None:raise
            context.abort(grpc.StatusCode.INTERNAL,str(exc))
    return call
