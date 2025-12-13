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
    cred = credentials.Certificate("google_credentials.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"Error initializing Firebase: {e}")
    db = None

# Health check endpoint for Render
@app.route("/")
def health_check():
    return "Server is up and running!"

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

        users_ref = db.collection('users')
        query = users_ref.where('usn_emp', '==', usn_emp).limit(1)
        user_docs = list(query.stream())

        if not user_docs:
            return jsonify({"error": "User not found"}), 404

        user = user_docs[0].to_dict()

        if user.get("password") == password:
            return jsonify({"message": "Login successful", "user": user})
        else:
            return jsonify({"error": "Invalid credentials"}), 401

    except Exception as e:
        return jsonify({"error": f"An error occurred: {e}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=False)
