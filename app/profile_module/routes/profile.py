from fastapi import APIRouter, Depends, status
from app.auth_module.models.user import User
from app.core.dependencies import get_current_user
from app.profile_module.schemas.profile import ProfileBase, ProfileResponse, ProfileUpdate
from app.profile_module.services.profile_service import ProfileService
from app.profile_module.core.dependencies import get_profile_service

profileRouter = APIRouter(prefix="/profiles", tags=["Profiles"])

@profileRouter.post(
    "/",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create User Profile",
    description="""Create a new profile for the authenticated user.
    
    **Authentication Required:**
    - Header: `Authorization`
    - Value: `Bearer <your_jwt_token>`
    
    **Enum Fields:**
    - `gender`: Male, Female
    - `fitness_goal`: Lose Weight, Maintain Weight, Build Muscle
    - `activity_level`: Sedentary, Lightly Active, Moderately Active, Very Active, Extra Active
    """,
    responses={
        201: {"description": "Profile created successfully"},
        401: {"description": "Unauthorized - Invalid or missing token"},
        400: {"description": "Bad Request - Invalid data or profile already exists"}
    }
)
def create_profile(
    profile_data: ProfileBase,
    current_user: User = Depends(get_current_user),
    profile_service: ProfileService = Depends(get_profile_service)
):
    """
    Create a profile for the current user.
    
    Required fields with enum values:
    - **gender**: Male | Female
    - **fitness_goal**: Lose Weight | Maintain Weight | Build Muscle
    - **activity_level**: Sedentary | Lightly Active | Moderately Active | Very Active | Extra Active
    """
    return profile_service.create_profile(current_user.id, profile_data)

@profileRouter.get(
    "/me",
    response_model=ProfileResponse,
    summary="Get My Profile",
    description="""Get the authenticated user's profile information.
    
    **Authentication Required:**
    - Header: `Authorization`
    - Value: `Bearer <your_jwt_token>`
    """,
    responses={
        200: {"description": "Profile retrieved successfully"},
        401: {"description": "Unauthorized - Invalid or missing token"},
        404: {"description": "Profile not found"}
    }
)
def get_my_profile(
    current_user: User = Depends(get_current_user),
    profile_service: ProfileService = Depends(get_profile_service)
):
    """
    Get the current user's profile.
    """
    return profile_service.get_profile_by_user_id(current_user.id)

@profileRouter.put(
    "/me",
    response_model=ProfileResponse,
    summary="Update My Profile",
    description="""Update the authenticated user's profile information.
    
    **Authentication Required:**
    - Header: `Authorization`
    - Value: `Bearer <your_jwt_token>`
    
    **Enum Fields (Optional):**
    - `gender`: Male, Female
    - `fitness_goal`: Lose Weight, Maintain Weight, Build Muscle
    - `activity_level`: Sedentary, Lightly Active, Moderately Active, Very Active, Extra Active
    
    All fields are optional - only send the fields you want to update.
    """,
    responses={
        200: {"description": "Profile updated successfully"},
        401: {"description": "Unauthorized - Invalid or missing token"},
        404: {"description": "Profile not found"}
    }
)
def update_my_profile(
    profile_data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    profile_service: ProfileService = Depends(get_profile_service)
):
    """
    Update the current user's profile.
    
    Optional enum fields:
    - **gender**: Male | Female
    - **fitness_goal**: Lose Weight | Maintain Weight | Build Muscle
    - **activity_level**: Sedentary | Lightly Active | Moderately Active | Very Active | Extra Active
    """
    return profile_service.update_profile(current_user.id, profile_data)
