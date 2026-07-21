import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import AVAILABLE_MODELS, MODEL_MAPPING, settings
from app.devin_client import devin_client
from app.models import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ModelInfo,
    ModelListResponse,
)
from app.session_manager import session_manager

app = FastAPI(title="Devin Proxy", version="1.0.0")

TERMINAL_STATUSES = {"exit", "error", "suspended"}


def verify_api_key(request: Request) -> None:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    else:
        token = auth
    if not settings.proxy_api_key:
        return
    if token != settings.proxy_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _build_prompt(messages: list[ChatMessage]) -> tuple[str, str]:
    """Return (full_context, latest_user_message) from the OpenAI messages."""
    parts = []
    latest_user = ""
    for msg in messages:
        prefix = msg.role.upper()
        parts.append(f"[{prefix}]\n{msg.content}")
        if msg.role == "user":
            latest_user = msg.content
    full_context = "\n\n".join(parts)
    return full_context, latest_user


def _gen_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models(_=Depends(verify_api_key)) -> ModelListResponse:
    return ModelListResponse(
        data=[ModelInfo(id=m) for m in AVAILABLE_MODELS]
    )


@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    req: ChatCompletionRequest,
    _=Depends(verify_api_key),
) -> JSONResponse | StreamingResponse:
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages is required")

    devin_mode = MODEL_MAPPING.get(req.model, "normal")
    messages_dicts = [{"role": m.role, "content": m.content} for m in req.messages]
    conv_hash = session_manager.conversation_hash(messages_dicts)

    full_context, latest_user = _build_prompt(req.messages)

    try:
        entry = await session_manager.get(conv_hash)
        if entry is None:
            entry = await session_manager.get_or_create(
                conv_hash=conv_hash,
                prompt=full_context,
                devin_mode=devin_mode,
                title=f"Proxy: {req.model}",
            )
        else:
            await devin_client.send_message(entry.session_id, latest_user)
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response else str(e)
        return JSONResponse(
            status_code=e.response.status_code if e.response else 502,
            content={"error": {"message": f"Devin API error: {detail}", "type": "upstream_error"}},
        )
    except httpx.RequestError as e:
        return JSONResponse(
            status_code=502,
            content={"error": {"message": f"Failed to reach Devin API: {e}", "type": "connection_error"}},
        )

    if req.stream:
        return StreamingResponse(
            _stream_response(entry, req.model),
            media_type="text/event-stream",
        )
    else:
        result = await _poll_until_done(entry)
        response = ChatCompletionResponse(
            id=_gen_id(),
            created=int(time.time()),
            model=req.model,
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(role="assistant", content=result),
                    finish_reason="stop",
                )
            ],
        )
        return JSONResponse(content=response.model_dump())


async def _poll_until_done(entry) -> str:
    elapsed = 0
    while elapsed < settings.max_poll_duration:
        try:
            session = await devin_client.get_session(entry.session_id)
        except httpx.HTTPError:
            await asyncio.sleep(settings.poll_interval)
            elapsed += settings.poll_interval
            continue
        status = session.get("status", "")
        if status in TERMINAL_STATUSES:
            break
        await asyncio.sleep(settings.poll_interval)
        elapsed += settings.poll_interval

    try:
        msgs = await devin_client.get_messages(entry.session_id)
    except httpx.HTTPError:
        return "Failed to retrieve output from Devin session."
    items = msgs.get("items", [])
    devin_messages = [m for m in items if m.get("source") == "devin"]
    if devin_messages:
        return devin_messages[-1].get("message", "")
    return "No output received from Devin session."


async def _stream_response(entry, model: str) -> AsyncGenerator[str, None]:
    chat_id = _gen_id()
    created = int(time.time())
    seen_event_ids: set[str] = set()
    elapsed = 0

    def make_chunk(content: str | None, finish_reason: str | None = None) -> str:
        delta = ChatCompletionChunkDelta()
        if content is not None:
            delta.content = content
        chunk = ChatCompletionChunk(
            id=chat_id,
            created=created,
            model=model,
            choices=[
                ChatCompletionChunkChoice(
                    delta=delta,
                    finish_reason=finish_reason,
                )
            ],
        )
        return f"data: {chunk.model_dump_json()}\n\n"

    try:
        yield make_chunk(None)

        while elapsed < settings.max_poll_duration:
            session = await devin_client.get_session(entry.session_id)
            status = session.get("status", "")

            msgs = await devin_client.get_messages(
                entry.session_id, after=entry.message_cursor
            )
            items = msgs.get("items", [])
            for item in items:
                event_id = item.get("event_id", "")
                if event_id in seen_event_ids:
                    continue
                seen_event_ids.add(event_id)
                if item.get("source") == "devin":
                    content = item.get("message", "")
                    if content:
                        yield make_chunk(content)
                entry.message_cursor = event_id

            if status in TERMINAL_STATUSES:
                break

            await asyncio.sleep(settings.poll_interval)
            elapsed += settings.poll_interval

        yield make_chunk(None, finish_reason="stop")
        yield "data: [DONE]\n\n"
    except Exception as e:
        error_chunk = {
            "error": {"message": str(e), "type": "internal_error"},
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"


@app.on_event("startup")
async def startup() -> None:
    session_manager.start_cleanup()
