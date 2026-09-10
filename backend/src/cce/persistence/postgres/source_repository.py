from uuid import uuid4
from cce.persistence.postgres.lifecycle_db import LifecycleDB, json_param


class PostgresSourceRepository:
    def __init__(self, dsn): self.db=LifecycleDB(dsn)

    def require_workspace(self, workspace_uuid, cur):
        cur.execute("SELECT workspace_uuid FROM workspace WHERE workspace_uuid=%s AND status='ACTIVE' FOR SHARE", (str(workspace_uuid),))
        if not cur.fetchone(): raise KeyError('Active workspace not found')

    def save_source(self, workspace_uuid, name, source_type, credential_ref, kind, config):
        source_id=uuid4()
        with self.db.transaction() as cur:
            self.require_workspace(workspace_uuid,cur)
            cur.execute("INSERT INTO cce_source(source_id,workspace_uuid,name,source_type,credential_ref,kind,config,enabled) VALUES(%s,%s,%s,%s,%s,%s,%s,true)",
                        (str(source_id),str(workspace_uuid),name,source_type,credential_ref,kind,json_param(config)))
        return self.get_source(workspace_uuid,source_id)

    def get_source(self, workspace_uuid, source_id):
        with self.db.transaction() as cur:
            self.require_workspace(workspace_uuid,cur)
            cur.execute('SELECT * FROM cce_source WHERE workspace_uuid=%s AND source_id=%s', (str(workspace_uuid),str(source_id)))
            row=cur.fetchone()
            if not row: raise KeyError('Workspace source not found')
            return dict(row)

    def get_internal_source(self, source_id):
        with self.db.transaction() as cur:
            cur.execute("SELECT s.* FROM cce_source s JOIN workspace w USING(workspace_uuid) WHERE source_id=%s AND w.status='ACTIVE'", (str(source_id),))
            row=cur.fetchone()
            if not row: raise KeyError('Source not found')
            return dict(row)

    def list_sources(self, workspace_uuid):
        with self.db.transaction() as cur:
            self.require_workspace(workspace_uuid,cur)
            cur.execute("SELECT s.*,to_jsonb(r) latest_ingestion FROM cce_source s LEFT JOIN LATERAL (SELECT run_id,status,started_at,finished_at,objects_processed,objects_failed,error_message FROM cce_ingestion_run WHERE source_id=s.source_id ORDER BY started_at DESC,run_id DESC LIMIT 1) r ON true WHERE s.workspace_uuid=%s AND s.archived_at IS NULL ORDER BY s.name", (str(workspace_uuid),))
            return [dict(row) for row in cur.fetchall()]

    def update(self, workspace_uuid, source_id, values):
        allowed={'name','credential_ref','config','enabled'}
        if not values or set(values)-allowed: raise ValueError('Invalid source update')
        with self.db.transaction() as cur:
            self.require_workspace(workspace_uuid,cur)
            assignments=','.join(key+'=%s' for key in values)
            params=[json_param(value) if key=='config' else value for key,value in values.items()]
            cur.execute('UPDATE cce_source SET '+assignments+',updated_at=now() WHERE workspace_uuid=%s AND source_id=%s AND archived_at IS NULL RETURNING source_id', (*params,str(workspace_uuid),str(source_id)))
            if not cur.fetchone(): raise KeyError('Workspace source not found')
        return self.get_source(workspace_uuid,source_id)

    def archive(self, workspace_uuid, source_id):
        with self.db.transaction() as cur:
            self.require_workspace(workspace_uuid,cur)
            cur.execute('UPDATE cce_source SET archived_at=coalesce(archived_at,now()),enabled=false,updated_at=now() WHERE workspace_uuid=%s AND source_id=%s RETURNING source_id',(str(workspace_uuid),str(source_id)))
            if not cur.fetchone(): raise KeyError('Workspace source not found')
        return self.get_source(workspace_uuid,source_id)

    def get_ingestion_run(self, workspace_uuid, run_id):
        with self.db.transaction() as cur:
            self.require_workspace(workspace_uuid,cur)
            cur.execute('SELECT r.* FROM cce_ingestion_run r JOIN cce_source s USING(source_id) WHERE s.workspace_uuid=%s AND r.run_id=%s',(str(workspace_uuid),str(run_id)))
            row=cur.fetchone()
            if not row: raise KeyError('Workspace ingestion run not found')
            return dict(row)
