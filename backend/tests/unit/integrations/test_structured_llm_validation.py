import copy
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from cce.governance.models import ExtractionResult
from cce.integrations.llm.client import StructuredLLM


class Request(BaseModel):
    content: str = 'source evidence'


def response(payload):
    return {'parsed': None, 'raw': SimpleNamespace(tool_calls=[{'args': payload}]),
            'parsing_error': None}


def candidate():
    return {'domain_id': str(uuid4()),
            'payload': {'asset_type': 'GLOSSARY', 'canonical_key': 'inventory',
                        'term': 'Inventory', 'definition': 'Goods available.'},
            'evidence': [{'source_id': str(uuid4()), 'source_item_id': str(uuid4()),
                          'source_uri': 'test:item', 'document_id': 'item',
                          'ingestion_run_id': str(uuid4()), 'content_hash': 'hash'}]}


def client(monkeypatch, results):
    calls = []

    class Model:
        def __init__(self, **kwargs):
            pass

        def with_structured_output(self, output_type, **kwargs):
            assert kwargs['method'] == 'json_mode'
            return self

        def invoke(self, messages):
            calls.append(copy.deepcopy(messages))
            return copy.deepcopy(results[min(len(calls) - 1, len(results) - 1)])

    monkeypatch.setitem(sys.modules, 'langchain_openai', SimpleNamespace(ChatOpenAI=Model))
    settings = SimpleNamespace(llm_provider='litellm', llm_api_key='test',
                               llm_base_url='http://test', llm_model='test',
                               llm_timeout=10, llm_max_retries=0)
    return StructuredLLM(settings), calls


def test_retries_string_payload_and_canonical_key_as_uuid(monkeypatch):
    valid = candidate()
    invalid = {**valid, 'payload': 'Goods available.', 'target_asset_id': 'GLOSSARY:INVENTORY'}
    llm, calls = client(monkeypatch, [response({'candidates': [invalid]}),
                                     response({'candidates': [valid]})])
    result = llm.invoke('extraction', 'Extract', Request(), ExtractionResult)
    assert result.candidates[0].payload.definition == 'Goods available.'
    assert result.candidates[0].target_asset_id is None
    assert len(calls) == 2
    assert '"$defs"' in calls[0][0][1]
    assert 'target_asset_id' in calls[1][-1][1]
    assert 'payload' in calls[1][-1][1]


def test_invalid_candidates_are_not_silently_dropped(monkeypatch):
    invalid = {**candidate(), 'payload': 'invalid'}
    llm, calls = client(monkeypatch, [response({'candidates': [invalid]})])
    with pytest.raises(ValidationError):
        llm.invoke('extraction', 'Extract', Request(), ExtractionResult)
    assert len(calls) == 3


def test_parsed_success_does_not_retry(monkeypatch):
    parsed = ExtractionResult.model_validate({'candidates': [candidate()]})
    llm, calls = client(monkeypatch, [{'parsed': parsed}])
    assert llm.invoke('extraction', 'Extract', Request(), ExtractionResult) == parsed
    assert len(calls) == 1


def test_json_content_fallback_normalizes_encoded_payload(monkeypatch):
    import json
    valid = candidate()
    valid['payload'] = json.dumps(valid['payload'])
    llm, calls = client(monkeypatch, [
        {'parsed': None, 'raw': SimpleNamespace(content=json.dumps({'candidates': [valid]})),
         'parsing_error': ValueError('encoded payload')}
    ])
    result = llm.invoke('extraction', 'Extract', Request(), ExtractionResult)
    assert result.candidates[0].payload.term == 'Inventory'
    assert len(calls) == 1
