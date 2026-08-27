from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import agent, evaluation, feedback, memories, metrics
from app.infrastructure.llm.adapter import LLMCallError
from app.infrastructure.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield

app = FastAPI(title="StudyFlow Memory API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LLMCallError)
async def handle_llm_error(_, exc: LLMCallError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": {
                    "code": exc.code,
                    "message": exc.message,
                    "retry_count": exc.retry_count + exc.format_repair_count,
            }
        },
    )

app.include_router(agent.router, prefix="/agent", tags=["agent"])
app.include_router(feedback.router, tags=["feedback"])
app.include_router(memories.router, tags=["memories"])
app.include_router(evaluation.router, tags=["evaluation"])
app.include_router(metrics.router, tags=["metrics"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
