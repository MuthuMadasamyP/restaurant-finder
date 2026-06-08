import logging
import re
from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.admin_data import SearchHistory, SearchResult, Setting, StarHotelSearch, User
from models.restaurant import Restaurant, SearchRequest, SearchResponse
from services.scraper import scrape_restaurants_threaded
from services.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)
STAR_HOTEL_PATTERN = re.compile(r"\b([1-7])\s*-?\s*star(?:\s+hotel|\s+hotels)?\b", re.IGNORECASE)


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Search for top restaurants near a location",
    description=(
        "Launches a headless Playwright browser, searches Google Maps for restaurants "
        "near the given location, and returns the requested number of results sorted by rating. "
        "This endpoint may take longer for larger result sets."
    ),
)
async def search_restaurants_endpoint(
    request: SearchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SearchResponse:
    """
    POST /api/search
    Body: { "location": "Chennai, India", "radius_km": 5, "max_results": 20 }
    """
    logger.info(
        "Search request - user=%s location=%r radius=%s km max_results=%s",
        user.email,
        request.location,
        request.radius_km,
        request.max_results,
    )

    settings = db.get(Setting, 1) or Setting(id=1)
    effective_limit = settings.daily_search_limit
    today_start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    today_count = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == user.id, SearchHistory.searched_at >= today_start)
        .count()
    )
    if today_count >= effective_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily search limit reached. Your current limit is {effective_limit} searches per day. "
                "Upgrade to Premium for more searches."
            ),
        )

    try:
        raw_results = await scrape_restaurants_threaded(
            request.location,
            request.radius_km,
            request.max_results,
        )
    except Exception as exc:
        logger.error("Scraper raised an unhandled exception: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Scraping failed unexpectedly: {exc}",
        )

    logger.info("Returning %d restaurants for %r", len(raw_results), request.location)
    restaurants = [Restaurant(**r) for r in raw_results]
    search_history = SearchHistory(
        user_id=user.id,
        location=request.location,
        radius=request.radius_km,
        restaurant_count=request.max_results,
    )
    db.add(search_history)
    db.flush()
    for index, restaurant in enumerate(restaurants, start=1):
        db.add(
            SearchResult(
                search_history_id=search_history.id,
                rank=index,
                name=restaurant.name or "Unknown restaurant",
                rating=restaurant.rating,
                category=restaurant.category,
                address=restaurant.address,
                phone=restaurant.phone,
                website=restaurant.website,
            )
        )
    star_match = STAR_HOTEL_PATTERN.search(request.location)
    if star_match:
        db.add(
            StarHotelSearch(
                user_id=user.id,
                star_term=f"{star_match.group(1)} star hotel",
                search_area=request.location,
            )
        )
    db.commit()

    return SearchResponse(
        success=True,
        location=request.location,
        radius_km=request.radius_km,
        total_found=len(restaurants),
        restaurants=restaurants,
        message=(
            f"Found {len(restaurants)} restaurants near {request.location}."
            if restaurants
            else "No restaurants found. Try a different location or increase the radius."
        ),
    )


@router.get("/search/history")
def user_search_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == user.id)
        .order_by(SearchHistory.searched_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": item.id,
            "search_area": item.location,
            "radius": item.radius,
            "restaurant_count": item.restaurant_count,
            "searched_at": item.searched_at.isoformat() if item.searched_at else None,
        }
        for item in rows
    ]


@router.get("/search/history/{history_id}/restaurants")
async def user_search_history_restaurants(
    history_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    history = (
        db.query(SearchHistory)
        .filter(SearchHistory.id == history_id, SearchHistory.user_id == user.id)
        .first()
    )
    if not history:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search history not found")

    rows = (
        db.query(SearchResult)
        .filter(SearchResult.search_history_id == history.id)
        .order_by(SearchResult.rank)
        .all()
    )
    if not rows:
        try:
            raw_results = await scrape_restaurants_threaded(
                history.location,
                history.radius,
                history.restaurant_count,
            )
        except Exception as exc:
            logger.error("History result rebuild failed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not load restaurants for this history: {exc}",
            ) from exc

        restaurants = [Restaurant(**r) for r in raw_results]
        for index, restaurant in enumerate(restaurants, start=1):
            db.add(
                SearchResult(
                    search_history_id=history.id,
                    rank=index,
                    name=restaurant.name or "Unknown restaurant",
                    rating=restaurant.rating,
                    category=restaurant.category,
                    address=restaurant.address,
                    phone=restaurant.phone,
                    website=restaurant.website,
                )
            )
        db.commit()
        rows = (
            db.query(SearchResult)
            .filter(SearchResult.search_history_id == history.id)
            .order_by(SearchResult.rank)
            .all()
        )

    return {
        "history": {
            "id": history.id,
            "search_area": history.location,
            "radius": history.radius,
            "restaurant_count": history.restaurant_count,
            "searched_at": history.searched_at.isoformat() if history.searched_at else None,
        },
        "restaurants": [
            {
                "rank": item.rank,
                "name": item.name,
                "rating": item.rating,
                "category": item.category,
                "address": item.address,
                "phone": item.phone,
                "website": item.website,
            }
            for item in rows
        ],
    }
