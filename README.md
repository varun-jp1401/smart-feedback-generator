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
- 💻 **Responsive UI** with Edcite branding

---

## 🧰 Tech Stack

- **Frontend**: HTML, CSS, JavaScript
- **Backend**: Python (Flask)
- **Database**: MySQL
- **AI/ML**:
  - `sentence-transformers` (all-mpnet-base-v2) for semantic matching
  - `KeyBERT` for keyword extraction
  - `DeepSeek LLaMA API` for generating human-like feedback

---

## 📂 Project Structure

