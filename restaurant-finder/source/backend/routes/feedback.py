from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models.admin_data import (
    ChennaiFavouriteHotel,
    CoimbatoreFavouriteHotel,
    Feedback,
    MaduraiFavouriteHotel,
    StarHotel,
    User,
)
from models.admin_schemas import FeedbackCreate, FavouriteRestaurantCreate, StarHotelCreate
from services.auth import get_current_user

router = APIRouter()


@router.post("/feedback")
def create_feedback(
    request: FeedbackCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    db.add(Feedback(user_id=user.id, rating=request.rating, feedback=request.feedback.strip()))
    db.commit()
    return {"message": "Feedback submitted successfully"}


@router.post("/star-hotels")
def create_star_hotel(
    request: StarHotelCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    db.add(StarHotel(user_id=user.id, hotel_name=request.hotel_name.strip(), area=request.area.strip()))
    db.commit()
    return {"message": "Hotel added to favorites"}


def favourite_model_for_area(area: str):
    normalized = area.lower()
    if "chennai" in normalized:
        return ChennaiFavouriteHotel
    if "madurai" in normalized:
        return MaduraiFavouriteHotel
    if "coimbatore" in normalized:
        return CoimbatoreFavouriteHotel
    return None


@router.post("/favorite-restaurant")
def create_favourite_restaurant(
    request: FavouriteRestaurantCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    model = favourite_model_for_area(request.search_area)
    if model is None:
        return {"message": "Favourite restaurant is tracked only for Chennai, Madurai, and Coimbatore."}

    db.add(
        model(
            user_id=user.id,
            restaurant_name=request.restaurant_name.strip(),
            search_area=request.search_area.strip(),
            rating=(request.rating or "").strip() or None,
            category=(request.category or "").strip() or None,
            address=(request.address or "").strip() or None,
        )
    )
    db.commit()
    return {"message": "Favourite restaurant saved"}
