from uuid import uuid4
from cce.governance.models import Actor, Workspace, WorkspaceCreate


class WorkspaceRepository:
    def __init__(self, db): self.db = db

    def create(self, request: WorkspaceCreate, actor: Actor) -> Workspace:
        actor.require("ADMIN")
        if not request.name.strip(): raise ValueError("Workspace name is required")
        workspace = Workspace(**request.model_dump(), workspace_id=request.name + "_workspace", created_by=actor.actor_id)
        with self.db.transaction() as cur:
            cur.execute("INSERT INTO workspace(workspace_uuid,workspace_id,name,description,created_by) VALUES(%s,%s,%s,%s,%s)",
                        (str(workspace.workspace_uuid), workspace.workspace_id, workspace.name, workspace.description, actor.actor_id))
            cur.execute("INSERT INTO context_package(package_id,workspace_uuid,name) VALUES(%s,%s,%s)", (str(uuid4()),str(workspace.workspace_uuid),workspace.name+"_package"))
        return workspace

    def get(self, workspace_id, *, include_archived=False, cur=None):
        if cur is None:
            with self.db.transaction() as cursor: return self.get(workspace_id, include_archived=include_archived, cur=cursor)
        cur.execute("SELECT workspace_uuid,workspace_id,name,description,status,created_by FROM workspace WHERE workspace_id=%s", (str(workspace_id),))
        row=cur.fetchone()
        if not row: raise KeyError("Workspace not found")
        if row['status'] != 'ACTIVE' and not include_archived: raise ValueError("Workspace is archived")
        return Workspace.model_validate(dict(row))

    def list(self):
        with self.db.transaction() as cur:
            cur.execute("SELECT workspace_uuid,workspace_id,name,description,status,created_by FROM workspace WHERE status='ACTIVE' ORDER BY name")
            return [Workspace.model_validate(dict(row)) for row in cur.fetchall()]

    def update(self, workspace_id, values, actor):
        actor.require('ADMIN')
        if set(values)-{'name','description'}: raise ValueError('Only name and description may be edited')
        with self.db.transaction() as cur:
            workspace=self.get(workspace_id,cur=cur)
            name=values.get('name',workspace.name)
            if not name or not name.strip(): raise ValueError('Workspace name is required')
            cur.execute('UPDATE workspace SET name=%s,description=%s,updated_at=now() WHERE workspace_uuid=%s', (name,values.get('description',workspace.description),str(workspace.workspace_uuid)))
        return self.get(workspace_id)

    def archive(self, workspace_id, actor):
        actor.require('ADMIN')
        with self.db.transaction() as cur:
            workspace=self.get(workspace_id,include_archived=True,cur=cur)
            cur.execute("UPDATE workspace SET status='ARCHIVED',updated_at=now() WHERE workspace_uuid=%s", (str(workspace.workspace_uuid),))
        return self.get(workspace_id,include_archived=True)
