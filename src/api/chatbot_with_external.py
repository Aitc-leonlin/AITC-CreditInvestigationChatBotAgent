from time import perf_counter

from fastapi import APIRouter, HTTPException, Request

from src.agent.graph import graph
from src.api.chatbot_base import (
    ChatbotWithExternalRequest,
    ChatbotWithExternalResponse,
    build_chatbot_response,
    build_graph_input,
    compact_text,
    dump_log_payload,
)


chatbot_with_external_router = APIRouter(tags=["chatbot"])


@chatbot_with_external_router.post(
    "/api/chatbot-with-external",
    response_model=ChatbotWithExternalResponse,
)
async def get_chatbot_answer_with_external(
    http_request: Request, request: ChatbotWithExternalRequest
):
    started_at = perf_counter()
    raw_request_body = await http_request.body()
    if raw_request_body:
        print(
            "[chatbotwithexternal] raw request body:\n"
            + raw_request_body.decode("utf-8", errors="replace")
        )

    if request.externalDataDecision == "adopted" and not compact_text(
        request.externalDataQueryText
    ):
        raise HTTPException(
            status_code=400,
            detail="externalDataQueryText is required when externalDataDecision is adopted.",
        )

    graph_input = build_graph_input(request, request_source="chatbot-with-external")
    graph_config = (
        {"configurable": {"thread_id": request.conversationId}}
        if request.conversationId
        else None
    )
    print(
        "[chatbotwithexternal] request payload:\n"
        + dump_log_payload(request.model_dump())
    )
    print("[chatbotwithexternal] graph input:\n" + dump_log_payload(graph_input))
    graph_answer = (
        graph.invoke(graph_input, config=graph_config)
        if graph_config
        else graph.invoke(graph_input)
    )
    print(
        "[timing] chatbotwithexternal.total_graph_to_final_answer took "
        f"{perf_counter() - started_at:.3f}s"
    )
    return build_chatbot_response(
        graph_answer,
        include_external_data_query_text=False,
        include_applied_external_data=True,
    )
