"""Atomize, fan out complete ON/OFF subgraphs, then synthesize only successful ON answers."""
import operator
from typing import Annotated, TypedDict
from uuid import uuid4
from langgraph.graph import START, END, StateGraph
from langgraph.types import Send
from cce.runtime.models import AtomicQuestions, AnswerResult, QueryRequest, QueryResponse, WorkspaceInfo, SynthesisRequest, SynthesisAnswer


class NoActivePackage(ValueError):
    code='NO_ACTIVE_PACKAGE'


class State(TypedDict, total=False):
    request: QueryRequest
    trace_id: object
    workspace: WorkspaceInfo
    package: object
    package_info: dict
    questions: list[str]
    results: Annotated[list,operator.add]
    response: QueryResponse


class CompoundQuery:
    def __init__(self, runtime, workspaces, context, feedback):
        self.runtime,self.workspaces,self.context,self.feedback=runtime,workspaces,context,feedback
        graph=StateGraph(State)
        graph.add_node('create_query_trace',self._create)
        graph.add_node('atomize_question',self._atomize)
        graph.add_node('answer_atomic_question',self._atomic)
        graph.add_node('final_synthesis',self._synthesize)
        graph.add_node('persist_final_trace',self._persist)
        graph.add_edge(START,'create_query_trace')
        graph.add_edge('create_query_trace','atomize_question')
        graph.add_conditional_edges('atomize_question',lambda s:[Send('answer_atomic_question',{'state':s,'question':q,'index':i}) for i,q in enumerate(s['questions'])])
        graph.add_edge('answer_atomic_question','final_synthesis')
        graph.add_edge('final_synthesis','persist_final_trace')
        graph.add_edge('persist_final_trace',END)
        self.graph=graph.compile()

    def run(self, request):
        workspace=self.workspaces.get(request.workspace_id)
        package=self.context.active(workspace.workspace_uuid)
        if package is None: raise NoActivePackage('Workspace has no active approved context package version.')
        trace_id=uuid4()
        try:
            return self.graph.invoke({'request':request,'trace_id':trace_id,'workspace':WorkspaceInfo(**workspace.model_dump(include={'workspace_uuid','workspace_id','name'})),
                'package':package,'package_info':self.context.get_package(workspace.workspace_uuid),'results':[]},config={'max_concurrency':5})['response']
        except Exception as exc:
            self.runtime.traces.fail_trace(trace_id,exc)
            raise

    def _create(self,state):
        self.runtime.traces.create_trace(state['trace_id'],state['request'])
        return {}

    def _atomize(self,state):
        result=self.runtime._call(state['trace_id'],'atomization','Split the question into 1–10 standalone atomic questions, preserving names, constraints and all original context. A simple question stays one question. If more than 10 are necessary, return all required questions so validation rejects; never truncate.',state['request'],AtomicQuestions)
        if any(not q.strip() for q in result.questions): raise ValueError('Atomic questions must not be empty')
        return {'questions':result.questions}

    def _atomic(self,work):
        state=work['state'];question=work['question']
        lessons=self.feedback.retrieve(state['workspace'].workspace_uuid,question)
        request=state['request'].model_copy(update={'question':question,'metadata':{'parent_trace_id':str(state['trace_id']),'feedback':lessons}})
        result=self.runtime.run(request,state['workspace'],state['package'])
        return {'results':[(work['index'],result)]}

    def _synthesize(self,state):
        results=[result for _,result in sorted(state['results'],key=lambda item:item[0])]
        successful=[r for r in results if r.context_on.status=='SUCCESS' and r.context_on.answer]
        failed=[r.question for r in results if r not in successful]
        status='SUCCESS' if not failed else ('PARTIAL' if successful else 'FAILED')
        if successful:
            inputs=SynthesisRequest(original_question=state['request'].question,successful_on_answers=[SynthesisAnswer(question=r.question,answer=r.context_on.answer,citations=r.context_on.citations) for r in successful])
            answer=self.runtime._call(state['trace_id'],'synthesis','Synthesize only the supplied successful governed answers. Preserve conditions and uncertainty; do not invent facts. Citation labels and coordinates are externally supplied.',inputs,AnswerResult).answer
        else: answer='No atomic question could be answered successfully.'
        if failed: answer+='\n\nUnable to answer: '+'; '.join(failed)
        package=state['package']
        return {'response':QueryResponse(trace_id=state['trace_id'],status=status,question=state['request'].question,workspace=state['workspace'],
            package={'name':state['package_info']['name'],'version':package.version,'package_version_id':str(package.package_version_id)},answer=answer,
            citations=[c for r in successful for c in r.context_on.citations],atomic_results=results,errors=[e for r in results for e in r.errors])}

    def _persist(self,state):
        self.runtime.traces.finish_trace(state['response'])
        return {}
