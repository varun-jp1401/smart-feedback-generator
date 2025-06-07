from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import re
import requests
import time
import random
import pandas as pd
import spacy 
import mysql.connector
from mysql.connector import Error
from difflib import SequenceMatcher
import os
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, static_folder='frontend', static_url_path='')

# Update CORS to allow Railway domain and remove specific localhost restriction
CORS(app, resources={r"/*": {"origins": "*"}})

nlp = spacy.load("en_core_web_sm")

TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"
TOGETHER_API_KEY = os.getenv("API_KEY")
MODEL_NAME = "deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free"

HEADERS = {
    "Authorization": f"Bearer {TOGETHER_API_KEY}",
    "Content-Type": "application/json"
}

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", 3306)),
        charset='utf8'
    )


def clean_response(text):
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

def extract_keywords(text, top_k=5):
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


def calculate_question_score_simple(ideal_answer, student_answer):
    """Simplified scoring function for testing"""
    if not student_answer or student_answer.strip().lower() in ["i don't know", "dont know", "no idea", ""]:
        return 0.0
    
   
    ideal_clean = ideal_answer.strip().lower()
    student_clean = student_answer.strip().lower()
    
    
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
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    grade = data.get("grade")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            return jsonify({"error": "Username already exists."}), 400

        cursor.execute("INSERT INTO users (username, password, grade) VALUES (%s, %s, %s)", (username, password, grade))
        conn.commit()
        return jsonify({"message": "User registered successfully!"})
    except Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT grade FROM users WHERE username=%s AND password=%s", (username, password))
        result = cursor.fetchone()
        if result:
            return jsonify({"message": "Login successful!", "grade": result[0]})
        else:
            return jsonify({"error": "Invalid username or password"}), 401
    except Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()


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
        
        possible_paths = [
            # Look in parent directory's data folder (since app.py is in backend/)
            os.path.join(os.path.dirname(BASE_DIR), "data", f"grade{grade}_v2.csv"),
            # Look in current directory's data folder
            os.path.join(BASE_DIR, "data", f"grade{grade}_v2.csv"),
            # Look in root data folder
            os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "data", f"grade{grade}_v2.csv"),
            # Alternative path
            os.path.join(os.path.dirname(BASE_DIR), "data", f"grade{grade}_v2"),
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
                os.path.join(os.path.dirname(BASE_DIR), "data"),
                os.path.join(BASE_DIR, "data"),
                os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "data")
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

# Add a health check endpoint
@app.route("/health")
def health_check():
    return jsonify({"status": "healthy", "message": "Flask app is running"})

# Serve main frontend pages with error handling
@app.route("/")
def serve_index():
    try:
        if os.path.exists(os.path.join(app.static_folder, "login.html")):
            return app.send_static_file("login.html")
        else:
            return jsonify({"message": "Welcome to Smart Feedback Generator API", "status": "running"}), 200
    except Exception as e:
        return jsonify({"error": "Frontend files not found", "message": str(e)}), 404

@app.route("/login")
def serve_login():
    try:
        return app.send_static_file("login.html")
    except Exception as e:
        return jsonify({"error": "login.html not found", "message": str(e)}), 404

@app.route("/register")
def serve_register():
    try:
        return app.send_static_file("register.html")
    except Exception as e:
        return jsonify({"error": "register.html not found", "message": str(e)}), 404

@app.route("/question")
def serve_question():
    try:
        return app.send_static_file("question.html")
    except Exception as e:
        return jsonify({"error": "question.html not found", "message": str(e)}), 404

# Serve static files (CSS, JS, etc.) with error handling
@app.route("/<path:path>")
def static_proxy(path):
    try:
        return send_from_directory(app.static_folder, path)
    except Exception as e:
        return jsonify({"error": f"File {path} not found", "message": str(e)}), 404

# Add error handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({
        "error": "Not Found",
        "message": "The requested URL was not found on the server.",
        "available_endpoints": [
            "/health",
            "/login (POST)",
            "/register (POST)", 
            "/get-questions (POST)",
            "/generate-feedback (POST)",
            "/calculate-score (POST)"
        ]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "error": "Internal Server Error",
        "message": "The server encountered an internal error."
    }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting Flask app on port {port}")
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"Static folder: {app.static_folder}")
    app.run(host="0.0.0.0", port=port, debug=False)