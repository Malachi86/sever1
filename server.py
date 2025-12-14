from flask import Flask, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import datetime

# Initialize Flask app
app = Flask(__name__)

# Enable CORS - Allow all origins for now for testing
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Initialize Firebase
try:
    # Make sure the path to your credentials file is correct
    cred = credentials.Certificate("google_credentials.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("--- Firebase Initialized Successfully ---")
except Exception as e:
    print(f"!!! Error initializing Firebase: {e} !!!")
    db = None

# Health check endpoint
@app.route("/")
def health_check():
    if db:
        return "Server is up and connected to Firebase."
    else:
        return "Server is up, but Firebase connection failed."

# API to get all users (Simplified)
@app.route("/api/users", methods=["GET"])
def get_users():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    try:
        users_ref = db.collection('users')
        docs = users_ref.stream()
        users = [doc.to_dict() for doc in docs]
        return jsonify(users)
    except Exception as e:
        print(f"!!! Error in /api/users: {e} !!!")
        return jsonify({"error": f"Failed to fetch users: {e}"}), 500

# API to check login credentials
@app.route("/api/login", methods=["POST"])
def login():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    try:
        data = request.get_json()
        usn_emp = data.get("usn_emp")
        password = data.get("password")

        if not usn_emp or not password:
            return jsonify({"error": "Missing USN/Employee ID or password"}), 400

        users_ref = db.collection('users')
        query = users_ref.where('usn_emp', '==', usn_emp).limit(1)
        user_docs = list(query.stream())

        if not user_docs:
            return jsonify({"error": "User not found"}), 404

        user = user_docs[0].to_dict()

        if user.get("password") == password:
            user.pop("password", None) 
            return jsonify({"message": "Login successful", "user": user})
        else:
            return jsonify({"error": "Invalid credentials"}), 401

    except Exception as e:
        print(f"!!! Error in /api/login: {e} !!!")
        return jsonify({"error": f"An error occurred: {e}"}), 500

# API to create a new user (Updated to handle teacher subjects)
@app.route("/api/register", methods=["POST"])
def register():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    try:
        data = request.get_json()
        usn_emp = data.get("usn_emp")
        role = data.get("role")

        # Check if user already exists
        users_ref = db.collection('users')
        doc_ref = users_ref.document(usn_emp)
        if doc_ref.get().exists:
            return jsonify({"error": "User with this USN/EMP already exists"}), 409

        # Create new user
        new_user = {
            "name": data.get("name") or data.get("fullName"),
            "usn_emp": usn_emp,
            "password": data.get("password"),
            "role": role
        }
        
        # If the new user is a teacher, add an empty subjects array
        if role == 'teacher':
            new_user['subjects'] = []

        doc_ref.set(new_user)
        return jsonify({"message": "User created successfully"}), 201

    except Exception as e:
        print(f"!!! Error in /api/register: {e} !!!")
        return jsonify({"error": f"An error occurred: {e}"}), 500

# API for enrollment
@app.route("/api/enrollments", methods=["POST"])
def create_enrollment():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    try:
        data = request.get_json()
        student_usn = data.get("student_usn")
        teacher_usn = data.get("teacher_usn")
        subject_name = data.get("subject_name")

        if not all([student_usn, teacher_usn, subject_name]):
            return jsonify({"error": "Missing required fields for enrollment"}), 400

        # Check for existing pending/approved enrollment
        enrollments_ref = db.collection('enrollments')
        existing_query = enrollments_ref.where('student_usn', '==', student_usn) \
                                        .where('teacher_usn', '==', teacher_usn) \
                                        .where('subject_name', '==', subject_name) \
                                        .where('status', 'in', ['Pending', 'Approved'])
        
        if len(list(existing_query.stream())) > 0:
            return jsonify({"error": "You already have a pending or approved enrollment for this subject."}), 409

        # Get student and teacher names
        student_doc = db.collection('users').document(student_usn).get()
        teacher_doc = db.collection('users').document(teacher_usn).get()

        if not student_doc.exists or not teacher_doc.exists:
             return jsonify({"error": "Invalid student or teacher ID"}), 404

        student_name = student_doc.to_dict().get('name')
        teacher_name = teacher_doc.to_dict().get('name')


        new_enrollment = {
            "student_usn": student_usn,
            "student_name": student_name,
            "teacher_usn": teacher_usn,
            "teacher_name": teacher_name,
            "subject_name": subject_name,
            "status": "Pending",
            "requested_at": datetime.datetime.utcnow().isoformat() + 'Z'
        }

        db.collection('enrollments').add(new_enrollment)
        
        return jsonify({"message": "Enrollment request submitted successfully"}), 201

    except Exception as e:
        print(f"!!! Error in /api/enrollments: {e} !!!")
        return jsonify({"error": f"An error occurred: {e}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=False)
