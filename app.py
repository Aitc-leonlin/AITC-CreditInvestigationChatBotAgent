import os
import sys
import asyncio
import json
import logging
from time import perf_counter
from typing import List

# import chromadb
import uvicorn

from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv

load_dotenv()

# from src.services.save_document_into_vectordb_service import establish_vector_data
from src.mappings.company_stock_code_array import CompanyStockCodeArray
from fastapi.middleware.cors import CORSMiddleware

# import LangChain lib
from langchain_community.utilities import SQLDatabase
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

# import type
from src.types.langgraph_state_types import OverallState

# import graph
from src.agent.graph import graph
from src.services.db_path import build_sqlite_db_diagnostics

# import api routers
from src.api.chatbot import chatbot_router


from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage


# 要開啟python專案時，都要下這個指令開啟該專案的虛擬環境
# python3 -m venv venv
# source venv/bin/activate


app = FastAPI()
api_router = APIRouter()
api_router.include_router(chatbot_router)
app.include_router(api_router)
logger = logging.getLogger(__name__)


def env_flag_enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().upper() == "TRUE"


def parse_cors_allow_origins() -> List[str]:
    configured = os.getenv("CORS_ALLOW_ORIGINS", "")
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    if origins:
        return origins
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://aitc-credit-investigation-chat-bot.vercel.app",
    ]


allow_origins = parse_cors_allow_origins()
is_render_deploy = env_flag_enabled("IS_RENDER_DEPLOY", default=False)
allow_origin_regex = (
    r"https://.*\.onrender\.com" if is_render_deploy and not os.getenv("CORS_ALLOW_ORIGINS") else None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def log_sqlite_db_diagnostics() -> None:
    diagnostics = build_sqlite_db_diagnostics()
    logger.warning("SQLite DB diagnostics:\n%s", json.dumps(diagnostics, ensure_ascii=False, indent=2))


log_sqlite_db_diagnostics()


# 建立 VectorStore
# client = chromadb.HttpClient(host="localhost", port=8000)
# embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

# vector_store = Chroma(
#     client=client, collection_name="a-test-collection", embedding_function=embeddings
# )


# Terminal chat mode
async def terminal_chat():
    while True:
        user_input = input("You: ")
        if user_input.lower() in ("exit", "quit"):
            break
        try:
            started_at = perf_counter()
            # graph_answer = graph.invoke({"user_input": user_input})
            graph_answer = graph.invoke(
                {
                    "messages": [HumanMessage(content=user_input)],
                    "user_input": user_input,
                },
                config={"configurable": {"thread_id": "1"}},
            )
            print(f"[timing] terminal_chat.total_graph_to_final_answer took {perf_counter() - started_at:.3f}s")
            # print("graph_answer==========:", graph_answer)

            # print("The answer is :", graph_answer["answer"])
        except Exception as err:
            print("Error:", err, file=sys.stderr)


if __name__ == "__main__":
    host = "0.0.0.0" if is_render_deploy else "localhost"
    default_port = 10000 if is_render_deploy else 3001
    port = int(os.environ.get("PORT", default_port))
    uvicorn.run(app, host=host, port=port)

    # 測試用：建立terminal ai chat bot
    # asyncio.run(terminal_chat())

    # 建立語意化的account title code到vector database
    # asyncio.run(establish_vector_data())
