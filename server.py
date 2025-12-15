
import json
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import datetime

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

DB_DIR = os.path.join(os.path.dirname(__file__))
USERS_FILE = os.path.join(DB_DIR, 'users.json')
ENROLLMENTS_FILE = os.path.join(DB_DIR, 'enrollments.json')

def read_data(file_path):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def write_data(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

@app.route("/")
def health_check():
    return "Server is up and running with local JSON database."

@app.route("/api/users", methods=['GET'])
def get_users():
    users = read_data(USERS_FILE)
    for user in users:
        if user.get('role') == 'teacher' and 'subjects' not in user:
            user['subjects'] = []
    return jsonify(users)

@app.route("/api/login", methods=['POST'])
def login():
    data = request.get_json()
    usn_emp = data.get("usn_emp")
    password = data.get("password")

    if not usn_emp or not password:
        return jsonify({"error": "Missing USN/Employee ID or password"}), 400

    users = read_data(USERS_FILE)
    user = next((u for u in users if u.get('usn_emp') == usn_emp), None)

    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.get("password") == password:
        user_info = user.copy()
        user_info.pop("password", None)
        return jsonify(user_info)
    else:
        return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/register", methods=['POST'])
def register():
    data = request.get_json()
    users = read_data(USERS_FILE)
    
    usn_emp = data.get("usn_emp")
    if any(u.get('usn_emp') == usn_emp for u in users):
        return jsonify({"error": "User with this USN/EMP already exists"}), 409

    new_user = {
        "name": data.get("name") or data.get("fullName"),
        "usn_emp": usn_emp,
        "password": data.get("password"),
        "role": data.get("role")
    }
    
    if new_user['role'] == 'teacher':
        new_user['subjects'] = []

    users.append(new_user)
    write_data(USERS_FILE, users)
    return jsonify({"message": "User created successfully"}), 201

@app.route("/api/enrollments", methods=['POST'])
def create_enrollment():
    data = request.get_json()
    student_usn = data.get("student_usn")
    teacher_usn = data.get("teacher_usn")
    subject_name = data.get("subject_name")

    if not all([student_usn, teacher_usn, subject_name]):
        return jsonify({"error": "Missing required fields for enrollment"}), 400

    enrollments = read_data(ENROLLMENTS_FILE)
    
    if any(
        e.get('student_usn') == student_usn and
        e.get('teacher_usn') == teacher_usn and
        e.get('subject_name') == subject_name and
        e.get('status') in ['Pending', 'Approved']
        for e in enrollments
    ):
        return jsonify({"error": "You already have a pending or approved enrollment for this subject."}), 409

    users = read_data(USERS_FILE)
    student = next((u for u in users if u.get('usn_emp') == student_usn), None)
    teacher = next((u for u in users if u.get('usn_emp') == teacher_usn), None)

    if not student or not teacher:
        return jsonify({"error": "Invalid student or teacher ID"}), 404

    new_enrollment = {
        "student_usn": student_usn,
        "student_name": student.get('name'),
        "teacher_usn": teacher_usn,
        "teacher_name": teacher.get('name'),
        "subject_name": subject_name,
        "status": "Pending",
        "requested_at": datetime.datetime.utcnow().isoformat() + 'Z'
    }
    
    enrollments.append(new_enrollment)
    write_data(ENROLLMENTS_FILE, enrollments)
    return jsonify({"message": "Enrollment request submitted successfully"}), 201

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)

