from flask import Flask, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore

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

# API to get all users
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
            # Don't send the password back to the client
            user.pop("password", None) 
            return jsonify({"message": "Login successful", "user": user})
        else:
            return jsonify({"error": "Invalid credentials"}), 401

    except Exception as e:
        print(f"!!! Error in /api/login: {e} !!!")
        return jsonify({"error": f"An error occurred: {e}"}), 500

# API to create a new user
@app.route("/api/register", methods=["POST"])
def register():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    try:
        data = request.get_json()
        usn_emp = data.get("usn_emp")
        
        # Check if user already exists
        users_ref = db.collection('users')
        query = users_ref.where('usn_emp', '==', usn_emp).limit(1)
        existing_users = list(query.stream())
        if existing_users:
            return jsonify({"error": "User with this USN/EMP already exists"}), 409

        # Create new user
        new_user = {
            "name": data.get("name") or data.get("fullName"),
            "usn_emp": usn_emp,
            "password": data.get("password"),
            "role": data.get("role")
        }
        users_ref.document(usn_emp).set(new_user)
        return jsonify({"message": "User created successfully"}), 201

    except Exception as e:
        print(f"!!! Error in /api/register: {e} !!!")
        return jsonify({"error": f"An error occurred: {e}"}), 500

if __name__ == '__main__':
    # Use Gunicorn for production, but app.run is fine for Render's environment
    # Render will use the start command `gunicorn server:app`
    # The host and port here are for local testing if you run `python server.py`
    app.run(host='0.0.0.0', port=10000, debug=False)
