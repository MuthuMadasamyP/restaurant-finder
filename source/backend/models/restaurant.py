from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    """Request body for the /api/search endpoint."""

    location: str = Field(..., min_length=5, description="City, neighborhood, or address to search")
    radius_km: float = Field(default=5.0, ge=0.5, le=50.0, description="Search radius in kilometers")
    max_results: int = Field(default=10, ge=1, le=100, description="Number of restaurants to return")

    @field_validator("location")
    @classmethod
    def location_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Location cannot be blank")
        return v.strip()


class Restaurant(BaseModel):
    """A single restaurant record extracted from Google Maps."""

    name: str
    rating: str = "N/A"
    address: str = "N/A"
    phone: str = "N/A"
    category: str = "N/A"
    website: str = "N/A"
    maps_url: str = "N/A"

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    """Response body returned by /api/search."""

    success: bool
    location: str
    radius_km: float
    total_found: int
    restaurants: list[Restaurant]
    message: str = ""


class RestaurantDetailRequest(BaseModel):
    """Request body for fetching one restaurant detail page."""

    maps_url: str = Field(..., min_length=10)


class ExportRequest(BaseModel):
    """Request body for the /api/export endpoint."""

    restaurants: list[Restaurant]
    location: str = "Unknown"
