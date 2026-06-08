from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from source.backend.database import get_db
from models.admin_data import (
    ChennaiFavouriteHotel,
    CoimbatoreFavouriteHotel,
    Feedback,
    MaduraiFavouriteHotel,
    SearchHistory,
    Setting,
    StarHotel,
    StarHotelSearch,
    User,
)
from models.admin_schemas import SettingsResponse, SettingsUpdate, UserResponse, UserStatusUpdate
from services.auth import get_current_admin

router = APIRouter()


def get_settings(db: Session) -> Setting:
    settings = db.get(Setting, 1)
    if not settings:
        settings = Setting(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def serialize_dt(value):
    return value.isoformat() if value else None


def favourite_model_for_area(area: str):
    normalized = area.lower()
    if "chennai" in normalized:
        return ChennaiFavouriteHotel
    if "madurai" in normalized:
        return MaduraiFavouriteHotel
    if "coimbatore" in normalized:
        return CoimbatoreFavouriteHotel
    return None


@router.get("/admin/settings", response_model=SettingsResponse)
def read_settings(_admin=Depends(get_current_admin), db: Session = Depends(get_db)) -> SettingsResponse:
    settings = get_settings(db)
    return SettingsResponse(
        daily_search_limit=settings.daily_search_limit,
        special_event_limit=settings.special_event_limit,
        event_enabled=settings.event_enabled,
        active_user_days=settings.active_user_days,
        effective_limit=settings.special_event_limit if settings.event_enabled else settings.daily_search_limit,
    )


@router.put("/admin/settings", response_model=SettingsResponse)
def update_settings(
    request: SettingsUpdate,
    _admin=Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> SettingsResponse:
    settings = get_settings(db)
    settings.daily_search_limit = request.daily_search_limit
    settings.special_event_limit = request.special_event_limit
    settings.event_enabled = request.event_enabled
    settings.active_user_days = request.active_user_days
    db.commit()
    return read_settings(_admin, db)


@router.get("/admin/summary")
def summary(_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    settings = get_settings(db)
    active_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.active_user_days)
    active_users = db.query(User).filter(User.last_login_at >= active_cutoff, User.status == "active").count()
    total_users = db.query(User).count()

    return {
        "users": total_users,
        "feedback": db.query(Feedback).count(),
        "star_hotels": db.query(StarHotelSearch).count(),
        "active_users": active_users,
        "inactive_users": max(total_users - active_users, 0),
    }


@router.get("/admin/users", response_model=list[UserResponse])
def users(_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.patch("/admin/users/{user_id}", response_model=UserResponse)
def update_user_status(
    user_id: int,
    request: UserStatusUpdate,
    _admin=Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="User not found")
    user.status = request.status
    db.commit()
    db.refresh(user)
    return user


@router.delete("/admin/users/{user_id}")
def delete_user(
    user_id: int,
    _admin=Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="User not found")

    for model in (
        Feedback,
        SearchHistory,
        StarHotel,
        StarHotelSearch,
        ChennaiFavouriteHotel,
        MaduraiFavouriteHotel,
        CoimbatoreFavouriteHotel,
    ):
        db.query(model).filter(model.user_id == user_id).delete(synchronize_session=False)

    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}


@router.get("/admin/search-history")
def search_history(_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(SearchHistory, User)
        .join(User, SearchHistory.user_id == User.id)
        .order_by(SearchHistory.searched_at.desc())
        .limit(500)
        .all()
    )
    return [
        {
            "user_name": user.name,
            "search_location": history.location,
            "radius": history.radius,
            "restaurant_count": history.restaurant_count,
            "searched_at": serialize_dt(history.searched_at),
        }
        for history, user in rows
    ]


@router.get("/admin/feedback")
def feedback(_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(Feedback, User)
        .join(User, Feedback.user_id == User.id)
        .order_by(Feedback.created_at.desc())
        .limit(500)
        .all()
    )
    return [
        {
            "user_name": user.name,
            "rating": item.rating,
            "feedback": item.feedback,
            "created_at": serialize_dt(item.created_at),
        }
        for item, user in rows
    ]


@router.get("/admin/star-hotels")
def star_hotels(_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(StarHotelSearch, User)
        .join(User, StarHotelSearch.user_id == User.id)
        .order_by(StarHotelSearch.created_at.desc())
        .limit(500)
        .all()
    )
    return [
        {
            "user_name": user.name,
            "hotel_name": item.star_term,
            "area": item.search_area,
            "created_at": serialize_dt(item.created_at),
        }
        for item, user in rows
    ]


@router.get("/admin/star-hotel-favourites")
def star_hotel_favourites(_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(StarHotel, User)
        .join(User, StarHotel.user_id == User.id)
        .order_by(StarHotel.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "user_name": user.name,
            "hotel_name": item.hotel_name,
            "location": item.area,
            "created_at": serialize_dt(item.created_at),
        }
        for item, user in rows
    ]


@router.get("/admin/area/{area_name}")
def area_analytics(area_name: str, _admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    histories = (
        db.query(SearchHistory, User)
        .join(User, SearchHistory.user_id == User.id)
        .filter(SearchHistory.location.ilike(f"%{area_name}%"))
        .order_by(SearchHistory.searched_at.desc())
        .all()
    )
    user_ids = {history.user_id for history, _user in histories}
    location_counts = Counter(history.location for history, _user in histories)
    star_hotel_count = (
        db.query(StarHotelSearch)
        .filter(StarHotelSearch.search_area.ilike(f"%{area_name}%"))
        .count()
    )
    favourite_model = favourite_model_for_area(area_name)
    favourites = db.query(favourite_model).all() if favourite_model else []
    favourite_counts = Counter(item.restaurant_name for item in favourites)

    return {
        "area": area_name,
        "total_users": len(user_ids),
        "total_search_count": len(histories),
        "star_hotel_count": star_hotel_count,
        "most_searched_locations": location_counts.most_common(10),
        "most_favourite_restaurants": favourite_counts.most_common(10),
        "searches": [
            {
                "user_name": user.name,
                "location": history.location,
                "radius": history.radius,
                "restaurant_count": history.restaurant_count,
                "searched_at": serialize_dt(history.searched_at),
            }
            for history, user in histories[:100]
        ],
    }


@router.get("/admin/analytics")
def analytics(_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    month_rows = (
        db.query(
            extract("year", SearchHistory.searched_at).label("year"),
            extract("month", SearchHistory.searched_at).label("month"),
            func.count(SearchHistory.id),
        )
        .group_by("year", "month")
        .order_by("year", "month")
        .all()
    )
    areas = ["Chennai", "Madurai", "Coimbatore"]
    area_months: dict[str, dict[str, int]] = {area: defaultdict(int) for area in areas}
    for area in areas:
        rows = (
            db.query(
                extract("year", SearchHistory.searched_at).label("year"),
                extract("month", SearchHistory.searched_at).label("month"),
                func.count(SearchHistory.id),
            )
            .filter(SearchHistory.location.ilike(f"%{area}%"))
            .group_by("year", "month")
            .order_by("year", "month")
            .all()
        )
        for year, month, count in rows:
            area_months[area][f"{int(year):04d}-{int(month):02d}"] = count

    settings = get_settings(db)
    active_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.active_user_days)
    active_users = db.query(User).filter(User.last_login_at >= active_cutoff, User.status == "active").count()
    total_users = db.query(User).count()

    daily_user_rows = (
        db.query(
            func.date(User.created_at).label("day"),
            func.count(User.id),
        )
        .group_by("day")
        .order_by("day")
        .all()
    )

    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    months = sorted(
        {f"{int(year):04d}-{int(month):02d}" for year, month, _count in month_rows}
        | {current_month}
    )
    month_counts = {
        f"{int(year):04d}-{int(month):02d}": count
        for year, month, count in month_rows
    }
    return {
        "months": months,
        "searches_per_month": [
            {"month": month, "count": month_counts.get(month, 0)}
            for month in months
        ],
        "area_series": {
            area: [area_months[area].get(month, 0) for month in months]
            for area in areas
        },
        "active_users": active_users,
        "inactive_users": max(total_users - active_users, 0),
        "daily_users": [
            {"day": str(day), "count": count}
            for day, count in daily_user_rows
        ],
    }
