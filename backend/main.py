from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import os

app = Flask(__name__)
CORS(app) # This allows your frontend PWA to talk to this backend

# 1. Connect to your MongoDB Atlas
# Render will securely inject your ATLAS_URI here later
mongo_uri = os.environ.get("ATLAS_URI")
client = MongoClient(mongo_uri)
db = client.farm_management # Name of your database

# 2. Set up our Collections (like tables in Excel)
labours_db = db.labours
attendance_db = db.attendance
config_db = db.config
ledger_db = db.ledger

# --- ROUTES (The tasks your app can perform) ---

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"message": "Python Labour Management System is Running!"})

# Task A: Set the Daily Wage and Rice Config
@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.json
    # Upsert means update if it exists, insert if it doesn't
    config_db.update_one(
        {"setting": "rates"}, 
        {"$set": {"daily_wage": data['wage'], "daily_rice_kg": data['rice']}}, 
        upsert=True
    )
    return jsonify({"message": "Rates updated successfully!"})

# Task B: Add a New Labourer
@app.route('/api/labour', methods=['POST'])
def add_labour():
    data = request.json
    # Expects: name, type (all_time or occasional)
    new_labour = {
        "name": data['name'],
        "type": data['type'], 
        "total_days_worked": 0,
        "total_amount_earned": 0,
        "total_amount_taken": 0,
        "total_rice_earned": 0,
        "total_rice_taken": 0
    }
    labours_db.insert_one(new_labour)
    return jsonify({"message": f"{data['name']} added successfully!"})

# We must tell Render how to run this file
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
