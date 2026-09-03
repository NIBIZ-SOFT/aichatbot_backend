import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.cms.public_pages_service import PublicPagesService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public-pages", tags=["Public Company & Legal Pages"])

@router.get("/{slug}")
async def get_public_page_content(slug: str, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Returns public page content, metadata, and markdown for /about, /privacy, /terms.
    Publicly accessible without authentication.
    """
    page = await PublicPagesService.get_page(db, slug)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page '{slug}' not found.")
    return page
