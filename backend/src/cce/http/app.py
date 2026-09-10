"""Thin workspace-scoped production HTTP adapter."""
from fastapi import FastAPI, Request, Body
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from psycopg2 import IntegrityError, DataError
from cce.governance.models import Actor
from cce.runtime.compound import NoActivePackage
from cce.workspaces.operations import Operations


def create_app(app_context):
    app=FastAPI(title='CCE Workspace API')
    operations=Operations(app_context)
    @app.exception_handler(KeyError)
    async def missing(request,exc): return JSONResponse(status_code=404,content={'detail':str(exc)})
    @app.exception_handler(PermissionError)
    async def forbidden(request,exc): return JSONResponse(status_code=403,content={'detail':str(exc)})
    @app.exception_handler(ValueError)
    async def invalid(request,exc):
        if isinstance(exc,NoActivePackage): return JSONResponse(status_code=409,content={'error':exc.code,'detail':str(exc)})
        return JSONResponse(status_code=400,content={'detail':str(exc)})
    @app.exception_handler(IntegrityError)
    async def conflict(request,exc): return JSONResponse(status_code=409,content={'detail':'Operation conflicts with existing workspace data or ownership constraints.'})
    @app.exception_handler(DataError)
    async def bad_data(request,exc): return JSONResponse(status_code=400,content={'detail':'Invalid resource identifier or value.'})
    @app.get('/health')
    def health(): return {'status':'SERVING' if getattr(app_context,'ready',False) else 'NOT_SERVING'}

    def endpoint(action):
        def query_handler(request:Request, workspace_id:str='',resource_id:str=''):
            return operations.execute(action,workspace_id,resource_id,dict(request.query_params),None)

        def body_handler(request:Request, workspace_id:str='',resource_id:str='', body:dict|None=Body(default=None)):
            data=dict(body or {})
            claims=data.pop('actor',None)
            actor=Actor.model_validate(claims) if claims else None
            return operations.execute(action,workspace_id,resource_id,data,actor)

        return query_handler, body_handler

    routes=[
      ('GET','/source-types','ListSourceTypes'),('GET','/workspaces','ListWorkspaces'),('POST','/workspaces','CreateWorkspace'),
      ('GET','/workspaces/{workspace_id}','GetWorkspace'),('PATCH','/workspaces/{workspace_id}','UpdateWorkspace'),('DELETE','/workspaces/{workspace_id}','ArchiveWorkspace'),
      ('POST','/workspaces/{workspace_id}/sources/discover','DiscoverSources'),('GET','/workspaces/{workspace_id}/sources','ListSources'),('POST','/workspaces/{workspace_id}/sources','RegisterSource'),
      ('GET','/workspaces/{workspace_id}/sources/{resource_id}','GetSource'),('PATCH','/workspaces/{workspace_id}/sources/{resource_id}','UpdateSource'),('DELETE','/workspaces/{workspace_id}/sources/{resource_id}','ArchiveSource'),
      ('POST','/workspaces/{workspace_id}/sources/{resource_id}/test','TestSource'),('POST','/workspaces/{workspace_id}/sources/{resource_id}/ingest','IngestSource'),
      ('GET','/workspaces/{workspace_id}/ingestion-runs/{resource_id}','GetIngestionRun'),
      ('GET','/workspaces/{workspace_id}/proposals','ListProposals'),('GET','/workspaces/{workspace_id}/proposals/{resource_id}','GetProposal'),('PATCH','/workspaces/{workspace_id}/proposals/{resource_id}','EditProposal'),
      ('POST','/workspaces/{workspace_id}/proposals/{resource_id}/approve','ApproveProposal'),('POST','/workspaces/{workspace_id}/proposals/{resource_id}/reject','RejectProposal'),
      ('GET','/workspaces/{workspace_id}/package','GetPackage'),('PATCH','/workspaces/{workspace_id}/package','RenamePackage'),('GET','/workspaces/{workspace_id}/package/versions','ListVersions'),('GET','/workspaces/{workspace_id}/package/versions/{resource_id}','GetVersion'),
      ('POST','/workspaces/{workspace_id}/query','Query'),('POST','/workspaces/{workspace_id}/feedback','Feedback'),('POST','/workspaces/{workspace_id}/retrieve','Retrieve')]
    for method,path,action in routes:
        query_handler,body_handler=endpoint(action)
        handler=query_handler if method=='GET' else body_handler
        app.add_api_route(path,handler,methods=[method],name=action)
    return app
