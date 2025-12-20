
import json
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import datetime

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

DB_DIR = os.path.dirname(__file__)
USERS_FILE = os.path.join(DB_DIR, 'users.json')
ENROLLMENTS_FILE = os.path.join(DB_DIR, 'enrollments.json')
REQUESTS_FILE = os.path.join(DB_DIR, 'requests.json')
ATTENDANCE_FILE = os.path.join(DB_DIR, 'attendance.json')
SUBJECTS_FILE = os.path.join(DB_DIR, 'subjects.json')
AUDIT_FILE = os.path.join(DB_DIR, 'audit.json')
LIBRARY_BOOKS_FILE = os.path.join(DB_DIR, 'library_books.json')
BORROW_REQUESTS_FILE = os.path.join(DB_DIR, 'borrow_requests.json')
BORROW_RECORDS_FILE = os.path.join(DB_DIR, 'borrow_records.json')

def read_data(file_path):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def write_data(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def log_audit(action, user, details):
    audit_log = read_data(AUDIT_FILE)
    audit_log.append({
        "timestamp": datetime.datetime.utcnow().isoformat() + 'Z',
        "action": action,
        "user": user,
        "details": details
    })
    write_data(AUDIT_FILE, audit_log)

@app.route("/")
def health_check():
    return "Server is up and running with local JSON database."

# --- User Management ---
@app.route("/api/users", methods=['GET'])
def get_users():
    return jsonify(read_data(USERS_FILE))

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
        log_audit("User Login", usn_emp, f"User {usn_emp} logged in successfully.")
        return jsonify(user_info)
    else:
        log_audit("Failed Login", usn_emp, f"Failed login attempt for user {usn_emp}.")
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
    log_audit("User Registration", usn_emp, f"New user {usn_emp} registered as {new_user['role']}.")
    return jsonify({"message": "User created successfully"}), 201

# --- Enrollments ---
@app.route("/api/enrollments", methods=['GET', 'POST'])
def handle_enrollments():
    if request.method == 'GET':
        return jsonify(read_data(ENROLLMENTS_FILE))
    else: # POST
        data = request.get_json()
        student_usn = data.get("student_usn")
        enrollments = read_data(ENROLLMENTS_FILE)
        if any(e.get('student_usn') == student_usn and e.get('subject_name') == data.get("subject_name") and e.get('status') in ['Pending', 'Approved'] for e in enrollments):
            return jsonify({"error": "You already have a pending or approved enrollment for this subject."}), 409
        
        users = read_data(USERS_FILE)
        student = next((u for u in users if u.get('usn_emp') == student_usn), None)
        teacher = next((u for u in users if u.get('usn_emp') == data.get("teacher_usn")), None)
        if not student or not teacher:
            return jsonify({"error": "Invalid student or teacher ID"}), 404

        new_enrollment = {
            "student_usn": student_usn,
            "student_name": student.get('name'),
            "teacher_usn": data.get("teacher_usn"),
            "teacher_name": teacher.get('name'),
            "subject_name": data.get("subject_name"),
            "status": "Pending",
            "requested_at": datetime.datetime.utcnow().isoformat() + 'Z'
        }
        enrollments.append(new_enrollment)
        write_data(ENROLLMENTS_FILE, enrollments)
        log_audit("Enrollment Request", student_usn, f"Student {student_usn} requested to enroll in {data.get('subject_name')}.")
        return jsonify({"message": "Enrollment request submitted"}), 201

@app.route("/api/enrollments/<string:enrollment_id>", methods=['PUT'])
def update_enrollment_status(enrollment_id):
    data = request.get_json()
    new_status = data.get("status")
    if new_status not in ["Approved", "Declined"]:
        return jsonify({"error": "Invalid status"}), 400
    
    enrollments = read_data(ENROLLMENTS_FILE)
    enrollment = next((e for e in enrollments if e.get('student_usn') + e.get('subject_name') == enrollment_id), None)
    
    if not enrollment:
        return jsonify({"error": "Enrollment not found"}), 404
        
    enrollment['status'] = new_status
    write_data(ENROLLMENTS_FILE, enrollments)
    log_audit("Enrollment Update", "Admin/Teacher", f"Enrollment for {enrollment['student_usn']} in {enrollment['subject_name']} set to {new_status}.")
    return jsonify({"message": f"Enrollment {new_status.lower()}"})

# --- Lab/Room Requests ---
@app.route("/api/requests", methods=['GET', 'POST'])
def handle_requests():
    if request.method == 'GET':
        return jsonify(read_data(REQUESTS_FILE))
    else: # POST
        data = request.get_json()
        requests = read_data(REQUESTS_FILE)
        new_request = {
            "id": f"REQ{len(requests) + 1}",
            **data,
            "status": "Pending",
            "requested_at": datetime.datetime.utcnow().isoformat() + 'Z'
        }
        requests.append(new_request)
        write_data(REQUESTS_FILE, requests)
        log_audit("Resource Request", data.get('student'), f"Request for {data.get('type')} created.")
        return jsonify(new_request), 201

@app.route("/api/requests/<string:request_id>", methods=['PUT'])
def update_request_status(request_id):
    data = request.get_json()
    new_status = data.get("status")
    if new_status not in ["Approved", "Declined"]:
        return jsonify({"error": "Invalid status"}), 400

    requests = read_data(REQUESTS_FILE)
    req = next((r for r in requests if r.get('id') == request_id), None)
    if not req:
        return jsonify({"error": "Request not found"}), 404
    
    req['status'] = new_status
    write_data(REQUESTS_FILE, requests)
    log_audit("Request Update", "Admin", f"Request {request_id} status updated to {new_status}.")
    return jsonify({"message": f"Request {new_status.lower()}"})

# --- Subjects ---
@app.route("/api/subjects", methods=['GET'])
def get_subjects():
    return jsonify(read_data(SUBJECTS_FILE))

# --- Attendance ---
@app.route("/api/attendance", methods=['GET', 'POST'])
def handle_attendance():
    if request.method == 'GET':
        return jsonify(read_data(ATTENDANCE_FILE))
    else: # POST
        data = request.get_json()
        attendance_records = read_data(ATTENDANCE_FILE)
        new_record = {
            "id": f"ATT{len(attendance_records) + 1}",
            **data,
            "timestamp": datetime.datetime.utcnow().isoformat() + 'Z'
        }
        attendance_records.append(new_record)
        write_data(ATTENDANCE_FILE, attendance_records)
        log_audit("Attendance Marked", data.get('teacher_id'), f"Attendance marked for subject {data.get('subject')}.")
        return jsonify(new_record), 201

# --- Library ---
@app.route("/api/library/books", methods=['GET'])
def get_library_books():
    return jsonify(read_data(LIBRARY_BOOKS_FILE))

@app.route("/api/library/borrow-requests", methods=['GET', 'POST'])
def handle_borrow_requests():
    if request.method == 'GET':
        return jsonify(read_data(BORROW_REQUESTS_FILE))
    else: # POST
        data = request.get_json()
        borrow_requests = read_data(BORROW_REQUESTS_FILE)
        new_borrow_request = {
            "id": f"BR{len(borrow_requests) + 1}",
            **data,
            "status": "Pending",
            "requested_at": datetime.datetime.utcnow().isoformat() + 'Z'
        }
        borrow_requests.append(new_borrow_request)
        write_data(BORROW_REQUESTS_FILE, borrow_requests)
        log_audit("Borrow Request", data.get('student'), f"Book {data.get('book_barcode')} requested.")
        return jsonify(new_borrow_request), 201

@app.route("/api/library/borrow-requests/<string:request_id>", methods=['PUT'])
def update_borrow_request(request_id):
    data = request.get_json()
    action = data.get("action") # "Approve" or "Decline"
    
    borrow_requests = read_data(BORROW_REQUESTS_FILE)
    req = next((r for r in borrow_requests if r.get('id') == request_id), None)
    if not req:
        return jsonify({"error": "Borrow request not found"}), 404

    if action == "Approve":
        days = int(data.get('days', 7))
        due_date = datetime.datetime.utcnow() + datetime.timedelta(days=days)
        req['status'] = 'Approved'
        req['due_date'] = due_date.isoformat() + 'Z'

        books = read_data(LIBRARY_BOOKS_FILE)
        book = next((b for b in books if b.get('barcode') == req.get('book_barcode')), None)
        if book:
            book['status'] = 'Borrowed'
            book['borrowed_by'] = req['student']
            book['due_date'] = req['due_date']
            write_data(LIBRARY_BOOKS_FILE, books)
        
        records = read_data(BORROW_RECORDS_FILE)
        records.append({
            "id": f"REC{len(records) + 1}",
            "book_barcode": req['book_barcode'],
            "book_title": req['book_title'],
            "student": req['student'],
            "student_name": req['student_name'],
            "borrowed_at": datetime.datetime.utcnow().isoformat() + 'Z',
            "due_date": req['due_date'],
            "returned_at": None
        })
        write_data(BORROW_RECORDS_FILE, records)
        log_audit("Borrow Request Approved", "Librarian", f"Request {request_id} approved.")
    elif action == "Decline":
        req['status'] = 'Declined'
        req['admin_feedback'] = data.get('feedback', '')
        log_audit("Borrow Request Declined", "Librarian", f"Request {request_id} declined.")
    else:
        return jsonify({"error": "Invalid action"}), 400
        
    write_data(BORROW_REQUESTS_FILE, borrow_requests)
    return jsonify(req)

@app.route("/api/library/return", methods=['POST'])
def return_book():
    data = request.get_json()
    barcode = data.get("barcode")
    books = read_data(LIBRARY_BOOKS_FILE)
    book = next((b for b in books if b.get('barcode') == barcode and b.get('status') == 'Borrowed'), None)
    
    if not book:
        return jsonify({"error": "Borrowed book with this barcode not found"}), 404
        
    student_id = book['borrowed_by']
    book['status'] = 'Available'
    book['borrowed_by'] = None
    book['due_date'] = None
    write_data(LIBRARY_BOOKS_FILE, books)

    records = read_data(BORROW_RECORDS_FILE)
    record = next((r for r in reversed(records) if r.get('book_barcode') == barcode and r.get('student') == student_id and not r.get('returned_at')), None)
    if record:
        record['returned_at'] = datetime.datetime.utcnow().isoformat() + 'Z'
        write_data(BORROW_RECORDS_FILE, records)

    log_audit("Book Return", "Librarian", f"Book {barcode} returned by {student_id}.")
    return jsonify({"message": "Book returned successfully"})

# --- Audit Log ---
@app.route("/api/audit-log", methods=['GET'])
def get_audit_log():
    return jsonify(read_data(AUDIT_FILE))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)
