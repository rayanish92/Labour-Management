from fastapi import APIRouter
from app.database import users_collection
from app.models import User

router = APIRouter()

@router.post("/users")
def create_user(user: User):
    result = users_collection.insert_one(user.dict())
    return {"id": str(result.inserted_id)}

@router.get("/users")
def get_users():
    users = []
    for user in users_collection.find():
        user["_id"] = str(user["_id"])
        users.append(user)
    return users
