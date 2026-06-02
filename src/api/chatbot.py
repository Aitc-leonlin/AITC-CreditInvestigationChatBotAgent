from time import perf_counter

from fastapi import APIRouter, Request

from src.agent.graph import graph
from src.api.chatbot_base import (
    ChatbotRequest,
    ChatbotResponse,
    build_chatbot_response,
    build_graph_input,
    dump_log_payload,
)


chatbot_router = APIRouter(tags=["chatbot"])


@chatbot_router.post("/api/chatbot", response_model=ChatbotResponse)
async def get_chatbot_answer(http_request: Request, request: ChatbotRequest):
    started_at = perf_counter()
    raw_request_body = await http_request.body()
    if raw_request_body:
        print(
            "[chatbot] raw request body:\n"
            + raw_request_body.decode("utf-8", errors="replace")
        )
    graph_input = build_graph_input(request, request_source="chatbot")
    graph_config = (
        {"configurable": {"thread_id": request.conversationId}}
        if request.conversationId
        else None
    )
    print("[chatbot] request payload:\n" + dump_log_payload(request.model_dump()))
    print("[chatbot] graph input:\n" + dump_log_payload(graph_input))
    graph_answer = (
        graph.invoke(graph_input, config=graph_config)
        if graph_config
        else graph.invoke(graph_input)
    )
    print(
        f"[timing] chatbot.total_graph_to_final_answer took "
        f"{perf_counter() - started_at:.3f}s"
    )
    return build_chatbot_response(graph_answer)
