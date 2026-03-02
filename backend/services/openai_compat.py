"""
Multi-Format Compatible API Layer

Provides endpoints that translate between various API formats and Google Gemini/CloudCode:
- OpenAI:     /v1/models, /v1/chat/completions
- Anthropic:  /v1/messages

CherryStudio and other clients can connect via either format.

Uses CloudCode endpoint (daily-cloudcode-pa.googleapis.com) with v1internal:{method} RPC format.
Antigravity OAuth tokens ONLY work with CloudCode — not with Vertex AI or generativelanguage.
"""

import fnmatch
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from database.connection import async_session
from models.model_mapping import ModelMapping
from services.cloudcode_proxy import get_pool, _proxy_state
from utils.proxy import get_chrome_client, create_chrome_client
from services.proxy_logger import get_proxy_logger
from utils.fingerprint import get_fingerprint

logger = logging.getLogger("openai_compat")

router = APIRouter()

# CloudCode API format: {upstream}/v1internal:{method}
# Same format used by fetchAvailableModels in gemini_api.py
CLOUDCODE_API_VERSION = "v1internal"
FALLBACK_PROJECT_ID = "bamboo-precept-lgxtn"

# Models available via CloudCode (Antigravity)
AVAILABLE_MODELS = [
    {"id": "claude-opus-4-6-thinking", "name": "Claude Opus 4.6 Thinking", "owned_by": "anthropic"},
    {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "owned_by": "anthropic"},
    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "owned_by": "google"},
    {"id": "gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash Lite", "owned_by": "google"},
    {"id": "gemini-2.5-flash-thinking", "name": "Gemini 2.5 Flash Thinking", "owned_by": "google"},
    {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "owned_by": "google"},
    {"id": "gemini-3-flash", "name": "Gemini 3 Flash", "owned_by": "google"},
    {"id": "gemini-3-pro-high", "name": "Gemini 3 Pro High", "owned_by": "google"},
    {"id": "gemini-3.1-flash-image", "name": "Gemini 3.1 Flash Image", "owned_by": "google"},
    {"id": "gemini-3-pro-low", "name": "Gemini 3 Pro Low", "owned_by": "google"},
    {"id": "gemini-3.1-pro-high", "name": "Gemini 3.1 Pro High", "owned_by": "google"},
    {"id": "gemini-3.1-pro-low", "name": "Gemini 3.1 Pro Low", "owned_by": "google"},
]


async def apply_model_mapping(model: str) -> tuple[str, str]:
    """Apply model mapping rules. Returns (mapped_model, original_model).

    If a mapping matches, returns (target, original_model).
    If no mapping matches, returns (model, "").
    """
    async with async_session() as session:
        result = await session.execute(
            select(ModelMapping)
            .where(ModelMapping.is_active == True)
            .order_by(ModelMapping.priority, ModelMapping.created_at)
        )
        mappings = result.scalars().all()

    for mapping in mappings:
        if mapping.pattern == model:
            # Exact match
            logger.info(f"Model mapping: {model} -> {mapping.target} (exact)")
            return mapping.target, model
        if "*" in mapping.pattern or "?" in mapping.pattern:
            # Wildcard match using fnmatch
            if fnmatch.fnmatch(model, mapping.pattern):
                logger.info(f"Model mapping: {model} -> {mapping.target} (wildcard: {mapping.pattern})")
                return mapping.target, model

    return model, ""


def _clean_schema_for_gemini(schema: dict) -> dict:
    """Recursively strip fields from JSON Schema that Gemini doesn't support.

    Gemini functionDeclarations.parameters only accepts a subset of OpenAPI Schema:
    type, description, enum, items, properties, required, nullable, format.
    Everything else causes 400 errors. Use allowlist approach for safety.
    """
    ALLOWED_KEYS = {
        "type", "description", "enum", "items", "properties",
        "required", "nullable", "format",
    }
    cleaned = {}
    for key, value in schema.items():
        if key not in ALLOWED_KEYS:
            continue
        if isinstance(value, dict):
            cleaned[key] = _clean_schema_for_gemini(value)
        elif isinstance(value, list):
            cleaned[key] = [
                _clean_schema_for_gemini(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


def _convert_openai_tools_to_gemini(tools: list[dict]) -> list[dict]:
    """Convert OpenAI tools format to Gemini functionDeclarations."""
    declarations = []
    for tool in tools:
        if tool.get("type") == "function":
            func = tool["function"]
            decl = {"name": func["name"]}
            if func.get("description"):
                decl["description"] = func["description"]
            if func.get("parameters"):
                decl["parameters"] = _clean_schema_for_gemini(func["parameters"])
            declarations.append(decl)
    if declarations:
        return [{"functionDeclarations": declarations}]
    return []


def _convert_openai_tool_choice_to_gemini(tool_choice) -> dict | None:
    """Convert OpenAI tool_choice to Gemini toolConfig."""
    if tool_choice is None:
        return None
    if isinstance(tool_choice, str):
        mode_map = {"auto": "AUTO", "none": "NONE", "required": "ANY"}
        mode = mode_map.get(tool_choice)
        if mode:
            return {"functionCallingConfig": {"mode": mode}}
    elif isinstance(tool_choice, dict):
        func_name = tool_choice.get("function", {}).get("name")
        if func_name:
            return {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [func_name]}}
    return None


def _convert_anthropic_tools_to_gemini(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tools format to Gemini functionDeclarations."""
    declarations = []
    for tool in tools:
        decl = {"name": tool["name"]}
        if tool.get("description"):
            decl["description"] = tool["description"]
        if tool.get("input_schema"):
            decl["parameters"] = _clean_schema_for_gemini(tool["input_schema"])
        declarations.append(decl)
    if declarations:
        return [{"functionDeclarations": declarations}]
    return []


def _convert_anthropic_tool_choice_to_gemini(tool_choice) -> dict | None:
    """Convert Anthropic tool_choice to Gemini toolConfig."""
    if tool_choice is None:
        return None
    if isinstance(tool_choice, dict):
        tc_type = tool_choice.get("type")
        if tc_type == "auto":
            return {"functionCallingConfig": {"mode": "AUTO"}}
        elif tc_type == "any":
            return {"functionCallingConfig": {"mode": "ANY"}}
        elif tc_type == "none":
            return {"functionCallingConfig": {"mode": "NONE"}}
        elif tc_type == "tool":
            func_name = tool_choice.get("name")
            if func_name:
                return {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [func_name]}}
    return None


def _extract_gemini_parts(parts: list[dict]) -> tuple[str, list[dict]]:
    """Extract text and functionCall parts from Gemini response.

    Returns (text, tool_calls) where tool_calls is a list of
    {"name": ..., "args": ...} dicts.
    """
    text_segments = []
    tool_calls = []
    for part in parts:
        if "text" in part:
            text_segments.append(part["text"])
        elif "functionCall" in part:
            fc = part["functionCall"]
            tool_calls.append({
                "name": fc.get("name", ""),
                "args": fc.get("args", {}),
            })
    return "".join(text_segments), tool_calls


@router.get("/models")
async def list_models():
    """OpenAI-compatible GET /v1/models endpoint."""
    return {
        "object": "list",
        "data": [
            {
                "id": m["id"],
                "object": "model",
                "created": 1700000000,
                "owned_by": m.get("owned_by", "google"),
            }
            for m in AVAILABLE_MODELS
        ],
    }


@router.post("/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible POST /v1/chat/completions endpoint.

    Translates OpenAI chat format to Gemini generateContent format,
    forwards to upstream via account pool, and translates response back.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "Invalid JSON body", "type": "invalid_request_error"}},
        )

    original_model_raw = body.get("model", "gemini-2.5-flash")
    model, original_model = await apply_model_mapping(original_model_raw)
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    temperature = body.get("temperature")
    if temperature == "[undefined]":
        temperature = None

    max_tokens = body.get("max_tokens") or body.get("max_completion_tokens")
    if max_tokens == "[undefined]":
        max_tokens = None
    elif max_tokens is not None:
        try:
            max_tokens = int(max_tokens)
            # CloudCode streaming endpoint rejects maxOutputTokens > ~64000
            max_tokens = min(max_tokens, 64000)
        except (ValueError, TypeError):
            max_tokens = None

    if not messages:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "messages is required", "type": "invalid_request_error"}},
        )

    # Build Gemini request
    gemini_contents, system_instruction = _convert_messages_to_gemini(messages)
    gemini_body = {"contents": gemini_contents}

    # System instruction from messages
    if system_instruction:
        gemini_body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    # Convert and forward tools
    tools = body.get("tools")
    if tools:
        gemini_tools = _convert_openai_tools_to_gemini(tools)
        if gemini_tools:
            gemini_body["tools"] = gemini_tools

    tool_choice = body.get("tool_choice")
    if tool_choice is not None:
        tool_config = _convert_openai_tool_choice_to_gemini(tool_choice)
        if tool_config:
            gemini_body["toolConfig"] = tool_config

    generation_config = {}
    if temperature is not None:
        generation_config["temperature"] = temperature
    if max_tokens is not None:
        generation_config["maxOutputTokens"] = max_tokens
    if generation_config:
        gemini_body["generationConfig"] = generation_config

    pool = get_pool()
    max_retries = min(pool.size, 5)

    for attempt in range(max(max_retries, 1)):
        account = await pool.get_current(request)
        if not account:
            return JSONResponse(
                status_code=503,
                content={"error": {"message": "No available accounts in pool", "type": "server_error"}},
            )

        # Wait for cooldown before sending request
        await pool.wait_cooldown(account["id"])

        upstream = _proxy_state["upstream"]
        project_id = account.get("project_id") or FALLBACK_PROJECT_ID
        fp = get_fingerprint()
        headers = fp.get_headers(account['access_token'], project_id)

        # All models (Gemini + Claude + GPT) use streamGenerateContent.
        # Packet capture confirmed: requestType:"agent" enables CloudCode to route
        # third-party models (Claude/GPT) to their respective backends.
        if stream:
            url = f"{upstream}/{CLOUDCODE_API_VERSION}:streamGenerateContent?alt=sse"
        else:
            url = f"{upstream}/{CLOUDCODE_API_VERSION}:generateContent"

        request_id = f"agent/{int(time.time() * 1000)}/{uuid.uuid4()}/0"
        payload = {
            "project": project_id,
            "requestId": request_id,
            "request": gemini_body,
            "model": model,
            "userAgent": "antigravity",
            "requestType": "agent",
        }

        # Mark request time for cooldown tracking
        pool.mark_request(account["id"])

        try:
            if stream:
                # Streaming: client lifecycle managed by the generator (closes in finally)
                client = create_chrome_client(timeout=180.0, account_id=account["id"])
                res = await _handle_stream(client, url, headers, payload, model, account, pool, original_model)
            else:
                async with get_chrome_client(timeout=180.0, account_id=account["id"]) as client:
                    res = await _handle_non_stream(client, url, headers, payload, model, account, pool, original_model)

            # If rate limit / quota exhausted happened, _handle_* might return 429 or 503
            # If so we want to continue the attempt loop to retry.
            res_status = getattr(res, "status_code", 200)
            if res_status == 401 and attempt < max_retries - 1:
                # Token expired — reload fresh tokens from DB
                logger.info("401 UNAUTHENTICATED — refreshing pool from DB")
                await pool.refresh()
                continue
            if res_status in (404, 429, 503) and attempt < max_retries - 1:
                continue
            return res
        except Exception as e:
            logger.error(f"OpenAI compat error: {e}")
            if attempt == max_retries - 1:
                return JSONResponse(
                    status_code=502,
                    content={"error": {"message": str(e), "type": "server_error"}},
                )
            continue

    return JSONResponse(
        status_code=503,
        content={"error": {"message": "All accounts exhausted", "type": "server_error"}},
    )


def _convert_messages_to_gemini(messages: list[dict]) -> tuple[list[dict], str | None]:
    """Convert OpenAI messages format to Gemini contents format.

    Returns (contents, system_instruction).
    Handles: system, user, assistant (with tool_calls), tool (function results).
    """
    contents = []
    system_instruction = None

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Handle system messages — Gemini uses systemInstruction
        if role == "system":
            if isinstance(content, str):
                system_instruction = content
            elif isinstance(content, list):
                system_instruction = "\n".join(
                    p.get("text", "") for p in content if p.get("type") == "text"
                )
            continue

        # Handle tool result messages (role: "tool")
        # Convert to plain user text — no special format that models could mimic.
        # Models must use native functionCall (via tools/functionDeclarations) not text patterns.
        if role == "tool":
            result_content = content if isinstance(content, str) else json.dumps(content)
            contents.append({
                "role": "user",
                "parts": [{"text": result_content}],
            })
            continue

        # Map roles: OpenAI → Gemini
        gemini_role = "user" if role == "user" else "model"

        # Handle assistant messages with tool_calls
        # Keep only text content, drop tool_calls — they already executed and results follow.
        # This prevents models from mimicking any tool-call text format in their output.
        if role == "assistant" and msg.get("tool_calls"):
            parts = []
            if content and isinstance(content, str):
                parts.append({"text": content})
            # If no text content, skip entirely — the tool results (next messages) carry the context
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue

        # Handle string content
        if isinstance(content, str):
            if content:  # Skip empty content
                contents.append({
                    "role": gemini_role,
                    "parts": [{"text": content}],
                })
        # Handle array content (multimodal)
        elif isinstance(content, list):
            parts = []
            for part in content:
                if part.get("type") == "text":
                    parts.append({"text": part["text"]})
            if parts:
                contents.append({"role": gemini_role, "parts": parts})

    return contents, system_instruction


async def _handle_non_stream(client, url, headers, body, model, account, pool, original_model=""):
    """Handle non-streaming request."""
    _proxy_state["total_requests"] += 1
    t0 = time.time()
    plog = get_proxy_logger()
    resp = await client.post(url, headers=headers, json=body)
    duration = (time.time() - t0) * 1000

    # Handle 404 — model not available on this account, rotate to next
    if resp.status_code == 404:
        upstream_error = resp.content.decode("utf-8", errors="replace") if hasattr(resp, "content") else resp.text
        logger.error(f"Upstream 404 body: {upstream_error}")
        await pool.rotate(account["id"], reason="model_not_found")
        plog.log("POST", "/v1/chat/completions", "openai", model, False, 404, duration,
                 account["email"], account["id"], error=f"Upstream 404: {upstream_error[:200]}", original_model=original_model)
        return JSONResponse(
            status_code=404,
            content={"error": {"message": f"Model {model} not found, rotating account", "type": "not_found_error"}},
        )

    # Handle quota errors with rotation
    if resp.status_code == 429:
        await pool.rotate(account["id"], reason="rate_limited")
        plog.log("POST", "/v1/chat/completions", "openai", model, False, 429, duration,
                 account["email"], account["id"], error="Rate limited", original_model=original_model)
        return JSONResponse(
            status_code=429,
            content={"error": {"message": "Rate limited, rotating account", "type": "rate_limit_error"}},
        )
    if resp.status_code == 403:
        text = resp.text
        if "RESOURCE_EXHAUSTED" in text or "quota" in text.lower():
            await pool.rotate(account["id"], reason="exhausted")
            plog.log("POST", "/v1/chat/completions", "openai", model, False, 403, duration,
                     account["email"], account["id"], error="Quota exhausted", original_model=original_model)
            return JSONResponse(
                status_code=429,
                content={"error": {"message": "Quota exhausted, rotating account", "type": "rate_limit_error"}},
            )

    if resp.status_code == 503:
        text = resp.text
        if "CAPACITY_EXHAUSTED" in text.upper() or "capacity" in text.lower():
            await pool.rotate(account["id"], reason="capacity_exhausted")
            plog.log("POST", "/v1/chat/completions", "openai", model, False, 503, duration,
                     account["email"], account["id"], error="Capacity exhausted", original_model=original_model)
            return JSONResponse(
                status_code=503,
                content={"error": {"message": "Capacity exhausted, rotating account", "type": "server_error"}},
            )

    if resp.status_code != 200:
        plog.log("POST", "/v1/chat/completions", "openai", model, False, resp.status_code, duration,
                 account["email"], account["id"], error=resp.text[:200], original_model=original_model)
        return JSONResponse(
            status_code=resp.status_code,
            content={"error": {"message": resp.text[:500], "type": "upstream_error"}},
        )

    # Parse Gemini response and convert to OpenAI format
    try:
        gemini_resp = resp.json()
    except Exception:
        plog.log("POST", "/v1/chat/completions", "openai", model, False, 502, duration,
                 account["email"], account["id"], error="Invalid upstream response", original_model=original_model)
        return JSONResponse(
            status_code=502,
            content={"error": {"message": "Invalid upstream response", "type": "server_error"}},
        )

    # Unwrap daily-cloudcode "response" envelope
    if "response" in gemini_resp:
        gemini_resp = gemini_resp["response"]

    # Extract text and functionCall parts from Gemini response
    text = ""
    tool_calls_raw = []
    candidates = gemini_resp.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        text, tool_calls_raw = _extract_gemini_parts(parts)

    # Build OpenAI response
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    usage = gemini_resp.get("usageMetadata", {})

    plog.log("POST", "/v1/chat/completions", "openai", model, False, 200, duration,
             account["email"], account["id"],
             input_tokens=usage.get("promptTokenCount", 0),
             output_tokens=usage.get("candidatesTokenCount", 0),
             original_model=original_model)

    # Build message with optional tool_calls
    message: dict = {"role": "assistant", "content": text or None}
    finish_reason = "stop"

    if tool_calls_raw:
        finish_reason = "tool_calls"
        message["tool_calls"] = [
            {
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["args"]),
                },
            }
            for tc in tool_calls_raw
        ]

    return JSONResponse(content={
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": usage.get("promptTokenCount", 0),
            "completion_tokens": usage.get("candidatesTokenCount", 0),
            "total_tokens": usage.get("totalTokenCount", 0),
        },
    })


async def _handle_stream(client, url, headers, body, model, account, pool, original_model=""):
    """Handle streaming request — true SSE streaming via curl_cffi.

    Uses stream=True + aiter_lines() for real-time token-by-token delivery.
    The client session is managed by the generator and closed when done.
    """
    _proxy_state["total_requests"] += 1
    t0 = time.time()
    plog = get_proxy_logger()
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    # True streaming POST
    resp = await client.post_stream(url, headers=headers, json=body)

    # For error responses, read body and return immediately
    if resp.status_code != 200:
        # Read error body
        error_parts = []
        try:
            async for chunk in resp.aiter_content():
                error_parts.append(chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk)
        except Exception:
            pass
        finally:
            await client.close()
        error_text = "".join(error_parts)
        duration = (time.time() - t0) * 1000

        if resp.status_code == 404:
            logger.error(f"Upstream 404 body: {error_text}")
            await pool.rotate(account["id"], reason="model_not_found")
            plog.log("POST", "/v1/chat/completions", "openai", model, True, 404, duration,
                     account["email"], account["id"], error=f"Upstream 404: {error_text[:200]}", original_model=original_model)
            return JSONResponse(status_code=404, content={"error": {"message": f"Model {model} not found", "type": "not_found_error"}})
        if resp.status_code == 429:
            await pool.rotate(account["id"], reason="rate_limited")
            plog.log("POST", "/v1/chat/completions", "openai", model, True, 429, duration,
                     account["email"], account["id"], error="Rate limited", original_model=original_model)
            return JSONResponse(status_code=429, content={"error": {"message": "Rate limited", "type": "rate_limit_error"}})
        if resp.status_code == 403 and ("RESOURCE_EXHAUSTED" in error_text or "quota" in error_text.lower()):
            await pool.rotate(account["id"], reason="exhausted")
            plog.log("POST", "/v1/chat/completions", "openai", model, True, 403, duration,
                     account["email"], account["id"], error="Quota exhausted", original_model=original_model)
            return JSONResponse(status_code=429, content={"error": {"message": "Quota exhausted", "type": "rate_limit_error"}})
        if resp.status_code == 503 and ("CAPACITY_EXHAUSTED" in error_text.upper() or "capacity" in error_text.lower()):
            await pool.rotate(account["id"], reason="capacity_exhausted")
            plog.log("POST", "/v1/chat/completions", "openai", model, True, 503, duration,
                     account["email"], account["id"], error="Capacity exhausted", original_model=original_model)
            return JSONResponse(status_code=503, content={"error": {"message": "Capacity exhausted", "type": "server_error"}})

        plog.log("POST", "/v1/chat/completions", "openai", model, True, resp.status_code, duration,
                 account["email"], account["id"], error=error_text[:200], original_model=original_model)
        return JSONResponse(status_code=resp.status_code, content={"error": {"message": error_text[:500], "type": "upstream_error"}})

    # Stream SSE in real-time
    async def stream_openai():
        input_tokens = 0
        output_tokens = 0
        tool_call_index = 0
        has_tool_calls = False
        try:
            async for raw_line in resp.aiter_lines():
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break

                try:
                    gemini_chunk = json.loads(data_str)
                    if "response" in gemini_chunk:
                        gemini_chunk = gemini_chunk["response"]
                except json.JSONDecodeError:
                    continue

                candidates = gemini_chunk.get("candidates", [])
                if not candidates:
                    continue
                parts = candidates[0].get("content", {}).get("parts", [])
                delta_text, delta_tool_calls = _extract_gemini_parts(parts)

                chunk_usage = gemini_chunk.get("usageMetadata", {})
                if chunk_usage:
                    input_tokens = chunk_usage.get("promptTokenCount", input_tokens)
                    output_tokens = chunk_usage.get("candidatesTokenCount", output_tokens)

                # Emit text delta
                if delta_text:
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{"index": 0, "delta": {"content": delta_text}, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"

                # Emit tool_calls deltas
                for tc in delta_tool_calls:
                    has_tool_calls = True
                    tc_delta = {
                        "tool_calls": [{
                            "index": tool_call_index,
                            "id": f"call_{uuid.uuid4().hex[:24]}",
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"]),
                            },
                        }]
                    }
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{"index": 0, "delta": tc_delta, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                    tool_call_index += 1

                # Check finish reason
                finish_reason_raw = candidates[0].get("finishReason")
                if finish_reason_raw:
                    finish_reason = "tool_calls" if has_tool_calls else "stop"
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"

            yield "data: [DONE]\n\n"
        finally:
            duration = (time.time() - t0) * 1000
            plog.log("POST", "/v1/chat/completions", "openai", model, True, 200, duration,
                     account["email"], account["id"], input_tokens=input_tokens, output_tokens=output_tokens,
                     original_model=original_model)
            await client.close()

    return StreamingResponse(
        content=stream_openai(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ============================================================
# Anthropic-compatible /v1/messages endpoint
# ============================================================

@router.post("/messages")
async def anthropic_messages(request: Request):
    """
    Anthropic-compatible POST /v1/messages endpoint.

    Translates Anthropic messages format to Gemini generateContent format,
    forwards to upstream via account pool, and translates response back.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"type": "error", "error": {"type": "invalid_request_error", "message": "Invalid JSON body"}},
        )

    original_model_raw = body.get("model", "gemini-2.5-flash")
    model, original_model = await apply_model_mapping(original_model_raw)
    messages = body.get("messages", [])
    system_text = body.get("system")
    if system_text == "[undefined]":
        system_text = None
    stream = body.get("stream", False)
    
    # Cherry Studio might send "[undefined]" string for empty values
    temperature = body.get("temperature")
    if temperature == "[undefined]":
        temperature = None
        
    max_tokens = body.get("max_tokens", 8192)
    if max_tokens == "[undefined]":
        max_tokens = 8192
    else:
        try:
            max_tokens = int(max_tokens)
            # CloudCode streaming endpoint rejects maxOutputTokens > ~64000
            # (verified: 64000 OK, 64500 rejected)
            max_tokens = min(max_tokens, 64000)
        except (ValueError, TypeError):
            max_tokens = 8192

    if not messages:
        return JSONResponse(
            status_code=400,
            content={"type": "error", "error": {"type": "invalid_request_error", "message": "messages is required"}},
        )

    # Convert Anthropic messages to Gemini contents
    gemini_contents = _convert_anthropic_messages_to_gemini(messages)
    gemini_body: dict = {"contents": gemini_contents}

    # Convert and forward tools
    tools = body.get("tools")
    if tools:
        gemini_tools = _convert_anthropic_tools_to_gemini(tools)
        if gemini_tools:
            gemini_body["tools"] = gemini_tools

    tool_choice = body.get("tool_choice")
    if tool_choice is not None:
        tool_config = _convert_anthropic_tool_choice_to_gemini(tool_choice)
        if tool_config:
            gemini_body["toolConfig"] = tool_config

    # System instruction
    if system_text:
        if isinstance(system_text, str):
            gemini_body["systemInstruction"] = {"parts": [{"text": system_text}]}
        elif isinstance(system_text, list):
            # Anthropic system can be a list of content blocks
            text_parts = []
            for block in system_text:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            if text_parts:
                gemini_body["systemInstruction"] = {"parts": [{"text": "\n".join(text_parts)}]}

    generation_config: dict = {}
    if temperature is not None:
        generation_config["temperature"] = temperature
    if max_tokens is not None:
        generation_config["maxOutputTokens"] = max_tokens
    if generation_config:
        gemini_body["generationConfig"] = generation_config

    pool = get_pool()
    max_retries = min(pool.size, 5)

    for attempt in range(max(max_retries, 1)):
        account = await pool.get_current(request)
        if not account:
            return JSONResponse(
                status_code=503,
                content={"type": "error", "error": {"type": "api_error", "message": "No available accounts in pool"}},
            )

        # Wait for cooldown before sending request
        await pool.wait_cooldown(account["id"])

        upstream = _proxy_state["upstream"]
        project_id = account.get("project_id") or FALLBACK_PROJECT_ID
        fp = get_fingerprint()
        headers = fp.get_headers(account['access_token'], project_id)

        # All models use streamGenerateContent with requestType:"agent"
        if stream:
            url = f"{upstream}/{CLOUDCODE_API_VERSION}:streamGenerateContent?alt=sse"
        else:
            url = f"{upstream}/{CLOUDCODE_API_VERSION}:generateContent"

        request_id = f"agent/{int(time.time() * 1000)}/{uuid.uuid4()}/0"
        payload = {
            "project": project_id,
            "requestId": request_id,
            "request": gemini_body,
            "model": model,
            "userAgent": "antigravity",
            "requestType": "agent",
        }

        # Mark request time for cooldown tracking
        pool.mark_request(account["id"])

        try:
            if stream:
                # Streaming: client lifecycle managed by the generator (closes in finally)
                client = create_chrome_client(timeout=180.0, account_id=account["id"])
                res = await _handle_anthropic_stream(client, url, headers, payload, model, account, pool, original_model)
            else:
                async with get_chrome_client(timeout=180.0, account_id=account["id"]) as client:
                    res = await _handle_anthropic_non_stream(client, url, headers, payload, model, account, pool, original_model)

            res_status = getattr(res, "status_code", 200)
            if res_status == 401 and attempt < max_retries - 1:
                logger.info("401 UNAUTHENTICATED — refreshing pool from DB")
                await pool.refresh()
                continue
            if res_status in (404, 429, 503) and attempt < max_retries - 1:
                continue
            return res
        except Exception as e:
            logger.error(f"Anthropic compat error: {e}")
            if attempt == max_retries - 1:
                return JSONResponse(
                    status_code=502,
                    content={"type": "error", "error": {"type": "api_error", "message": str(e)}},
                )
            continue

    return JSONResponse(
        status_code=529,
        content={"type": "error", "error": {"type": "overloaded_error", "message": "All accounts exhausted"}},
    )


def _convert_anthropic_messages_to_gemini(messages: list[dict]) -> list[dict]:
    """Convert Anthropic messages format to Gemini contents format.

    Handles: user (text + tool_result), assistant (text + tool_use).
    Tool interactions in history are flattened to text because CloudCode
    loses tool IDs when converting functionCall/functionResponse back to
    Claude format, causing 'tool_use.id: Field required' errors.
    """
    contents = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        gemini_role = "user" if role == "user" else "model"

        if isinstance(content, str):
            if content:  # Skip empty content
                contents.append({
                    "role": gemini_role,
                    "parts": [{"text": content}],
                })
        elif isinstance(content, list):
            parts = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")

                if block_type == "text":
                    text = block.get("text", "")
                    if text:
                        parts.append({"text": text})

                elif block_type == "tool_use":
                    # Drop tool_use from history — model already executed it, result follows.
                    # No text representation to prevent models from mimicking tool-call patterns.
                    pass

                elif block_type == "tool_result":
                    # Convert tool result to plain text — no special tags.
                    result_content = block.get("content", "")
                    if isinstance(result_content, list):
                        result_text = "\n".join(
                            b.get("text", "") for b in result_content
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    elif isinstance(result_content, str):
                        result_text = result_content
                    else:
                        result_text = json.dumps(result_content)
                    if result_text:
                        parts.append({"text": result_text})

            if parts:
                contents.append({"role": gemini_role, "parts": parts})

    return contents


async def _handle_anthropic_non_stream(client, url, headers, body, model, account, pool, original_model=""):
    """Handle Anthropic non-streaming request."""
    _proxy_state["total_requests"] += 1
    t0 = time.time()
    plog = get_proxy_logger()
    resp = await client.post(url, headers=headers, json=body)
    duration = (time.time() - t0) * 1000

    if resp.status_code == 404:
        upstream_error = resp.content.decode("utf-8", errors="replace") if hasattr(resp, "content") else resp.text
        logger.error(f"Upstream 404 body: {upstream_error}")
        await pool.rotate(account["id"], reason="model_not_found")
        plog.log("POST", "/v1/messages", "anthropic", model, False, 404, duration,
                 account["email"], account["id"], error=f"Upstream 404: {upstream_error[:200]}", original_model=original_model)
        return JSONResponse(
            status_code=404,
            content={"type": "error", "error": {"type": "not_found_error", "message": f"Model {model} not found, rotating account"}},
        )

    if resp.status_code == 429:
        await pool.rotate(account["id"], reason="rate_limited")
        plog.log("POST", "/v1/messages", "anthropic", model, False, 429, duration,
                 account["email"], account["id"], error="Rate limited", original_model=original_model)
        return JSONResponse(
            status_code=429,
            content={"type": "error", "error": {"type": "rate_limit_error", "message": "Rate limited, rotating account"}},
        )
    if resp.status_code == 403:
        text = resp.text
        if "RESOURCE_EXHAUSTED" in text or "quota" in text.lower():
            await pool.rotate(account["id"], reason="exhausted")
            plog.log("POST", "/v1/messages", "anthropic", model, False, 403, duration,
                     account["email"], account["id"], error="Quota exhausted", original_model=original_model)
            return JSONResponse(
                status_code=429,
                content={"type": "error", "error": {"type": "rate_limit_error", "message": "Quota exhausted, rotating account"}},
            )
    if resp.status_code == 503:
        text = resp.text
        if "CAPACITY_EXHAUSTED" in text.upper() or "capacity" in text.lower():
            await pool.rotate(account["id"], reason="capacity_exhausted")
            plog.log("POST", "/v1/messages", "anthropic", model, False, 503, duration,
                     account["email"], account["id"], error="Capacity exhausted", original_model=original_model)
            return JSONResponse(
                status_code=503,
                content={"type": "error", "error": {"type": "api_error", "message": "Capacity exhausted, rotating account"}},
            )

    if resp.status_code != 200:
        plog.log("POST", "/v1/messages", "anthropic", model, False, resp.status_code, duration,
                 account["email"], account["id"], error=resp.text[:200], original_model=original_model)
        return JSONResponse(
            status_code=resp.status_code,
            content={"type": "error", "error": {"type": "api_error", "message": resp.text[:500]}},
        )

    try:
        gemini_resp = resp.json()
    except Exception:
        plog.log("POST", "/v1/messages", "anthropic", model, False, 502, duration,
                 account["email"], account["id"], error="Invalid upstream response", original_model=original_model)
        return JSONResponse(
            status_code=502,
            content={"type": "error", "error": {"type": "api_error", "message": "Invalid upstream response"}},
        )

    # Unwrap daily-cloudcode "response" envelope
    if "response" in gemini_resp:
        gemini_resp = gemini_resp["response"]

    text = ""
    tool_calls_raw = []
    candidates = gemini_resp.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        text, tool_calls_raw = _extract_gemini_parts(parts)

    usage = gemini_resp.get("usageMetadata", {})
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    plog.log("POST", "/v1/messages", "anthropic", model, False, 200, duration,
             account["email"], account["id"],
             input_tokens=usage.get("promptTokenCount", 0),
             output_tokens=usage.get("candidatesTokenCount", 0),
             original_model=original_model)

    # Build Anthropic content blocks
    content_blocks = []
    if text:
        content_blocks.append({"type": "text", "text": text})
    for tc in tool_calls_raw:
        content_blocks.append({
            "type": "tool_use",
            "id": f"toolu_{uuid.uuid4().hex[:24]}",
            "name": tc["name"],
            "input": tc["args"],
        })
    if not content_blocks:
        content_blocks.append({"type": "text", "text": ""})

    stop_reason = "tool_use" if tool_calls_raw else "end_turn"

    return JSONResponse(content={
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("promptTokenCount", 0),
            "output_tokens": usage.get("candidatesTokenCount", 0),
        },
    })


async def _handle_anthropic_stream(client, url, headers, body, model, account, pool, original_model=""):
    """Handle Anthropic streaming request — true SSE streaming via curl_cffi."""
    _proxy_state["total_requests"] += 1
    t0 = time.time()
    plog = get_proxy_logger()
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    # True streaming POST
    resp = await client.post_stream(url, headers=headers, json=body)

    # For error responses, read body and return immediately
    if resp.status_code != 200:
        error_parts = []
        try:
            async for chunk in resp.aiter_content():
                error_parts.append(chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk)
        except Exception:
            pass
        finally:
            await client.close()
        error_text = "".join(error_parts)
        duration = (time.time() - t0) * 1000

        if resp.status_code == 404:
            logger.error(f"Upstream 404 body: {error_text}")
            await pool.rotate(account["id"], reason="model_not_found")
            plog.log("POST", "/v1/messages", "anthropic", model, True, 404, duration,
                     account["email"], account["id"], error=f"Upstream 404: {error_text[:200]}", original_model=original_model)
            return JSONResponse(status_code=404, content={"type": "error", "error": {"type": "not_found_error", "message": f"Model {model} not found"}})
        if resp.status_code == 429:
            await pool.rotate(account["id"], reason="rate_limited")
            plog.log("POST", "/v1/messages", "anthropic", model, True, 429, duration,
                     account["email"], account["id"], error="Rate limited", original_model=original_model)
            return JSONResponse(status_code=429, content={"type": "error", "error": {"type": "rate_limit_error", "message": "Rate limited"}})
        if resp.status_code == 403 and ("RESOURCE_EXHAUSTED" in error_text or "quota" in error_text.lower()):
            await pool.rotate(account["id"], reason="exhausted")
            plog.log("POST", "/v1/messages", "anthropic", model, True, 403, duration,
                     account["email"], account["id"], error="Quota exhausted", original_model=original_model)
            return JSONResponse(status_code=429, content={"type": "error", "error": {"type": "rate_limit_error", "message": "Quota exhausted"}})
        if resp.status_code == 503 and ("CAPACITY_EXHAUSTED" in error_text.upper() or "capacity" in error_text.lower()):
            await pool.rotate(account["id"], reason="capacity_exhausted")
            plog.log("POST", "/v1/messages", "anthropic", model, True, 503, duration,
                     account["email"], account["id"], error="Capacity exhausted", original_model=original_model)
            return JSONResponse(status_code=503, content={"type": "error", "error": {"type": "api_error", "message": "Capacity exhausted"}})

        plog.log("POST", "/v1/messages", "anthropic", model, True, resp.status_code, duration,
                 account["email"], account["id"], error=error_text[:200], original_model=original_model)
        return JSONResponse(status_code=resp.status_code, content={"type": "error", "error": {"type": "api_error", "message": error_text[:500]}})

    # Stream SSE in real-time
    async def stream_anthropic():
        input_tokens = 0
        output_tokens = 0
        content_index = 0
        has_tool_use = False
        text_block_started = False
        try:
            # Send Anthropic SSE preamble
            start_event = {
                "type": "message_start",
                "message": {
                    "id": msg_id, "type": "message", "role": "assistant",
                    "content": [], "model": model,
                    "stop_reason": None, "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            }
            yield f"event: message_start\ndata: {json.dumps(start_event)}\n\n"
            yield f"event: ping\ndata: {json.dumps({'type': 'ping'})}\n\n"

            async for raw_line in resp.aiter_lines():
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break

                try:
                    gemini_chunk = json.loads(data_str)
                    if "response" in gemini_chunk:
                        gemini_chunk = gemini_chunk["response"]
                except json.JSONDecodeError:
                    continue

                candidates = gemini_chunk.get("candidates", [])
                if not candidates:
                    continue
                parts = candidates[0].get("content", {}).get("parts", [])
                delta_text, delta_tool_calls = _extract_gemini_parts(parts)

                chunk_usage = gemini_chunk.get("usageMetadata", {})
                if chunk_usage:
                    input_tokens = chunk_usage.get("promptTokenCount", input_tokens)
                    output_tokens = chunk_usage.get("candidatesTokenCount", output_tokens)

                # Emit text delta
                if delta_text:
                    if not text_block_started:
                        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': content_index, 'content_block': {'type': 'text', 'text': ''}})}\n\n"
                        text_block_started = True
                    delta_event = {
                        "type": "content_block_delta", "index": content_index,
                        "delta": {"type": "text_delta", "text": delta_text},
                    }
                    yield f"event: content_block_delta\ndata: {json.dumps(delta_event)}\n\n"

                # Emit tool_use blocks
                for tc in delta_tool_calls:
                    has_tool_use = True
                    # Close text block if it was open
                    if text_block_started:
                        yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': content_index})}\n\n"
                        content_index += 1
                        text_block_started = False

                    tool_use_id = f"toolu_{uuid.uuid4().hex[:24]}"
                    # Start tool_use block
                    yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': content_index, 'content_block': {'type': 'tool_use', 'id': tool_use_id, 'name': tc['name'], 'input': {}}})}\n\n"
                    # Send input as a single JSON delta
                    input_json = json.dumps(tc["args"])
                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': content_index, 'delta': {'type': 'input_json_delta', 'partial_json': input_json}})}\n\n"
                    # Stop tool_use block
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': content_index})}\n\n"
                    content_index += 1

            # Close text block if still open
            if text_block_started:
                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': content_index})}\n\n"

            # Send Anthropic SSE epilogue
            stop_reason = "tool_use" if has_tool_use else "end_turn"
            yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': stop_reason, 'stop_sequence': None}, 'usage': {'output_tokens': output_tokens}})}\n\n"
            yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

        finally:
            duration = (time.time() - t0) * 1000
            plog.log("POST", "/v1/messages", "anthropic", model, True, 200, duration,
                     account["email"], account["id"], input_tokens=input_tokens, output_tokens=output_tokens,
                     original_model=original_model)
            await client.close()

    return StreamingResponse(
        content=stream_anthropic(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
