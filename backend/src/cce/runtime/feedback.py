"""Feedback metadata is PostgreSQL governed state; feedback embeddings live in
the same AgenticPlane/local index boundary used for all other vector search
(see docs/decisions/ADR-003-agentic-plane-boundary.md) -- never a bespoke
pgvector column, so CCE never needs the Postgres `vector` extension just to
support feedback, on Azure-managed Postgres or anywhere else."""
from uuid import uuid4, uuid5, NAMESPACE_URL
from typing import Literal
from pydantic import Field
from cce.context_packages.models.assets import Model
from cce.persistence.postgres.lifecycle_db import json_param


class FeedbackAnalysis(Model):
    issue_category: str
    critique: str
    lesson: str
    confidence: float = Field(ge=0,le=1)


class FeedbackRequest(Model):
    trace_id: str
    rating: Literal['GOOD','BAD']
    comment: str = ''


def _feedback_source_id(workspace_uuid):
    return str(uuid5(NAMESPACE_URL, f'cce-feedback:{workspace_uuid}'))


class FeedbackService:
    def __init__(self, db, llm, index_client, top_k=5):
        self.db,self.llm,self.index_client,self.top_k=db,llm,index_client,top_k

    def submit(self, workspace_uuid, request, actor):
        with self.db.transaction() as cur:
            cur.execute('SELECT response FROM query_trace WHERE trace_id=%s AND workspace_uuid=%s AND parent_trace_id IS NULL', (request.trace_id,str(workspace_uuid)))
            row=cur.fetchone()
            if not row or not row['response']: raise KeyError('Completed workspace query not found')
            response=row['response']
        analysis=None
        comment=request.comment.strip()
        if request.rating=='BAD' and not comment:
            analysis=self.llm.invoke('feedback', 'Infer a possible failure category, short critique, recommended lesson and confidence from this explicitly downvoted response. Do not produce chain-of-thought. An inferred correction is uncertain, not truth.', response, FeedbackAnalysis)
        eligible=request.rating=='GOOD' or bool(comment) or (analysis is not None and analysis.confidence>=.70)
        critique=comment or (analysis.critique+'\nLesson: '+analysis.lesson if analysis else '')
        fid=uuid4()
        context=[item['context_on'].get('context_used',[]) for item in response.get('atomic_results',[])]
        with self.db.transaction() as cur:
            cur.execute('''INSERT INTO query_feedback(feedback_id,trace_id,workspace_uuid,rating,user_comment,question,answer,package_version_id,context_used,citations,issue_category,generated_critique,inference_confidence,lesson_eligible,created_by)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(trace_id,created_by) DO UPDATE SET rating=excluded.rating,user_comment=excluded.user_comment,issue_category=excluded.issue_category,generated_critique=excluded.generated_critique,inference_confidence=excluded.inference_confidence,lesson_eligible=excluded.lesson_eligible
            RETURNING feedback_id,rating,lesson_eligible,inference_confidence''',
            (str(fid),request.trace_id,str(workspace_uuid),request.rating,comment,response['question'],response['answer'],response['package'].get('package_version_id'),json_param(context),json_param(response.get('citations',[])),analysis.issue_category if analysis else None,critique,analysis.confidence if analysis else None,eligible,actor.actor_id))
            result=dict(cur.fetchone())
        if eligible:
            example=response['answer'] if request.rating=='GOOD' else (comment or critique)
            self.index_client.index({
                'document_id': f'feedback:{fid}',
                'source_id': _feedback_source_id(workspace_uuid),
                'metadata': {
                    'workspace_uuid': str(workspace_uuid),
                    'kind': 'feedback',
                    'rating': request.rating,
                    'lesson_eligible': True,
                    'question': response['question'],
                    'example': example,
                },
                'blocks': [{'id': 'feedback', 'type': 'text', 'text': response['question']}],
            })
        return result

    def retrieve(self, workspace_uuid, question):
        hits=self.index_client.search(question, limit=self.top_k, metadata_filter={
            'workspace_uuid': str(workspace_uuid), 'kind': 'feedback', 'lesson_eligible': True,
        })
        return [dict(
            label='GOOD / positive feedback' if h['metadata']['rating']=='GOOD' else 'BAD / negative lesson — avoid this failure',
            question=h['metadata']['question'],
            example=h['metadata']['example'],
        ) for h in hits]
