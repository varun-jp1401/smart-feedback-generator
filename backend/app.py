from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import re
import requests
import time
import random
import pandas as pd
import mysql.connector
from mysql.connector import Error
from difflib import SequenceMatcher
from dotenv import load_dotenv
import traceback

# Load environment variables
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, static_folder='frontend', static_url_path='')

# Allow CORS from anywhere in production
CORS(app, resources={r"/*": {"origins": "*"}})

# Load spaCy model with error handling
nlp = None
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    print("✓ spaCy model loaded successfully")
except Exception as e:
    print(f"⚠️  Warning: spaCy model failed to load: {e}")
    print("App will continue with basic text processing")

# API configuration
TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"
TOGETHER_API_KEY = os.getenv("API_KEY")
MODEL_NAME = "deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free"

HEADERS = {
    "Authorization": f"Bearer {TOGETHER_API_KEY}",
    "Content-Type": "application/json"
} if TOGETHER_API_KEY else {}

def get_db_connection():
    """Get database connection using Railway environment variables"""
    try:
        connection = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST"),
            user=os.getenv("MYSQL_USER"), 
            password=os.getenv("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DATABASE"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
            charset='utf8mb4',
            autocommit=True,
            connect_timeout=10,
            connection_timeout=10
        )
        print("✓ Database connection successful")
        return connection
    except Error as e:
        print(f"❌ Database connection error: {e}")
        return None

def clean_response(text):
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

def extract_keywords(text, top_k=5):
    """Extract keywords with fallback if spaCy is not available"""
    if nlp:
        try:
            doc = nlp(text)
            keywords = list(set([chunk.text.lower() for chunk in doc.noun_chunks if len(chunk.text.strip()) > 2]))
            return keywords[:top_k]
        except Exception as e:
            print(f"spaCy processing error: {e}")
    
    # Fallback: simple word extraction
    words = [word.lower().strip() for word in text.split() if len(word.strip()) > 3]
    return list(set(words))[:top_k]

def find_missing_keywords(keywords, student_answer):
    student_answer = student_answer.lower()
    return [kw for kw in keywords if kw not in student_answer]

def calculate_question_score(ideal_answer, student_answer):
    """Calculate total score for a question (0-2 marks)"""
    if not student_answer or student_answer.strip().lower() in ["i don't know", "dont know", "no idea", ""]:
        return 0.0
    
    ideal_clean = ideal_answer.strip().lower()
    student_clean = student_answer.strip().lower()
    
    if ideal_clean == student_clean:
        return 2.0
    
    similarity = SequenceMatcher(None, ideal_clean, student_clean).ratio()
    
    if similarity >= 0.95:  
        return 2.0
    elif similarity >= 0.8: 
        return 1.5
    elif similarity >= 0.6:  
        return 1.0
    elif similarity >= 0.4:  
        return 0.5
    else:
        return 0.0

def build_prompt(question, ideal_answer, student_answer, missing_keywords):
    hint = ""
    if missing_keywords:
        hint = "It seems the student may have missed one or more important scientific ideas. Consider gently prompting them to revisit key parts of the process."

    return (
        f"You are a supportive but strict middle school science teacher giving feedback to students.\n\n"
        f"Question: {question}\n"
        f"Ideal Answer: {ideal_answer}\n"
        f"Student Answer: {student_answer}\n\n"
        f"{hint}\n\n"
        f"Write helpful, constructive feedback:\n"
        f"- If the answer is correct or very close, say it's correct.\n"
        f"- If they missed something important, hint at it without giving the keyword away.\n"
        f"- If there's a spelling mistake in important keywords, suggest checking it.\n"
        f"- Be friendly and encouraging.\n"
        f"- If the student doesn't know, tell them it's fine and move on."
    )

def generate_feedback(question, ideal_answer, student_answer):
    """Generate AI feedback with error handling"""
    if not TOGETHER_API_KEY:
        return "Feedback generation unavailable - API key not configured."
    
    try:
        keywords = extract_keywords(ideal_answer)
        missing = find_missing_keywords(keywords, student_answer)
        prompt = build_prompt(question, ideal_answer, student_answer, missing)

        payload = {
            "model": MODEL_NAME,
            "max_tokens": 1500,
            "temperature": 0.7,
            "top_p": 0.9,
            "messages": [
                {"role": "system", "content": "You are a helpful science teacher."},
                {"role": "user", "content": prompt}
            ]
        }

        response = requests.post(TOGETHER_API_URL, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        return clean_response(raw)
    except Exception as e:
        print(f"Feedback generation error: {e}")
        return f"Great attempt! Keep working on understanding the key concepts."

# Health check endpoint for Railway
@app.route("/health")
def health_check():
    status = {
        "status": "healthy",
        "message": "Smart Feedback Generator is running",
        "spacy_available": nlp is not None,
        "api_key_configured": bool(TOGETHER_API_KEY),
        "data_directory_exists": os.path.exists(os.path.join(BASE_DIR, "data"))
    }
    
    # Check database connection
    conn = get_db_connection()
    status["database_connected"] = conn is not None
    if conn:
        conn.close()
    
    # List data files for debugging
    data_dir = os.path.join(BASE_DIR, "data")
    if os.path.exists(data_dir):
        status["data_files"] = os.listdir(data_dir)
    
    return jsonify(status)

@app.route("/generate-feedback", methods=["POST"])
def feedback_api():
    try:
        data = request.get_json()
        question = data.get("question")
        ideal_answer = data.get("ideal_answer")
        student_answer = data.get("student_answer")

        if not all([question, ideal_answer, student_answer]):
            return jsonify({"error": "Missing input fields"}), 400

        feedback = generate_feedback(question, ideal_answer, student_answer)
        return jsonify({"feedback": feedback})
    except Exception as e:
        print(f"Feedback API error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/calculate-score", methods=["POST"])
def calculate_score():
    try:
        data = request.get_json()
        questions = data.get("questions")  
        answers = data.get("answers")      
        
        if not questions or not answers:
            return jsonify({"error": "Missing questions or answers"}), 400
        
        if len(questions) != len(answers):
            return jsonify({"error": "Mismatch in number of questions and answers"}), 400
        
        total_score = 0
        question_scores = []
        
        for i, (question_obj, student_answer) in enumerate(zip(questions, answers)):
            ideal_answer = question_obj.get("Answer", "")
            question_score = calculate_question_score(ideal_answer, student_answer)
            total_score += question_score
            
            question_scores.append({
                "question_number": i + 1,
                "score": question_score,
                "max_score": 2.0
            })
        
        max_total_score = len(questions) * 2.0
        percentage = (total_score / max_total_score) * 100 if max_total_score > 0 else 0
        
        return jsonify({
            "total_score": round(total_score, 1),
            "max_score": max_total_score,
            "percentage": round(percentage, 1),
            "question_scores": question_scores,
            "grade": get_letter_grade(percentage)
        })
    except Exception as e:
        print(f"Score calculation error: {e}")
        return jsonify({"error": "Internal server error"}), 500

def get_letter_grade(percentage):
    """Convert percentage to letter grade"""
    if percentage >= 90:
        return "A+"
    elif percentage >= 80:
        return "A"
    elif percentage >= 70:
        return "B"
    elif percentage >= 60:
        return "C"
    elif percentage >= 50:
        return "D"
    else:
        return "F"

@app.route("/register", methods=["POST"])
def register():
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")
        grade = data.get("grade")

        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            return jsonify({"error": "Username already exists."}), 400

        cursor.execute("INSERT INTO users (username, password, grade) VALUES (%s, %s, %s)", (username, password, grade))
        conn.commit()
        return jsonify({"message": "User registered successfully!"})
    except Exception as e:
        print(f"Registration error: {e}")
        return jsonify({"error": "Registration failed"}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500

        cursor = conn.cursor()
        cursor.execute("SELECT grade FROM users WHERE username=%s AND password=%s", (username, password))
        result = cursor.fetchone()
        if result:
            return jsonify({"message": "Login successful!", "grade": result[0]})
        else:
            return jsonify({"error": "Invalid username or password"}), 401
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({"error": "Login failed"}), 500
    finally:
        if 'cursor' in locals(): 
            cursor.close()
        if 'conn' in locals(): 
            conn.close()

@app.route("/get-questions", methods=["POST"])
def get_questions():
    try:
        data = request.get_json()
        username = data.get("username")
        if not username:
            return jsonify({"error": "Username is required"}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500

        cursor = conn.cursor()
        cursor.execute("SELECT grade FROM users WHERE username = %s", (username,))
        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "User not found"}), 404

        grade = result[0]
        
        # Try different paths for the CSV file
        possible_paths = [
            os.path.join(BASE_DIR, "data", f"grade{grade}_v2.csv"),
            os.path.join(BASE_DIR, f"grade{grade}_v2.csv"),
            f"data/grade{grade}_v2.csv",
            f"grade{grade}_v2.csv"
        ]
        
        file_path = None
        for path in possible_paths:
            if os.path.exists(path):
                file_path = path
                print(f"✓ Found CSV file at: {path}")
                break
        
        if not file_path:
            print(f"❌ CSV file not found for grade {grade}")
            print(f"BASE_DIR: {BASE_DIR}")
            print(f"Current working directory: {os.getcwd()}")
            print(f"Files in current directory: {os.listdir('.')}")
            if os.path.exists("data"):
                print(f"Files in data directory: {os.listdir('data')}")
            
            return jsonify({
                "error": f"Question file not found for grade {grade}. Please contact support."
            }), 500

        try:
            df = pd.read_csv(file_path)
            print(f"✓ Successfully loaded CSV with {len(df)} rows")
        except Exception as csv_error:
            print(f"❌ Error reading CSV: {csv_error}")
            return jsonify({"error": f"Error reading question file"}), 500
        
        required_columns = ["Difficulty", "Question", "Answer"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return jsonify({
                "error": f"Invalid question file format. Missing columns: {missing_columns}"
            }), 500

        def sample_questions(level, n):
            level_questions = df[df["Difficulty"] == level]
            available_count = len(level_questions)
            
            if available_count == 0:
                return []
            
            sample_size = min(n, available_count)
            return level_questions.sample(sample_size, replace=False).to_dict(orient="records")

        # Sample questions by difficulty
        easy = sample_questions("Easy", 2)
        medium = sample_questions("Medium", 2)
        difficult = sample_questions("Difficult", 1)

        selected = easy + medium + difficult
        
        # Remove duplicates
        seen_questions = set()
        unique_selected = []
        for q in selected:
            if q["Question"] not in seen_questions:
                seen_questions.add(q["Question"])
                unique_selected.append(q)
        
        # Fill up to 5 questions if needed
        if len(unique_selected) < 5:
            used_questions = {q["Question"] for q in unique_selected}
            remaining_questions = df[~df["Question"].isin(used_questions)]
            
            needed = 5 - len(unique_selected)
            if len(remaining_questions) >= needed:
                additional = remaining_questions.sample(needed).to_dict(orient="records")
                unique_selected.extend(additional)

        if len(unique_selected) == 0:
            return jsonify({"error": "No questions available"}), 500

        random.shuffle(unique_selected)
        print(f"✓ Successfully loaded {len(unique_selected)} questions")
        
        return jsonify({"questions": unique_selected})

    except Exception as e:
        error_details = traceback.format_exc()
        print(f"❌ Error in get_questions: {error_details}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if 'cursor' in locals(): 
            cursor.close()
        if 'conn' in locals(): 
            conn.close()

# Serve main frontend pages
@app.route("/")
@app.route("/login")
def serve_login():
    return app.send_static_file("login.html")

@app.route("/register")
def serve_register():
    return app.send_static_file("register.html")

@app.route("/question")
def serve_question():
    return app.send_static_file("question.html")

# Serve static files (CSS, JS, etc.)
@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory(app.static_folder, path)

if __name__ == "__main__":
    print("🚀 Starting Smart Feedback Generator...")
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"Data directory exists: {os.path.exists(os.path.join(BASE_DIR, 'data'))}")
    print(f"Environment variables loaded: API_KEY={'✓' if TOGETHER_API_KEY else '❌'}")
    
    # Use Railway's PORT environment variable
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)