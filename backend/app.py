"""Vibe-Research 后端 —— A股数据层 HTTP 接口（FastAPI）。

端点全部在 /api 下，前端 vite 代理 /api → localhost:8900。
只读、无状态、按用户传入代码返回客观数据。不预置标的、不建议。

启动：
    uvicorn app:app --host 127.0.0.1 --port 8900
"""

from __future__ import annotations

import json
import os
import base64
import hashlib
import hmac
import time
import uuid

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=False)

import astock
import chat as chat_layer
import cli_runtime
import debate as debate_layer
import gstock
import newsradar
import portfolio as pf
import market
import myreports as mr
import private_json as pj
import reflection as reflect_layer
import user_storage as us

app = FastAPI(title="Vibe-Research API", version="0.2.2")

# 每半小时后台刷新持仓数据
pf.start_scheduler(1800)

# CORS：默认放开（本地自托管友好）；公网部署时用 VR_ALLOW_ORIGINS 收紧成白名单。
#   例：VR_ALLOW_ORIGINS="https://myhost"  （逗号分隔多个）
_ORIGINS = [o.strip() for o in os.environ.get("VR_ALLOW_ORIGINS", "*").split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 可选鉴权：设了 VR_API_KEY 就要求所有 /api/* 带 `Authorization: Bearer <key>`
#   （本地自托管不设=开放；公网部署务必设，否则别人能读你的持仓/调你的后端）。
_API_KEY = os.environ.get("VR_API_KEY", "").strip()

_SESSION_COOKIE = "vr_session"
_REMEMBER_TTL_SECONDS = 30 * 24 * 60 * 60
_SESSION_TTL_SECONDS = 12 * 60 * 60


def _parse_login_users(raw: str) -> dict[str, dict[str, str]]:
    users: dict[str, dict[str, str]] = {}
    for entry in raw.split(","):
        parts = entry.strip().split(":")
        if len(parts) != 3:
            continue
        username, password, role = (part.strip() for part in parts)
        if username and password:
            users[username] = {"password": password, "role": role or "user"}
    return users


_LOGIN_USERS_RAW = os.environ.get("LOGIN_USERS", "")
_LOGIN_USERS = _parse_login_users(_LOGIN_USERS_RAW)
_LOGIN_SECRET = os.environ.get("LOGIN_REMEMBER_SECRET", "").strip() or hashlib.sha256(
    _LOGIN_USERS_RAW.encode("utf-8")
).hexdigest()


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _create_session(username: str, role: str, ttl_seconds: int) -> str:
    payload = _b64encode(json.dumps({
        "v": 1,
        "username": username,
        "role": role,
        "exp": int(time.time()) + ttl_seconds,
    }, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64encode(hmac.new(
        _LOGIN_SECRET.encode("utf-8"), payload.encode("ascii"), hashlib.sha256,
    ).digest())
    return f"{payload}.{signature}"


def _session_user(request: Request) -> dict[str, str] | None:
    token = request.cookies.get(_SESSION_COOKIE, "")
    try:
        payload, signature = token.split(".", 1)
        expected = _b64encode(hmac.new(
            _LOGIN_SECRET.encode("utf-8"), payload.encode("ascii"), hashlib.sha256,
        ).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_b64decode(payload))
        if data.get("v") != 1 or int(data.get("exp", 0)) < int(time.time()):
            return None
        username = str(data.get("username", ""))
        role = str(data.get("role", ""))
        user = _LOGIN_USERS.get(username)
        if not user or user.get("role") != role:
            return None
        return {"username": username, "role": role}
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


@app.middleware("http")
async def _require_api_key(request: Request, call_next):
    is_auth_route = request.url.path.startswith("/api/auth/")
    valid_bearer = bool(
        _API_KEY and request.headers.get("authorization", "") == f"Bearer {_API_KEY}"
    )
    session_user = _session_user(request) if _LOGIN_USERS else None
    request.state.user = (
        us.UserIdentity(session_user["username"], session_user["role"])
        if session_user
        else us.UserIdentity("_local", "local") if not _LOGIN_USERS else None
    )
    valid_session = bool(session_user)
    if (
        (_API_KEY or _LOGIN_USERS)
        and request.method != "OPTIONS"
        and request.url.path.startswith("/api/")
        and request.url.path != "/api/health"
        and not is_auth_route
    ):
        if not valid_bearer and not valid_session:
            return JSONResponse({"detail": "登录已失效，请重新登录"}, status_code=401)
    return await call_next(request)

_CODE_RE = r"^\d{6}$"


def _validate(code: str) -> str:
    code = (code or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(400, "代码必须是 6 位数字")
    return code


@app.get("/api/health")
def health():
    return {"ok": True, "service": "vibe-research-api", "version": "0.2.2"}


class LoginReq(BaseModel):
    username: str
    password: str
    remember: bool = True


@app.get("/api/auth/status")
def auth_status(request: Request):
    if not _LOGIN_USERS:
        return {"enabled": False, "authenticated": True, "user": None}
    user = _session_user(request)
    return {"enabled": True, "authenticated": bool(user), "user": user}


@app.post("/api/auth/login")
def auth_login(req: LoginReq):
    user = _LOGIN_USERS.get(req.username.strip())
    supplied = req.password
    valid = bool(user and hmac.compare_digest(user["password"], supplied))
    if not valid:
        raise HTTPException(401, "账号或密码错误")

    ttl = _REMEMBER_TTL_SECONDS if req.remember else _SESSION_TTL_SECONDS
    response = JSONResponse({
        "ok": True,
        "user": {"username": req.username.strip(), "role": user["role"]},
    })
    response.set_cookie(
        _SESSION_COOKIE,
        _create_session(req.username.strip(), user["role"], ttl),
        max_age=_REMEMBER_TTL_SECONDS if req.remember else None,
        httponly=True,
        secure=os.environ.get("VR_COOKIE_SECURE", "").lower() in ("1", "true", "yes"),
        samesite="lax",
        path="/",
    )
    return response


@app.post("/api/auth/logout")
def auth_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(_SESSION_COOKIE, path="/", samesite="lax")
    return response


class LLMConfig(BaseModel):
    provider: str = ""       # cli-* = 订阅接入（调本机 CLI）；其余 = API 接入
    baseURL: str = ""        # 订阅接入时留空
    apiKey: str = ""         # 订阅接入时留空
    model: str


class ChatReq(BaseModel):
    messages: list[dict]
    context: str = ""
    llm: LLMConfig


@app.post("/api/chat")
def chat(req: ChatReq):
    """系统 AI 对话，**流式** NDJSON（每行一个事件 {type: tool|delta|done|error}）。

    - API 接入：OpenAI 兼容 function-calling，边流答案边推工具调用事件。
    - 订阅接入（provider=cli-*）：调本机已登录的 CLI，stdout 边出边流（数据靠 context）。
    配置错误（缺 key / 未装 CLI）走 HTTP 400；运行时错误走流内 error 事件。用户配置随请求传入，后端不持久化。
    """
    if not req.messages:
        raise HTTPException(400, "messages 不能为空")
    if not req.llm.model:
        raise HTTPException(400, "缺少模型配置，请先在「接入 AI」里选择")

    is_cli = req.llm.provider.startswith("cli-")
    if is_cli:
        kind = req.llm.provider[4:]
        if not cli_runtime.detect_cli(kind):
            raise HTTPException(400, f"未检测到「{kind}」对应的本机命令。请先安装并登录该 CLI，或改用「API 接入」。")
    elif not req.llm.apiKey or not req.llm.baseURL:
        raise HTTPException(400, "缺少 Base URL 或 API Key，请先在「接入 AI」里填写")

    cfg = req.llm.model_dump()

    def gen():
        try:
            events = (chat_layer.run_chat_cli_stream if is_cli else chat_layer.run_chat_stream)(cfg, req.messages, req.context)
            for ev in events:
                yield json.dumps(ev, ensure_ascii=False) + "\n"
        except Exception as e:  # noqa: BLE001 — 运行时错误以流内事件上报，不中断连接
            yield json.dumps({"type": "error", "message": f"对话失败：{e}"}, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


def _check_llm(llm: LLMConfig) -> dict:
    """校验模型配置并返回 cfg（chat / debate / reflect 三个流式端点共用）。

    配置问题走 HTTP 400（前端能弹提示引导去「接入 AI」页），运行时错误留给流内 error 事件。
    """
    if not llm.model:
        raise HTTPException(400, "缺少模型配置，请先在「接入 AI」里选择")
    if llm.provider.startswith("cli-"):
        kind = llm.provider[4:]
        if not cli_runtime.detect_cli(kind):
            raise HTTPException(400, f"未检测到「{kind}」对应的本机命令。请先安装并登录该 CLI，或改用「API 接入」。")
    elif not llm.apiKey or not llm.baseURL:
        raise HTTPException(400, "缺少 Base URL 或 API Key，请先在「接入 AI」里填写")
    return llm.model_dump()


def _ndjson(events):
    """把事件生成器包成 NDJSON 流；运行时异常转成流内 error 事件，不中断连接。"""
    def gen():
        try:
            for ev in events():
                yield json.dumps(ev, ensure_ascii=False) + "\n"
        except Exception as e:  # noqa: BLE001
            yield json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


class DebateReq(BaseModel):
    code: str
    rounds: int = 1
    llm: LLMConfig


@app.post("/api/debate")
def debate(req: DebateReq):
    """多空辩论：后端先拉客观事实底稿，再让多方 / 空方 / 中立主持依次发言，**流式** NDJSON。

    刻意不产出买卖结论——终点是「分歧点 + 验证清单」，判断留给用户自己。
    """
    code = _validate(req.code)
    cfg = _check_llm(req.llm)
    rounds = 2 if req.rounds >= 2 else 1
    return _ndjson(lambda: debate_layer.run_debate_stream(cfg, code, rounds))


class ReflectReq(BaseModel):
    source: str
    title: str = ""
    llm: LLMConfig


@app.post("/api/reflect")
def reflect(req: ReflectReq):
    """反思：对一段已写好的分析做推理审计（哪些有数据支撑、最脆弱一环、验证清单），流式 NDJSON。"""
    if not (req.source or "").strip():
        raise HTTPException(400, "source 不能为空")
    cfg = _check_llm(req.llm)
    return _ndjson(lambda: reflect_layer.run_reflection_stream(cfg, req.source, req.title))


class HoldingIn(BaseModel):
    code: str
    shares: float
    cost: float


def _private_user_dir(request: Request):
    return us.user_dir(us.private_identity(request))


class WatchlistIn(BaseModel):
    codes: list[str]


@app.get("/api/watchlist")
def watchlist_get(request: Request):
    data = pj.load(_private_user_dir(request) / "watchlist.json", [])
    return {"data": data if isinstance(data, list) else []}


@app.put("/api/watchlist")
def watchlist_put(body: WatchlistIn, request: Request):
    codes: list[str] = []
    for raw in body.codes:
        code = str(raw).strip()
        if not code.isdigit() or len(code) != 6:
            raise HTTPException(400, "股票代码必须是 6 位数字")
        if code not in codes:
            codes.append(code)
    if len(codes) > 200:
        raise HTTPException(400, "自选股最多保存 200 个代码")
    pj.save(_private_user_dir(request) / "watchlist.json", codes)
    return {"data": codes}


class NoteIn(BaseModel):
    kind: str
    title: str
    content: str
    source: str = ""


@app.get("/api/notes")
def notes_get(request: Request):
    data = pj.load(_private_user_dir(request) / "notes.json", [])
    return {"data": data if isinstance(data, list) else []}


@app.post("/api/notes")
def notes_add(body: NoteIn, request: Request):
    kind, title, content, source = (
        body.kind.strip(), body.title.strip(), body.content, body.source.strip()
    )
    if not kind or len(kind) > 50 or not title or len(title) > 200:
        raise HTTPException(400, "记录类型或标题不符合长度要求")
    if not content or len(content) > 100_000 or len(source) > 500:
        raise HTTPException(400, "记录正文或来源不符合长度要求")
    path = _private_user_dir(request) / "notes.json"
    note = {
        "id": uuid.uuid4().hex, "kind": kind, "title": title,
        "content": content, "source": source, "ts": int(time.time() * 1000),
    }

    def add(items):
        items = items if isinstance(items, list) else []
        if len(items) >= 1000:
            raise HTTPException(400, "研究记录最多保存 1000 条")
        return note, [note, *items]

    return {"data": pj.mutate(path, [], add)}


@app.delete("/api/notes/{note_id}")
def notes_delete(note_id: str, request: Request):
    path = _private_user_dir(request) / "notes.json"

    def remove(items):
        items = items if isinstance(items, list) else []
        found = any(item.get("id") == note_id for item in items if isinstance(item, dict))
        return found, [item for item in items if not isinstance(item, dict) or item.get("id") != note_id]

    if not pj.mutate(path, [], remove):
        raise HTTPException(404, "研究记录不存在")
    return {"data": {"ok": True}}


class StoredChatMessage(BaseModel):
    role: str
    content: str


class StoredChatIn(BaseModel):
    messages: list[StoredChatMessage]


def _chat_path(request: Request, scope: str):
    scope = scope.strip()
    if not scope or len(scope) > 200 or any(ord(char) < 32 for char in scope):
        raise HTTPException(400, "会话范围无效")
    key = hashlib.sha256(scope.encode("utf-8")).hexdigest()
    return scope, _private_user_dir(request) / "chats" / f"{key}.json"


@app.get("/api/chats/{scope}")
def stored_chat_get(scope: str, request: Request):
    clean_scope, path = _chat_path(request, scope)
    data = pj.load(path, None)
    if not isinstance(data, dict) or data.get("scope") != clean_scope:
        data = {"scope": clean_scope, "messages": [], "updatedAt": 0}
    return {"data": data}


@app.put("/api/chats/{scope}")
def stored_chat_put(scope: str, body: StoredChatIn, request: Request):
    clean_scope, path = _chat_path(request, scope)
    if len(body.messages) > 40:
        raise HTTPException(400, "会话最多保存 40 条消息")
    messages = []
    for message in body.messages:
        if message.role not in {"user", "assistant"} or not message.content:
            raise HTTPException(400, "会话消息格式无效")
        messages.append({"role": message.role, "content": message.content})
    data = {"scope": clean_scope, "messages": messages, "updatedAt": int(time.time() * 1000)}
    if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > 512 * 1024:
        raise HTTPException(413, "会话内容超过 512 KiB")
    pj.save(path, data)
    return {"data": data}


@app.delete("/api/chats/{scope}")
def stored_chat_delete(scope: str, request: Request):
    _, path = _chat_path(request, scope)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(500, "清除会话失败") from exc
    return {"data": {"ok": True}}


@app.get("/api/portfolio")
def portfolio_get(request: Request):
    """持仓 + 实时盈亏（浮动盈亏红涨绿跌）。"""
    data_dir = _private_user_dir(request)
    try:
        return {"data": pf.get_portfolio(data_dir)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"持仓读取异常：{e}") from e


@app.post("/api/portfolio/holding")
def portfolio_add(h: HoldingIn, request: Request):
    """加一笔持仓（同代码按加权平均成本合并）。存本地，不上传。"""
    code = (h.code or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(400, "代码必须是 6 位数字")
    if h.shares <= 0:
        raise HTTPException(400, "数量必须大于 0")
    # 成本价不限正负：融券 / 返息 / 摊薄后为负成本等情形按结果计算，用户想怎么输就怎么输。
    return {"data": pf.add_holding(code, h.shares, h.cost, _private_user_dir(request))}


@app.delete("/api/portfolio/holding")
def portfolio_remove(request: Request, code: str = Query(...)):
    return {"data": pf.remove_holding(code.strip(), _private_user_dir(request))}


# ---- 我的研报（用户上传自己的研报，存本地、不上传、不进开源仓库）----

class ReportIn(BaseModel):
    name: str
    content_b64: str


@app.get("/api/myreports")
def myreports_list(request: Request):
    return {"data": mr.list_reports(_private_user_dir(request) / "reports")}


@app.post("/api/myreports")
def myreports_upload(r: ReportIn, request: Request):
    """上传一份研报（base64）→ 存本地 + 按文件名自动打行业标签。"""
    try:
        return {"data": mr.save_report(r.name, r.content_b64, _private_user_dir(request) / "reports")}
    except mr.ReportError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/myreports/file/{rid}")
def myreports_file(rid: str, request: Request):
    """下载/预览某份研报原文件。"""
    hit = mr.report_path(rid, _private_user_dir(request) / "reports")
    if not hit:
        raise HTTPException(404, "研报不存在")
    path, name = hit
    return FileResponse(str(path), filename=name)


@app.delete("/api/myreports/{rid}")
def myreports_delete(rid: str, request: Request):
    return {"data": {"ok": mr.delete_report(rid, _private_user_dir(request) / "reports")}}


class CloseIn(BaseModel):
    code: str
    date: str
    price: float
    shares: float
    cost: float


@app.post("/api/portfolio/close")
def portfolio_close(c: CloseIn, request: Request):
    """记一笔已清仓（已实现盈亏）。存本地。"""
    code = (c.code or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(400, "代码必须是 6 位数字")
    if c.price <= 0 or c.shares <= 0:
        raise HTTPException(400, "清仓价与股数必须大于 0")
    # 买入成本不限正负（同持仓录入）：按 (清仓价 - 成本) × 股数 的结果计算已实现盈亏。
    date = (c.date or "").strip()
    if not date:
        raise HTTPException(400, "请填清仓日期")
    from datetime import datetime
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "清仓日期格式应为 YYYY-MM-DD") from None
    return {"data": pf.close_position(code, date, c.price, c.shares, c.cost, _private_user_dir(request))}


@app.delete("/api/portfolio/close")
def portfolio_close_remove(request: Request, index: int = Query(...)):
    return {"data": pf.remove_closed(index, _private_user_dir(request))}


@app.post("/api/portfolio/refresh")
def portfolio_refresh(request: Request):
    """手动刷新：立即重拉行情算盈亏。"""
    data_dir = _private_user_dir(request)
    try:
        return {"data": pf.get_portfolio(data_dir)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"刷新失败：{e}") from e


@app.get("/api/radar")
def radar():
    """资讯雷达：12 赛道公开 RSS 资讯（读缓存，无缓存返回赛道骨架）。"""
    try:
        return {"data": newsradar.get_radar(force=False)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"资讯雷达异常：{e}") from e


@app.post("/api/radar/refresh")
def radar_refresh():
    """强制重抓全部 RSS 源（耗时约 20-40s），更新缓存。"""
    try:
        return {"data": newsradar.fetch_radar()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"资讯雷达刷新失败：{e}") from e


@app.get("/api/market/overview")
def market_overview():
    """市场情绪 + 板块资金流（板块/大盘级，全站共享缓存 5 分钟）。"""
    try:
        return {"data": market.get_overview()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"市场总览异常：{e}") from e


@app.get("/api/market/emotion")
def market_emotion():
    """短线情绪：连板梯队 / 最高连板 / 炸板率 / 封板率 / 晋级率 / 涨跌停家数。

    含连板梯队个股清单（code/name/连板数等）——2026-07-05 起如实展示客观公开榜单（东财同款），
    只呈现事实，不附推荐/评分/预测/买卖时机。全站共享缓存 5 分钟。
    """
    try:
        return {"data": market.get_short_term_emotion()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"短线情绪异常：{e}") from e


@app.get("/api/market/turnover-top")
def market_turnover_top():
    """全市场成交额榜 Top20（客观公开榜单数据，非推荐/非预测/不评分）。全站共享缓存 5 分钟。"""
    try:
        return {"data": market.get_turnover_top()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"成交额榜异常：{e}") from e


@app.get("/api/global/indices")
def global_indices():
    """全球指数快照（道指 / 标普500 / 纳斯达克 / 恒生 / 恒生科技）—— A 股看隔夜外围脸色。缓存 5 分钟。"""
    try:
        return {"data": market.get_global_indices()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"全球指数异常：{e}") from e


@app.get("/api/global/stock")
def global_stock(symbol: str = Query(..., min_length=1, max_length=16)):
    """美股 / 港股个股聚合：行情 + 关键财务指标（东财域内源）。symbol 如 AAPL / BABA / 00700。"""
    try:
        data = gstock.us_hk_stock(symbol.strip())
        if not data:
            raise HTTPException(404, f"未找到美股/港股代码「{symbol}」")
        return {"data": data}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"美港股查询异常：{e}") from e


@app.get("/api/global/hk/cashflow")
def global_hk_cashflow(symbol: str = Query(..., min_length=1, max_length=16)):
    """港股现金流量表（东财域内源 RPT_HKSK_FN_CASHFLOW）：经营/投资/筹资/净增加，多期。symbol 如 00700。"""
    try:
        data = gstock.hk_cashflow(symbol.strip())
        if not data:
            raise HTTPException(404, f"未找到港股「{symbol}」的现金流数据（仅港股支持）")
        return {"data": data}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"港股现金流查询异常：{e}") from e


@app.get("/api/indices")
def indices():
    """A股大盘指数实时行情（上证/深证成指/创业板指/沪深300）。仅标准库。"""
    try:
        return {"data": astock.index_quote()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"指数行情异常：{e}") from e


@app.get("/api/quote")
def quote(codes: str = Query(..., description="逗号分隔的 6 位代码")):
    """实时行情：现价/涨跌/PE/PB/市值/换手/涨跌停。仅标准库，永远可用。"""
    lst = [c.strip() for c in codes.split(",") if c.strip()]
    if not lst or any(not c.isdigit() or len(c) != 6 for c in lst):
        raise HTTPException(400, "codes 必须是逗号分隔的 6 位数字")
    try:
        return {"data": astock.tencent_quote(lst)}
    except Exception as e:  # noqa: BLE001 — 边界统一兜底
        raise HTTPException(502, f"行情源异常：{e}") from e


import time as _time
_PCT_CACHE: dict = {}


@app.get("/api/valuation/percentile")
def valuation_percentile(code: str = Query(...)):
    """PE-TTM / PB 历史分位（近5年）。全站缓存 30 分钟/代码（历史序列日频、变化慢）。"""
    code = _validate(code)
    hit = _PCT_CACHE.get(code)
    if hit and _time.time() - hit[0] < 1800:
        return {"data": hit[1]}
    try:
        data = astock.valuation_percentile(code)
        _PCT_CACHE[code] = (_time.time(), data)
        return {"data": data}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"估值分位异常：{e}") from e


_ANN_CACHE: dict = {}


@app.get("/api/announcements")
def announcements(code: str = Query(...)):
    """个股近期公告（东财，仅 requests）。缓存 15 分钟/代码。"""
    code = _validate(code)
    hit = _ANN_CACHE.get(code)
    if hit and _time.time() - hit[0] < 900:
        return {"data": hit[1]}
    try:
        data = astock.announcements(code)
        _ANN_CACHE[code] = (_time.time(), data)
        return {"data": data}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"公告源异常：{e}") from e


_FIN_CACHE: dict = {}


@app.get("/api/financials")
def financials(code: str = Query(...)):
    """财务关键指标（同花顺财务摘要，最新报告期）。缓存 30 分钟/代码。"""
    code = _validate(code)
    hit = _FIN_CACHE.get(code)
    if hit and _time.time() - hit[0] < 1800:
        return {"data": hit[1]}
    try:
        data = astock.financials(code)
        _FIN_CACHE[code] = (_time.time(), data)
        return {"data": data}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"财务摘要异常：{e}") from e


@app.get("/api/valuation")
def valuation(code: str = Query(...)):
    """完整估值：行情 + 一致预期 + 前向PE/PEG/消化年数。"""
    code = _validate(code)
    try:
        return {"data": astock.full_valuation(code)}
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"估值计算异常：{e}") from e


@app.get("/api/reports")
def reports(code: str = Query(...), pages: int = Query(2, ge=1, le=5)):
    """个股研报列表（东财，含 PDF 链接）。仅需 requests。"""
    code = _validate(code)
    try:
        rows = astock.eastmoney_reports(code, max_pages=pages)
        for r in rows:
            r["pdfUrl"] = astock.pdf_url(r.get("infoCode", "")) if r.get("infoCode") else None
        return {"data": rows}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"研报源异常：{e}") from e


@app.get("/api/news")
def news(code: str = Query(...), limit: int = Query(20, ge=1, le=50)):
    """个股新闻（东财，需 akshare）。"""
    code = _validate(code)
    try:
        return {"data": astock.stock_news(code, limit=limit)}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"新闻源异常：{e}") from e


@app.get("/api/info")
def info(code: str = Query(...)):
    """个股基本面：行业/股本/上市时间（需 akshare）。"""
    code = _validate(code)
    try:
        return {"data": astock.individual_info(code)}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"基本面源异常：{e}") from e


@app.get("/api/disclosure")
def disclosure(code: str = Query(...)):
    """巨潮公告列表（需 akshare）。"""
    code = _validate(code)
    try:
        return {"data": astock.disclosure(code)}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"公告源异常：{e}") from e


@app.get("/api/kline")
def kline(code: str = Query(...), category: int = Query(4), offset: int = Query(60, ge=1, le=800)):
    """K线（需 mootdx）。category 4=日 5=周 6=月 11=60分钟。"""
    code = _validate(code)
    try:
        return {"data": astock.kline(code, category=category, offset=offset)}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"K线源异常：{e}") from e


@app.get("/api/finance")
def finance(code: str = Query(...)):
    """季报财务快照（需 mootdx）。"""
    code = _validate(code)
    try:
        return {"data": astock.finance(code)}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"财务源异常：{e}") from e


# ---------------------------------------------------------------------------
# 资金面 / 筹码 / 信号（东财数据中心，v3.3 并入）—— 均为「用户查的那只股」的公开数据。
# 东财有 1s 限流，这些多为日/季级静态数据，统一走 30 分钟缓存，进一步降低被封风险。
# ---------------------------------------------------------------------------

_DC_CACHE: dict = {}  # key=(endpoint, code) -> (ts, data)


def _cached(endpoint: str, code: str, ttl: int, fetch):
    key = (endpoint, code)
    hit = _DC_CACHE.get(key)
    if hit and _time.time() - hit[0] < ttl:
        return hit[1]
    data = fetch()
    _DC_CACHE[key] = (_time.time(), data)
    return data


@app.get("/api/margin")
def margin(code: str = Query(...)):
    """融资融券明细（东财，日级）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("margin", code, 1800, lambda: astock.margin_trading(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"融资融券异常：{e}") from e


@app.get("/api/block-trade")
def block_trade(code: str = Query(...)):
    """大宗交易（东财）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("block", code, 1800, lambda: astock.block_trade(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"大宗交易异常：{e}") from e


@app.get("/api/holders")
def holders(code: str = Query(...)):
    """股东户数变化（东财，季度级）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("holders", code, 1800, lambda: astock.holder_num_change(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"股东户数异常：{e}") from e


@app.get("/api/dividend")
def dividend(code: str = Query(...)):
    """分红送转历史（东财）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("dividend", code, 1800, lambda: astock.dividend_history(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"分红送转异常：{e}") from e


@app.get("/api/fund-flow")
def fund_flow(code: str = Query(...)):
    """个股资金流（东财 push2his，120 日主力净流入）。缓存 15 分钟。
    注：push2his 对部分大陆住宅 IP 有间歇风控，可能返回空（非代码问题）。"""
    code = _validate(code)
    try:
        return {"data": _cached("fundflow", code, 900, lambda: astock.stock_fund_flow_120d(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"资金流异常：{e}") from e


@app.get("/api/dragon-tiger")
def dragon_tiger(code: str = Query(...)):
    """龙虎榜：该股近期上榜记录 + 买卖席位 + 机构净买（东财）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("dt", code, 1800, lambda: astock.dragon_tiger_board(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"龙虎榜异常：{e}") from e


@app.get("/api/lockup")
def lockup(code: str = Query(...)):
    """限售解禁日历：历史解禁 + 未来 90 天待解禁（东财）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("lockup", code, 1800, lambda: astock.lockup_expiry(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"解禁日历异常：{e}") from e


@app.get("/api/blocks")
def blocks(code: str = Query(...)):
    """个股所属板块/概念归属（东财 slist）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("blocks", code, 1800, lambda: astock.concept_blocks(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"板块归属异常：{e}") from e


@app.get("/api/hot-concepts")
def hot_concepts(code: str = Query(...)):
    """个股当下被市场归到哪些概念在炒（东财热门概念命中）。缓存 15 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("hotcon", code, 900, lambda: astock.hot_concepts(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"热门概念异常：{e}") from e


@app.get("/api/investor-qa")
def investor_qa(code: str = Query(...)):
    """互动易问答（巨潮）：投资者提问 + 公司回复。缓存 15 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("irm", code, 900, lambda: astock.investor_qa(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"互动易异常：{e}") from e


@app.get("/api/industry")
def industry(top: int = Query(20, ge=5, le=50)):
    """全行业涨跌幅排名（东财行业板块，板块级、零个股名单）。缓存 5 分钟。"""
    key = ("industry", str(top))
    hit = _DC_CACHE.get(key)
    if hit and _time.time() - hit[0] < 300:
        return {"data": hit[1]}
    try:
        data = astock.industry_comparison(top_n=top)
        _DC_CACHE[key] = (_time.time(), data)
        return {"data": data}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"行业排名异常：{e}") from e
