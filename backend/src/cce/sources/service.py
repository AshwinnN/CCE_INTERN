from cce.connectors.factory import ConnectorFactory
from cce.sources.catalog import source_type_definition, is_user_schema
from cce.sources.models import IngestionRunResult


class SourceService:
    def __init__(self, *, source_repository, metadata_repository, checkpoint_store, index_client, ingestion_repository, **kwargs):
        self.source_repository=source_repository
        self.metadata_repository=metadata_repository
        self.checkpoint_store=checkpoint_store
        self.index_client=index_client
        self.ingestion_repository=ingestion_repository

    def register_source(self, workspace_uuid, *, name, source_type, credential_ref, config):
        if not name.strip() or not credential_ref.strip(): raise ValueError('Source name and credential reference are required')
        definition=source_type_definition(source_type)
        parsed=definition.validate_config(config)
        return self.source_repository.save_source(workspace_uuid,name,source_type,credential_ref,definition.kind,parsed.model_dump(mode='json'))

    def list_sources(self, workspace_uuid): return self.source_repository.list_sources(workspace_uuid)
    def get_source(self, workspace_uuid, source_id): return self.source_repository.get_source(workspace_uuid,source_id)

    def update(self, workspace_uuid, source_id, values):
        source=self.get_source(workspace_uuid,source_id)
        if 'name' in values and not values['name'].strip(): raise ValueError('Source name is required')
        if 'credential_ref' in values and not values['credential_ref'].strip(): raise ValueError('Credential reference is required')
        if 'config' in values: values['config']=source_type_definition(source['source_type']).validate_config(values['config']).model_dump(mode='json')
        return self.source_repository.update(workspace_uuid,source_id,values)

    def discover(self, workspace_uuid, *, source_type, credential_ref, config):
        with self.source_repository.db.transaction() as cur: self.source_repository.require_workspace(workspace_uuid,cur)
        connector=ConnectorFactory.create_source(source_type,config,credential_ref,'draft',draft=True)
        try:
            connector.connect()
            schemas=connector.list_schemas() if source_type_definition(source_type).schema_capable else []
            return {'connection_status':'SUCCESS','schemas':[s for s in schemas if is_user_schema(source_type,s)]}
        finally: connector.close()

    def test_connection(self, workspace_uuid, source_id):
        source=self.get_source(workspace_uuid,source_id)
        self._enabled(source)
        connector=self._build_connector(source)
        try:
            connector.connect()
            return {'source_id':source_id,'status':'SUCCESS'}
        finally: connector.close()

    def trigger_ingestion(self, workspace_uuid, source_id):
        source=self.get_source(workspace_uuid,source_id)
        self._enabled(source)
        run=self.ingestion_repository.create_or_resume(source_id)
        return IngestionRunResult(ingestion_run_id=str(run.ingestion_run_id),status=run.status.value,objects_processed=run.objects_processed,objects_failed=run.objects_failed)

    def get_ingestion_status(self, workspace_uuid, run_id):
        return self.source_repository.get_ingestion_run(workspace_uuid,run_id)

    def _enabled(self,source):
        if not source['enabled'] or source.get('archived_at'): raise ValueError('Source is disabled or archived')

    def _require_source(self, source_id):
        source=self.source_repository.get_internal_source(source_id)
        self._enabled(source)
        return self._normalize_source(source)

    @staticmethod
    def _normalize_source(source):
        from cce.sources.catalog import normalize_stored_config
        return {**source, 'config': normalize_stored_config(source['source_type'], source['config'])}

    def _build_connector(self, source):
        source = self._normalize_source(source)
        if source['source_type']=='local-fs':
            return ConnectorFactory.create_unstructured('local-fs',root_path=source['config']['root_path'],source_id=str(source['source_id']))
        return ConnectorFactory.create_source(source['source_type'],source['config'],source['credential_ref'],str(source['source_id']))
