"""Typed grounding adapter reusing existing parsers, normalization and DLP helpers.

The governed source graph does not invoke the legacy dictionary-state graph or
its SDK emit/checkpoint nodes. Raw provider envelopes are confined here.
"""
import hashlib
import json
import tempfile
from pathlib import Path
from uuid import UUID,uuid4
from pydantic import Field
from cce.context_packages.models.assets import Model
from cce.connectors.base.canonical_types import canonicalize_type
from cce.ingestion.lifecycle_models import SourceItem,GroundedItem
from cce.ingestion.orchestrator import persist_structured_metadata_node
from cce.ingestion.normalizers.document import normalize_to_canonical
from cce.ingestion.models import DocumentMetadata
from cce.ingestion.parsers.factory import ParserFactory
from cce.ingestion.change_detection.file_detection import detect_mime_type
from cce.security.dlp import redact_text

class GroundingAdapter:
    def __init__(self,sources):self.sources=sources
    def discover(self,source_id)->list[SourceItem]:
        source=self.sources._require_source(str(source_id));connector=self.sources._build_connector(source)
        try:
            connector.connect();items=[];config=source.get('config') or {}
            if source['kind']=='structured':
                if 'schema_selection' in config or source['source_type'] == 'mysql':
                    from cce.sources.catalog import source_type_definition, selected_schemas
                    typed = source_type_definition(source['source_type']).validate_config(config)
                    schemas = selected_schemas(source['source_type'], typed, connector)
                else:
                    schemas = [config.get('schema', 'PUBLIC')]
                for schema in schemas:
                    if config.get('max_tables'):raise ValueError('Governed ingestion requires a complete configured schema inventory; remove max_tables')
                    card=connector.get_schema_card(schema)
                    # The existing deterministic persistence helper keeps one full schema snapshot.
                    persisted=persist_structured_metadata_node({'kind':'structured','raw_content':card,'adapter':source['source_type'],
                        'source_id':str(source_id),'schema_database':config.get('database'),
                        '_metadata_repository':self.sources.metadata_repository,'warnings':[]})
                    if persisted['warnings']:raise RuntimeError('; '.join(persisted['warnings']))
                    for table in card.get('tables',[]):
                        identity=f"{config.get('database','')}.{schema}.{table['name']}"
                        semantic={k:v for k,v in table.items() if k!='row_count'}
                        for column in semantic.get('columns',[]):
                            canonical,details=canonicalize_type(column.get('type',''),source['source_type'])
                            column['canonical_type']=canonical;column['type_detail']=details
                        content=json.dumps(semantic,sort_keys=True,default=str)
                        # Keep the content hash of the source, but persist only redacted sample metadata.
                        safe=json.loads(redact_text(content))
                        items.append(SourceItem(source_item_id=uuid4(),source_id=source_id,source_native_id=identity,
                            canonical_uri=source['source_type']+':'+identity,content_hash=hashlib.sha256(content.encode()).hexdigest(),
                            change_type='NEW',metadata={'schema':schema,'table':safe}))
            else:
                for obj in connector.list_objects(config.get('prefix')).get('objects',[]):
                    error=None
                    try:data=connector.fetch_object(obj['object_id']);digest=hashlib.sha256(data).hexdigest()
                    except Exception as exc:digest='unreadable';error=str(exc)
                    items.append(SourceItem(source_item_id=uuid4(),source_id=source_id,source_native_id=obj['object_id'],
                        canonical_uri=obj.get('source_ref') or obj['object_id'],content_hash=digest,change_type='NEW',
                        metadata={'object':obj,'discovery_error':error}))
            return items
        finally:connector.close()
    def ground(self,item:SourceItem,run_id:UUID)->GroundedItem:
        if item.metadata.get('discovery_error'):raise RuntimeError(item.metadata['discovery_error'])
        source=self.sources._require_source(str(item.source_id));connector=self.sources._build_connector(source)
        try:
            connector.connect()
            if source['kind']=='structured':
                normalized=normalize_to_canonical({'schema':item.metadata['schema'],'tables':[item.metadata['table']]},'structured',source['source_type'])
            else:
                data=connector.fetch_object(item.source_native_id or item.canonical_uri)
                if hashlib.sha256(data).hexdigest()!=item.content_hash:raise RuntimeError('Source changed during processing; retry ingestion')
                suffix=Path(item.metadata.get("object", {}).get("filename") or item.source_native_id or item.canonical_uri).suffix
                with tempfile.TemporaryDirectory(prefix='cce-ground-') as directory:
                    path=Path(directory)/('document'+suffix);path.write_bytes(data)
                    mime=detect_mime_type(str(path));parser=ParserFactory.get_parser(mime)
                    if parser is None:raise ValueError(f'Unsupported document MIME type: {mime}')
                    parsed=parser.parse(str(path),DocumentMetadata(document_id=item.source_native_id or item.canonical_uri,
                        source_system=source['source_type'],source_uri=item.canonical_uri,mime_type=mime))
                    if parsed.status.value!='SUCCESS' or parsed.document is None:
                        raise ValueError('; '.join(parsed.errors or ['Incomplete document extraction']))
                    normalized=normalize_to_canonical(parsed.document.model_dump(mode='json'),'unstructured')
            from cce.ingestion.lifecycle_models import IndexBlock,IndexCell,GroundingPayload
            blocks=[]
            def append_block(element):
                cells=[IndexCell(**{**c, 'text':redact_text(c.get('text',''))}) for c in element.get('cells',[])]
                block=IndexBlock(id=element['id'],type=element.get('type','text'),text=redact_text(element.get('text','')),cells=cells,
                    metadata={**element.get('metadata',{}), **{k:element[k] for k in ('page_number','bbox','confidence','parent_id','order') if element.get(k) is not None}})
                blocks.append(block)
                for table in element.get('tables',[]):append_block(table)
            for element in normalized.get('elements',[]):append_block(element)
            content='\n'.join([part for b in blocks for part in [b.text,*[c.text for c in b.cells]] if part])
            if not content:raise ValueError('No normalized text extracted')
            payload=GroundingPayload(document_id=item.source_native_id or item.canonical_uri,source_id=item.source_id,
                source_ref=item.canonical_uri,object_id=item.source_native_id or item.canonical_uri,revision=item.content_hash,
                trace_id=run_id,blocks=blocks,metadata=normalized.get("metadata",{}))
            return GroundedItem(content=content,payload=payload)
        finally:connector.close()
