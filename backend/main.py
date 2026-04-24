from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from datetime import datetime

app = Flask(__name__)
CORS(app) # Allows the frontend to talk to the backend securely

# 1. Database Connection
mongo_uri = os.environ.get("ATLAS_URI")
client = MongoClient(mongo_uri)
db = client.farm_management

# Collections
labours_db = db.labours
attendance_db = db.attendance
config_db = db.config
transactions_db = db.transactions

# --- APP ROUTES ---

# 1. Set and Get Daily Wage & Rice Rates
@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'POST':
        data = request.json
        config_db.update_one(
            {"setting": "rates"}, 
            {"$set": {"daily_wage": float(data['wage']), "daily_rice_kg": float(data['rice'])}}, 
            upsert=True
        )
        return jsonify({"message": "Rates updated successfully!"})
    else:
        config = config_db.find_one({"setting": "rates"})
        if not config:
            return jsonify({"daily_wage": 0, "daily_rice_kg": 0})
        return jsonify({"daily_wage": config["daily_wage"], "daily_rice_kg": config["daily_rice_kg"]})

# 2. Add Labourers & View Their Calculated Accounts
@app.route('/api/labours', methods=['GET', 'POST'])
def handle_labours():
    if request.method == 'POST':
        data = request.json
        new_labour = {
            "name": data['name'],
            "type": data['type'], # 'all_time' or 'occasional'
            "created_at": datetime.now().strftime("%Y-%m-%d")
        }
        labours_db.insert_one(new_labour)
        return jsonify({"message": "Labourer added!"})
    
    else:
        # Get the current rates to calculate earnings
        config = config_db.find_one({"setting": "rates"}) or {"daily_wage": 0, "daily_rice_kg": 0}
        wage_rate = config["daily_wage"]
        rice_rate = config["daily_rice_kg"]
        
        labours = list(labours_db.find())
        results = []
        
        for lab in labours:
            lab_id = str(lab['_id'])
            
            # Count how many days they were present
            present_days = attendance_db.count_documents({"labour_id": lab_id, "status": "present"})
            
            # Calculate Total Earnings
            amount_earned = present_days * wage_rate
            rice_earned = present_days * rice_rate
            
            # Calculate What They Have Already Taken (Advances)
            txns = list(transactions_db.find({"labour_id": lab_id}))
            amount_taken = sum(t['amount'] for t in txns if t['type'] == 'money')
            rice_taken = sum(t['amount'] for t in txns if t['type'] == 'rice')
            
            results.append({
                "id": lab_id,
                "name": lab["name"],
                "type": lab["type"], # Helps frontend split into the two sections
                "days_worked": present_days,
                "amount_earned": amount_earned,
                "amount_taken": amount_taken,
                "amount_due": amount_earned - amount_taken, # Auto-calculated Due
                "rice_earned": rice_earned,
                "rice_taken": rice_taken,
                "rice_due": rice_earned - rice_taken # Auto-calculated Rice Due
            })
        return jsonify(results)

# 3. Mark Attendance (With Season Filters)
@app.route('/api/attendance', methods=['POST'])
def mark_attendance():
    data = request.json
    record = {
        "labour_id": data['labour_id'],
        "date": data['date'], # Format: YYYY-MM-DD
        "status": data['status'], # 'present' or 'absent'
        "season": data.get('season', 'none') # boro_chas, boro_harvest, borsa_chas, borsa_harvest
    }
    # Update if already marked today, otherwise create new
    attendance_db.update_one(
        {"labour_id": data['labour_id'], "date": data['date']},
        {"$set": record},
        upsert=True
    )
    return jsonify({"message": f"Marked {data['status']} for {data['date']}"})

# 4. Give Advance Money or Rice (Ledger)
@app.route('/api/transactions', methods=['POST'])
def add_transaction():
    data = request.json
    record = {
        "labour_id": data['labour_id'],
        "type": data['type'], # 'money' or 'rice'
        "amount": float(data['amount']),
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    transactions_db.insert_one(record)
    return jsonify({"message": f"{data['type'].capitalize()} recorded successfully!"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
