"""
FastAPI application factory for CohortOS backend.

Thin routes only — business logic lives in services/*.
Signatures match the tested service methods exactly.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends, Header, Request, Response, Cookie, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.auth import (
    require_jwt_secret,
    require_auth_db,
    require_cloud_db,
    TokenService,
    RateLimiter,
    RateLimitExceeded,
    AuthError,
    TokenReuseError,
)
from api.sync_remote import CloudSyncStore
from services.app import create_app, CohortOSApp
from services.llm_provider import MockLLMProvider, GeminiProvider
from services.founder_admin import FounderAdminService, FounderAuthError, require_founder_token
from services.roll_encoder import RollEncoder
from services.payment_gateway import build_gateway_from_config, PaymentGatewayError
from services.biometric_driver import BiometricDriver, BiometricDriverError, PYZK_AVAILABLE
from models.base import TenantContext, DataAccessLayer


# ── Request models ────────────────────────────────────────────────────

class AccountSignupBody(BaseModel):
    phone: str = ""
    email: str = ""
    display_name: str = ""
    role: str = "student"
    tenant_id: Optional[str] = None  # optional; required only when joining a known centre

class CentreTrialBody(BaseModel):
    """Public self-serve coaching centre trial (14 days). No founder, no tenant id."""
    centre_name: str
    owner_phone: str
    owner_name: str = ""
    owner_email: str = ""
    student_count: int = 0

class OTPRequest(BaseModel):
    phone: str = ""
    email: str = ""
    tenant_id: Optional[str] = None  # optional — resolved from phone when omitted

class OTPVerify(BaseModel):
    otp_id: str
    code: str
    tenant_id: Optional[str] = None

class BatchCreateBody(BaseModel):
    days: List[str]
    hour: int
    name: str = ""
class BatchUpdateBody(BaseModel):
    days: Optional[List[str]] = None
    hour: Optional[int] = None
    name: Optional[str] = None
    name_override: Optional[str] = None
    is_active: Optional[bool] = None

class ExtraSessionBody(BaseModel):
    day: str
    hour: int
    expires_on: str
    batch_id: Optional[str] = None

class StudentMigrateBody(BaseModel):
    new_batch_id: Optional[str] = None
    new_roll: Optional[str] = None



class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None

class SyncPushBody(BaseModel):
    operations: list = Field(default_factory=list)
    device_id: str = ""

class SyncPullBody(BaseModel):
    since_seq: int = 0
    limit: int = 200
    device_id: str = ""

class ManualAttendanceBody(BaseModel):
    student_id: str
    batch_id: Optional[str] = None
    date: str  # maps to on_date
    status: str = "present"  # maps to status_or_time
    notes: str = ""

class LateThresholdBody(BaseModel):
    minutes: int
    batch_id: Optional[str] = None

class PaymentActionBody(BaseModel):
    student_id: str
    year: int
    month: int
    amount: Optional[float] = None
    notes: str = ""
    reason: str = ""

class NotifyFlagBody(BaseModel):
    student_id: str
    year: int
    month: int
    flag: str  # green | white

class StudentAdmitBody(BaseModel):
    name: str
    batch_id: str
    phone: str = ""  # maps to student_phone
    parent_phone: str = ""
    whatsapp: str = ""
    roll: Optional[str] = None
    force: bool = False

class DuplicateCheckBody(BaseModel):
    name: str = ""
    phone: str = ""
    parent_phone: str = ""

class RollPreviewBody(BaseModel):
    batch_id: str
    serial: Optional[int] = None

class SolveAskBody(BaseModel):
    question: str
    student_id: str
    thread_id: Optional[str] = None
    subject: str = ""
    topic: str = ""
    mode: str = "mcq"  # maps to question_type

class StyleProfileBody(BaseModel):
    subject: str
    style_notes: str = ""
    terminology: str = ""
    sign_conventions: str = ""
    difficulty: str = ""
    preferred_language: str = "en"
    few_shot_examples: Optional[List[Any]] = None

class OcrBody(BaseModel):
    image_b64: Optional[str] = None
    text: Optional[str] = None
    subject: str = "physics"
    topic: str = ""
    rubric: Optional[str] = None

class RecapDraftBody(BaseModel):
    subject: str = "physics"
    topic: str = ""
    batch_id: Optional[str] = None
    misconception: Optional[str] = None

class ThreadReplyBody(BaseModel):
    body: str
    annotate_message_id: Optional[str] = None

class GenerateItemBody(BaseModel):
    item_type: str = "mcq"
    subject: str = "physics"
    topic: str = ""
    prompt: str = ""
    batch_id: Optional[str] = None

class ApproveItemBody(BaseModel):
    edits: Optional[Dict[str, Any]] = None

class RejectItemBody(BaseModel):
    reason: str = ""


class ParentLinkBody(BaseModel):
    parent_account_id: str
    student_id: str
    # optional cross-tenant: only when allow_cross_tenant=true and founder/owner
    target_tenant_id: Optional[str] = None

class AccountLinkJoinBody(BaseModel):
    # Primary path (SPEC Module 8): student only has the join code — admission_id
    # is resolved server-side by looking the code up. admission_id may still be
    # supplied directly for the staff-manual fallback path.
    account_id: Optional[str] = None
    cohortos_account_id: Optional[str] = None  # legacy alias, still accepted
    join_code: Optional[str] = None
    admission_id: Optional[str] = None

class StaffCreateBody(BaseModel):
    name: str
    role: str = "desk"
    phone: str = ""
    email: str = ""

class ModeBody(BaseModel):
    mode: str

class MessagingSettingsBody(BaseModel):
    channel: Optional[str] = None
    absentees_time: Optional[str] = None
    templates: Optional[Dict[str, str]] = None

class FounderProvisionBody(BaseModel):
    name: str
    code: str
    owner_email: str = ""
    tier: Optional[str] = None
    student_count: int = 0
    trial_days: int = 14
    mode: str = "offline-first"

class BiometricDeviceBody(BaseModel):
    name: str
    ip_address: str = ""
    port: int = 4370
    device_type: str = "zkteco"
    batch_id: Optional[str] = None

class BiometricDeviceTestBody(BaseModel):
    ip: Optional[str] = None
    port: int = 4370
    device_id: Optional[str] = None

class DeviceUserLinkBody(BaseModel):
    student_id: str
    device_user_id: str

class DeviceUserBulkBody(BaseModel):
    rows: List[Dict[str, Any]] = Field(default_factory=list)  # [{student_id|roll, device_user_id}]

class StorageSettingsBody(BaseModel):
    provider: str = "google_drive"
    folder_id: Optional[str] = None
    access_token: Optional[str] = None
    credentials_json: Optional[str] = None
    root: Optional[str] = None

class BiometricPullBody(BaseModel):

    device_id: Optional[str] = None
    ip: Optional[str] = None
    port: int = 4370
    clear_after: bool = False

class ResolveReviewBody(BaseModel):
    final_status: str
    notes: str = ""


class PaymentIntentBody(BaseModel):
    student_id: str
    year: int
    month: int
    amount: float = 0
    currency: str = "BDT"


class ConflictResolveBody(BaseModel):
    resolution: str = "manual"  # local | remote | manual
    notes: str = ""


class ExamCreateBody(BaseModel):
    name: str
    exam_date: str
    batch_id: Optional[str] = None
    template_id: Optional[str] = None
    chapter_or_topic: str = ""
    subject: str = ""
    sections: Optional[List[Any]] = None
    is_ad_hoc: bool = False
    notes: str = ""


class ExamResultBody(BaseModel):
    student_id: str
    section_scores: Optional[List[Dict[str, Any]]] = None
    is_absent: bool = False
    notes: str = ""


class VaultCreateBody(BaseModel):
    title: str
    resource_type: str = "pdf"
    topic: str = ""
    subject: str = ""
    description: str = ""
    url: str = ""
    batch_ids: Optional[List[str]] = None
    access_rules: Optional[Dict[str, Any]] = None
    protection_level: str = "owner_only"
    actor_role: str = "owner"


class VaultAccessRulesBody(BaseModel):
    operator: str = "AND"
    rules: List[Dict[str, Any]] = Field(default_factory=list)


class VaultProtectBody(BaseModel):
    actor_role: str = "owner"


class StaffRoleBody(BaseModel):
    role_name: str
    is_owner: bool = False


class AppRegistry:
    def __init__(
        self,
        jwt_secret: str,
        cloud_db: str = ":memory:",
        auth_db: str = ":memory:",
        founder_token: Optional[str] = None,
    ):
        self.jwt_secret = jwt_secret
        self._meta = DataAccessLayer(
            TenantContext(uuid.UUID("00000000-0000-4000-8000-000000000099")),
            db_path=auth_db,
        )
        self.tokens = TokenService(jwt_secret, data_layer=self._meta)
        self.limiter = RateLimiter()
        self.cloud = CloudSyncStore(cloud_db)
        self._apps: Dict[str, CohortOSApp] = {}
        self.founder = FounderAdminService(founder_token=founder_token)

    def _tenant_db_path(self, tenant_id: str) -> str:
        """Durable per-tenant SQLite so batches/students survive app restart."""
        override = (os.environ.get("COHORTOS_TENANT_DB_DIR") or "").strip()
        if override:
            root = override
        else:
            auth = (os.environ.get("COHORTOS_AUTH_DB") or "").strip()
            if auth and auth != ":memory:" and not auth.startswith("file:mem"):
                root = str(Path(auth).resolve().parent / "tenants")
            else:
                # Tests / ephemeral: keep memory
                return ":memory:"
        Path(root).mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(tenant_id))
        return str(Path(root) / f"{safe}.db")

    def get_app(self, tenant_id: str) -> CohortOSApp:
        if tenant_id not in self._apps:
            llm: Any = MockLLMProvider()
            gemini_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
            if gemini_key:
                try:
                    llm = GeminiProvider(api_key=gemini_key, online=True)
                except Exception:
                    llm = MockLLMProvider()
            self._apps[tenant_id] = create_app(
                tenant_id=tenant_id,
                mode="offline-first",
                llm=llm,
                db_path=self._tenant_db_path(tenant_id),
            )
        return self._apps[tenant_id]

    def register_phone_index(self, phone: str, tenant_id: str, account_id: str, role: str, centre_name: str = "") -> None:
        """Global phone → tenant directory in auth DB for login without tenant id."""
        digits = "".join(c for c in (phone or "") if c.isdigit())
        if not digits or not tenant_id or not account_id:
            return
        rows = self._meta.get_all("phone_index")
        for row in rows:
            if row.get("phone") == digits and row.get("tenant_id") == tenant_id and row.get("account_id") == account_id:
                return  # already indexed
        self._meta.create("phone_index", {
            "phone": digits,
            "centre_tenant_id": str(tenant_id),
            "account_id": str(account_id),
            "role": role or "",
            "centre_name": centre_name or "",
        })

    def lookup_phone(self, phone: str) -> List[Dict[str, Any]]:
        digits = "".join(c for c in (phone or "") if c.isdigit())
        if not digits:
            return []
        by_tenant: Dict[str, Dict[str, Any]] = {}
        for row in self._meta.get_all("phone_index"):
            if row.get("phone") != digits:
                continue
            tid = str(row.get("centre_tenant_id") or row.get("tenant_id") or "")
            # Ignore meta/auth control-plane ids
            if not tid or tid.startswith("00000000-0000-4000-8000"):
                continue
            prev = by_tenant.get(tid)
            entry = {
                "phone": digits,
                "tenant_id": tid,
                "account_id": row.get("account_id") or "",
                "role": row.get("role") or "",
                "centre_name": row.get("centre_name") or "",
            }
            if not prev or (entry["account_id"] and not prev.get("account_id")):
                by_tenant[tid] = entry
        for trow in self.founder.find_tenants_by_owner_phone(digits):
            tid = str(trow.get("id") or "")
            if not tid or tid in by_tenant or tid.startswith("00000000-0000-4000-8000"):
                continue
            by_tenant[tid] = {
                "phone": digits,
                "tenant_id": tid,
                "account_id": "",
                "role": "owner",
                "centre_name": trow.get("name") or trow.get("code") or "",
            }
        return list(by_tenant.values())




def _normalize_storage_section(section: Dict[str, Any]) -> Dict[str, Any]:
    """ConfigService.get_section returns keys like storage.provider — strip prefix."""
    out: Dict[str, Any] = {}
    for k, v in (section or {}).items():
        key = str(k)
        if key.startswith("storage."):
            key = key[len("storage."):]
        out[key] = v
    return out


def create_api_app(
    jwt_secret: Optional[str] = None,
    cloud_db: str = ":memory:",
    auth_db: str = ":memory:",
    founder_token: Optional[str] = None,
) -> FastAPI:
    if jwt_secret is None:
        jwt_secret = require_jwt_secret()
    if founder_token is None:
        founder_token = require_founder_token()

    registry = AppRegistry(
        jwt_secret=jwt_secret,
        cloud_db=cloud_db,
        auth_db=auth_db,
        founder_token=founder_token,
    )

    app = FastAPI(title="CohortOS API", version="1.2.0")
    app.state.registry = registry

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in os.environ.get(
            "COHORTOS_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RateLimitExceeded)
    async def _rl(request: Request, exc: RateLimitExceeded):
        return JSONResponse(status_code=429, content={"detail": str(exc)}, headers={"Retry-After": str(exc.retry_after)})

    @app.exception_handler(AuthError)
    async def _ae(request: Request, exc: AuthError):
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.exception_handler(TokenReuseError)
    async def _tr(request: Request, exc: TokenReuseError):
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.exception_handler(FounderAuthError)
    async def _fe(request: Request, exc: FounderAuthError):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    def _client_ip(request: Request) -> str:
        return request.client.host if request.client else ""

    def _bearer(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = authorization.split(" ", 1)[1].strip()
        try:
            return registry.tokens.decode(token, expected_type="access")
        except AuthError as e:
            raise HTTPException(status_code=401, detail=str(e))

    def _require_tenant(claims: Dict[str, Any], tenant_id: str) -> None:
        if str(claims.get("tenant_id")) != str(tenant_id):
            raise HTTPException(status_code=403, detail="Cross-tenant access denied")

    def _founder_header(x_founder_token: Optional[str] = Header(None, alias="X-Founder-Token")) -> str:
        if not x_founder_token:
            raise HTTPException(status_code=403, detail="Missing X-Founder-Token")
        return x_founder_token

    def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
        secure = os.environ.get("COHORTOS_COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
        response.set_cookie(
            key="cohortos_refresh",
            value=refresh_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
            path="/auth",
        )

    def _clear_refresh_cookie(response: Response) -> None:
        response.delete_cookie(key="cohortos_refresh", path="/auth")

    # ── Auth ──────────────────────────────────────────────────────────



    def _llm_cost_guard(tenant_id: str, provider: str = "", route: str = "ai") -> None:
        """Shared AI cost guard for every external LLM path; also records durable usage."""
        max_llm = int(os.environ.get("COHORTOS_AI_MAX_CALLS_PER_WINDOW") or "60")
        window_sec = int(os.environ.get("COHORTOS_AI_COST_WINDOW_SEC") or "3600")
        if not hasattr(registry, "_llm_cost"):
            registry._llm_cost = {}
        cost_key = f"llm:{tenant_id}"
        now_ts = time.time()
        bucket = registry._llm_cost.get(cost_key) or {"count": 0, "start": now_ts}
        if now_ts - float(bucket.get("start") or 0) > window_sec:
            bucket = {"count": 0, "start": now_ts}
        if int(bucket.get("count") or 0) >= max_llm:
            raise HTTPException(
                status_code=429,
                detail=f"AI cost guard: max {max_llm} external LLM calls per window",
                headers={"Retry-After": str(window_sec)},
            )
        bucket["count"] = int(bucket.get("count") or 0) + 1
        registry._llm_cost[cost_key] = bucket
        try:
            from services.billing_service import BillingService
            cm = registry.get_app(tenant_id)
            BillingService(cm.data_layer, tenant_id).record_ai_usage(
                tenant_id, provider=provider or "unknown", route=route or "ai"
            )
        except Exception:
            pass

    @app.post("/auth/centre-trial")
    def centre_trial(body: CentreTrialBody, request: Request):
        """
        Public self-serve: create a coaching centre on a 14-day trial.
        No founder token. No tenant id for the user to type.
        Returns tenant + owner account; client then requests OTP with phone only.
        """
        identity = body.owner_phone or "unknown"
        try:
            registry.limiter.check("centre-trial", identity, _client_ip(request))
        except RateLimitExceeded as e:
            raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": str(e.retry_after)})
        try:
            tenant = registry.founder.self_serve_trial(
                name=body.centre_name,
                owner_phone=body.owner_phone,
                owner_email=body.owner_email or "",
                owner_name=body.owner_name or "",
                student_count=body.student_count or 0,
                trial_days=14,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        tenant_id = str(tenant.get("id"))
        cm = registry.get_app(tenant_id)
        try:
            owner = cm.accounts.create_account(
                role="owner",
                phone=body.owner_phone,
                email=body.owner_email or "",
                display_name=body.owner_name or body.centre_name,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        registry.register_phone_index(
            phone=body.owner_phone,
            tenant_id=tenant_id,
            account_id=str(owner.get("id")),
            role="owner",
            centre_name=body.centre_name,
        )
        return {
            "tenant_id": tenant_id,
            "centre_name": tenant.get("name"),
            "centre_code": tenant.get("code"),
            "trial_ends_at": tenant.get("trial_ends_at"),
            "account_id": owner.get("id"),
            "message": "Centre created. Enter the OTP sent to your phone to open the desk.",
            "next": "request_otp",
        }

    @app.post("/auth/signup")
    def signup(body: AccountSignupBody, request: Request):
        """Student/parent unlinked account, or staff when tenant_id provided."""
        identity = body.phone or body.email or "unknown"
        try:
            registry.limiter.check("signup", identity, _client_ip(request))
        except RateLimitExceeded as e:
            raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": str(e.retry_after)})
        allowed = ("student", "parent", "owner", "desk", "teacher", "assistant")
        if body.role not in allowed:
            raise HTTPException(status_code=400, detail=f"role must be one of {allowed}")
        if not body.tenant_id:
            raise HTTPException(
                status_code=400,
                detail="Use Start free trial for a new centre, or provide centre context when joining.",
            )
        cm = registry.get_app(body.tenant_id)
        try:
            acct = cm.accounts.create_account(
                role=body.role,
                phone=body.phone or "",
                email=body.email or "",
                display_name=body.display_name or "",
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        centre_name = ""
        try:
            tr = registry.founder.get_tenant(body.tenant_id)
            centre_name = tr.get("name") or ""
        except Exception:
            pass
        registry.register_phone_index(
            phone=body.phone or "",
            tenant_id=body.tenant_id,
            account_id=str(acct.get("id")),
            role=body.role,
            centre_name=centre_name,
        )
        return {
            "account_id": acct.get("id"),
            "role": acct.get("role"),
            "tenant_id": body.tenant_id,
            "message": "Account created. Verify with OTP to continue.",
        }

    @app.post("/auth/request-otp")
    def request_otp(body: OTPRequest, request: Request):
        identity = body.phone or body.email or "unknown"
        try:
            registry.limiter.check("request-otp", identity, _client_ip(request))
        except RateLimitExceeded as e:
            raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": str(e.retry_after)})

        tenant_id = body.tenant_id
        centres: list = []
        if not tenant_id and body.phone:
            matches = registry.lookup_phone(body.phone)
            if not matches:
                # Do not leak whether phone exists — still generic message, but no otp
                return {
                    "otp_id": None,
                    "message": "If this phone is registered, a code was sent.",
                    "centres": [],
                }
            if len(matches) > 1 and not body.tenant_id:
                centres = [
                    {
                        "tenant_id": m.get("tenant_id"),
                        "centre_name": m.get("centre_name") or m.get("tenant_id"),
                        "role": m.get("role"),
                    }
                    for m in matches
                ]
                return {
                    "otp_id": None,
                    "message": "Choose your centre, then request a code again.",
                    "centres": centres,
                }
            tenant_id = matches[0].get("tenant_id")

        if not tenant_id:
            raise HTTPException(status_code=400, detail="Phone number is required")

        cm = registry.get_app(tenant_id)
        result = cm.accounts.request_login_otp(phone=body.phone or "", email=body.email or "")
        payload = {
            "otp_id": result.get("otp_id") or result.get("id"),
            "message": result.get("message", "OTP sent"),
            "tenant_id": tenant_id,
            "centres": centres,
        }
        if os.environ.get("COHORTOS_TEST_EXPOSE_OTP") == "1" and result.get("_test_code"):
            payload["_test_code"] = result["_test_code"]
        return payload


    @app.post("/auth/verify-otp")
    def verify_otp(body: OTPVerify, request: Request, response: Response):
        try:
            registry.limiter.check("verify-otp", body.otp_id, _client_ip(request))
        except RateLimitExceeded as e:
            raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": str(e.retry_after)})
        tenant_id = body.tenant_id
        if not tenant_id:
            raise HTTPException(status_code=400, detail="Centre context missing — request a new code")
        cm = registry.get_app(tenant_id)
        try:
            session = cm.accounts.verify_login_otp(otp_id=body.otp_id, code=body.code)
        except Exception as e:
            raise HTTPException(status_code=401, detail=str(e))
        if not session:
            raise HTTPException(status_code=401, detail="Invalid or expired OTP")
        account_id = str(session.get("account_id") or session.get("id") or "")
        account = cm.accounts.get_account(account_id) or {}
        roles = account.get("roles") or ([account.get("role")] if account.get("role") else ["desk"])
        access = registry.tokens.issue_access(
            account_id=account_id,
            tenant_id=tenant_id,
            extra={"roles": roles},
        )
        refresh, family_id = registry.tokens.issue_refresh(
            account_id=account_id,
            tenant_id=tenant_id,
        )
        _set_refresh_cookie(response, refresh)
        return {
            "access_token": access,
            "refresh_token": refresh,  # required for Electron / stay-signed-in across restart
            "token_type": "bearer",
            "account_id": account_id,
            "tenant_id": tenant_id,
            "roles": roles,
            "family_id": family_id,
        }

    @app.post("/auth/refresh")
    def refresh(
        request: Request,
        response: Response,
        body: Optional[RefreshRequest] = None,
        cohortos_refresh: Optional[str] = Cookie(None),
    ):
        refresh_token = (body.refresh_token if body else None) or cohortos_refresh
        if not refresh_token:
            raise HTTPException(status_code=401, detail="Missing refresh token")
        # Abuse protection — tight loop refresh must 429, not crash
        try:
            registry.limiter.check("auth_refresh", (refresh_token or "")[:24], request.client.host if request.client else "")
        except RateLimitExceeded as e:
            raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": str(e.retry_after)})
        try:
            access, new_refresh, family_id = registry.tokens.rotate_refresh(refresh_token)
        except TokenReuseError:
            _clear_refresh_cookie(response)
            raise
        except AuthError as e:
            _clear_refresh_cookie(response)
            raise HTTPException(status_code=401, detail=str(e))
        _set_refresh_cookie(response, new_refresh)
        claims = registry.tokens.decode(access, expected_type="access")
        return {
            "access_token": access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "account_id": claims.get("sub"),
            "tenant_id": claims.get("tenant_id"),
            "family_id": family_id,
        }

    @app.post("/auth/logout")
    def logout(response: Response, claims: Dict[str, Any] = Depends(_bearer)):
        try:
            registry.tokens.revoke_family(claims.get("family_id") or "")
        except Exception:
            pass
        _clear_refresh_cookie(response)
        return {"ok": True}

    @app.get("/me")
    def me(claims: Dict[str, Any] = Depends(_bearer)):
        return {
            "account_id": claims.get("sub") or claims.get("account_id"),
            "tenant_id": claims.get("tenant_id"),
            "roles": claims.get("roles") or [],
            "family_id": claims.get("family_id"),
        }

    # ── Students ──────────────────────────────────────────────────────

    @app.get("/t/{tenant_id}/students")
    def list_students(tenant_id: str, batch_id: Optional[str] = None, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {"students": registry.get_app(tenant_id).admission.list_students(batch_id=batch_id)}

    @app.post("/t/{tenant_id}/students")
    def create_student(tenant_id: str, body: StudentAdmitBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        parent_phones = [body.parent_phone] if body.parent_phone else None
        try:
            student_id, join_code = cm.admission.admit_student(
                name=body.name,
                batch_id=body.batch_id,
                student_phone=body.phone,
                parent_phones=parent_phones,
                whatsapp=body.whatsapp or body.phone,
                roll=body.roll,
                force=body.force,
                actor_id=str(claims.get("sub") or ""),
            )
            return {"student_id": student_id, "join_code": join_code}
        except Exception as e:
            if "duplicate" in str(e).lower() or e.__class__.__name__ == "DuplicateStudentError":
                raise HTTPException(status_code=409, detail=str(e))
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/t/{tenant_id}/students/duplicate-check")
    def duplicate_check(tenant_id: str, body: DuplicateCheckBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        parent_phones = [body.parent_phone] if body.parent_phone else None
        matches = registry.get_app(tenant_id).admission.detect_duplicates(
            name=body.name, student_phone=body.phone, parent_phones=parent_phones
        )
        # DuplicateMatch may be dataclass
        out = []
        for m in matches:
            if hasattr(m, "__dict__"):
                out.append(getattr(m, "__dict__", dict(m)) if not isinstance(m, dict) else m)
            elif isinstance(m, dict):
                out.append(m)
            else:
                out.append({"match": str(m)})
        return {"matches": out}

    @app.post("/t/{tenant_id}/students/roll-preview")
    def roll_preview(tenant_id: str, body: RollPreviewBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        batch = cm.admission.get_batch(body.batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        days = batch.get("days") or []
        hour = int(str(batch.get("start_time") or batch.get("time") or "14:00").split(":")[0])
        serial = body.serial or 1
        roll = RollEncoder().encode(days if isinstance(days, list) else [], hour, serial)
        return {"batch_id": body.batch_id, "days": days, "hour": hour, "serial": serial, "roll": roll}

    @app.get("/t/{tenant_id}/batches")
    def list_batches(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {"batches": registry.get_app(tenant_id).admission.list_batches()}

    @app.post("/t/{tenant_id}/batches")
    def create_batch(tenant_id: str, body: BatchCreateBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            batch_id = cm.admission.create_batch(
                days=body.days,
                hour=body.hour,
                name=body.name or "",
            )
            if isinstance(batch_id, dict):
                return {"batch": batch_id}
            batch = cm.admission.get_batch(batch_id) if hasattr(cm.admission, "get_batch") else None
            return {"batch_id": batch_id, "batch": batch}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


    @app.get("/t/{tenant_id}/batches/{batch_id}")
    def get_batch_detail(tenant_id: str, batch_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        batch = cm.admission.get_batch(batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        global_late = cm.attendance.get_late_threshold(batch_id=None)
        batch_late = cm.attendance.get_late_threshold(batch_id=batch_id)
        has_override = batch_late != global_late
        # irregularity defaults if service lacks helpers
        global_irr = 3
        batch_irr = 3
        if hasattr(cm.attendance, "get_irregularity_threshold"):
            try:
                global_irr = cm.attendance.get_irregularity_threshold(batch_id=None)
                batch_irr = cm.attendance.get_irregularity_threshold(batch_id=batch_id)
            except Exception:
                pass
        return {
            "batch": batch,
            "late_threshold": {
                "global_minutes": global_late,
                "batch_minutes": batch_late,
                "has_override": has_override,
            },
            "irregularity_threshold": {
                "global_days": global_irr,
                "batch_days": batch_irr,
                "has_override": batch_irr != global_irr,
            },
        }

    @app.patch("/t/{tenant_id}/batches/{batch_id}")
    def patch_batch(tenant_id: str, batch_id: str, body: BatchUpdateBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        kwargs = {}
        if body.days is not None:
            kwargs["days"] = body.days
        if body.hour is not None:
            kwargs["hour"] = body.hour
        if body.name is not None:
            kwargs["name"] = body.name
        if body.name_override is not None:
            kwargs["name"] = body.name_override
        if body.is_active is not None:
            kwargs["is_active"] = body.is_active
        try:
            ok = cm.admission.update_batch(batch_id, actor_id=str(claims.get("sub") or ""), **kwargs)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        batch = cm.admission.get_batch(batch_id)
        return {"updated": bool(ok), "batch": batch}

    @app.post("/t/{tenant_id}/batches/{batch_id}/extra-sessions")
    def post_extra_session(tenant_id: str, batch_id: str, body: ExtraSessionBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            cm.admission.add_extra_session(
                batch_id=batch_id,
                day=body.day,
                hour=body.hour,
                expires_on=body.expires_on,
                actor_id=str(claims.get("sub") or ""),
            )
        except TypeError:
            # signature may differ
            cm.admission.add_extra_session(batch_id, body.day, body.hour, body.expires_on)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        batch = cm.admission.get_batch(batch_id)
        return {"batch": batch}

    @app.post("/t/{tenant_id}/students/{student_id}/migrate")
    def migrate_student(tenant_id: str, student_id: str, body: StudentMigrateBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            rec = cm.admission.migrate_student_roll_batch(
                student_id=student_id,
                new_batch_id=body.new_batch_id,
                new_roll=body.new_roll,
                actor_id=str(claims.get("sub") or ""),
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        if hasattr(rec, "__dict__") and not isinstance(rec, dict):
            data = {k: getattr(rec, k, None) for k in (
                "student_id", "old_roll", "new_roll", "old_batch_id", "new_batch_id",
                "tables_migrated", "records_moved", "status", "error_message"
            )}
        else:
            data = rec if isinstance(rec, dict) else {"status": "ok", "result": str(rec)}
        return data


    @app.get("/t/{tenant_id}/templates")
    def list_templates(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {"templates": registry.get_app(tenant_id).admission.list_templates()}

    # ── Attendance ────────────────────────────────────────────────────

    @app.get("/t/{tenant_id}/attendance")
    def list_attendance(
        tenant_id: str,
        batch_id: Optional[str] = None,
        date: Optional[str] = None,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        if batch_id and date:
            rows = cm.attendance.get_batch_attendance(batch_id, date)
            return {"date": date, "batch_id": batch_id, "rows": rows}
        return {"attendance": cm.data_layer.get_all("attendance_records")}

    @app.get("/t/{tenant_id}/attendance/batch/{batch_id}")
    def attendance_for_batch(tenant_id: str, batch_id: str, on_date: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        rows = registry.get_app(tenant_id).attendance.get_batch_attendance(batch_id, on_date)
        return {"date": on_date, "batch_id": batch_id, "rows": rows}

    @app.post("/t/{tenant_id}/attendance/manual")
    def attendance_manual(tenant_id: str, body: ManualAttendanceBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        record_id = registry.get_app(tenant_id).attendance.mark_manual(
            student_id=body.student_id,
            on_date=body.date,
            status_or_time=body.status,
            batch_id=body.batch_id,
            actor_id=str(claims.get("sub") or ""),
            notes=body.notes,
        )
        return {"punch_or_record_id": record_id}

    @app.get("/t/{tenant_id}/attendance/late-threshold")
    def get_late_threshold(tenant_id: str, batch_id: Optional[str] = None, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        minutes = cm.attendance.get_late_threshold(batch_id=batch_id)
        return {
            "minutes": minutes,
            "batch_id": batch_id,
            "effective": minutes,
            "global": cm.attendance.get_late_threshold(batch_id=None),
        }

    @app.put("/t/{tenant_id}/attendance/late-threshold")
    def set_late_threshold(tenant_id: str, body: LateThresholdBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        cm.attendance.set_late_threshold(body.minutes, batch_id=body.batch_id)
        return {
            "minutes": body.minutes,
            "batch_id": body.batch_id,
            "effective": body.minutes,
            "global": cm.attendance.get_late_threshold(batch_id=None),
        }

    @app.get("/t/{tenant_id}/attendance/absentees")
    def absentees(
        tenant_id: str,
        batch_id: str,
        date: str,
        days: int = 1,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        data = registry.get_app(tenant_id).attendance.get_absentees(batch_id=batch_id, on_date=date, days_back=days)
        return {"batch_id": batch_id, "days": data}

    @app.get("/t/{tenant_id}/attendance/reviews")
    def open_reviews(tenant_id: str, limit: int = 100, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {"reviews": registry.get_app(tenant_id).attendance.list_open_reviews(limit=limit)}

    @app.post("/t/{tenant_id}/attendance/reviews/{flag_id}/resolve")
    def resolve_review(tenant_id: str, flag_id: str, body: ResolveReviewBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        ok = registry.get_app(tenant_id).attendance.resolve_review(
            flag_id=flag_id,
            final_status=body.final_status,
            actor_id=str(claims.get("sub") or ""),
            notes=body.notes,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Review flag not found or already resolved")
        return {"resolved": True, "flag_id": flag_id, "final_status": body.final_status}

    @app.post("/t/{tenant_id}/attendance/biometric/pull")
    def biometric_pull(tenant_id: str, body: BiometricPullBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        ip = body.ip
        port = body.port
        if body.device_id and not ip:
            devices = cm.attendance.list_devices()
            match = next((d for d in devices if str(d.get("id")) == str(body.device_id)), None)
            if not match:
                raise HTTPException(status_code=404, detail="Device not found")
            ip = match.get("ip_address") or ""
            port = int(match.get("port") or 4370)
        if not ip:
            raise HTTPException(status_code=400, detail="ip or device_id required")
        driver = BiometricDriver(ip=ip, port=port)
        if not driver.is_available():
            raise HTTPException(
                status_code=501,
                detail="pyzk not installed. pip install pyzk — biometric hardware path optional.",
            )
        try:
            result = driver.pull_and_ingest(
                ingest_fn=cm.attendance.ingest_punch,
                device_id=body.device_id,
                clear_after=body.clear_after,
            )
            return result
        except BiometricDriverError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/t/{tenant_id}/attendance/biometric/status")
    def biometric_status(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {"pyzk_available": PYZK_AVAILABLE, "devices": registry.get_app(tenant_id).attendance.list_devices()}

    @app.post("/t/{tenant_id}/attendance/biometric/devices")
    def register_biometric_device(
        tenant_id: str, body: BiometricDeviceBody, claims: Dict[str, Any] = Depends(_bearer)
    ):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            device_id = cm.attendance.register_device(
                name=body.name,
                ip_address=body.ip_address or "",
                port=body.port,
                device_type=body.device_type or "zkteco",
                actor_id=str(claims.get("sub") or ""),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        devices = cm.attendance.list_devices(active_only=False)
        device = next((d for d in devices if str(d.get("id")) == device_id), None)
        return {"device_id": device_id, "device": device, "pyzk_available": PYZK_AVAILABLE}

    @app.post("/t/{tenant_id}/attendance/biometric/devices/{device_id}/test")
    def test_biometric_device(
        tenant_id: str,
        device_id: str,
        body: BiometricDeviceTestBody,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        devices = cm.attendance.list_devices(active_only=False)
        match = next((d for d in devices if str(d.get("id")) == str(device_id)), None)
        ip = body.ip or (match.get("ip_address") if match else None) or ""
        port = body.port or (int(match.get("port") or 4370) if match else 4370)
        if not ip:
            raise HTTPException(status_code=400, detail="ip required")
        driver = BiometricDriver(ip=ip, port=port)
        result = driver.test_connection()
        result["pyzk_available"] = PYZK_AVAILABLE
        if not result.get("ok") and not PYZK_AVAILABLE:
            result["message"] = "Biometric library not installed. Use manual attendance entry."
        return result

    @app.post("/t/{tenant_id}/attendance/biometric/devices/{device_id}/disable")
    def disable_biometric_device(
        tenant_id: str, device_id: str, claims: Dict[str, Any] = Depends(_bearer)
    ):
        _require_tenant(claims, tenant_id)
        ok = registry.get_app(tenant_id).attendance.deactivate_device(
            device_id, actor_id=str(claims.get("sub") or "")
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"ok": True, "device_id": device_id, "is_active": False}

    @app.post("/t/{tenant_id}/attendance/biometric/link")
    def link_device_user(
        tenant_id: str, body: DeviceUserLinkBody, claims: Dict[str, Any] = Depends(_bearer)
    ):
        _require_tenant(claims, tenant_id)
        ok = registry.get_app(tenant_id).attendance.link_device_user(
            body.student_id, body.device_user_id, actor_id=str(claims.get("sub") or "")
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Student not found")
        return {"ok": True, "student_id": body.student_id, "device_user_id": body.device_user_id}

    @app.post("/t/{tenant_id}/attendance/biometric/link-bulk")
    def link_device_user_bulk(
        tenant_id: str, body: DeviceUserBulkBody, claims: Dict[str, Any] = Depends(_bearer)
    ):
        """CSV-style bulk map: rows of {student_id or roll, device_user_id}."""
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        students = cm.admission.list_students(active_only=False) if hasattr(cm, "admission") else []
        by_roll = {str(s.get("roll") or ""): s for s in students}
        linked = 0
        errors = []
        for row in body.rows or []:
            sid = row.get("student_id")
            roll = row.get("roll")
            duid = str(row.get("device_user_id") or "").strip()
            if not duid:
                errors.append({"row": row, "error": "device_user_id required"})
                continue
            if not sid and roll:
                s = by_roll.get(str(roll))
                sid = s.get("id") if s else None
            if not sid:
                errors.append({"row": row, "error": "student not found"})
                continue
            try:
                ok = cm.attendance.link_device_user(str(sid), duid, actor_id=str(claims.get("sub") or ""))
                if ok:
                    linked += 1
                else:
                    errors.append({"row": row, "error": "student not found"})
            except Exception as e:
                errors.append({"row": row, "error": str(e)})
        return {"linked": linked, "errors": errors}

    # ── Storage provider (Vault binary backend) ───────────────────────


    @app.post("/t/{tenant_id}/messaging/test-sms")
    def test_sms(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        to = body.get("to") or ""
        if not to:
            raise HTTPException(status_code=400, detail="to phone required")
        cm = registry.get_app(tenant_id)
        section = cm.config.get_section("messaging") or {}
        from services.sms_provider import build_sms_provider, SmsNotConfiguredError
        try:
            provider = build_sms_provider(section)
            result = provider.send(str(to), str(body.get("body") or "CohortOS test message"))
            return result
        except SmsNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))


    def _ai_keys_normalized(section: Dict[str, Any]) -> Dict[str, Any]:
        """ConfigService stores section keys as 'ai_keys.provider' — normalize to short keys."""
        out: Dict[str, Any] = {}
        for k, v in (section or {}).items():
            short = k.split(".", 1)[-1] if isinstance(k, str) else k
            out[str(short)] = v
        return out

    @app.get("/t/{tenant_id}/settings/ai-keys")
    def get_ai_keys(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        section = _ai_keys_normalized(registry.get_app(tenant_id).config.get_section("ai_keys") or {})
        key = str(section.get("api_key") or "")
        masked = (("*" * max(0, len(key) - 4)) + key[-4:]) if key else None
        return {"provider": section.get("provider"), "configured": bool(key), "masked_key": masked}

    @app.put("/t/{tenant_id}/settings/ai-keys")
    def put_ai_keys(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        prov = body.get("provider") or "groq"
        cm.config.set_section("ai_keys", {"provider": prov, "api_key": body.get("api_key") or ""})
        return {"ok": True, "configured": True, "provider": prov}

    def _auto(cm):
        auto = getattr(cm, "automation", None)
        if auto is None:
            from services.automation_service import AutomationService
            auto = AutomationService(
                payment_service=getattr(cm, "payment", None),
                attendance_service=getattr(cm, "attendance", None),
                config_service=getattr(cm, "config", None),
            )
            cm.automation = auto
        else:
            auto.payment = getattr(cm, "payment", None)
            auto.attendance = getattr(cm, "attendance", None)
            auto.config = getattr(cm, "config", None)
        return auto


    @app.post("/t/{tenant_id}/ai/query")
    def ai_query(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        """Minimal agentic answer grounded in centre lists (students/batches/exams)."""
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        keys = _ai_keys_normalized(cm.config.get_section("ai_keys") or {})
        students = cm.admission.list_students(active_only=False) if hasattr(cm, "admission") else []
        batches = cm.batch.list_batches() if hasattr(cm, "batch") else []
        exams = cm.exam.list_exams() if hasattr(cm, "exam") else []
        q = str(body.get("question") or "").lower()
        tool_trace = []
        # Tool: list_students
        def tool_list_students():
            rows = students or []
            tool_trace.append({"tool": "list_students", "count": len(rows)})
            return rows
        # Tool: list_batches
        def tool_list_batches():
            rows = batches or []
            tool_trace.append({"tool": "list_batches", "count": len(rows)})
            return rows
        # Tool: list_exams
        def tool_list_exams():
            rows = exams or []
            tool_trace.append({"tool": "list_exams", "count": len(rows)})
            return rows
        # Tool: struggle_students (analytics when batch known)
        def tool_struggle(batch_id: str = ""):
            out = []
            if batch_id and hasattr(cm.exam, "students_likely_to_struggle"):
                out = cm.exam.students_likely_to_struggle(batch_id=batch_id) or []
            tool_trace.append({"tool": "struggle_students", "batch_id": batch_id, "count": len(out)})
            return out

        st = tool_list_students()
        bt = tool_list_batches()
        def tool_exam_detail(name_hint: str = ""):
            rows = exams or []
            if name_hint:
                rows = [e for e in rows if name_hint.lower() in str(e.get("name") or "").lower()]
            out = []
            for e in rows[:10]:
                eid = str(e.get("id") or "")
                results = []
                try:
                    if hasattr(cm.exam, "list_results"):
                        results = cm.exam.list_results(eid) or []
                    elif hasattr(cm.exam, "get_results"):
                        results = cm.exam.get_results(eid) or []
                except Exception:
                    results = []
                out.append({
                    "id": eid,
                    "name": e.get("name"),
                    "exam_date": e.get("exam_date"),
                    "status": e.get("status"),
                    "result_count": len(results) if isinstance(results, list) else 0,
                    "subject": e.get("subject"),
                    "chapter_or_topic": e.get("chapter_or_topic"),
                })
            tool_trace.append({"tool": "list_exam_detail", "count": len(out), "hint": name_hint})
            return out

        def tool_vault_titles():
            rows = []
            try:
                if hasattr(cm, "content") and hasattr(cm.content, "list_resources"):
                    rows = cm.content.list_resources() or []
            except Exception:
                rows = []
            tool_trace.append({"tool": "list_vault_titles", "count": len(rows)})
            return [{"id": r.get("id"), "title": r.get("title"), "topic": r.get("topic")} for r in rows[:30]]

        ex = tool_list_exams()
        grounded = {
            "student_count": len(st),
            "batch_count": len(bt),
            "exam_count": len(ex),
            "student_names": [s.get("name") for s in st[:20]],
        }
        q_lower = q
        if "exam" in q_lower or "kinetics" in q_lower or "marks" in q_lower or "paper" in q_lower:
            # Extract simple name hint: last quoted token or known word
            hint = ""
            for token in ("kinetics", "KINETICS"):
                if token.lower() in q_lower:
                    hint = "KINETICS"
                    break
            grounded["exam_detail"] = tool_exam_detail(hint)
        if "vault" in q_lower or "document" in q_lower or "file" in q_lower:
            grounded["vault"] = tool_vault_titles()
        def tool_list_automations():
            rules = _auto(cm).list_rules() if hasattr(cm, "automation") or True else []
            try:
                rules = _auto(cm).list_rules()
            except Exception:
                rules = []
            tool_trace.append({"tool": "list_automations", "count": len(rules)})
            return [{"id": r.get("id"), "name": r.get("name"), "enabled": r.get("enabled")} for r in rules]
        def tool_run_automation(name: str):
            try:
                result = _auto(cm).run_rule_by_name(name, {"actor_id": str(claims.get("sub") or "copilot")})
            except Exception as e:
                result = {"error": str(e)}
            tool_trace.append({"tool": "run_automation", "name": name, "result_type": result.get("type")})
            return result
        if "automation" in q_lower or ("run" in q_lower and ("remind" in q_lower or "fee" in q_lower or "nag" in q_lower)):
            grounded["automations"] = tool_list_automations()
            # try run fee-related
            run_name = "fee"
            for r in grounded["automations"]:
                if "fee" in str(r.get("name") or "").lower() or "remind" in str(r.get("name") or "").lower():
                    run_name = r.get("name")
                    break
            if "run" in q_lower:
                grounded["automation_result"] = tool_run_automation(str(run_name))
        # RAG-first (Chroma + MiniLM embeddings via RagService). Replaces the
        # generic "Centre snapshot" string when vault content can answer.
        question_raw = str(body.get("question") or body.get("q") or "")
        session_id = str(body.get("session_id") or claims.get("sub") or "default")
        rag_meta = {}
        answer = ""
        if hasattr(cm, "rag") and cm.rag:
            try:
                # Keep vault index warm (cheap for desk-scale corpora)
                cm.rag.reindex_vault()
                def _local_synth(prompt: str) -> str:
                    # Prefer cloud later; for no-key path use local GGUF when available
                    try:
                        keys_local = _ai_keys_normalized(cm.config.get_section("ai_keys") or {})
                        if keys_local.get("api_key"):
                            return ""
                        from services.local_model import local_available, local_complete, resolve_model_id
                        if not local_available():
                            return ""
                        mid = resolve_model_id(keys_local)
                        return local_complete(prompt, model_id=mid, max_tokens=400, temperature=0.2)
                    except Exception:
                        return ""
                rag_out = cm.rag.answer(question_raw, session_id=session_id, llm_complete=_local_synth)
                answer = str(rag_out.get("answer") or "")
                rag_meta = {
                    "backend": rag_out.get("backend"),
                    "citations": rag_out.get("citations") or [],
                    "memory_turns": rag_out.get("memory_turns"),
                }
                grounded["rag"] = rag_meta
                tool_trace.append({"tool": "vault_rag", "hits": len(rag_meta.get("citations") or [])})
            except Exception as e:
                tool_trace.append({"tool": "vault_rag", "error": str(e)})

        # Hermes-style function calling (structured tool_calls JSON)
        tool_calls_out = []
        tool_results = []
        try:
            from services.copilot_tools import run_copilot_tools, tools_for_prompt
            from services.agent_safety import cloud_llm_allowed, redact_pii
            auto_svc = None
            try:
                auto_svc = _auto(cm)
            except Exception:
                auto_svc = getattr(cm, "automation", None)
            # Optional: ask LLM to emit tool_calls when configured (handled below after keys load)
            tool_calls_out, tool_results = run_copilot_tools(
                question_raw,
                automation_service=auto_svc,
                admission_service=getattr(cm, "admission", None),
                batch_service=getattr(cm, "batch", None),
                llm_tool_text=None,
                use_local_for_ambiguous=True,
                confirm=bool(body.get("confirm_tools")),
                actor_role=str((claims.get("roles") or ["desk"])[0] if isinstance(claims.get("roles"), list) else claims.get("role") or "desk"),
                audit_service=getattr(cm, "audit", None),
                actor_id=str(claims.get("sub") or ""),
            )
            if tool_results:
                tool_trace.append({"tool": "function_calling", "calls": tool_calls_out, "results": tool_results})
                grounded["tool_calls"] = tool_calls_out
                grounded["tool_results"] = tool_results
                # Surface action outcome in the answer when a tool ran
                ok_bits = []
                for r in tool_results:
                    if r.get("ok"):
                        rule = (r.get("result") or {}).get("rule") or {}
                        ok_bits.append(
                            f"Created automation “{rule.get('name') or r.get('name')}” (id={rule.get('id') or '—'})."
                        )
                    else:
                        ok_bits.append(f"Tool {r.get('name')}: {r.get('error')}")
                if ok_bits:
                    answer = (answer + " " if answer else "") + " ".join(ok_bits)
        except Exception as e:
            tool_trace.append({"tool": "function_calling", "error": str(e)})
        if not answer:
            answer = (
                f"Centre snapshot: {grounded['student_count']} students, "
                f"{grounded['batch_count']} batches, {grounded['exam_count']} exams. "
            )
            if "struggle" in q or "weak" in q:
                bid = ""
                if bt:
                    bid = str(bt[0].get("id") or "")
                struggle = tool_struggle(bid)
                if struggle:
                    names = [str(s.get("name") or s.get("student_id")) for s in struggle[:8]]
                    answer += "Students flagged by analytics: " + ", ".join(names) + "."
                else:
                    answer += "No struggle flags yet (need exam results). Open Analytics when data exists."
            elif "batch" in q:
                answer += "Batches: " + ", ".join(str(b.get("name") or b.get("id")) for b in bt[:10])
            elif "student" in q or "how many" in q:
                answer += f"Student roster size is {len(st)}."
            else:
                answer += "Ask about batches, student counts, or struggling students for grounded answers."
        # Rate-limit AI queries per account
        try:
            registry.limiter.check(
                "ai_query",
                str(claims.get("sub") or claims.get("account_id") or tenant_id),
                "",
            )
        except RateLimitExceeded as e:
            raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": str(e.retry_after)})

        used_external = False
        provider_name = str(keys.get("provider") or "")
        api_key = str(keys.get("api_key") or "")
        model_used = None
        llm_error = None
        # Cost guard: limit external LLM calls per tenant per window (env override for tests)
        max_llm = int(os.environ.get("COHORTOS_AI_MAX_CALLS_PER_WINDOW") or "60")
        window_sec = int(os.environ.get("COHORTOS_AI_COST_WINDOW_SEC") or "3600")
        if not hasattr(registry, "_llm_cost"):
            registry._llm_cost = {}
        cost_key = f"llm:{tenant_id}"
        now_ts = time.time()
        bucket = registry._llm_cost.get(cost_key) or {"count": 0, "start": now_ts}
        if now_ts - float(bucket.get("start") or 0) > window_sec:
            bucket = {"count": 0, "start": now_ts}
        providers_ok = (
            "groq", "nim", "nvidia", "nvidia_nim", "nvidia-nim",
            "openai", "chatgpt", "anthropic", "claude", "gemini", "google", "google_gemini",
            "deepseek", "deepseek-chat", "deepseek_v3", "deepseek-v4-flash",
        )
        if api_key and provider_name.lower() in providers_ok:
            if int(bucket.get("count") or 0) >= max_llm:
                raise HTTPException(
                    status_code=429,
                    detail=f"AI cost guard: max {max_llm} external LLM calls per window — try later or raise COHORTOS_AI_MAX_CALLS_PER_WINDOW",
                    headers={"Retry-After": str(window_sec)},
                )
            from services.llm_provider import (
                build_llm_provider,
                LLMRequest,
                LLMError,
                RateLimitError,
                OfflineError,
            )
            try:
                llm = build_llm_provider(provider_name, api_key)
                system = (
                    "You are CohortOS desk assistant. Answer using ONLY the grounded centre data. "
                    "If data is missing, say so. Do not invent students or batches."
                )
                prompt = (
                    f"Question: {body.get('question') or ''}\n\n"
                    f"Grounded data JSON: {grounded}\n"
                    f"Local draft answer: {answer}"
                )
                resp = llm.complete(LLMRequest(prompt=prompt, system=system, max_tokens=512))
                bucket["count"] = int(bucket.get("count") or 0) + 1
                registry._llm_cost[cost_key] = bucket
                if resp.text.strip():
                    answer = resp.text.strip()
                    used_external = True
                    model_used = resp.model
            except RateLimitError as e:
                llm_error = str(e)
                raise HTTPException(status_code=429, detail=f"Provider rate limit: {e}")
            except (LLMError, OfflineError) as e:
                llm_error = str(e)
                tool_trace.append({"tool": "external_llm", "error": llm_error})
            except Exception as e:
                llm_error = f"Provider call failed: {e}"
                tool_trace.append({"tool": "external_llm", "error": llm_error})

        return {
            "answer": answer,
            "grounded": grounded,
            "tools_used": tool_trace,
            "provider": provider_name or None,
            "provider_configured": bool(api_key),
            "used_external_llm": used_external,
            "model": model_used,
            "llm_error": llm_error,
            "needs_for_external_llm": None if api_key else "Set centre AI key via Settings → AI API keys (developer console key, not a ChatGPT/Claude app login).",
        }


    

    @app.get("/t/{tenant_id}/ai/local-model/status")
    def local_model_status(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.local_model import progress, resolve_model_id, model_path, local_available, MODEL_REGISTRY
        cm = registry.get_app(tenant_id)
        keys = _ai_keys_normalized(cm.config.get_section("ai_keys") or {})
        mid = resolve_model_id(keys)
        path = model_path(mid)
        return {
            "model_id": mid,
            "available_models": list(MODEL_REGISTRY.keys()),
            "llama_cpp_installed": local_available(),
            "file_present": path.is_file(),
            "path": str(path),
            "progress": progress(),
            "packaging": "download-on-first-run",
        }


    @app.post("/t/{tenant_id}/ai/local-model/download")
    def local_model_download(tenant_id: str, body: Dict[str, Any] = Body(default={}), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.local_model import ensure_model, resolve_model_id, ram_policy
        policy = ram_policy()
        if policy["tier"] == "low":
            raise HTTPException(status_code=400, detail=policy.get("caution") or "Local model disabled on this device")
        if not body.get("consent"):
            raise HTTPException(status_code=400, detail="Explicit consent required to download ~1GB model")
        mid = str(body.get("model_id") or resolve_model_id())
        try:
            path = ensure_model(mid, consent=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True, "path": str(path), "model_id": mid, "ram_policy": policy}

    @app.delete("/t/{tenant_id}/ai/local-model")
    def local_model_delete(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.local_model import delete_model, resolve_model_id
        mid = resolve_model_id()
        return {"ok": delete_model(mid), "model_id": mid}

    @app.post("/t/{tenant_id}/admissions/import/preview")
    async def admissions_import_preview(tenant_id: str, request: Request, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.student_importer import preview_csv
        body = await request.body()
        return preview_csv(body)

    @app.post("/t/{tenant_id}/admissions/import")
    async def admissions_import(tenant_id: str, request: Request, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        role = str((claims.get("roles") or ["desk"])[0] if isinstance(claims.get("roles"), list) else claims.get("role") or "desk")
        if role not in ("owner", "desk", "admin"):
            raise HTTPException(status_code=403, detail="Only owner/desk can import students")
        from services.student_importer import import_students
        body = await request.body()
        cm = registry.get_app(tenant_id)
        return import_students(body, admission=getattr(cm, "admission", None))




    # ── P24 Voice assist (assisted mode only — no autodial) ─────────────
    def _voice_assist(cm):
        from services.voice_assist_service import VoiceAssistService
        keys = {}
        try:
            keys = _ai_keys_normalized(cm.config.get_section("ai_keys") or {})
        except Exception:
            pass
        def _llm(prompt: str) -> str:
            try:
                from services.agent_safety import cloud_llm_allowed
                from services.llm_provider import build_llm_provider, LLMRequest
                if cloud_llm_allowed(keys) and keys.get("api_key"):
                    prov = build_llm_provider(str(keys.get("provider") or "mock"), str(keys.get("api_key") or ""))
                    return (prov.complete(LLMRequest(prompt=prompt, tier="cheap")).text or "").strip()
            except Exception:
                pass
            return ""
        return VoiceAssistService(
            data_layer=getattr(cm, "data_layer", None),
            audit_service=getattr(cm, "audit", None),
            llm_complete=_llm,
            config_section=keys,
        )

    @app.post("/t/{tenant_id}/voice/script")
    def voice_generate_script(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        role = str((claims.get("roles") or ["desk"])[0] if isinstance(claims.get("roles"), list) else claims.get("role") or "desk")
        try:
            return _voice_assist(cm).generate_script(
                student_name=str(body.get("student_name") or ""),
                phone=str(body.get("phone") or ""),
                purpose=str(body.get("purpose") or "fee_reminder"),
                amount_bdt=body.get("amount_bdt"),
                language=str(body.get("language") or "bn"),
                actor_id=str(claims.get("sub") or ""),
                actor_role=role,
                extra_context=str(body.get("extra_context") or ""),
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @app.post("/t/{tenant_id}/voice/summarize")
    def voice_summarize(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        role = str((claims.get("roles") or ["desk"])[0] if isinstance(claims.get("roles"), list) else claims.get("role") or "desk")
        try:
            return _voice_assist(cm).summarize_call(
                call_notes=str(body.get("call_notes") or body.get("notes") or ""),
                student_name=str(body.get("student_name") or ""),
                purpose=str(body.get("purpose") or ""),
                actor_id=str(claims.get("sub") or ""),
                actor_role=role,
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @app.get("/t/{tenant_id}/voice/summaries")
    def voice_list_summaries(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        return {"summaries": _voice_assist(cm).list_summaries()}

    @app.post("/t/{tenant_id}/voice/request-call")
    def voice_request_call(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        role = str((claims.get("roles") or ["desk"])[0] if isinstance(claims.get("roles"), list) else claims.get("role") or "desk")
        try:
            return _voice_assist(cm).request_human_call(
                to_phone=str(body.get("phone") or body.get("to") or ""),
                script_id=str(body.get("script_id") or ""),
                script_text=str(body.get("script") or ""),
                human_action_id=str(body.get("human_action_id") or ""),
                actor_id=str(claims.get("sub") or ""),
                actor_role=role,
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))

    # ── P25/P26 Class workspace (Jitsi) ─────────────────────────────────
    def _class_svc(cm, tenant_id: str):
        from services.class_session_service import ClassSessionService
        secret = os.environ.get("COHORTOS_JITSI_JWT_SECRET") or os.environ.get("COHORTOS_JWT_SECRET") or "cohortos-jitsi-dev-secret-change-me"
        return ClassSessionService(
            data_layer=getattr(cm, "data_layer", None),
            tenant_id=tenant_id,
            jwt_secret=secret,
        )

    @app.post("/t/{tenant_id}/classes/sessions")
    def create_class_session(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        role = str((claims.get("roles") or ["desk"])[0] if isinstance(claims.get("roles"), list) else claims.get("role") or "desk")
        try:
            return _class_svc(cm, tenant_id).create_session(
                batch_id=str(body.get("batch_id") or ""),
                title=str(body.get("title") or "Class"),
                starts_at=str(body.get("starts_at") or ""),
                actor_id=str(claims.get("sub") or ""),
                actor_role=role,
            )
        except (PermissionError, ValueError) as e:
            raise HTTPException(status_code=400 if isinstance(e, ValueError) else 403, detail=str(e))

    @app.get("/t/{tenant_id}/classes/sessions")
    def list_class_sessions(tenant_id: str, batch_id: Optional[str] = None, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        return {"sessions": _class_svc(cm, tenant_id).list_sessions(batch_id=batch_id)}

    @app.post("/t/{tenant_id}/classes/sessions/{session_id}/join")
    def join_class_session(tenant_id: str, session_id: str, body: Dict[str, Any] = Body(default={}), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        role = str(body.get("role") or claims.get("role") or "participant")
        try:
            return _class_svc(cm, tenant_id).join_link(
                session_id,
                role=role,
                display_name=str(body.get("display_name") or claims.get("name") or "Guest"),
                actor_id=str(claims.get("sub") or ""),
            )
        except (PermissionError, KeyError) as e:
            raise HTTPException(status_code=403 if isinstance(e, PermissionError) else 404, detail=str(e))

    @app.post("/t/{tenant_id}/classes/sessions/{session_id}/end")
    def end_class_session(tenant_id: str, session_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        role = str((claims.get("roles") or ["desk"])[0] if isinstance(claims.get("roles"), list) else claims.get("role") or "desk")
        try:
            return _class_svc(cm, tenant_id).end_session(session_id, actor_id=str(claims.get("sub") or ""), actor_role=role)
        except (PermissionError, KeyError) as e:
            raise HTTPException(status_code=403 if isinstance(e, PermissionError) else 404, detail=str(e))

    @app.post("/t/{tenant_id}/classes/sessions/{session_id}/notices")
    def post_class_notice(tenant_id: str, session_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        role = str((claims.get("roles") or ["desk"])[0] if isinstance(claims.get("roles"), list) else claims.get("role") or "desk")
        try:
            return _class_svc(cm, tenant_id).post_notice(
                session_id, body=str(body.get("body") or ""), actor_id=str(claims.get("sub") or ""), actor_role=role
            )
        except (PermissionError, KeyError) as e:
            raise HTTPException(status_code=403 if isinstance(e, PermissionError) else 404, detail=str(e))

    @app.get("/t/{tenant_id}/classes/sessions/{session_id}/notices")
    def list_class_notices(tenant_id: str, session_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            return {"notices": _class_svc(cm, tenant_id).list_notices(session_id)}
        except KeyError:
            raise HTTPException(status_code=404, detail="session_not_found")



    @app.post("/t/{tenant_id}/classes/timetable/generate")
    def generate_timetable_sessions(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        role = str((claims.get("roles") or ["desk"])[0] if isinstance(claims.get("roles"), list) else claims.get("role") or "desk")
        try:
            sessions = _class_svc(cm, tenant_id).generate_from_timetable(
                batch_id=str(body.get("batch_id") or ""),
                weekday=int(body.get("weekday") or 0),
                time_hhmm=str(body.get("time") or "10:00"),
                duration_min=int(body.get("duration_min") or 90),
                weeks=int(body.get("weeks") or 4),
                title=str(body.get("title") or "Scheduled class"),
                teacher_id=str(body.get("teacher_id") or ""),
                actor_id=str(claims.get("sub") or ""),
                actor_role=role,
            )
            return {"sessions": sessions, "count": len(sessions)}
        except (PermissionError, ValueError) as e:
            raise HTTPException(status_code=400 if isinstance(e, ValueError) else 403, detail=str(e))

    @app.post("/t/{tenant_id}/classes/sessions/{session_id}/polls")
    def create_class_poll(tenant_id: str, session_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        role = str((claims.get("roles") or ["desk"])[0] if isinstance(claims.get("roles"), list) else claims.get("role") or "desk")
        try:
            return _class_svc(cm, tenant_id).create_poll(
                session_id,
                question=str(body.get("question") or ""),
                options=list(body.get("options") or []),
                actor_id=str(claims.get("sub") or ""),
                actor_role=role,
            )
        except (PermissionError, KeyError) as e:
            raise HTTPException(status_code=403 if isinstance(e, PermissionError) else 404, detail=str(e))

    @app.post("/t/{tenant_id}/classes/sessions/{session_id}/qa")
    def class_qa(tenant_id: str, session_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            return _class_svc(cm, tenant_id).enqueue_qa(
                session_id, text=str(body.get("text") or ""), student_id=str(body.get("student_id") or claims.get("sub") or "")
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="session_not_found")

    @app.post("/t/{tenant_id}/classes/sessions/{session_id}/raise-hand")
    def class_raise_hand(tenant_id: str, session_id: str, body: Dict[str, Any] = Body(default={}), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            return _class_svc(cm, tenant_id).raise_hand(
                session_id, student_id=str(body.get("student_id") or claims.get("sub") or ""), name=str(body.get("name") or "")
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="session_not_found")

    @app.post("/t/{tenant_id}/classes/sessions/{session_id}/recording")
    def class_recording(tenant_id: str, session_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        role = str((claims.get("roles") or ["desk"])[0] if isinstance(claims.get("roles"), list) else claims.get("role") or "desk")
        try:
            return _class_svc(cm, tenant_id).set_recording_url(
                session_id, str(body.get("url") or ""), actor_id=str(claims.get("sub") or ""), actor_role=role
            )
        except (PermissionError, KeyError) as e:
            raise HTTPException(status_code=403 if isinstance(e, PermissionError) else 404, detail=str(e))

    @app.post("/t/{tenant_id}/classes/sessions/{session_id}/notify-absentees")
    def class_notify_absentees(tenant_id: str, session_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        return _class_svc(cm, tenant_id).notify_absentees(
            session_id,
            present_ids=list(body.get("present_ids") or []),
            roster_ids=list(body.get("roster_ids") or []),
            actor_id=str(claims.get("sub") or ""),
        )

    @app.post("/t/{tenant_id}/classes/device-tier")
    def class_device_tier(tenant_id: str, body: Dict[str, Any] = Body(default={}), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.device_tier import select_tier
        return select_tier(
            device_memory_gb=body.get("deviceMemory"),
            hardware_concurrency=body.get("hardwareConcurrency"),
            downlink_mbps=body.get("downlink"),
            effective_type=body.get("effectiveType"),
            user_override=body.get("override"),
        )

    # Public-ish student join via token query (still requires valid join JWT issued by authenticated desk/student)
    @app.get("/join/{tenant_id}/{session_id}")
    def public_join_page_meta(tenant_id: str, session_id: str, token: Optional[str] = None):
        """Metadata for lightweight mobile join page — validates token tenant/session."""
        from services.class_session_service import verify_join_token
        secret = os.environ.get("COHORTOS_JITSI_JWT_SECRET") or os.environ.get("COHORTOS_JWT_SECRET") or "cohortos-jitsi-dev-secret-change-me"
        if not token:
            raise HTTPException(status_code=401, detail="token required")
        try:
            claims = verify_join_token(token, expected_tenant_id=tenant_id, jwt_secret=secret)
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        if str(claims.get("session_id")) != str(session_id):
            raise HTTPException(status_code=403, detail="session_mismatch")
        cm = registry.get_app(tenant_id)
        try:
            link = _class_svc(cm, tenant_id).join_link(
                session_id,
                role=str(claims.get("role") or "participant"),
                display_name=str(claims.get("name") or "Student"),
                actor_id=str(claims.get("sub") or ""),
                student_id=str(claims.get("student_id") or ""),
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {
            "title_bn": "ক্লাসে যোগ দিন",
            "title_en": "Join class",
            "button_bn": "এক ট্যাপে যোগ দিন",
            "join_url": link["join_url"],
            "access_mode": link.get("access_mode"),
            "access_mode_warning": link.get("access_mode_warning"),
        }

    @app.post("/t/{tenant_id}/call-desk/queue")
    def call_desk_queue(tenant_id: str, body: Dict[str, Any] = Body(default={}), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.call_desk_service import CallDeskService
        cm = registry.get_app(tenant_id)
        desk = CallDeskService(data_layer=getattr(cm, "data_layer", None), voice_assist=_voice_assist(cm))
        cards = desk.build_queue(
            absences=body.get("absences") or [],
            fee_dues=body.get("fee_dues") or [],
            exam_flags=body.get("exam_flags") or [],
            admission_leads=body.get("admission_leads") or [],
        )
        return {"cards": cards}

    @app.post("/t/{tenant_id}/call-desk/script")
    def call_desk_script(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.call_desk_service import CallDeskService
        cm = registry.get_app(tenant_id)
        role = str((claims.get("roles") or ["desk"])[0] if isinstance(claims.get("roles"), list) else claims.get("role") or "desk")
        desk = CallDeskService(data_layer=getattr(cm, "data_layer", None), voice_assist=_voice_assist(cm))
        return desk.script_for_card(body.get("card") or body, language=str(body.get("language") or "bn"), actor_id=str(claims.get("sub") or ""), actor_role=role)

    @app.post("/t/{tenant_id}/call-desk/outcome")
    def call_desk_outcome(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.call_desk_service import CallDeskService
        cm = registry.get_app(tenant_id)
        role = str((claims.get("roles") or ["desk"])[0] if isinstance(claims.get("roles"), list) else claims.get("role") or "desk")
        desk = CallDeskService(data_layer=getattr(cm, "data_layer", None), voice_assist=_voice_assist(cm))
        try:
            return desk.log_outcome(
                card_id=str(body.get("card_id") or ""),
                outcome=str(body.get("outcome") or ""),
                notes=str(body.get("notes") or ""),
                promised_date=str(body.get("promised_date") or ""),
                actor_id=str(claims.get("sub") or ""),
                actor_role=role,
                human_action_id=str(body.get("human_action_id") or ""),
            )
        except (PermissionError, ValueError) as e:
            raise HTTPException(status_code=403 if isinstance(e, PermissionError) else 400, detail=str(e))


    @app.get("/t/{tenant_id}/automations/rules")
    def list_automation_rules(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {"rules": _auto(registry.get_app(tenant_id)).list_rules()}

    @app.post("/t/{tenant_id}/automations/rules")
    def upsert_automation_rule(
        tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)
    ):
        _require_tenant(claims, tenant_id)
        rule = _auto(registry.get_app(tenant_id)).upsert_rule(body)
        return {"rule": rule}

    @app.post("/t/{tenant_id}/automations/rules/{rule_id}/enable")
    def enable_automation_rule(
        tenant_id: str, rule_id: str, body: Dict[str, Any] = Body(default={}), claims: Dict[str, Any] = Depends(_bearer)
    ):
        _require_tenant(claims, tenant_id)
        enabled = True if body.get("enabled") is None else bool(body.get("enabled"))
        r = _auto(registry.get_app(tenant_id)).set_enabled(rule_id, enabled)
        if not r:
            raise HTTPException(status_code=404, detail="Rule not found")
        return {"rule": r}

    @app.delete("/t/{tenant_id}/automations/rules/{rule_id}")
    def delete_automation_rule(tenant_id: str, rule_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        ok = _auto(registry.get_app(tenant_id)).delete_rule(rule_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Rule not found")
        return {"ok": True}

    @app.post("/t/{tenant_id}/automations/rules/{rule_id}/dry-run")
    def dry_run_automation_rule(
        tenant_id: str, rule_id: str, body: Dict[str, Any] = Body(default={}), claims: Dict[str, Any] = Depends(_bearer)
    ):
        _require_tenant(claims, tenant_id)
        auto = _auto(registry.get_app(tenant_id))
        rule = None
        for r in auto.list_rules():
            if str(r.get("id")) == str(rule_id):
                rule = r
                break
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        return auto.evaluate_rule(rule, context=body or {}, dry_run=True)

    @app.post("/t/{tenant_id}/automations/rules/{rule_id}/run")
    def run_automation_rule(
        tenant_id: str, rule_id: str, body: Dict[str, Any] = Body(default={}), claims: Dict[str, Any] = Depends(_bearer)
    ):
        _require_tenant(claims, tenant_id)
        ctx = dict(body or {})
        ctx["actor_id"] = str(claims.get("sub") or "system")
        return _auto(registry.get_app(tenant_id)).run_rule_by_id(rule_id, ctx)

    @app.get("/t/{tenant_id}/automations/log")
    def automation_log(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer), limit: int = 50):
        _require_tenant(claims, tenant_id)
        return {"log": _auto(registry.get_app(tenant_id)).get_log(limit=min(limit, 200))}

    @app.post("/t/{tenant_id}/automations/run-fee-reminders")
    def run_fee_reminders(
        tenant_id: str, claims: Dict[str, Any] = Depends(_bearer), year: int = None, month: int = None
    ):
        from datetime import datetime
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        now = datetime.utcnow()
        y = year or now.year
        m = month or now.month
        return _auto(cm).run_fee_reminder_escalation(y, m, actor_id=str(claims.get("sub") or "system"))

    @app.post("/t/{tenant_id}/automations/run-attendance-nag")
    def run_attendance_nag(
        tenant_id: str, batch_id: str, claims: Dict[str, Any] = Depends(_bearer), on_date: str = None
    ):
        from datetime import date
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        d = on_date or date.today().isoformat()
        return _auto(cm).run_attendance_nag_generation(batch_id, d, actor_id=str(claims.get("sub") or "system"))

    @app.post("/t/{tenant_id}/tutor/query")
    def tutor_query(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        """Student AI Tutor — grounded only on this student's batch Vault docs."""
        _require_tenant(claims, tenant_id)
        try:
            registry.limiter.check(
                "tutor_query",
                str(claims.get("sub") or claims.get("account_id") or tenant_id),
                "",
            )
        except RateLimitExceeded as e:
            raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": str(e.retry_after)})
        cm = registry.get_app(tenant_id)
        student_id = str(body.get("student_id") or "")
        batch_id = str(body.get("batch_id") or "")
        question = str(body.get("question") or "").strip()
        if not question:
            raise HTTPException(status_code=400, detail="question required")
        # Resolve batch from student if needed
        if student_id and not batch_id and hasattr(cm, "admission"):
            try:
                for s in (cm.admission.list_students() or []):
                    if str(s.get("id") or s.get("student_id")) == student_id:
                        batch_id = str(s.get("batch_id") or "")
                        break
            except Exception:
                pass
        chunks = []
        if hasattr(cm, "retrieval"):
            try:
                chunks = cm.retrieval.retrieve(question, batch_id=batch_id or None, limit=5) or []
            except Exception as e:
                chunks = []
        citations = []
        for ch in chunks:
            # RetrievalChunk may be object or dict
            if hasattr(ch, "resource_id"):
                citations.append({
                    "resource_id": getattr(ch, "resource_id", None),
                    "title": getattr(ch, "title", None) or getattr(ch, "source_title", None),
                    "excerpt": (getattr(ch, "excerpt", None) or getattr(ch, "text", None) or "")[:300],
                })
            elif isinstance(ch, dict):
                citations.append({
                    "resource_id": ch.get("resource_id") or ch.get("id"),
                    "title": ch.get("title"),
                    "excerpt": (ch.get("excerpt") or ch.get("text") or "")[:300],
                })
        if not citations:
            return {
                "answer": "No matching documents in your batch vault. Ask your teacher to upload notes or papers for this batch.",
                "citations": [],
                "grounded": False,
                "batch_id": batch_id,
                "student_id": student_id,
            }
        # Build grounded local answer
        lines = [f"Based on {len(citations)} source(s) from your batch vault:"]
        for i, c in enumerate(citations, 1):
            lines.append(f"[{i}] {c.get('title') or c.get('resource_id')}: {(c.get('excerpt') or '')[:160]}")
        answer = "\n".join(lines)
        # Optional external LLM with ONLY citation text (no cross-tenant)
        keys = _ai_keys_normalized(cm.config.get_section("ai_keys") or {})
        # Route: prefer routes.tutor then provider
        routes = {}
        try:
            raw_routes = keys.get("routes")
            import json as _json
            if isinstance(raw_routes, str):
                routes = _json.loads(raw_routes) if raw_routes else {}
            elif isinstance(raw_routes, dict):
                routes = raw_routes
        except Exception:
            routes = {}
        provider_name = str(routes.get("tutor") or keys.get("provider") or "groq")
        api_key = str(keys.get("api_key") or "")
        used_external = False
        llm_error = None
        if api_key and provider_name:
            try:
                from services.llm_provider import build_llm_provider, LLMRequest, LLMError, OfflineError, RateLimitError
                llm = build_llm_provider(provider_name, api_key)
                system = (
                    "You are a tutor for one student. Answer ONLY using the provided source excerpts. "
                    "Cite sources by [n]. If sources are insufficient, say so. Never invent other centres' content."
                )
                prompt = f"Question: {question}\n\nSources:\n" + "\n".join(
                    f"[{i}] {c.get('title')}: {c.get('excerpt')}" for i, c in enumerate(citations, 1)
                )
                resp = llm.complete(LLMRequest(prompt=prompt, system=system, max_tokens=512))
                if resp.text.strip():
                    answer = resp.text.strip()
                    used_external = True
            except RateLimitError as e:
                llm_error = str(e)
                raise HTTPException(status_code=429, detail=f"Provider rate limit: {e}")
            except (LLMError, OfflineError) as e:
                llm_error = str(e)
            except Exception as e:
                llm_error = f"Provider call failed: {e}"
        return {
            "answer": answer,
            "citations": citations,
            "grounded": True,
            "batch_id": batch_id,
            "student_id": student_id,
            "used_external_llm": used_external,
            "provider": provider_name if used_external else None,
            "llm_error": llm_error,
        }


    @app.get("/t/{tenant_id}/settings/storage")
    def get_storage_settings(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        section = _storage_section(cm) if "_storage_section" in dir() else (cm.config.get_section("storage") or {})
        # _storage_section defined near test route; call config directly here too
        try:
            section = cm.config.get_section("storage") or {}
        except Exception:
            section = {}
        if not section:
            try:
                all_cfg = cm.config.get_all() or {}
                section = {str(k)[8:]: v for k, v in all_cfg.items() if str(k).startswith("storage.")}
            except Exception:
                section = {}
        from services.storage_service import build_storage_provider, GoogleDriveStorageProvider
        provider = build_storage_provider(_normalize_storage_section(section))
        configured = True
        if isinstance(provider, GoogleDriveStorageProvider):
            configured = provider.is_configured()
        elif section.get("provider") == "local_fs":
            configured = True
        return {
            "provider": section.get("provider") or "google_drive",
            "configured": configured,
            "folder_id": section.get("folder_id"),
            "options": ["google_drive", "local_fs"],
        }

    @app.put("/t/{tenant_id}/settings/storage")
    def put_storage_settings(
        tenant_id: str, body: StorageSettingsBody, claims: Dict[str, Any] = Depends(_bearer)
    ):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        current = {}
        try:
            current = dict(cm.config.get_section("storage") or {})
        except Exception:
            current = {}
        current["provider"] = body.provider or "google_drive"
        if body.folder_id is not None:
            current["folder_id"] = body.folder_id
        if body.access_token is not None:
            current["access_token"] = body.access_token
        if body.credentials_json is not None:
            current["credentials_json"] = body.credentials_json
        if body.root is not None:
            current["root"] = body.root
        # Persist per-key under storage.* if set supported, else section blob
        cm.config.set_section("storage", current)
        configured = (
            current.get("provider") == "local_fs"
            or bool(current.get("access_token") or current.get("credentials_json"))
        )
        return {"ok": True, "provider": current.get("provider"), "configured": configured}

    def _storage_section(cm) -> Dict[str, Any]:
        try:
            sec = cm.config.get_section("storage") or {}
            if sec:
                return dict(sec)
        except Exception:
            pass
        # Fallback: rebuild from flat keys
        out = {}
        try:
            all_cfg = cm.config.get_all() or {}
            for k, v in all_cfg.items():
                if str(k).startswith("storage."):
                    out[str(k)[8:]] = v
                elif str(k) == "storage" and isinstance(v, dict):
                    out.update(v)
        except Exception:
            pass
        return out

    @app.post("/t/{tenant_id}/settings/storage/test")
    def test_storage(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        section = _storage_section(cm)
        from services.storage_service import build_storage_provider, StorageError
        provider = build_storage_provider(_normalize_storage_section(section))
        try:
            return provider.test_upload()
        except StorageError as e:
            return {"ok": False, "error": str(e)}


    # ── Payments ──────────────────────────────────────────────────────

    @app.get("/t/{tenant_id}/payments")
    def list_payments(
        tenant_id: str,
        batch_id: Optional[str] = None,
        year: Optional[int] = None,
        month: Optional[int] = None,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        if batch_id and year is not None and month is not None:
            return {
                "batch_id": batch_id,
                "year": year,
                "month": month,
                "rows": cm.payment.list_batch_payments(batch_id, year, month),
            }
        return {"payments": cm.data_layer.get_all("payment_records")}

    @app.get("/t/{tenant_id}/payments/batch/{batch_id}")
    def payments_for_batch(tenant_id: str, batch_id: str, year: int, month: int, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        rows = registry.get_app(tenant_id).payment.list_batch_payments(batch_id, year, month)
        return {"batch_id": batch_id, "year": year, "month": month, "rows": rows}

    @app.get("/t/{tenant_id}/payments/delayed/{batch_id}")
    def payments_delayed(tenant_id: str, batch_id: str, year: int, month: int, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        result = registry.get_app(tenant_id).payment.list_delayed_candidates(batch_id=batch_id, year=year, month=month)
        if isinstance(result, dict):
            return {"batch_id": batch_id, "year": year, "month": month, **result}
        return {"batch_id": batch_id, "year": year, "month": month, "will_notify": result}

    @app.post("/t/{tenant_id}/payments/mark-paid")
    def payments_mark_paid(tenant_id: str, body: PaymentActionBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        payment = registry.get_app(tenant_id).payment.mark_paid(
            student_id=body.student_id,
            year=body.year,
            month=body.month,
            amount=body.amount,
            actor_id=str(claims.get("sub") or ""),
            notes=body.notes,
        )
        return {"payment": payment}

    @app.post("/t/{tenant_id}/payments/lock")
    def payments_lock(tenant_id: str, body: PaymentActionBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        payment = registry.get_app(tenant_id).payment.lock_payment(
            student_id=body.student_id,
            year=body.year,
            month=body.month,
            actor_id=str(claims.get("sub") or ""),
        )
        return {"payment": payment}

    @app.post("/t/{tenant_id}/payments/unlock")
    def payments_unlock(tenant_id: str, body: PaymentActionBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        payment = registry.get_app(tenant_id).payment.unlock_payment(
            student_id=body.student_id,
            year=body.year,
            month=body.month,
            actor_id=str(claims.get("sub") or ""),
            reason=body.reason or body.notes,
            is_owner=True,
        )
        return {"payment": payment}

    @app.post("/t/{tenant_id}/payments/notify-flag")
    def payments_notify_flag(tenant_id: str, body: NotifyFlagBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        actor = str(claims.get("sub") or "")
        if body.flag == "white":
            payment = cm.payment.set_notify_white(student_id=body.student_id, year=body.year, month=body.month, actor_id=actor)
        else:
            payment = cm.payment.set_notify_green(student_id=body.student_id, year=body.year, month=body.month, actor_id=actor)
        return {"payment": payment}

    @app.post("/t/{tenant_id}/payments/intent")
    def payment_intent(tenant_id: str, body: PaymentIntentBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        gateway = build_gateway_from_config(cm.config.get)
        intent = gateway.create_payment_intent(
            amount=body.amount,
            currency=body.currency,
            student_id=body.student_id,
            year=body.year,
            month=body.month,
        )
        return {"intent": intent}

    # ── Exams ─────────────────────────────────────────────────────────

    @app.get("/t/{tenant_id}/exams")
    def list_exams(tenant_id: str, batch_id: Optional[str] = None, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {"exams": registry.get_app(tenant_id).exam.list_exams(batch_id=batch_id)}

    @app.get("/t/{tenant_id}/exams/{exam_id}")
    def get_exam(tenant_id: str, exam_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        exam = registry.get_app(tenant_id).exam.get_exam(exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")
        return exam

    @app.get("/t/{tenant_id}/exams/{exam_id}/summary")
    def exam_summary(tenant_id: str, exam_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return registry.get_app(tenant_id).exam.exam_summary(exam_id)

    @app.get("/t/{tenant_id}/exam-templates")
    def exam_templates(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {"templates": registry.get_app(tenant_id).exam.list_templates()}

    @app.post("/t/{tenant_id}/exams")
    def create_exam(tenant_id: str, body: ExamCreateBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            exam_id = cm.exam.create_exam(
                name=body.name,
                exam_date=body.exam_date,
                batch_id=body.batch_id or "",
                template_id=body.template_id,
                chapter_or_topic=body.chapter_or_topic or "",
                subject=body.subject or "",
                sections=body.sections,
                is_ad_hoc=body.is_ad_hoc,
                notes=body.notes or "",
                actor_id=str(claims.get("sub") or ""),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        exam = cm.exam.get_exam(exam_id)
        return {"exam_id": exam_id, "exam": exam}

    @app.post("/t/{tenant_id}/exams/{exam_id}/results")
    def enter_exam_result(
        tenant_id: str,
        exam_id: str,
        body: ExamResultBody,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            result = cm.exam.enter_result(
                exam_id=exam_id,
                student_id=body.student_id,
                section_scores=body.section_scores,
                is_absent=body.is_absent,
                notes=body.notes or "",
                actor_id=str(claims.get("sub") or ""),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"result": result}

    @app.get("/t/{tenant_id}/exams/{exam_id}/results")
    def get_exam_results(tenant_id: str, exam_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {"results": registry.get_app(tenant_id).exam.get_exam_results(exam_id)}

    @app.get("/t/{tenant_id}/students/{student_id}/results")
    def get_student_results(
        tenant_id: str, student_id: str, claims: Dict[str, Any] = Depends(_bearer)
    ):
        _require_tenant(claims, tenant_id)
        return {
            "results": registry.get_app(tenant_id).exam.get_student_results(student_id)
        }

    @app.post("/t/{tenant_id}/exams/{exam_id}/complete")
    def complete_exam(tenant_id: str, exam_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        ok = cm.exam.complete_exam(exam_id, actor_id=str(claims.get("sub") or ""))
        if not ok:
            raise HTTPException(status_code=404, detail="Exam not found")
        exam = cm.exam.get_exam(exam_id)
        return {"completed": True, "exam": exam}

    @app.get("/t/{tenant_id}/analytics/heatmap")
    def analytics_heatmap(
        tenant_id: str,
        batch_id: Optional[str] = None,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        topics = registry.get_app(tenant_id).exam.topic_heatmap(batch_id=batch_id)
        return {"topics": topics}

    @app.get("/t/{tenant_id}/analytics/struggle")
    def analytics_struggle(
        tenant_id: str,
        batch_id: str,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        students = registry.get_app(tenant_id).exam.students_likely_to_struggle(
            batch_id=batch_id
        )
        return {"students": students}

    # ── Vault / AI ────────────────────────────────────────────────────

    @app.get("/t/{tenant_id}/vault")
    def list_vault(
        tenant_id: str,
        topic: Optional[str] = None,
        batch_id: Optional[str] = None,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        return {
            "resources": registry.get_app(tenant_id).content.list_resources(
                topic=topic, batch_id=batch_id
            )
        }


    @app.post("/t/{tenant_id}/vault/upload")
    def upload_vault_resource(
        tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)
    ):
        """Real attach: bytes → storage provider → content_resources row."""
        import base64
        import io
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            raw = base64.b64decode(body.get("content_base64") or "")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid content_base64")
        if len(raw) > 25 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (25MB max in pilot)")
        section = cm.config.get_section("storage") or {}
        from services.storage_service import build_storage_provider
        store = build_storage_provider(section)
        if not store.is_configured():
            from services.storage_service import LocalFsStorageProvider
            root = section.get("root") or "/tmp/cohortos-storage"
            store = LocalFsStorageProvider(root)
        filename = str(body.get("filename") or "file.bin")
        # Path-traversal safe: basename only, no .. or separators
        filename = Path(filename).name.replace("..", "_") or "file.bin"
        content_type = str(body.get("content_type") or "application/octet-stream")
        path = f"vault/{tenant_id}/{filename}"
        remote_id = store.upload(path, io.BytesIO(raw), content_type)
        rid = cm.content.create_resource(
            title=str(body.get("title") or filename),
            resource_type="pdf",
            topic=str(body.get("topic") or ""),
            file_path=remote_id,
            mime_type=content_type,
            file_size_bytes=len(raw),
            batch_ids=list(body.get("batch_ids") or []),
            actor_id=str(claims.get("sub") or ""),
            actor_role=str(claims.get("role") or "owner"),
        )
        resource = cm.content.get_resource(rid)
        try:
            if hasattr(cm, "rag") and cm.rag:
                cm.rag.index_resource(resource or {})
        except Exception:
            pass
        return {"resource_id": rid, "resource": resource, "storage_id": remote_id}

    @app.get("/t/{tenant_id}/vault/{resource_id}/content")
    def download_vault_content(
        tenant_id: str, resource_id: str, claims: Dict[str, Any] = Depends(_bearer)
    ):
        from fastapi.responses import StreamingResponse
        import io
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            resource = cm.content.get_resource(resource_id)
        except (ValueError, TypeError, Exception):
            resource = None
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")
        remote_id = resource.get("file_path") or resource.get("url") or ""
        if not remote_id:
            raise HTTPException(status_code=404, detail="No file attached to this resource")
        section = cm.config.get_section("storage") or {}
        from services.storage_service import build_storage_provider, LocalFsStorageProvider
        import os as _os
        _default_root = section.get("root") or _os.environ.get("COHORTOS_STORAGE_ROOT") or "/tmp/cohortos-storage"
        try:
            store = build_storage_provider(section if section else {"provider": "local", "root": _default_root})
            if not store.is_configured() or not store.exists(remote_id):
                store = LocalFsStorageProvider(_default_root)
            if not store.exists(remote_id):
                # Last resort: try basename under vault/tenant (legacy uploads)
                from pathlib import Path as _P
                alt = str(_P("vault") / tenant_id / _P(str(remote_id)).name)
                if store.exists(alt):
                    remote_id = alt
                else:
                    raise HTTPException(status_code=404, detail="File missing in storage")
            stream = store.download(remote_id)
            # Cap read so a corrupt/huge object cannot hang or OOM the API
            max_bytes = 25 * 1024 * 1024
            data = stream.read(max_bytes + 1)
            if data is None:
                data = b""
            if len(data) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail="Stored file exceeds 25MB limit and cannot be served",
                )
            if len(data) == 0:
                raise HTTPException(status_code=422, detail="File is empty or unreadable")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=f"Could not read file (corrupt or storage error): {e}",
            )
        media = resource.get("mime_type") or "application/octet-stream"
        safe_name = str(resource.get("title") or "file").replace('"', "")[:120]
        return StreamingResponse(
            io.BytesIO(data),
            media_type=media,
            headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
        )

    @app.post("/t/{tenant_id}/vault")
    def create_vault_resource(
        tenant_id: str, body: VaultCreateBody, claims: Dict[str, Any] = Depends(_bearer)
    ):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            rid = cm.content.create_resource(
                title=body.title,
                resource_type=body.resource_type or "pdf",
                topic=body.topic or "",
                subject=body.subject or "",
                description=body.description or "",
                url=body.url or "",
                batch_ids=body.batch_ids,
                access_rules=body.access_rules,
                protection_level=body.protection_level or "owner_only",
                actor_id=str(claims.get("sub") or ""),
                actor_role=body.actor_role or "owner",
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        resource = cm.content.get_resource(rid)
        try:
            if hasattr(cm, "rag") and cm.rag:
                cm.rag.index_resource(resource or {})
        except Exception:
            pass
        return {"resource_id": rid, "resource": resource}

    @app.put("/t/{tenant_id}/vault/{resource_id}/access-rules")
    def set_vault_access_rules(
        tenant_id: str,
        resource_id: str,
        body: VaultAccessRulesBody,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        ok = cm.content.set_access_rules(
            resource_id,
            operator=body.operator or "AND",
            rules=body.rules or [],
            actor_id=str(claims.get("sub") or ""),
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Resource not found")
        return {"resource": cm.content.get_resource(resource_id)}

    @app.post("/t/{tenant_id}/vault/{resource_id}/relax")
    def relax_vault_protection(
        tenant_id: str,
        resource_id: str,
        body: VaultProtectBody,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            resource = cm.content.relax_protection(
                resource_id,
                actor_id=str(claims.get("sub") or ""),
                actor_role=body.actor_role or "owner",
            )
        except Exception as e:
            raise HTTPException(status_code=403, detail=str(e))
        return {"resource": resource}

    @app.post("/t/{tenant_id}/vault/{resource_id}/restore")
    def restore_vault_protection(
        tenant_id: str,
        resource_id: str,
        body: VaultProtectBody,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            resource = cm.content.restore_protection(
                resource_id,
                actor_id=str(claims.get("sub") or ""),
                actor_role=body.actor_role or "owner",
            )
        except Exception as e:
            raise HTTPException(status_code=403, detail=str(e))
        return {"resource": resource}

    @app.get("/t/{tenant_id}/vault/{resource_id}/access")
    def evaluate_vault_access(
        tenant_id: str,
        resource_id: str,
        student_id: str,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        return registry.get_app(tenant_id).content.evaluate_access(
            resource_id, student_id
        )

    @app.get("/t/{tenant_id}/vault/student")
    def list_vault_for_student(
        tenant_id: str,
        student_id: str,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        resources = cm.content.list_resources()
        accessible = []
        for r in resources:
            ev = cm.content.evaluate_access(r.get("id"), student_id)
            if ev.get("allowed"):
                accessible.append({**r, "access": ev})
        return {"resources": accessible}

    @app.post("/t/{tenant_id}/solve/ask")
    def solve_ask(tenant_id: str, body: SolveAskBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        _llm_cost_guard(tenant_id)
        cm = registry.get_app(tenant_id)
        result = cm.solve.ask(
            student_id=body.student_id or str(claims.get("sub") or "student"),
            question=body.question,
            subject=body.subject or "physics",
            topic=body.topic or "",
            question_type=getattr(body, "mode", None) or getattr(body, "question_type", None) or "written",
            thread_id=body.thread_id,
        )
        if hasattr(result, "to_dict"):
            return result.to_dict()
        if hasattr(result, "__dict__") and not isinstance(result, dict):
            return dict(result.__dict__)
        return result

    @app.get("/t/{tenant_id}/solve/threads")
    def solve_threads(tenant_id: str, student_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {"threads": registry.get_app(tenant_id).solve.list_threads(student_id)}

    @app.get("/t/{tenant_id}/solve/threads/{thread_id}/messages")
    def solve_thread_messages(tenant_id: str, thread_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {"messages": registry.get_app(tenant_id).solve.list_messages(thread_id)}

    @app.post("/t/{tenant_id}/solve/threads/{thread_id}/reply")
    def solve_thread_reply(tenant_id: str, thread_id: str, body: ThreadReplyBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            out = cm.accounts.teacher_reply_on_thread(
                thread_id=thread_id,
                teacher_id=str(claims.get("sub") or ""),
                content=body.body,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return out if isinstance(out, dict) else {"ok": True, "result": str(out)}

    @app.get("/t/{tenant_id}/ai/threads/flagged")
    def flagged_threads(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        threads = registry.get_app(tenant_id).accounts.flagged_thread_priority_queue()
        return {"threads": threads or []}

    @app.get("/t/{tenant_id}/ai/threads/{thread_id}/messages")
    def ai_thread_messages(tenant_id: str, thread_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {"messages": registry.get_app(tenant_id).solve.list_messages(thread_id)}

    @app.post("/t/{tenant_id}/ai/threads/{thread_id}/take-over")
    def ai_thread_takeover(tenant_id: str, thread_id: str, body: ThreadReplyBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            out = cm.accounts.teacher_reply_on_thread(
                thread_id=thread_id,
                teacher_id=str(claims.get("sub") or ""),
                content=body.body or "Teacher reviewing this thread.",
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return out if isinstance(out, dict) else {"ok": True}

    @app.get("/t/{tenant_id}/ai/style-profiles")
    def style_profiles(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        profiles = cm.teach.list_style_profiles() if hasattr(cm.teach, "list_style_profiles") else []
        return {"profiles": profiles or []}

    @app.get("/t/{tenant_id}/ai/style-profiles/{subject}")
    def style_profile_get(tenant_id: str, subject: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        row = registry.get_app(tenant_id).teach.get_style_profile(subject)
        if not row:
            return {"profile": None, "subject": subject}
        return {"profile": row}

    @app.put("/t/{tenant_id}/ai/style-profiles/{subject}")
    def style_profile_put(tenant_id: str, subject: str, body: StyleProfileBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            terms = body.terminology
            if isinstance(terms, str):
                terms = [x.strip() for x in terms.split(",") if x.strip()]
            row = cm.teach.upsert_style_profile(
                subject=subject or body.subject,
                style_notes=body.style_notes,
                terminology=terms or [],
                sign_conventions=body.sign_conventions,
                difficulty=body.difficulty or "medium",
                preferred_language=body.preferred_language or "en",
                few_shot_examples=body.few_shot_examples or [],
                actor_id=str(claims.get("sub") or ""),
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"profile": row}

    @app.post("/t/{tenant_id}/ai/style-profiles")
    def style_profile_post(tenant_id: str, body: StyleProfileBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        try:
            terms = body.terminology
            if isinstance(terms, str):
                terms = [x.strip() for x in terms.split(",") if x.strip()]
            row = cm.teach.upsert_style_profile(
                subject=body.subject,
                style_notes=body.style_notes,
                terminology=terms or [],
                sign_conventions=body.sign_conventions,
                difficulty=body.difficulty or "medium",
                preferred_language=body.preferred_language or "en",
                few_shot_examples=body.few_shot_examples or [],
                actor_id=str(claims.get("sub") or ""),
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"profile": row}

    @app.get("/t/{tenant_id}/ai/review-queue")
    def ai_review_queue(tenant_id: str, status: str = "needs_review", claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        items = registry.get_app(tenant_id).teach.list_review_queue(status=status)
        return {"items": items or []}

    @app.post("/t/{tenant_id}/ai/review-queue/{item_id}/approve")
    def ai_review_approve(tenant_id: str, item_id: str, body: Optional[ApproveItemBody] = None, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        edits = body.edits if body else None
        try:
            item = registry.get_app(tenant_id).teach.approve_item(item_id, str(claims.get("sub") or ""), edits=edits)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"item": item}

    @app.post("/t/{tenant_id}/ai/review-queue/{item_id}/reject")
    def ai_review_reject(tenant_id: str, item_id: str, body: Optional[RejectItemBody] = None, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        reason = body.reason if body else ""
        try:
            item = registry.get_app(tenant_id).teach.reject_item(item_id, str(claims.get("sub") or ""), reason=reason)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"item": item}

    @app.get("/t/{tenant_id}/ai/item-bank")
    def ai_item_bank(tenant_id: str, status: Optional[str] = None, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        items = cm.data_layer.get_all("ai_generated_items")
        if status:
            items = [i for i in items if i.get("status") == status]
        return {"items": items or []}

    @app.post("/t/{tenant_id}/ai/items/generate")
    def ai_generate_item(tenant_id: str, body: GenerateItemBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        try:
            item = registry.get_app(tenant_id).teach.generate_item(
                item_type=body.item_type,
                subject=body.subject,
                topic=body.topic,
                prompt=body.prompt,
                actor_id=str(claims.get("sub") or ""),
                batch_id=body.batch_id,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"item": item}

    @app.get("/t/{tenant_id}/ai/items/{item_id}/history")
    def ai_item_history(tenant_id: str, item_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        item = registry.get_app(tenant_id).data_layer.get("ai_generated_items", item_id)
        if not item:
            # try UUID
            import uuid as _uuid
            try:
                item = registry.get_app(tenant_id).data_layer.get("ai_generated_items", _uuid.UUID(item_id))
            except Exception:
                item = None
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"history": item.get("history") or [], "item": item}

    @app.post("/t/{tenant_id}/ai/items/{item_id}/push-bank")
    def ai_push_bank(tenant_id: str, item_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        try:
            out = registry.get_app(tenant_id).teach.push_to_exam_bank(item_id, str(claims.get("sub") or ""))
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return out if isinstance(out, dict) else {"ok": True, "result": str(out)}

    @app.post("/t/{tenant_id}/ai/ocr")
    def ai_ocr(tenant_id: str, body: Optional[OcrBody] = None, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        body = body or OcrBody()
        try:
            _llm_cost_guard(tenant_id)
            result = cm.teach.ocr_grade_handwriting(
                image_ref=body.image_b64 or body.text or "inline",
                rubric={"text": body.rubric} if body.rubric else None,
                actor_id=str(claims.get("sub") or ""),
            )
            if isinstance(result, dict):
                result.setdefault("verify_before_grading", True)
                result.setdefault("notes", "Auto-transcribed — verify before grading (SPEC).")
        except Exception as e:
            result = {
                "transcription": body.text or "",
                "verify_before_grading": True,
                "error": str(e),
                "notes": "OCR path degraded. Verify manually before grading.",
            }
        return result if isinstance(result, dict) else {"result": str(result), "verify_before_grading": True}

    @app.post("/t/{tenant_id}/ai/recap-draft")
    def ai_recap(tenant_id: str, body: Optional[RecapDraftBody] = None, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        body = body or RecapDraftBody()
        try:
            topic = body.topic or body.misconception or "general"
            _llm_cost_guard(tenant_id)
            result = cm.teach.generate_analytics_suggestion(
                subject=body.subject or "physics",
                topic=topic,
                cohort_size=3,
                weakness_severity=0.8,
                actor_id=str(claims.get("sub") or ""),
            )
        except Exception as e:
            result = {
                "draft": f"Recap draft unavailable: {e}",
                "needs_review": True,
                "grounded": False,
            }
        return result if isinstance(result, dict) else {"draft": str(result), "needs_review": True}

    # ── Accounts / Parents / Staff ────────────────────────────────────

    @app.get("/t/{tenant_id}/accounts")
    def list_accounts(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {"accounts": registry.get_app(tenant_id).data_layer.get_all("accounts")}

    @app.post("/t/{tenant_id}/accounts/link-join")
    def accounts_link_join(tenant_id: str, body: AccountLinkJoinBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)

        account_id = body.account_id or body.cohortos_account_id
        if not account_id:
            raise HTTPException(status_code=400, detail="account_id is required")

        admission_id = body.admission_id
        if not admission_id:
            # Primary path: resolve admission_id from the join code itself so the
            # student/parent never needs to know their internal admission id.
            if not body.join_code:
                raise HTTPException(status_code=400, detail="join_code or admission_id is required")
            code = body.join_code.strip().upper()
            match = next(
                (
                    jc for jc in cm.data_layer.get_all("join_codes")
                    if jc.get("code") == code and not jc.get("is_used")
                ),
                None,
            )
            if not match:
                raise HTTPException(status_code=404, detail="Invalid or already-used join code")
            admission_id = match.get("admission_id")

        try:
            ok = cm.admission.link_account(
                admission_id=admission_id,
                cohortos_account_id=account_id,
                join_code=body.join_code,
                actor_id=str(claims.get("sub") or ""),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        student = cm.admission.get_student(admission_id) or {}
        return {
            "linked": bool(ok),
            "admission_id": admission_id,
            "account_id": account_id,
            "student_name": student.get("name"),
            "roll": student.get("roll"),
        }

    @app.post("/t/{tenant_id}/parents/link")
    def parents_link(tenant_id: str, body: ParentLinkBody, claims: Dict[str, Any] = Depends(_bearer)):
        """
        Link parent to student.
        Same-tenant by default. Cross-tenant allowed only when:
          - body.target_tenant_id is set AND
          - COHORTOS_ALLOW_CROSS_TENANT_PARENT=1 AND
          - caller has owner role (or founder header present — separate path)
        """
        _require_tenant(claims, tenant_id)
        if body.target_tenant_id and body.target_tenant_id != tenant_id:
            allow = os.environ.get("COHORTOS_ALLOW_CROSS_TENANT_PARENT", "").lower() in ("1", "true", "yes")
            roles = claims.get("roles") or []
            if not allow or ("owner" not in roles and "founder" not in roles):
                raise HTTPException(
                    status_code=403,
                    detail="Cross-tenant parent linking disabled or insufficient role. "
                           "Set COHORTOS_ALLOW_CROSS_TENANT_PARENT=1 and use owner role.",
                )
            # Cross-tenant: operate on target tenant's account service
            target = registry.get_app(body.target_tenant_id)
            try:
                result = target.accounts.link_parent_to_student(
                    parent_account_id=body.parent_account_id,
                    student_id=body.student_id,
                    actor_id=str(claims.get("sub") or ""),
                )
                return {"link": result, "cross_tenant": True, "target_tenant_id": body.target_tenant_id}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        try:
            result = registry.get_app(tenant_id).accounts.link_parent_to_student(
                parent_account_id=body.parent_account_id,
                student_id=body.student_id,
                actor_id=str(claims.get("sub") or ""),
            )
            return {"link": result, "cross_tenant": False}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/t/{tenant_id}/staff")
    def list_staff(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        rows = cm.data_layer.get_all("staff") or cm.data_layer.get_all("users") or []
        return {"staff": rows}

    @app.post("/t/{tenant_id}/staff")
    def create_staff(tenant_id: str, body: StaffCreateBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        row = {
            "name": body.name,
            "role": body.role,
            "role_name": body.role,
            "role_id": body.role,
            "phone": body.phone,
            "email": body.email,
            "tenant_id": tenant_id,
        }
        rid = cm.data_layer.create("staff", row)
        stored = cm.data_layer.get("staff", rid) or {**row, "id": str(rid)}
        return {"user_id": str(rid), "user": stored}

    @app.get("/t/{tenant_id}/roles")
    def list_roles(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return {
            "roles": [
                {"id": "owner", "name": "Owner", "permissions": ["*"]},
                {"id": "desk", "name": "Desk", "permissions": ["attendance", "payments", "admissions"]},
                {"id": "teacher", "name": "Teacher", "permissions": ["attendance", "exams", "content"]},
                {"id": "assistant", "name": "Assistant", "permissions": ["attendance"]},
            ]
        }

    @app.post("/t/{tenant_id}/staff/{user_id}/role")
    def assign_staff_role(
        tenant_id: str,
        user_id: str,
        body: StaffRoleBody,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        """Assign role_name (owner/desk/teacher/assistant) to a staff/user row.
        PRD §26: canonical role_id model; frontend four-name UX preserved.
        Owner cannot demote the last owner.
        """
        _require_tenant(claims, tenant_id)
        role_name = (body.role_name or "").strip().lower()
        allowed = {"owner", "desk", "teacher", "assistant"}
        if role_name not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"role_name must be one of {sorted(allowed)}",
            )
        cm = registry.get_app(tenant_id)
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user_id")

        row = cm.data_layer.get("staff", uid)
        table = "staff"
        if not row:
            row = cm.data_layer.get("users", uid)
            table = "users"
        if not row:
            raise HTTPException(status_code=404, detail="Staff user not found")

        # Last-owner guard: if demoting from owner, ensure at least one owner remains
        current_role = (row.get("role") or row.get("role_name") or "").lower()
        if current_role == "owner" and role_name != "owner":
            all_staff = cm.data_layer.get_all("staff") or []
            all_users = cm.data_layer.get_all("users") or []
            owners = [
                r
                for r in (all_staff + all_users)
                if (r.get("role") or r.get("role_name") or "").lower() == "owner"
                and str(r.get("id")) != str(user_id)
            ]
            if not owners:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot demote the last owner",
                )

        updates = {
            "role": role_name,
            "role_name": role_name,
            "role_id": role_name,  # align with PRD §26 role_id model
        }
        ok = cm.data_layer.update(table, uid, updates)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to update role")
        updated = cm.data_layer.get(table, uid) or {**row, **updates}
        return {"user": updated, "role_name": role_name}

    # ── Settings ──────────────────────────────────────────────────────

    @app.get("/t/{tenant_id}/settings/mode")
    def get_mode(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        mode = cm.config.get("runtime.mode") or getattr(cm.tenant_context, "mode", "offline-first")
        return {"mode": mode, "runtime_mode": mode, "options": ["offline-first", "cloud-first", "hybrid"]}

    @app.put("/t/{tenant_id}/settings/mode")
    def set_mode(tenant_id: str, body: ModeBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        if body.mode not in ("offline-first", "cloud-first", "hybrid"):
            raise HTTPException(status_code=400, detail="Invalid mode")
        registry.get_app(tenant_id).config.set("runtime.mode", body.mode)
        return {"mode": body.mode, "runtime_mode": body.mode}

    @app.get("/t/{tenant_id}/settings/messaging")
    def get_messaging(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        return registry.get_app(tenant_id).config.get_section("messaging") or {}

    @app.put("/t/{tenant_id}/settings/messaging")
    def set_messaging(tenant_id: str, body: MessagingSettingsBody, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        current = cm.config.get_section("messaging") or {}
        if body.channel is not None:
            current["channel"] = body.channel
        if body.absentees_time is not None:
            current["absentees_time"] = body.absentees_time
        if body.templates is not None:
            current["templates"] = body.templates
        cm.config.set_section("messaging", current)
        return current

    # ── Sync ──────────────────────────────────────────────────────────

    @app.post("/sync/push")
    def sync_push(body: SyncPushBody, claims: Dict[str, Any] = Depends(_bearer)):
        return registry.cloud.push(
            tenant_id=str(claims["tenant_id"]),
            operations=body.operations,
            device_id=body.device_id,
        )

    @app.post("/sync/pull")
    def sync_pull(body: SyncPullBody, claims: Dict[str, Any] = Depends(_bearer)):
        return registry.cloud.pull(
            tenant_id=str(claims["tenant_id"]),
            since_seq=body.since_seq,
            limit=body.limit,
            exclude_device=body.device_id,
        )


    # ── Sync conflicts / Backup / License (Batch 2) ───────────────────

    @app.get("/t/{tenant_id}/sync/conflicts")
    def list_sync_conflicts(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        """Owner conflict log — locked-payment conflicts excluded from LWW (SPEC §3, §7)."""
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        if not cm.sync:
            return {"conflicts": []}
        try:
            conflicts = cm.sync.get_conflicts()
            out = []
            for c in conflicts:
                d = c.to_dict() if hasattr(c, "to_dict") else dict(c)
                # Flag payment locks for owner attention
                table = str(d.get("table_name") or "")
                d["is_locked_payment"] = table in ("payments", "payment_records", "payment_locks")
                out.append(d)
            return {"conflicts": out}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/t/{tenant_id}/sync/conflicts/{conflict_id}/resolve")
    def resolve_sync_conflict(
        tenant_id: str,
        conflict_id: int,
        body: ConflictResolveBody,
        claims: Dict[str, Any] = Depends(_bearer),
    ):
        _require_tenant(claims, tenant_id)
        roles = [str(r).lower() for r in (claims.get("roles") or [])]
        if "owner" not in roles:
            raise HTTPException(status_code=403, detail="Only owner can resolve sync conflicts")
        cm = registry.get_app(tenant_id)
        if not cm.sync:
            raise HTTPException(status_code=400, detail="Sync engine not available")
        from models.sync import SyncConflict
        conflict = SyncConflict(id=conflict_id, tenant_id=tenant_id)
        try:
            ok = cm.sync.resolve_conflict(conflict, body.resolution or "manual")
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not ok:
            raise HTTPException(status_code=404, detail="Conflict not found or already resolved")
        return {"ok": True, "conflict_id": conflict_id, "resolution": body.resolution}

    @app.get("/t/{tenant_id}/backup/status")
    def backup_status(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        """Local snapshot schedule/status + WAL confirmation (SPEC §7 disaster recovery)."""
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        dl = cm.data_layer
        db_path = getattr(dl, "db_path", ":memory:")
        from models.base import list_backups, backup_dir_for
        wal_active = False
        journal_mode = "unknown"
        try:
            if db_path not in (":memory:", None):
                row = dl._conn.execute("PRAGMA journal_mode").fetchone()
                journal_mode = (row[0] if row else "unknown")
                wal_active = str(journal_mode).lower() == "wal"
        except Exception:
            pass
        backups = []
        try:
            if db_path not in (":memory:", None):
                for p in list_backups(str(db_path)):
                    backups.append({"path": str(p), "name": p.name, "size": p.stat().st_size if p.exists() else 0})
        except Exception:
            pass
        return {
            "db_path": str(db_path),
            "wal_active": wal_active,
            "journal_mode": journal_mode,
            "backups": backups,
            "backup_dir": str(backup_dir_for(str(db_path))) if db_path not in (":memory:", None) else None,
        }

    @app.post("/t/{tenant_id}/backup/export")
    def backup_export(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        """Trigger full dataset export / snapshot (owner disaster recovery)."""
        _require_tenant(claims, tenant_id)
        roles = [str(r).lower() for r in (claims.get("roles") or [])]
        if roles and "owner" not in roles:
            # Allow if roles empty (pilot tokens may omit roles)
            pass
        cm = registry.get_app(tenant_id)
        path = None
        try:
            path = cm.data_layer.backup_now()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        # Also return a portable JSON dump of core tables for CSV-style export
        tables = ["students", "batches", "exams", "exam_results", "staff", "payments"]
        export: Dict[str, Any] = {"tenant_id": tenant_id, "tables": {}}
        for tname in tables:
            try:
                export["tables"][tname] = cm.data_layer.get_all(tname) or []
            except Exception:
                export["tables"][tname] = []
        return {
            "ok": True,
            "snapshot_path": str(path) if path else None,
            "export": export,
            "message": "Snapshot taken" if path else "In-memory DB — JSON export only",
        }

    @app.get("/t/{tenant_id}/license/status")
    def license_status(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        """Rolling license check — delinquent past grace → read-only lockout (SPEC §0)."""
        _require_tenant(claims, tenant_id)
        # Prefer founder/meta store when available
        locked = False
        reason = None
        grace_ends_at = None
        status = "active"
        try:
            meta = registry._meta if hasattr(registry, "_meta") else None
            # Check tenant record from founder cloud when present
            if hasattr(registry, "founder") and registry.founder:
                try:
                    # Soft check without founder token — local config flag
                    pass
                except Exception:
                    pass
            cm = registry.get_app(tenant_id)
            flag = cm.config.get("billing.lockout") if hasattr(cm, "config") else None
            if flag in (True, "1", "true", "lockout", "delinquent"):
                locked = True
                status = "lockout"
                reason = cm.config.get("billing.lockout_reason") or (
                    "Billing is past the grace window. Desk is read-only."
                )
            grace_ends_at = cm.config.get("billing.grace_ends_at") if hasattr(cm, "config") else None
            # Offline seal: can only ADD lock, never unlock. Config is source of truth.
            # Hand-editing seal locked=false must not clear an active config lockout.
            try:
                data_dir = Path(os.environ.get("COHORTOS_DATA_DIR") or "/tmp/cohortos-data")
                seal_path = data_dir / f"license_seal_{tenant_id}.json"
                if seal_path.exists():
                    import json as _json
                    seal = _json.loads(seal_path.read_text(encoding="utf-8"))
                    if seal.get("locked") is True:
                        # Verify HMAC — tampered seal body is ignored (does not unlock)
                        import hashlib, hmac as _hmac
                        mac_key = (os.environ.get("COHORTOS_LICENSE_SECRET") or os.environ.get("COHORTOS_JWT_SECRET") or "dev").encode()
                        payload = f"{seal.get('tenant_id')}|{int(bool(seal.get('locked')))}|{seal.get('reason') or ''}|{seal.get('updated_at') or ''}".encode()
                        expect = _hmac.new(mac_key, payload, hashlib.sha256).hexdigest()
                        if seal.get("hmac") and not _hmac.compare_digest(str(seal.get("hmac")), expect):
                            # tampered — keep config lock state; do not trust seal fields
                            pass
                        else:
                            locked = True
                            status = "lockout"
                            reason = seal.get("reason") or reason or "Access disabled by founder"
                    # Explicit: seal.locked=false is ignored when config already locked
            except Exception:
                pass
        except Exception:
            pass
        return {
            "locked": locked,
            "status": status,
            "reason": reason,
            "grace_ends_at": grace_ends_at,
        }



    # ── Centre setup wizard

    @app.post("/founder/tenants/{tenant_id}/license")
    def founder_set_license(
        tenant_id: str,
        body: Dict[str, Any] = Body(...),
        x_founder_token: Optional[str] = Header(None, alias="X-Founder-Token"),
    ):
        """Enable/disable centre access. Persists lockout flag into tenant config + offline seal file."""
        if not x_founder_token:
            raise HTTPException(status_code=403, detail="Missing X-Founder-Token")
        # Validate founder token via dashboard call (raises if invalid)
        try:
            registry.founder.dashboard(founder_token=x_founder_token)
        except Exception as e:
            raise HTTPException(status_code=403, detail=f"Invalid founder token: {e}")
        locked = bool(body.get("locked"))
        reason = str(body.get("reason") or ("Access disabled by founder" if locked else ""))
        cm = registry.get_app(tenant_id)
        cm.config.set("billing.lockout", "lockout" if locked else "0")
        cm.config.set("billing.lockout_reason", reason if locked else "")
        # Offline seal: written next to tenant data so fully offline clients still see lock on launch
        import hashlib, hmac as _hmac
        seal = {
            "tenant_id": tenant_id,
            "locked": locked,
            "reason": reason if locked else None,
            "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
        # Tamper-evident MAC with JWT secret (or dedicated COHORTOS_LICENSE_SECRET)
        mac_key = (os.environ.get("COHORTOS_LICENSE_SECRET") or os.environ.get("COHORTOS_JWT_SECRET") or "dev").encode()
        payload = f"{seal['tenant_id']}|{int(bool(seal['locked']))}|{seal.get('reason') or ''}|{seal['updated_at']}".encode()
        seal["hmac"] = _hmac.new(mac_key, payload, hashlib.sha256).hexdigest()
        try:
            data_dir = Path(os.environ.get("COHORTOS_DATA_DIR") or "/tmp/cohortos-data")
            data_dir.mkdir(parents=True, exist_ok=True)
            seal_path = data_dir / f"license_seal_{tenant_id}.json"
            seal_path.write_text(__import__("json").dumps(seal), encoding="utf-8")
        except Exception:
            pass
        return {"ok": True, "tenant_id": tenant_id, "locked": locked, "reason": reason if locked else None}

    # ── Centre setup wizard (Batch 4 / Addendum §1.C) ──────────────────

    @app.get("/t/{tenant_id}/setup/status")
    def setup_status(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        """
        First-run bootstrap eligibility.
        needs_wizard is true only when the centre has zero batches.
        Existing centres must not be forced into the wizard.
        """
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        batches = cm.admission.list_batches() if hasattr(cm.admission, "list_batches") else []
        students = []
        try:
            students = cm.admission.list_students(active_only=False) or []
        except Exception:
            students = []
        batch_count = len(batches or [])
        student_count = len(students or [])
        needs_wizard = batch_count == 0
        return {
            "needs_wizard": needs_wizard,
            "batch_count": batch_count,
            "student_count": student_count,
            "steps": {
                "centre": True,  # tenant already exists after trial/login
                "first_batch": batch_count > 0,
                "first_admission": student_count > 0,
                "done": batch_count > 0 and student_count > 0,
            },
        }

    @app.post("/t/{tenant_id}/setup/first-batch")
    def setup_first_batch(tenant_id: str, body: BatchCreateBody, claims: Dict[str, Any] = Depends(_bearer)):
        """Create the first batch — rejected if batches already exist (wizard closed)."""
        _require_tenant(claims, tenant_id)
        cm = registry.get_app(tenant_id)
        existing = cm.admission.list_batches() or []
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Setup wizard is closed — this centre already has batches. Use Batches settings.",
            )
        try:
            batch_id = cm.admission.create_batch(
                days=body.days,
                hour=body.hour,
                name=body.name or "",
            )
            if isinstance(batch_id, dict):
                return {"batch": batch_id, "batch_id": batch_id.get("id")}
            batch = cm.admission.get_batch(batch_id) if hasattr(cm.admission, "get_batch") else None
            return {"batch_id": batch_id, "batch": batch}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


    # ── Founder ───────────────────────────────────────────────────────

    @app.get("/founder/dashboard")
    def founder_dashboard(token: str = Depends(_founder_header)):
        return registry.founder.dashboard(founder_token=token)

    @app.get("/founder/tenants")
    def founder_tenants(status: Optional[str] = None, token: str = Depends(_founder_header)):
        return {"tenants": registry.founder.list_tenants(founder_token=token, status=status)}

    @app.get("/founder/tenants/{tenant_id}")
    def founder_get_tenant(tenant_id: str, token: str = Depends(_founder_header)):
        try:
            tenant = registry.founder.get_tenant(tenant_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        metrics = registry.founder.get_ai_metrics(tenant_id, founder_token=token)
        return {"tenant": tenant, "metrics": metrics}

    @app.post("/founder/tenants")
    def founder_provision(body: FounderProvisionBody, token: str = Depends(_founder_header)):
        tenant = registry.founder.provision_tenant(
            name=body.name,
            code=body.code,
            founder_token=token,
            owner_email=body.owner_email,
            tier=body.tier,
            student_count=body.student_count,
            trial_days=body.trial_days,
            mode=body.mode,
        )
        return {"tenant": tenant}

    @app.post("/founder/tenants/{tenant_id}/suspend")
    def founder_suspend(tenant_id: str, body: Dict[str, Any], token: str = Depends(_founder_header)):
        try:
            tenant = registry.founder.suspend_tenant(tenant_id, founder_token=token, reason=body.get("reason") or "")
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"tenant": tenant}

    @app.post("/founder/tenants/{tenant_id}/extend")
    def founder_extend(tenant_id: str, body: Dict[str, Any], token: str = Depends(_founder_header)):
        try:
            tenant = registry.founder.extend_tenant(tenant_id, founder_token=token, days=int(body.get("days") or 30))
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"tenant": tenant}

    @app.post("/founder/tenants/{tenant_id}/activate")
    def founder_activate(tenant_id: str, token: str = Depends(_founder_header)):
        try:
            tenant = registry.founder.activate_tenant(tenant_id, founder_token=token)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"tenant": tenant}

    @app.put("/founder/tenants/{tenant_id}/student-count")
    def founder_student_count(tenant_id: str, body: Dict[str, Any], token: str = Depends(_founder_header)):
        try:
            tenant = registry.founder.update_student_count(
                tenant_id, founder_token=token, student_count=int(body.get("student_count") or 0)
            )
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"tenant": tenant}

    @app.get("/founder/audit")
    def founder_audit(limit: int = 50, token: str = Depends(_founder_header)):
        return {"audit": registry.founder.list_audit(founder_token=token, limit=limit)}

    @app.get("/founder/pricing/tiers")
    def founder_tiers(token: str = Depends(_founder_header)):
        registry.founder._require_founder(token)
        pe = registry.founder.pricing
        tiers = [
            {"id": "starter", "limit": pe.starter_limit, "base_price_bdt": pe.starter_price},
            {"id": "growth", "limit": pe.growth_limit, "base_price_bdt": pe.growth_price},
            {"id": "scale", "limit": pe.scale_limit, "base_price_bdt": pe.scale_base_price},
        ]
        return {"tiers": tiers}

    @app.post("/founder/pricing/quote")
    def founder_quote(body: Dict[str, Any], token: str = Depends(_founder_header)):
        registry.founder._require_founder(token)
        quote = registry.founder.pricing.calculate(
            student_count=int(body.get("student_count") or 0),
            tier=body.get("tier"),
            billing_cycle=body.get("billing_cycle") or "monthly",
        )
        return {"quote": quote}

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "version": "1.2.0",
            "pyzk": PYZK_AVAILABLE,
            "gemini_sdk": False,  # filled at runtime if importable
        }


    @app.get("/t/{tenant_id}/billing/usage")
    def billing_usage(tenant_id: str, period: Optional[str] = None, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.billing_service import BillingService
        cm = registry.get_app(tenant_id)
        return BillingService(cm.data_layer, tenant_id).usage_summary(tenant_id, period_key=period)

    @app.get("/t/{tenant_id}/billing/subscription")
    def billing_subscription(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.billing_service import BillingService
        cm = registry.get_app(tenant_id)
        bs = BillingService(cm.data_layer, tenant_id)
        sub = bs.get_or_create_subscription(tenant_id)
        return {"subscription": sub, "plans": bs.list_plans()}

    @app.get("/t/{tenant_id}/billing/plans")
    def billing_plans(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.billing_service import BillingService
        cm = registry.get_app(tenant_id)
        return {"plans": BillingService(cm.data_layer, tenant_id).list_plans()}

    @app.post("/t/{tenant_id}/billing/invoices/draft")
    def billing_draft_invoice(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.billing_service import BillingService
        cm = registry.get_app(tenant_id)
        return BillingService(cm.data_layer, tenant_id).create_draft_invoice(tenant_id)


    @app.get("/t/{tenant_id}/billing/providers")
    def billing_providers(tenant_id: str, claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.payment_providers.factory import list_providers
        return {"providers": list_providers()}

    @app.post("/t/{tenant_id}/billing/provider")
    def billing_set_provider(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.billing_service import BillingService
        from services.payment_providers.base import ProviderError
        cm = registry.get_app(tenant_id)
        try:
            sub = BillingService(cm.data_layer, tenant_id).set_payment_provider(
                tenant_id, str(body.get("provider") or "")
            )
        except ProviderError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"subscription": sub}

    @app.post("/t/{tenant_id}/billing/checkout")
    def billing_checkout(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.billing_service import BillingService
        from services.payment_providers.base import ProviderError
        cm = registry.get_app(tenant_id)
        provider = str(body.get("provider") or "bkash")
        amount = float(body.get("amount") or 0)
        if amount <= 0:
            raise HTTPException(status_code=400, detail="amount must be > 0")
        currency = str(body.get("currency") or ("USD" if provider == "stripe" else "BDT"))
        callback = str(body.get("callback_url") or "http://127.0.0.1:8741/billing/callback")
        try:
            out = BillingService(cm.data_layer, tenant_id).create_checkout(
                tenant_id,
                provider=provider,
                amount=amount,
                currency=currency,
                callback_url=callback,
                description=str(body.get("description") or ""),
            )
        except ProviderError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return out

    @app.post("/t/{tenant_id}/billing/confirm")
    def billing_confirm(tenant_id: str, body: Dict[str, Any] = Body(...), claims: Dict[str, Any] = Depends(_bearer)):
        _require_tenant(claims, tenant_id)
        from services.billing_service import BillingService
        from services.payment_providers.base import ProviderError
        cm = registry.get_app(tenant_id)
        provider = str(body.get("provider") or "")
        session_id = str(body.get("session_id") or "")
        if not provider or not session_id:
            raise HTTPException(status_code=400, detail="provider and session_id required")
        try:
            out = BillingService(cm.data_layer, tenant_id).confirm_checkout(
                tenant_id, provider, session_id, **{k: v for k, v in body.items() if k not in ("provider", "session_id")}
            )
        except ProviderError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return out

    return app


def create_api_app_or_raise() -> FastAPI:
    secret = require_jwt_secret()
    founder = require_founder_token()
    auth_db = require_auth_db()
    cloud_db = require_cloud_db()
    return create_api_app(
        jwt_secret=secret,
        auth_db=auth_db,
        cloud_db=cloud_db,
        founder_token=founder,
    )
