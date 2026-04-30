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
        config_db.update_one({"setting": "rates"}, {"$set": request.json}, upsert=True)
        return jsonify({"message": "Rates updated successfully!"})
    else:
        config = config_db.find_one({"setting": "rates"}) or {}
        if '_id' in config: del config['_id']
        return jsonify(config)

@app.route('/api/labours', methods=['GET', 'POST'])
def handle_labours():
    if request.method == 'POST':
        data = request.json
        new_labour = {"name": data['name'], "type": data['type'], "created_at": datetime.now().strftime("%Y-%m-%d")}
        labours_db.insert_one(new_labour)
        return jsonify({"message": "Labourer added!"})
    
    else:
        # NEW: 'period' allows "2026" (Year), "2026-04" (Month), or "2026-04-27" (Day)
        period_filter = request.args.get('period', request.args.get('year', 'all'))
        date_filter = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
        
        config = config_db.find_one({"setting": "rates"}) or {}
        labours = list(labours_db.find())
        
        att_query = {"status": "present"}
        txn_query = {}
        if period_filter != 'all':
            att_query["date"] = {"$regex": f"^{period_filter}"}
            txn_query["date"] = {"$regex": f"^{period_filter}"}
            
        all_attendance = list(attendance_db.find(att_query))
        all_txns = list(transactions_db.find(txn_query))
        today_attendance = list(attendance_db.find({"date": date_filter}))

        att_dict = {}
        for a in all_attendance: att_dict.setdefault(a['labour_id'], []).append(a)
            
        txn_dict = {}
        for t in all_txns: txn_dict.setdefault(t['labour_id'], []).append(t)
            
        today_dict = {a['labour_id']: a for a in today_attendance}

        results = []
        for lab in labours:
            lab_id = str(lab['_id'])
            
            l_att = att_dict.get(lab_id, [])
            l_txn = txn_dict.get(lab_id, [])
            l_today = today_dict.get(lab_id, {})
            
            current_status = l_today.get('status', 'none')
            current_mode = l_today.get('all_time_mode', 'none')
            current_season = l_today.get('season', 'none')
            
            att_harvest = 0
            att_non = 0
            total_days = len(l_att)
            
            if lab["type"] == "all_time":
                att_harvest = sum(1 for a in l_att if a.get('all_time_mode') == 'harvest')
                att_non = total_days - att_harvest
                
                wage_h = float(config.get("all_time_wage_harvest", 0))
                rice_h = float(config.get("all_time_rice_harvest", 0))
                wage_n = float(config.get("all_time_wage_non_harvest", 0))
                rice_n = float(config.get("all_time_rice_non_harvest", 0))
                
                amount_earned = (att_harvest * wage_h) + (att_non * wage_n)
                rice_earned = (att_harvest * rice_h) + (att_non * rice_n)
            else:
                amount_earned = total_days * float(config.get("occasional_wage", 0))
                rice_earned = total_days * float(config.get("occasional_rice", 0))
            
            amount_taken = sum(t['amount'] for t in l_txn if t['type'] == 'money')
            rice_taken = sum(t['amount'] for t in l_txn if t['type'] == 'rice')
            
            results.append({
                "id": lab_id, "name": lab["name"], "type": lab["type"], 
                "current_status": current_status, "current_mode": current_mode, "current_season": current_season,
                "days_worked": total_days, "harvest_days": att_harvest, "non_harvest_days": att_non,
                "amount_earned": amount_earned, "amount_taken": amount_taken, "amount_due": amount_earned - amount_taken, 
                "rice_earned": rice_earned, "rice_taken": rice_taken, "rice_due": rice_earned - rice_taken
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
        labours_db.update_one({"_id": ObjectId(lab_id)}, {"$set": {"name": request.json['name']}})
        return jsonify({"message": "Updated"})

@app.route('/api/attendance', methods=['POST'])
def mark_attendance():
    data = request.json
    record = {
        "labour_id": data['labour_id'], "date": data['date'], "status": data['status'], 
        "season": data.get('season', 'none'), "all_time_mode": data.get('all_time_mode', 'non_harvest')
    }
    attendance_db.update_one({"labour_id": data['labour_id'], "date": data['date']}, {"$set": record}, upsert=True)
    return jsonify({"message": "Attendance marked"})

@app.route('/api/transactions', methods=['POST'])
def add_transaction():
    data = request.json
    transactions_db.insert_one({
        "labour_id": data['labour_id'], "type": data['type'], 
        "amount": float(data['amount']), "date": datetime.now().strftime("%Y-%m-%d")
    })
    return jsonify({"message": "Recorded"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
