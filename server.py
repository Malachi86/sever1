
import json
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# --- Firebase Initialization ---
try:
    # Path for Render secret file
    cred_path = "/etc/secrets/google_credentials.json"
    if not os.path.exists(cred_path):
        # Fallback for local development
        cred_path = "firebase-credentials.json"
        
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase initialized successfully.")
except Exception as e:
    print(f"Firebase initialization failed: {e}")
    db = None


app = Flask(__name__)

# --- CORS Configuration ---
CORS(app, supports_credentials=True)

def log_audit(action, user, details):
    if not db:
        print("Audit Error: Firestore not initialized.")
        return

    db.collection('audit').add({
        "timestamp": datetime.datetime.utcnow().isoformat() + 'Z',
        "action": action,
        "user": user,
        "details": details
    })

@app.route("/")
def index():
    if db:
        return "Server is up and running. Firestore is connected."
    else:
        return "Server is up and running, but Firestore connection failed."

@app.route("/health")
def health_check():
    return jsonify({
        "status": "ok",
        "firebase": db is not None,
        "timestamp": datetime.datetime.utcnow().isoformat() + 'Z'
    })

# --- User Management ---
@app.route("/api/users", methods=['GET'])
def get_users():
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500
    users_ref = db.collection('users')
    docs = users_ref.stream()
    users = [doc.to_dict() for doc in docs]
    return jsonify(users)

@app.route("/api/users/<string:usn_emp>", methods=['DELETE'])
def delete_user(usn_emp):
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500

    try:
        users_ref = db.collection('users')
        query = users_ref.where('usn_emp', '==', usn_emp).limit(1)
        docs = query.stream()

        doc_to_delete = None
        for doc in docs:
            doc_to_delete = doc
            break

        if not doc_to_delete:
            return jsonify({"error": "User not found"}), 404

        doc_to_delete.reference.delete()
        log_audit("User Deletion", "Admin", f"User with usn_emp {usn_emp} deleted.")
        return jsonify({"message": "User deleted successfully"}), 200

    except Exception as e:
        log_audit("User Deletion Failed", "Admin", f"Error deleting user {usn_emp}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/teachers", methods=['GET'])
def get_teachers():
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500
    users_ref = db.collection('users')
    query = users_ref.where('role', '==', 'teacher')
    docs = query.stream()
    teachers = {doc.id: doc.to_dict() for doc in docs}
    return jsonify(teachers)

@app.route("/api/login", methods=['POST'])
def login():
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500
        
    data = request.get_json()
    usn_emp = data.get("usn_emp")
    password = data.get("password")

    if not usn_emp or not password:
        return jsonify({"error": "Missing USN/Employee ID or password"}), 400

    users_ref = db.collection('users')
    query = users_ref.where('usn_emp', '==', usn_emp).limit(1)
    results = query.stream()
    
    user_data = None
    doc_id = None
    for doc in results:
        user_data = doc.to_dict()
        doc_id = doc.id
        break 

    if not user_data:
        log_audit("Failed Login", usn_emp, f"User {usn_emp} not found.")
        return jsonify({"error": "User not found"}), 404

    if user_data.get("password") == password:
        user_info = user_data.copy()
        user_info.pop("password", None)
        user_info['id'] = doc_id
        log_audit("User Login", usn_emp, f"User {usn_emp} logged in successfully.")
        return jsonify(user_info)
    else:
        log_audit("Failed Login", usn_emp, f"Failed login attempt for user {usn_emp}.")
        return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/register", methods=['POST'])
def register():
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500

    data = request.get_json()
    usn_emp = data.get("usn_emp")
    
    users_ref = db.collection('users')
    query = users_ref.where('usn_emp', '==', usn_emp).limit(1)
    if any(query.stream()):
        return jsonify({"error": "User with this USN/EMP already exists"}), 409

    new_user_data = {
        "name": data.get("name") or data.get("fullName"),
        "usn_emp": usn_emp,
        "password": data.get("password"),
        "role": data.get("role")
    }
    if new_user_data['role'] == 'teacher':
        new_user_data['subjects'] = []
    
    db.collection('users').add(new_user_data)
    
    log_audit("User Registration", usn_emp, f"New user {usn_emp} registered as {new_user_data['role']}.")
    return jsonify({"message": "User created successfully"}), 201

# --- Enrollments ---
@app.route("/api/enrollments", methods=['GET', 'POST'])
def handle_enrollments():
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500
    
    enrollments_ref = db.collection('enrollments')

    if request.method == 'GET':
        docs = enrollments_ref.stream()
        enrollments = [doc.to_dict() for doc in docs]
        return jsonify(enrollments)
    else: # POST
        data = request.get_json()
        student_usn = data.get("student_usn")

        # Check for existing pending or approved enrollment
        existing_enrollment_query = enrollments_ref.where('student_usn', '==', student_usn).where('subject_name', '==', data.get("subject_name")).where('status', 'in', ['Pending', 'Approved'])
        if any(existing_enrollment_query.stream()):
            return jsonify({"error": "You already have a pending or approved enrollment for this subject."}), 409
        
        # Get student and teacher details
        users_ref = db.collection('users')
        student_query = users_ref.where('usn_emp', '==', student_usn).limit(1)
        student = next((doc.to_dict() for doc in student_query.stream()), None)

        teacher_query = users_ref.where('usn_emp', '==', data.get("teacher_usn")).limit(1)
        teacher = next((doc.to_dict() for doc in teacher_query.stream()), None)

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
        
        db.collection('enrollments').add(new_enrollment)
        log_audit("Enrollment Request", student_usn, f"Student {student_usn} requested to enroll in {data.get('subject_name')}.")
        return jsonify({"message": "Enrollment request submitted"}), 201

@app.route("/api/enrollments/<string:enrollment_id>", methods=['PUT'])
def update_enrollment_status(enrollment_id):
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500
        
    data = request.get_json()
    new_status = data.get("status")
    if new_status not in ["Approved", "Declined"]:
        return jsonify({"error": "Invalid status"}), 400
    
    enrollment_ref = db.collection('enrollments').document(enrollment_id)
    enrollment = enrollment_ref.get()

    if not enrollment.exists:
        return jsonify({"error": "Enrollment not found"}), 404
        
    enrollment_ref.update({'status': new_status})
    log_audit("Enrollment Update", "Admin/Teacher", f"Enrollment for {enrollment.to_dict()['student_usn']} in {enrollment.to_dict()['subject_name']} set to {new_status}.")
    return jsonify({"message": f"Enrollment {new_status.lower()}"})

# --- Lab/Room Requests ---
@app.route("/api/requests", methods=['GET', 'POST'])
def handle_requests():
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500
    
    requests_ref = db.collection('requests')

    if request.method == 'GET':
        docs = requests_ref.stream()
        requests = [doc.to_dict() for doc in docs]
        return jsonify(requests)
    else: # POST
        data = request.get_json()
        new_request = {
            **data,
            "status": "Pending",
            "requested_at": datetime.datetime.utcnow().isoformat() + 'Z'
        }
        update_time, request_ref = requests_ref.add(new_request)
        new_request['id'] = request_ref.id
        
        log_audit("Resource Request", data.get('student'), f"Request for {data.get('type')} created.")
        return jsonify(new_request), 201

@app.route("/api/requests/<string:request_id>", methods=['PUT'])
def update_request_status(request_id):
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500

    data = request.get_json()
    new_status = data.get("status")
    if new_status not in ["Approved", "Declined"]:
        return jsonify({"error": "Invalid status"}), 400

    request_ref = db.collection('requests').document(request_id)
    if not request_ref.get().exists:
        return jsonify({"error": "Request not found"}), 404
    
    request_ref.update({'status': new_status})
    log_audit("Request Update", "Admin", f"Request {request_id} status updated to {new_status}.")
    return jsonify({"message": f"Request {new_status.lower()}"})

# --- Subjects ---
@app.route("/api/subjects", methods=['GET'])
def get_subjects():
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500
    
    subjects_ref = db.collection('subjects')
    docs = subjects_ref.stream()
    subjects = [doc.to_dict() for doc in docs]
    return jsonify(subjects)

# --- Attendance ---
@app.route("/api/attendance", methods=['GET', 'POST'])
def handle_attendance():
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500

    attendance_ref = db.collection('attendance')

    if request.method == 'GET':
        docs = attendance_ref.stream()
        attendance = [doc.to_dict() for doc in docs]
        return jsonify(attendance)
    else: # POST
        data = request.get_json()
        new_record = {
            **data,
            "timestamp": datetime.datetime.utcnow().isoformat() + 'Z'
        }
        
        update_time, record_ref = attendance_ref.add(new_record)
        new_record['id'] = record_ref.id
        log_audit("Attendance Marked", data.get('teacher_id'), f"Attendance marked for subject {data.get('subject')}.")
        return jsonify(new_record), 201

# --- Library ---
@app.route("/api/library/books", methods=['GET'])
def get_library_books():
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500
    
    books_ref = db.collection('library_books')
    docs = books_ref.stream()
    books = [doc.to_dict() for doc in docs]
    return jsonify(books)

@app.route("/api/library/borrow-requests", methods=['GET', 'POST'])
def handle_borrow_requests():
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500
    
    borrow_requests_ref = db.collection('borrow_requests')
    
    if request.method == 'GET':
        docs = borrow_requests_ref.stream()
        requests = [doc.to_dict() for doc in docs]
        return jsonify(requests)
    else: # POST
        data = request.get_json()
        new_borrow_request = {
            **data,
            "status": "Pending",
            "requested_at": datetime.datetime.utcnow().isoformat() + 'Z'
        }
        
        update_time, req_ref = borrow_requests_ref.add(new_borrow_request)
        new_borrow_request['id'] = req_ref.id
        log_audit("Borrow Request", data.get('student'), f"Book {data.get('book_barcode')} requested.")
        return jsonify(new_borrow_request), 201

@app.route("/api/library/borrow-requests/<string:request_id>", methods=['PUT'])
def update_borrow_request(request_id):
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500

    data = request.get_json()
    action = data.get("action") # "Approve" or "Decline"
    
    borrow_request_ref = db.collection('borrow_requests').document(request_id)
    req = borrow_request_ref.get()
    
    if not req.exists:
        return jsonify({"error": "Borrow request not found"}), 404

    req_data = req.to_dict()

    if action == "Approve":
        days = int(data.get('days', 7))
        due_date = datetime.datetime.utcnow() + datetime.timedelta(days=days)
        
        borrow_request_ref.update({
            'status': 'Approved',
            'due_date': due_date.isoformat() + 'Z'
        })

        books_ref = db.collection('library_books')
        book_query = books_ref.where('barcode', '==', req_data.get('book_barcode')).limit(1)
        book_doc = next(book_query.stream(), None)

        if book_doc:
            book_doc.reference.update({
                'status': 'Borrowed',
                'borrowed_by': req_data['student'],
                'due_date': due_date.isoformat() + 'Z'
            })

        db.collection('borrow_records').add({
            "book_barcode": req_data['book_barcode'],
            "book_title": req_data['book_title'],
            "student": req_data['student'],
            "student_name": req_data['student_name'],
            "borrowed_at": datetime.datetime.utcnow().isoformat() + 'Z',
            "due_date": due_date.isoformat() + 'Z',
            "returned_at": None
        })
        log_audit("Borrow Request Approved", "Librarian", f"Request {request_id} approved.")
    elif action == "Decline":
        borrow_request_ref.update({
            'status': 'Declined',
            'admin_feedback': data.get('feedback', '')
        })
        log_audit("Borrow Request Declined", "Librarian", f"Request {request_id} declined.")
    else:
        return jsonify({"error": "Invalid action"}), 400
        
    return jsonify(borrow_request_ref.get().to_dict())

@app.route("/api/library/return", methods=['POST'])
def return_book():
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500

    data = request.get_json()
    barcode = data.get("barcode")
    
    books_ref = db.collection('library_books')
    book_query = books_ref.where('barcode', '==', barcode).where('status', '==', 'Borrowed').limit(1)
    book_doc = next(book_query.stream(), None)
    
    if not book_doc:
        return jsonify({"error": "Borrowed book with this barcode not found"}), 404
        
    book_data = book_doc.to_dict()
    student_id = book_data['borrowed_by']
    
    book_doc.reference.update({
        'status': 'Available',
        'borrowed_by': None,
        'due_date': None
    })

    records_ref = db.collection('borrow_records')
    record_query = records_ref.where('book_barcode', '==', barcode).where('student', '==', student_id).where('returned_at', '==', None).limit(1)
    record_doc = next(record_query.stream(), None)

    if record_doc:
        record_doc.reference.update({
            'returned_at': datetime.datetime.utcnow().isoformat() + 'Z'
        })

    log_audit("Book Return", "Librarian", f"Book {barcode} returned by {student_id}.")
    return jsonify({"message": "Book returned successfully"})

# --- Missing Routes ---
@app.route("/api/books", methods=['GET'])
def get_books():
    return get_library_books()

@app.route("/api/audit", methods=['GET'])
def get_audit():
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500
    
    audit_ref = db.collection('audit')
    docs = audit_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
    audit_logs = [doc.to_dict() for doc in docs]
    return jsonify(audit_logs)

@app.route("/api/reservations", methods=['GET'])
def get_reservations():
    if not db:
        return jsonify({"error": "Firestore not initialized"}), 500
    
    reservations_ref = db.collection('reservations')
    docs = reservations_ref.stream()
    reservations = [doc.to_dict() for doc in docs]
    return jsonify(reservations)

# --- Audit Log (Kept for compatibility) ---
@app.route("/api/audit-log", methods=['GET'])
def get_audit_log():
    return get_audit()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)
