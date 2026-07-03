from typing import TypedDict, List, Annotated
import operator


class AgentState(TypedDict):
    # Using Annotated with operator.add ensures that messages 
    # are appended to the history rather than replaced.
    messages: Annotated[List[dict], operator.add]
    current_query: str
    documents: List[str]
    plan: List[str]
    status: str
    final_answer: str
    retry_count: int
    needs_retry: bool
    retrieval_failed: bool
    # Set by the retrieval/context guard when injection markers were stripped
    # from one or more retrieved documents.
    injection_detected: bool
    # Routing decision emitted by the document grader:
    #   "generate"  -> relevant docs found, proceed to responder
    #   "rewrite"   -> no relevant docs, retry budget remains (query phrasing issue)
    #   "websearch" -> no relevant docs after retries (likely a knowledge gap)
    next_action: str
