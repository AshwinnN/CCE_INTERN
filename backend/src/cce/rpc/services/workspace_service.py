from google.protobuf.json_format import MessageToDict, ParseDict
from fastapi.encoders import jsonable_encoder
from cce.governance.models import Actor
from cce.workspaces.operations import Operations
from cce.runtime.compound import NoActivePackage


class WorkspaceRPCService:
    def __init__(self, app): self.operations=Operations(app)

    def invoke(self, action, request, context):
        from cce.gen.cce.v1.workspaces_pb2 import WorkspaceResponse
        import grpc
        try:
            actor=Actor(actor_id=request.actor.actor_id,roles=list(request.actor.roles)) if request.actor.actor_id else None
            result=self.operations.execute(action,request.workspace_id,request.resource_id,MessageToDict(request.payload,preserving_proto_field_name=True),actor)
            response=WorkspaceResponse()
            ParseDict(jsonable_encoder(result),response.data)
            return response
        except KeyError as exc: context.abort(grpc.StatusCode.NOT_FOUND,str(exc))
        except PermissionError as exc: context.abort(grpc.StatusCode.PERMISSION_DENIED,str(exc))
        except NoActivePackage as exc: context.abort(grpc.StatusCode.FAILED_PRECONDITION,str(exc))
        except ValueError as exc: context.abort(grpc.StatusCode.INVALID_ARGUMENT,str(exc))

    def CreateWorkspace(self, request, context): return self.invoke("CreateWorkspace",request,context)
    def ListWorkspaces(self, request, context): return self.invoke("ListWorkspaces",request,context)
    def GetWorkspace(self, request, context): return self.invoke("GetWorkspace",request,context)
    def UpdateWorkspace(self, request, context): return self.invoke("UpdateWorkspace",request,context)
    def ArchiveWorkspace(self, request, context): return self.invoke("ArchiveWorkspace",request,context)
    def ListSourceTypes(self, request, context): return self.invoke("ListSourceTypes",request,context)
    def DiscoverSources(self, request, context): return self.invoke("DiscoverSources",request,context)
    def RegisterSource(self, request, context): return self.invoke("RegisterSource",request,context)
    def ListSources(self, request, context): return self.invoke("ListSources",request,context)
    def GetSource(self, request, context): return self.invoke("GetSource",request,context)
    def UpdateSource(self, request, context): return self.invoke("UpdateSource",request,context)
    def ArchiveSource(self, request, context): return self.invoke("ArchiveSource",request,context)
    def TestSource(self, request, context): return self.invoke("TestSource",request,context)
    def IngestSource(self, request, context): return self.invoke("IngestSource",request,context)
    def GetIngestionRun(self, request, context): return self.invoke("GetIngestionRun",request,context)
    def ListProposals(self, request, context): return self.invoke("ListProposals",request,context)
    def GetProposal(self, request, context): return self.invoke("GetProposal",request,context)
    def EditProposal(self, request, context): return self.invoke("EditProposal",request,context)
    def ApproveProposal(self, request, context): return self.invoke("ApproveProposal",request,context)
    def RejectProposal(self, request, context): return self.invoke("RejectProposal",request,context)
    def GetPackage(self, request, context): return self.invoke("GetPackage",request,context)
    def RenamePackage(self, request, context): return self.invoke("RenamePackage",request,context)
    def ListVersions(self, request, context): return self.invoke("ListVersions",request,context)
    def GetVersion(self, request, context): return self.invoke("GetVersion",request,context)
    def Query(self, request, context): return self.invoke("Query",request,context)
    def Feedback(self, request, context): return self.invoke("Feedback",request,context)
    def Retrieve(self, request, context): return self.invoke("Retrieve",request,context)
