import os
import sys
import asyncio
from time import perf_counter

# import chromadb
import uvicorn

from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv

load_dotenv()

# from src.services.save_document_into_vectordb_service import establish_vector_data
from src.mappings.company_stock_code_array import CompanyStockCodeArray
from fastapi.middleware.cors import CORSMiddleware

# import LangChain lib
from langchain.chains import LLMChain
from langchain_community.utilities import SQLDatabase
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

# import type
from src.types.langgraph_state_types import OverallState

# import graph
from src.agent.graph import graph

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


# print("✅ OPENAI_MODEL_NAME:", os.getenv("OPENAI_MODEL_NAME"))
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",  # Next.js
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,  # 需要帶 cookie/認證時要開
    allow_methods=["*"],
    allow_headers=["*"],
)


def env_flag_enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().upper() == "TRUE"


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
    is_render_deploy = env_flag_enabled("IS_RENDER_DEPLOY", default=False)
    host = "0.0.0.0" if is_render_deploy else "localhost"
    default_port = 10000 if is_render_deploy else 3001
    port = int(os.environ.get("PORT", default_port))
    uvicorn.run(app, host=host, port=port)

    # 測試用：建立terminal ai chat bot
    # asyncio.run(terminal_chat())

    # 建立語意化的account title code到vector database
    # asyncio.run(establish_vector_data())
