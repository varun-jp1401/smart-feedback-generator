from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import re
import requests
import time
import random
import pandas as pd
import spacy 
from difflib import SequenceMatcher
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2 import OperationalError

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'frontend'))


# Create Flask app with proper static folder configuration
app = Flask(__name__, 
           static_folder=FRONTEND_DIR if os.path.exists(FRONTEND_DIR) else None,
           static_url_path='')

# Enable CORS for all routes
CORS(app, resources={r"/*": {"origins": "*"}})

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
    print("✓ spaCy model loaded successfully")
except Exception as e:
    print(f"❌ Error loading spaCy model: {e}")
    nlp = None

# API Configuration
TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"
TOGETHER_API_KEY = os.getenv("API_KEY")
MODEL_NAME = "deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free"

HEADERS = {
    "Authorization": f"Bearer {TOGETHER_API_KEY}",
    "Content-Type": "application/json"
}

# Database configuration
DB_CONFIG = {
    'host': os.getenv("DB_HOST"),
    'database': os.getenv("DB_NAME"),
    'user': os.getenv("DB_USER"),
    'password': os.getenv("DB_PASSWORD"),
    'port': int(os.getenv("DB_PORT", 5432))
}

print("=== Environment Check ===")
print(f"BASE_DIR: {BASE_DIR}")
print(f"FRONTEND_DIR: {FRONTEND_DIR}")
print(f"Frontend exists: {os.path.exists(FRONTEND_DIR)}")
print(f"API_KEY set: {'Yes' if TOGETHER_API_KEY else 'No'}")
print(f"DB_HOST set: {'Yes' if os.getenv('DB_HOST') else 'No'}")
print(f"DB_USER: {os.getenv('DB_USER')}")
print(f"DB_NAME: {os.getenv('DB_NAME')}")
print(f"DB_PORT: {os.getenv('DB_PORT')}")

if os.path.exists(FRONTEND_DIR):
    frontend_files = os.listdir(FRONTEND_DIR)
    print(f"Frontend files: {frontend_files}")
else:
    print("❌ Frontend directory not found")

def get_db_connection():
    try:
        print("Attempting to connect to PostgreSQL...")
        conn = psycopg2.connect(**DB_CONFIG)
        print("✓ PostgreSQL connection successful")
        return conn
    except OperationalError as e:
        print(f"❌ PostgreSQL connection error: {e}")
        raise


def init_database():
    """Initialize database tables"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create users table if it doesn't exist
        create_users_table = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            grade INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """

        
        cursor.execute(create_users_table)
        conn.commit()
        print("✓ Database tables initialized successfully")
        
        # Check if table exists and show structure
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'users';
        """)
        columns = cursor.fetchall()
        print(f"Users table structure: {columns}")

        
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'users';
        """)
        columns = cursor.fetchall()
        print(f"Users table structure: {columns}")

        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
    finally:
        if 'cursor' in locals(): 
            cursor.close()
        if 'conn' in locals(): 
            conn.close()

# Initialize database on startup
init_database()

# Keep all your existing utility functions exactly as they are
def clean_response(text):
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

def extract_keywords(text, top_k=5):
    if not nlp:
        return text.split()[:top_k]  # Fallback if spaCy not loaded
    doc = nlp(text)
    keywords = list(set([chunk.text.lower() for chunk in doc.noun_chunks if len(chunk.text.strip()) > 2]))
    return keywords[:top_k]

def find_missing_keywords(keywords, student_answer):
    student_answer = student_answer.lower()
    return [kw for kw in keywords if kw not in student_answer]

def calculate_keyword_score(ideal_answer, student_answer):
    """Calculate score based on keyword coverage (0-1 marks)"""
    keywords = extract_keywords(ideal_answer, top_k=10)
    if not keywords:
        return 1.0 
    
    student_answer_lower = student_answer.lower()
    ideal_answer_lower = ideal_answer.lower()
    
    if student_answer_lower.strip() == ideal_answer_lower.strip():
        return 1.0
    
    similarity = SequenceMatcher(None, ideal_answer_lower, student_answer_lower).ratio()
    if similarity >= 0.8:  
        return 1.0
    
    matched_keywords = 0
    
    for keyword in keywords:
        if keyword in student_answer_lower:
            matched_keywords += 1
            continue
            
        keyword_words = keyword.split()
        if len(keyword_words) > 1:
            found_words = sum(1 for word in keyword_words if word in student_answer_lower)
            if found_words >= len(keyword_words) * 0.7:  
                matched_keywords += 1
        else:
            student_words = student_answer_lower.split()
            for student_word in student_words:
                word_similarity = SequenceMatcher(None, keyword, student_word).ratio()
                if word_similarity >= 0.8:  
                    matched_keywords += 1
                    break
    
    coverage_ratio = matched_keywords / len(keywords)
    
    if coverage_ratio >= 0.6: 
        return 1.0
    elif coverage_ratio >= 0.3:  
        return 0.5
    else:
        return 0.0

def calculate_spelling_score(ideal_answer, student_answer):
    """Calculate score based on spelling accuracy (0-1 marks)"""
    keywords = extract_keywords(ideal_answer, top_k=10)
    if not keywords:
        return 1.0  
    
    student_answer_lower = student_answer.lower()
    ideal_answer_lower = ideal_answer.lower()
    
    if student_answer_lower.strip() == ideal_answer_lower.strip():
        return 1.0
    
    similarity = SequenceMatcher(None, ideal_answer_lower, student_answer_lower).ratio()
    if similarity >= 0.85:  
        return 1.0
    
    student_words = set(student_answer_lower.split())
    spelling_errors = 0
    total_important_words = 0
    
    for keyword in keywords:
        keyword_words = keyword.split()
        for word in keyword_words:
            if len(word) < 3:  
                continue
                
            total_important_words += 1
            
            if word in student_words:
                continue
            
            best_similarity = 0
            for student_word in student_words:
                if len(student_word) < 3:  
                    continue
                similarity = SequenceMatcher(None, word, student_word).ratio()
                best_similarity = max(best_similarity, similarity)
            
            if best_similarity < 0.75:  
                spelling_errors += 1
    
    if total_important_words == 0:
        return 1.0
    
    error_ratio = spelling_errors / total_important_words
    
    if error_ratio <= 0.15:  
        return 1.0
    elif error_ratio <= 0.4:  
        return 0.5
    else:
        return 0.0

def calculate_question_score(ideal_answer, student_answer):
    """Calculate total score for a question (0-2 marks)"""
    if not student_answer or student_answer.strip().lower() in ["i don't know", "dont know", "no idea", ""]:
        return 0.0
    
    ideal_clean = ideal_answer.strip().lower()
    student_clean = student_answer.strip().lower()
    
    if ideal_clean == student_clean:
        return 2.0
    
    overall_similarity = SequenceMatcher(None, ideal_clean, student_clean).ratio()
    if overall_similarity >= 0.9: 
        return 2.0
    elif overall_similarity >= 0.8:  
        return 1.8
    elif overall_similarity >= 0.7:  
        return 1.5
    
    keyword_score = calculate_keyword_score(ideal_answer, student_answer)
    spelling_score = calculate_spelling_score(ideal_answer, student_answer)
    
    total_score = keyword_score + spelling_score
    return round(total_score, 1)  

def build_prompt(question, ideal_answer, student_answer, missing_keywords):
    hint = ""
    if missing_keywords:
        hint = "It seems the student may have missed one or more important scientific ideas. Consider gently prompting them to revisit key parts of the process."

    return (
        f"You are a supportive but strict middle school science teacher and you are giving the feedback to the students.\n\n"
        f"Question: {question}\n"
        f"Ideal Answer: {ideal_answer}\n"
        f"Student Answer: {student_answer}\n\n"
        f"{hint}\n\n"
        f"Now write helpful, constructive feedback for the student:\n"
        f"- If the answer is same as or very close to the ideal answer or it has all the keywords, say it's correct and donot give any other furthur explanation.\n"
        f"- If they missed something important, just hint at it — do not give the keyword.This is very important donot give the keyword away but at the same time try your best at hinting.\n"
        f"- If there's a spelling mistake in the important keywords only, suggest checking it without revealing it.This is important to check.\n"
        f"- Do NOT include internal thoughts or use <think> tags.\n"
        f"- If the answer is completely wrong and not even close, don't hesitate to say it.\n"
        f"- if the student says he doesnt know the answer,tell him its fine and move on to the next question"
        f"- Be friendly and encouraging."
    )

def generate_feedback(question, ideal_answer, student_answer):
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

    try:
        response = requests.post(TOGETHER_API_URL, headers=HEADERS, json=payload, timeout=60)
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        return clean_response(raw)
    except Exception as e:
        return f"Error generating feedback: {str(e)}"

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

# Health check endpoint
@app.route("/health", methods=["GET"])
def health_check():
    try:
        # Test database connection
        conn = get_db_connection()
        conn.close()
        db_status = "connected"
    except:
        db_status = "disconnected"
    
    return jsonify({
        "status": "healthy",
        "frontend_available": os.path.exists(FRONTEND_DIR),
        "api_key_configured": bool(TOGETHER_API_KEY),
        "db_configured": bool(os.getenv("DB_HOST")),
        "db_status": db_status
    })

@app.route("/generate-feedback", methods=["POST"])
def feedback_api():
    data = request.get_json()
    question = data.get("question")
    ideal_answer = data.get("ideal_answer")
    student_answer = data.get("student_answer")

    if not all([question, ideal_answer, student_answer]):
        return jsonify({"error": "Missing input fields"}), 400

    feedback = generate_feedback(question, ideal_answer, student_answer)
    return jsonify({"feedback": feedback})

@app.route("/calculate-score", methods=["POST"])
def calculate_score():
    data = request.get_json()
    questions = data.get("questions")  
    answers = data.get("answers")      
    
    if not questions or not answers:
        return jsonify({"error": "Missing questions or answers"}), 400
    
    if len(questions) != len(answers):
        return jsonify({"error": "Mismatch in number of questions and answers"}), 400
    
    total_score = 0
    question_scores = []
    debug_info = []
    
    for i, (question_obj, student_answer) in enumerate(zip(questions, answers)):
        ideal_answer = question_obj.get("Answer", "")
        
        question_score = calculate_question_score(ideal_answer, student_answer)
        total_score += question_score
        
        debug_info.append({
            "question_num": i + 1,
            "ideal_answer": ideal_answer,
            "student_answer": student_answer,
            "score": question_score,
            "similarity": round(SequenceMatcher(None, ideal_answer.lower(), student_answer.lower()).ratio(), 3)
        })
        
        question_scores.append({
            "question_number": i + 1,
            "score": question_score,
            "max_score": 2.0
        })
    
    max_total_score = len(questions) * 2.0
    percentage = (total_score / max_total_score) * 100 if max_total_score > 0 else 0
    
    print("=== SCORING DEBUG INFO ===")
    for debug in debug_info:
        print(f"Q{debug['question_num']}: Score={debug['score']}/2.0, Similarity={debug['similarity']}")
        print(f"  Ideal: {debug['ideal_answer'][:100]}...")
        print(f"  Student: {debug['student_answer'][:100]}...")
        print()
    
    return jsonify({
        "total_score": round(total_score, 1),
        "max_score": max_total_score,
        "percentage": round(percentage, 1),
        "question_scores": question_scores,
        "grade": get_letter_grade(percentage),
        "debug_info": debug_info  
    })

@app.route("/register", methods=["POST"])
def register():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
            
        username = data.get("username")
        password = data.get("password")
        grade = data.get("grade")

        print(f"Registration attempt: username={username}, grade={grade}")

        if not all([username, password, grade]):
            return jsonify({"error": "Missing required fields: username, password, or grade"}), 400

        # Validate grade
        try:
            grade = int(grade)
            if not (1 <= grade <= 12):
                return jsonify({"error": "Grade must be between 1 and 12"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Grade must be a valid number"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if username already exists
        cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            return jsonify({"error": "Username already exists."}), 400

        # Insert new user
        cursor.execute(
            "INSERT INTO users (username, password, grade) VALUES (%s, %s, %s)", 
            (username, password, grade)
        )
        conn.commit()
        print(f"✓ User {username} registered successfully")
        
        return jsonify({"message": "User registered successfully!"})
        
    except Exception as e:
        print(f"❌ Database error during registration: {e}")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except Exception as e:
        print(f"❌ Unexpected error during registration: {e}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500
    finally:
        if 'cursor' in locals(): 
            cursor.close()
        if 'conn' in locals(): 
            conn.close()

@app.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
            
        username = data.get("username")
        password = data.get("password")

        if not all([username, password]):
            return jsonify({"error": "Missing username or password"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT grade FROM users WHERE username=%s AND password=%s", (username, password))
        result = cursor.fetchone()
        
        if result:
            return jsonify({"message": "Login successful!", "grade": result[0]})
        else:
            return jsonify({"error": "Invalid username or password"}), 401
            
    except Exception as e:
        print(f"❌ Database error during login: {e}")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except Exception as e:
        print(f"❌ Unexpected error during login: {e}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500
    finally:
        if 'cursor' in locals(): 
            cursor.close()
        if 'conn' in locals(): 
            conn.close()

@app.route("/get-questions", methods=["POST"])
def get_questions():
    data = request.get_json()
    username = data.get("username")
    if not username:
        return jsonify({"error": "Username is required"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT grade FROM users WHERE username = %s", (username,))
        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "User not found"}), 404

        grade = result[0]
        
        # Updated paths for Railway deployment
        possible_paths = [
            os.path.join(BASE_DIR, "data", f"grade{grade}_v2.csv"),
            os.path.join(os.path.dirname(BASE_DIR), "data", f"grade{grade}_v2.csv"),
            os.path.join("/app", "data", f"grade{grade}_v2.csv"),
            os.path.join("/app/backend", "data", f"grade{grade}_v2.csv"),
        ]
        
        file_path = None
        for path in possible_paths:
            print(f"Trying path: {path}")
            if os.path.exists(path):
                file_path = path
                print(f"✓ Found file at: {path}")
                break
        
        if not file_path:
            print(f"BASE_DIR: {BASE_DIR}")
            print(f"Looking for grade: {grade}")
            
            data_dirs_to_check = [
                os.path.join(BASE_DIR, "data"),
                os.path.join(os.path.dirname(BASE_DIR), "data"),
                os.path.join("/app", "data"),
                os.path.join("/app/backend", "data")
            ]
            
            for data_dir in data_dirs_to_check:
                if os.path.exists(data_dir):
                    available_files = os.listdir(data_dir)
                    print(f"Files in {data_dir}: {available_files}")
                    return jsonify({
                        "error": f"Question file not found for grade {grade}. Available files in {data_dir}: {available_files}"
                    }), 500
            
            return jsonify({"error": f"No data directory found. Searched paths: {data_dirs_to_check}"}), 500

        try:
            df = pd.read_csv(file_path)
        except Exception as csv_error:
            print(f"Error reading CSV: {csv_error}")
            return jsonify({"error": f"Error reading CSV file: {str(csv_error)}"}), 500
        
        required_columns = ["Difficulty", "Question", "Answer"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            available_columns = list(df.columns)
            print(f"Available columns: {available_columns}")
            return jsonify({
                "error": f"Missing columns in CSV: {missing_columns}. Available columns: {available_columns}"
            }), 500

        difficulty_counts = df['Difficulty'].value_counts().to_dict()
        print(f"Question counts by difficulty: {difficulty_counts}")

        def sample_questions(level, n):
            level_questions = df[df["Difficulty"] == level]
            available_count = len(level_questions)
            
            if available_count == 0:
                print(f"Warning: No {level} questions available")
                return []
            
            sample_size = min(n, available_count)
            if available_count < n:
                print(f"Warning: Only {available_count} {level} questions available, requested {n}")
            
            return level_questions.sample(sample_size, replace=False).to_dict(orient="records")

        easy = sample_questions("Easy", 2)
        medium = sample_questions("Medium", 2)
        difficult = sample_questions("Difficult", 1)

        selected = easy + medium + difficult
        
        seen_questions = set()
        unique_selected = []
        for q in selected:
            if q["Question"] not in seen_questions:
                seen_questions.add(q["Question"])
                unique_selected.append(q)
        
        if len(unique_selected) < 5:
            used_questions = {q["Question"] for q in unique_selected}
            remaining_questions = df[~df["Question"].isin(used_questions)]
            
            needed = 5 - len(unique_selected)
            if len(remaining_questions) >= needed:
                additional = remaining_questions.sample(needed).to_dict(orient="records")
                unique_selected.extend(additional)

        if len(unique_selected) == 0:
            return jsonify({"error": "No questions found"}), 500

        random.shuffle(unique_selected)

        print(f"Successfully loaded {len(unique_selected)} unique questions")
        
        question_titles = [q["Question"][:50] + "..." if len(q["Question"]) > 50 else q["Question"] for q in unique_selected]
        print(f"Selected questions: {question_titles}")
        
        return jsonify({"questions": unique_selected})

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in get_questions: {error_details}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500
    finally:
        if 'cursor' in locals(): 
            cursor.close()
        if 'conn' in locals(): 
            conn.close()

# Serve main frontend pages
@app.route("/")
def serve_root():
    if os.path.exists(FRONTEND_DIR):
        try:
            return send_from_directory(FRONTEND_DIR, "login.html")
        except:
            pass
    return jsonify({"message": "Smart Feedback Generator API", "status": "running"})

@app.route("/login")
def serve_login():
    if os.path.exists(FRONTEND_DIR):
        try:
            return send_from_directory(FRONTEND_DIR, "login.html")
        except:
            pass
    return jsonify({"error": "Frontend not available"})

@app.route("/register")
def serve_register():
    if os.path.exists(FRONTEND_DIR):
        try:
            return send_from_directory(FRONTEND_DIR, "register.html")
        except:
            pass
    return jsonify({"error": "Frontend not available"})

@app.route("/question")
def serve_question():
    if os.path.exists(FRONTEND_DIR):
        try:
            return send_from_directory(FRONTEND_DIR, "question.html")
        except:
            pass
    return jsonify({"error": "Frontend not available"})

# Serve static files (CSS, JS, etc.)
@app.route("/<path:filename>")
def static_proxy(filename):
    if os.path.exists(FRONTEND_DIR):
        try:
            return send_from_directory(FRONTEND_DIR, filename)
        except:
            pass
    return jsonify({"error": f"File {filename} not found"}), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting server on port {port}")
    print(f"Environment: {os.environ.get('RAILWAY_ENVIRONMENT', 'local')}")
    app.run(host="0.0.0.0", port=port, debug=False)