from pymongo import MongoClient
import os

MONGO_URI = os.environ.get("MONGO_URL")

client = MongoClient(MONGO_URL)
db = client["pwa_db"]

users_collection = db["users"]
