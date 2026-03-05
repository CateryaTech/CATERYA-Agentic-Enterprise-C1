"""
CATERYA Enterprise — FastAPI REST API
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

Run:  uvicorn api.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from auth.jwt_handler import JWTHandler, AuthError
from src.caterya.core.evaluator import CATERYAEvaluator
from src.caterya.blockchain.provenance_chain import ProvenanceChain

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CATERYA Enterprise API",
    description="Multi-tenant agentic AI platform with ethical evaluation",
    version="1.0.0",
    contact={"name": "Ary HH", "email": "cateryatech@proton.me"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth dependency ───────────────────────────────────────────────────────────

async def get_current_user(authorization: str = Header(...)) -> Dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.removeprefix("Bearer ")
    try:
        return JWTHandler.decode_token(token)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))


# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    tenant_id: str
    email: str
    password: str

class WorkflowRequest(BaseModel):
    query: str
    llm_provider: str = "ollama"
    llm_model: str = "llama3"
    cos_threshold: float = 0.7

class EvaluateRequest(BaseModel):
    output: str
    context: Optional[Dict[str, Any]] = None

class TenantProvisionRequest(BaseModel):
    slug: str
    name: str
    plan: str = "free"
    admin_email: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "caterya-enterprise"}


@app.post("/auth/login")
async def login(req: LoginRequest):
    # In production: verify against DB
    token = JWTHandler.create_access_token(
        user_id="demo-user",
        tenant_id=req.tenant_id,
        email=req.email,
        role="admin",
    )
    refresh = JWTHandler.create_refresh_token("demo-user", req.tenant_id)
    return {"access_token": token, "refresh_token": refresh, "token_type": "bearer"}


@app.post("/auth/refresh")
async def refresh_token(refresh_token: str):
    try:
        new_token = JWTHandler.refresh_access_token(refresh_token)
        return {"access_token": new_token, "token_type": "bearer"}
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.post("/workflow/run")
async def run_workflow(
    req: WorkflowRequest,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(get_current_user),
):
    from workflows.langgraph_workflow import CateryaWorkflow
    try:
        wf = CateryaWorkflow(
            tenant_id=user["tenant_id"],
            cos_threshold=req.cos_threshold,
            llm_provider=req.llm_provider,
            llm_model=req.llm_model,
        )
        result = wf.run(req.query, user_id=user["sub"])
        return {
            "session_id":   result.get("session_id"),
            "final_output": result.get("final_output"),
            "cos_result":   result.get("cos_result"),
            "guardrail_blocked": result.get("guardrail_blocked"),
        }
    except Exception as exc:
        logger.exception("Workflow error")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/evaluate")
async def evaluate_output(
    req: EvaluateRequest,
    user: Dict = Depends(get_current_user),
):
    ev = CATERYAEvaluator(tenant_id=user["tenant_id"])
    ctx = req.context or {}
    ctx.setdefault("tenant_id", user["tenant_id"])
    result = ev.evaluate(req.output, context=ctx)
    return result.to_dict()


@app.get("/provenance/{session_id}")
async def get_provenance(session_id: str, user: Dict = Depends(get_current_user)):
    # In production: fetch from Redis/DB
    return {"message": "Provenance chain retrieval requires Redis connection", "session_id": session_id}


@app.post("/tenants/provision")
async def provision_tenant(
    req: TenantProvisionRequest,
    user: Dict = Depends(get_current_user),
):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=500, detail="DATABASE_URL not configured")

    from tenancy.isolation import TenantManager
    mgr = TenantManager(db_url)
    tenant = mgr.provision_tenant(req.slug, req.name, req.plan, req.admin_email)
    return tenant.to_dict()
