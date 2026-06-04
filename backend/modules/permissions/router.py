from fastapi import APIRouter, Depends

from backend.core.portal_permission_engine import get_permission_snapshot
from backend.modules.auth.router import get_current_user

router = APIRouter(prefix="/api/permissions", tags=["Permissions"])


@router.get("/me")
def get_my_permissions(current_user: dict = Depends(get_current_user)):
    return {
        "status": "success",
        "data": get_permission_snapshot(current_user),
    }
