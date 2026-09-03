import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.seo.seo_service import SeoService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meta-data", tags=["Public SEO & Platform Metadata"])

@router.get("/public")
async def get_public_seo_metadata(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Returns public SEO meta-data, Open Graph, Twitter cards, schema markup and verification tags.
    Publicly accessible for Next.js layout, landing page, search crawlers, and social preview bots.
    """
    try:
        data = await SeoService.get_seo_metadata(db)
        return data
    except Exception as e:
        logger.error(f"Failed to fetch public SEO metadata: {e}")
        return SeoService.DEFAULT_SEO_CONFIG
