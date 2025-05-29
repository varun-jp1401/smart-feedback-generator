# 🧠 Smart Feedback Generator

A web-based smart feedback platform built during an internship at **Edcite Learning**, designed to help students in Grades 5, 6, and 7 receive personalized, AI-powered feedback on short answers.

---

## 🚀 Features

- 🔐 **Login & Registration** (with grade selection)
- 🏫 **Grade-specific questions** pulled dynamically from CSVs
- 🎯 **Randomized question set** (2 Easy, 2 Medium, 1 Difficult)
- 📝 **Student answers evaluated** using semantic similarity & keyword coverage
- 🤖 **AI-powered feedback** using DeepSeek LLaMA + KeyBERT
  - Subtle spelling mistake hints
  - Clues for missing keywords (without revealing answers)
- 📊 **Question palette** like TCS iON to track progress
- 🔄 **Retry / Next** buttons and per-question feedback
- 💻 **Responsive UI**

---

## 🧰 Tech Stack

- **Frontend**: HTML, CSS, JavaScript
- **Backend**: Python (Flask)
- **Database**: MySQL
- **AI/ML**:
  - `KeyBERT` for keyword extraction
  - `DeepSeek LLaMA API` for generating human-like feedback

---

## 📂 Project Structure

smart_feedback_generator/
│
├── backend/ # Flask backend (API, routes, MySQL)
├── static/ # CSS, JS files
├── templates/ # HTML templates (login, register, questions)
├── datasets/ # CSV files for grades 5–7
├── venv/ # Virtual environment (ignored in Git)
├── app.py # Main Flask app
├── requirements.txt # Python dependencies
└── .gitignore # Git exclusions



---

## 🛠️ Setup Instructions

1. **Clone the repository**
   ```bash
   git clone https://github.com/YOUR-USERNAME/smart-feedback-generator.git
   cd smart-feedback-generator


2. Create and activate virtual environment

  `python -m venv venv`
 ` venv\Scripts\activate `     # On Windows
  # or
 ` source venv/bin/activate`  # On Mac/Linux

3. Install dependencies
  `pip install -r requirements.txt`

4. Set up MySQL Database

  Create a database (e.g., smart_feedback)
  Create a table users with columns: id, username, password, grade
  Update DB credentials inside app.py

5. Run the Flask app 
  `python app.py`
  
 6. Open with Live Server or Access the app in browser   