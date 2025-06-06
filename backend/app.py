from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import re
import requests
import time
import random
import pandas as pd
import spacy 
from replit import db
from mysql.connector import Error
from difflib import SequenceMatcher
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


app = Flask(__name__, static_folder='frontend', static_url_path='')

CORS(app)

nlp = spacy.load("en_core_web_sm")

TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"
TOGETHER_API_KEY = os.getenv("API_KEY")
MODEL_NAME = "deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free"

HEADERS = {
    "Authorization": f"Bearer {TOGETHER_API_KEY}",
    "Content-Type": "application/json"
}


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

    if f"user:{username}" in db:
        return jsonify({"error": "Username already exists."}), 400

    db[f"user:{username}"] = {
        "password": password,
        "grade": grade
    }
    return jsonify({"message": "User registered successfully!"})


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    user = db.get(f"user:{username}")
    if user and user["password"] == password:
        return jsonify({"message": "Login successful!", "grade": user["grade"]})
    else:
        return jsonify({"error": "Invalid username or password"}), 401


@app.route("/get-questions", methods=["POST"])
def get_questions():
    data = request.get_json()
    username = data.get("username")
    if not username:
        return jsonify({"error": "Username is required"}), 400

    # Get grade from Replit DB
    user = db.get(f"user:{username}")
    if not user:
        return jsonify({"error": "User not found"}), 404

    grade = user.get("grade")
    if not grade:
        return jsonify({"error": "User does not have a grade set"}), 400

    # Try to locate the CSV file for this grade
    file_path = f"data/grade{grade}_v2.csv"
    if not os.path.exists(file_path):
        return jsonify({"error": f"Data file not found for grade {grade}"}), 500

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        return jsonify({"error": f"Error reading CSV: {str(e)}"}), 500

    required_columns = ["Difficulty", "Question", "Answer"]
    if not all(col in df.columns for col in required_columns):
        return jsonify({"error": "CSV file is missing required columns"}), 500

    def sample_questions(level, n):
        level_df = df[df["Difficulty"] == level]
        if level_df.empty:
            return []
        return level_df.sample(min(n, len(level_df))).to_dict(orient="records")

    easy = sample_questions("Easy", 2)
    medium = sample_questions("Medium", 2)
    difficult = sample_questions("Difficult", 1)

    selected = easy + medium + difficult
    random.shuffle(selected)

    return jsonify({"questions": selected})


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
    app.run(host="0.0.0.0", port=3000)
