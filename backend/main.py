from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

mongo_uri = os.environ.get("ATLAS_URI")
client = MongoClient(mongo_uri)
db = client.farm_management

labours_db = db.labours
attendance_db = db.attendance
config_db = db.config
transactions_db = db.transactions

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'POST':
        data = request.json
        # Dynamically update only the fields sent in the request
        config_db.update_one(
            {"setting": "rates"}, 
            {"$set": data}, 
            upsert=True
        )
        return jsonify({"message": "Rates updated successfully!"})
    else:
        config = config_db.find_one({"setting": "rates"}) or {}
        # Remove the MongoDB ID so it doesn't break the JSON response
        if '_id' in config:
            del config['_id']
        return jsonify(config)

@app.route('/api/labours', methods=['GET', 'POST'])
def handle_labours():
    if request.method == 'POST':
        data = request.json
        new_labour = {
            "name": data['name'],
            "type": data['type'],
            "created_at": datetime.now().strftime("%Y-%m-%d")
        }
        labours_db.insert_one(new_labour)
        return jsonify({"message": "Labourer added!"})
    
    else:
        year_filter = request.args.get('year', 'all')
        date_filter = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
        
        config = config_db.find_one({"setting": "rates"}) or {}
        
        labours = list(labours_db.find())
        results = []
        
        for lab in labours:
            lab_id = str(lab['_id'])
            
            # 1. Fetch Today's Status (For Button Colors)
            today_record = attendance_db.find_one({"labour_id": lab_id, "date": date_filter})
            current_status = today_record['status'] if today_record else "none"
            
            # 2. Setup Year Queries
            att_query = {"labour_id": lab_id, "status": "present"}
            txn_query = {"labour_id": lab_id}
            if year_filter != 'all':
                att_query["date"] = {"$regex": f"^{year_filter}"}
                txn_query["date"] = {"$regex": f"^{year_filter}"}
                
            # 3. Calculate Earnings based on Worker Type
            if lab["type"] == "all_time":
                # Separate Harvest vs Non-Harvest days
                att_harvest = attendance_db.count_documents({**att_query, "all_time_mode": "harvest"})
                att_non = attendance_db.count_documents({**att_query, "all_time_mode": {"$ne": "harvest"}}) # $ne means 'not equal'
                
                wage_h = float(config.get("all_time_wage_harvest", 0))
                rice_h = float(config.get("all_time_rice_harvest", 0))
                wage_n = float(config.get("all_time_wage_non_harvest", 0))
                rice_n = float(config.get("all_time_rice_non_harvest", 0))
                
                amount_earned = (att_harvest * wage_h) + (att_non * wage_n)
                rice_earned = (att_harvest * rice_h) + (att_non * rice_n)
                total_days = att_harvest + att_non
            else:
                total_days = attendance_db.count_documents(att_query)
                amount_earned = total_days * float(config.get("occasional_wage", 0))
                rice_earned = total_days * float(config.get("occasional_rice", 0))
            
            # 4. Calculate Taken and Due
            txns = list(transactions_db.find(txn_query))
            amount_taken = sum(t['amount'] for t in txns if t['type'] == 'money')
            rice_taken = sum(t['amount'] for t in txns if t['type'] == 'rice')
            
            results.append({
                "id": lab_id,
                "name": lab["name"],
                "type": lab["type"], 
                "current_status": current_status, # NEW: Sent to UI for button color
                "days_worked": total_days,
                "amount_earned": amount_earned,
                "amount_taken": amount_taken,
                "amount_due": amount_earned - amount_taken, 
                "rice_earned": rice_earned,
                "rice_taken": rice_taken,
                "rice_due": rice_earned - rice_taken
            })
        return jsonify(results)

@app.route('/api/labours/<lab_id>', methods=['PUT', 'DELETE'])
def modify_labour(lab_id):
    if request.method == 'DELETE':
        labours_db.delete_one({"_id": ObjectId(lab_id)})
        attendance_db.delete_many({"labour_id": lab_id})
        transactions_db.delete_many({"labour_id": lab_id})
        return jsonify({"message": "Deleted"})
    if request.method == 'PUT':
        data = request.json
        labours_db.update_one({"_id": ObjectId(lab_id)}, {"$set": {"name": data['name']}})
        return jsonify({"message": "Updated"})

@app.route('/api/attendance', methods=['POST'])
def mark_attendance():
    data = request.json
    record = {
        "labour_id": data['labour_id'],
        "date": data['date'], 
        "status": data['status'], 
        "season": data.get('season', 'none'),
        "all_time_mode": data.get('all_time_mode', 'non_harvest') # NEW: Tracks if this day was a harvest day
    }
    attendance_db.update_one(
        {"labour_id": data['labour_id'], "date": data['date']},
        {"$set": record},
        upsert=True
    )
    return jsonify({"message": "Attendance marked"})

@app.route('/api/transactions', methods=['POST'])
def add_transaction():
    data = request.json
    transactions_db.insert_one({
        "labour_id": data['labour_id'],
        "type": data['type'],
        "amount": float(data['amount']),
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    return jsonify({"message": "Recorded"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
