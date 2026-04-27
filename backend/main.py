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
        config_db.update_one(
            {"setting": "rates"}, 
            {"$set": {
                "all_time_wage": float(data.get('all_time_wage', 0)), 
                "all_time_rice": float(data.get('all_time_rice', 0)),
                "occasional_wage": float(data.get('occasional_wage', 0)),
                "occasional_rice": float(data.get('occasional_rice', 0))
            }}, 
            upsert=True
        )
        return jsonify({"message": "Rates updated successfully!"})
    else:
        config = config_db.find_one({"setting": "rates"}) or {}
        return jsonify({
            "all_time_wage": config.get("all_time_wage", 0),
            "all_time_rice": config.get("all_time_rice", 0),
            "occasional_wage": config.get("occasional_wage", 0),
            "occasional_rice": config.get("occasional_rice", 0)
        })

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
        # NEW: Catch the year filter from the app
        year_filter = request.args.get('year', 'all')
        
        config = config_db.find_one({"setting": "rates"}) or {}
        all_time_wage = config.get("all_time_wage", 0)
        all_time_rice = config.get("all_time_rice", 0)
        occasional_wage = config.get("occasional_wage", 0)
        occasional_rice = config.get("occasional_rice", 0)
        
        labours = list(labours_db.find())
        results = []
        
        for lab in labours:
            lab_id = str(lab['_id'])
            
            # Setup database queries
            att_query = {"labour_id": lab_id, "status": "present"}
            txn_query = {"labour_id": lab_id}
            
            # Apply Year Filter if not set to 'all'
            if year_filter != 'all':
                att_query["date"] = {"$regex": f"^{year_filter}"}
                txn_query["date"] = {"$regex": f"^{year_filter}"}
                
            present_days = attendance_db.count_documents(att_query)
            
            if lab["type"] == "all_time":
                wage_rate = all_time_wage
                rice_rate = all_time_rice
            else:
                wage_rate = occasional_wage
                rice_rate = occasional_rice
                
            amount_earned = present_days * wage_rate
            rice_earned = present_days * rice_rate
            
            txns = list(transactions_db.find(txn_query))
            amount_taken = sum(t['amount'] for t in txns if t['type'] == 'money')
            rice_taken = sum(t['amount'] for t in txns if t['type'] == 'rice')
            
            results.append({
                "id": lab_id,
                "name": lab["name"],
                "type": lab["type"], 
                "days_worked": present_days,
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
        return jsonify({"message": "Worker & records deleted"})
        
    if request.method == 'PUT':
        data = request.json
        labours_db.update_one(
            {"_id": ObjectId(lab_id)},
            {"$set": {"name": data['name']}}
        )
        return jsonify({"message": "Worker name updated"})

@app.route('/api/attendance', methods=['POST'])
def mark_attendance():
    data = request.json
    record = {
        "labour_id": data['labour_id'],
        "date": data['date'], 
        "status": data['status'], 
        "season": data.get('season', 'none') 
    }
    attendance_db.update_one(
        {"labour_id": data['labour_id'], "date": data['date']},
        {"$set": record},
        upsert=True
    )
    return jsonify({"message": f"Marked {data['status']} for {data['date']}"})

@app.route('/api/transactions', methods=['POST'])
def add_transaction():
    data = request.json
    record = {
        "labour_id": data['labour_id'],
        "type": data['type'],
        "amount": float(data['amount']),
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    transactions_db.insert_one(record)
    return jsonify({"message": f"{data['type'].capitalize()} recorded successfully!"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
