"""Shared workspace application boundary used by HTTP and gRPC."""
from pydantic import Field
from cce.context_packages.models.assets import Model, Asset
from cce.governance.models import Actor, WorkspaceCreate, ProposalFilter, ReviewRequest
from cce.runtime.models import QueryRequest
from cce.runtime.feedback import FeedbackRequest


class SourceDraft(Model):
    source_type: str
    credential_ref: str = Field(min_length=1)
    config: dict


class SourceRegistration(SourceDraft):
    name: str = Field(min_length=1)


class QueryBody(Model):
    question: str = Field(min_length=1,max_length=16000)


class EditProposal(Model):
    payload: Asset
    comment: str = ''


class Operations:
    def __init__(self, app): self.app=app

    def execute(self, action, workspace_id='', resource_id='', payload=None, actor=None):
        app=self.app; data=dict(payload or {})
        if action=='ListSourceTypes':
            from cce.sources.catalog import SOURCE_TYPES
            return [d.public() for d in SOURCE_TYPES.values()]
        if action=='ListWorkspaces': return app.workspace_repository.list()
        if action=='CreateWorkspace': return app.workspace_repository.create(WorkspaceCreate.model_validate(data),actor)
        workspace=app.workspace_repository.get(workspace_id)
        wid=workspace.workspace_uuid
        if action=='GetWorkspace': return workspace
        if action=='UpdateWorkspace': return app.workspace_repository.update(workspace_id,data,actor)
        if action=='ArchiveWorkspace': return app.workspace_repository.archive(workspace_id,actor)
        if action in {'RegisterSource','DiscoverSources','UpdateSource','ArchiveSource','TestSource','IngestSource','RenamePackage'}:
            if actor is None: raise PermissionError('ADMIN actor required')
            actor.require('ADMIN')
        if action=='RegisterSource': return app.source_service.register_source(wid,**SourceRegistration.model_validate(data).model_dump())
        if action=='DiscoverSources': return app.source_service.discover(wid,**SourceDraft.model_validate(data).model_dump())
        if action=='ListSources': return app.source_service.list_sources(wid)
        if action=='GetSource': return app.source_service.get_source(wid,resource_id)
        if action=='UpdateSource': return app.source_service.update(wid,resource_id,data)
        if action=='ArchiveSource': return app.source_repository.archive(wid,resource_id)
        if action=='TestSource': return app.source_service.test_connection(wid,resource_id)
        if action=='IngestSource': return app.source_service.trigger_ingestion(wid,resource_id)
        if action=='GetIngestionRun': return app.source_service.get_ingestion_status(wid,resource_id)
        if action=='ListProposals': return app.governance_service.list_proposals(ProposalFilter(workspace_uuid=wid,**data))
        if action=='GetProposal': return app.governance_service.get_proposal(resource_id,wid)
        if action in {'EditProposal','ApproveProposal','RejectProposal'}:
            if actor is None: raise PermissionError('STEWARD actor required')
            if action=='EditProposal': values=EditProposal.model_validate(data).model_dump()
            else:
                if set(data)-{'comment'}: raise ValueError('Only comment is accepted for a decision')
                values=data
            request=ReviewRequest(workspace_uuid=wid,proposal_id=resource_id,actor=actor,**values)
            fn={'EditProposal':app.governance_service.edit_proposal,'ApproveProposal':app.governance_service.approve_proposal,'RejectProposal':app.governance_service.reject_proposal}[action]
            return fn(request)
        if action=='GetPackage': return app.package_service.get_package(wid)
        if action=='RenamePackage':
            if set(data)!={'name'}: raise ValueError('Package rename requires name')
            return app.package_service.rename(wid,data['name'])
        if action=='ListVersions': return app.package_service.versions(wid)
        if action=='GetVersion': return app.package_service.get_package_version(wid,resource_id)
        if action=='Query':
            question=QueryBody.model_validate(data)
            return app.query_service.query(QueryRequest(workspace_id=workspace_id,question=question.question,actor_id=actor.actor_id if actor else None))
        if action=='Feedback':
            if actor is None: raise PermissionError('Feedback actor required')
            return app.feedback_service.submit(wid,FeedbackRequest.model_validate(data),actor)
        if action=='Retrieve':
            question=QueryBody.model_validate(data)
            ids=[str(s['source_id']) for s in app.source_service.list_sources(wid) if s['enabled']]
            hits=app.index_client.search(question.question,limit=10,metadata_filter={'workspace_uuid':str(wid),'source_id':{'$in':ids}})
            return [h for h in hits if h.get('metadata',{}).get('workspace_uuid')==str(wid) and h.get('metadata',{}).get('source_id') in ids]
        raise ValueError('Unknown workspace operation')
