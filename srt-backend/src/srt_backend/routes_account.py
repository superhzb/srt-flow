"""Account routes — self-serve data erasure (GDPR/Law 25 right to erasure).

``DELETE /api/account`` erases the authenticated user's identity + uploaded
content (see :func:`pkg_job_orch.api.erase_user`) and clears the session
cookie. Financial ledger rows are retained for tax/Stripe reconciliation.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pkg_auth.api import get_current_user
from pkg_auth.config import load_settings
from pkg_auth.models import User
from pkg_job_orch.api import erase_user, session_scope

__all__ = ["router"]

router = APIRouter(prefix="/account", tags=["account"])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    """Permanently erase the current user's account, jobs, and uploaded files."""
    ctx = request.app.state.job_ctx
    with session_scope() as session:
        erase_user(session, ctx.storage, user.id)
    settings = load_settings()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(settings.session_cookie_name)
    return response
