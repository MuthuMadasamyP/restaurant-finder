import io
import logging
import re
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from models.restaurant import ExportRequest
from services.exporter import export_to_excel

router = APIRouter()
logger = logging.getLogger(__name__)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post(
    "/export",
    summary="Export restaurant list to Excel (.xlsx)",
    description="Converts the provided restaurant list to a formatted Excel workbook.",
    responses={200: {"content": {XLSX_MIME: {}}, "description": "Formatted .xlsx file"}},
)
async def export_restaurants_endpoint(request: ExportRequest) -> StreamingResponse:
    if not request.restaurants:
        raise HTTPException(status_code=400, detail="No restaurant data to export.")

    logger.info("Export request - %d restaurants, location=%r", len(request.restaurants), request.location)

    try:
        xlsx_bytes = export_to_excel(request.restaurants, request.location)
    except Exception as exc:
        logger.error("Export failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}")

    safe_loc = re.sub(r"[^A-Za-z0-9_-]+", "_", request.location).strip("_")[:30] or "restaurants"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"restaurants_{safe_loc}_{timestamp}.xlsx"

    logger.info("Streaming %d bytes as %s", len(xlsx_bytes), filename)

    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
