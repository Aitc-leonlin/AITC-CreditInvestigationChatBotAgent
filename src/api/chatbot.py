from fastapi import APIRouter
from time import perf_counter

# import graph
from src.agent.graph import graph

chatbot_router = APIRouter(tags=["chatbot"])


@chatbot_router.get("/chatbot/{user_input}")
async def get_chatbot_answer(user_input: str):
    started_at = perf_counter()
    graph_answer = graph.invoke({"user_input": user_input})
    print(f"[timing] chatbot.total_graph_to_final_answer took {perf_counter() - started_at:.3f}s")

    return {"answer": graph_answer["answer"]}
