let questions = [];
let currentQuestionIndex = 0;
let status = ["not-visited", "not-visited", "not-visited", "not-visited", "not-visited"];
let userAnswers = ["", "", "", "", ""]; 

window.onload = async () => {
    const username = localStorage.getItem("username");
    const grade = localStorage.getItem("grade");

    if (!username || !grade) {
        alert("Missing username or grade. Please login again.");
        window.location.href = "login.html";
        return;
    }

    document.getElementById("username").innerText = username;
    document.getElementById("grade").innerText = `Grade ${grade}`;

    try {
        const response = await fetch("http://127.0.0.1:5000/get-questions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username })
        });

        const data = await response.json();

        if (!data.questions || data.questions.length === 0) {
            document.getElementById("question-text").innerText = "❌ Failed to load questions.";
            return;
        }

        questions = data.questions;
        renderPalette();
        showQuestion();
    } catch (err) {
        document.getElementById("question-text").innerText = "❌ Error loading questions.";
        console.error(err);
    }
};

function renderPalette() {
    const palette = document.getElementById("palette");
    palette.innerHTML = "";

    for (let i = 0; i < questions.length; i++) {
        const btn = document.createElement("button");
        btn.innerText = i + 1;
        btn.className = status[i];
        btn.onclick = () => jumpToQuestion(i);
        palette.appendChild(btn);
    }
}

function showQuestion() {
    document.getElementById("feedback").innerText = "";
    
    document.getElementById("student-answer").value = userAnswers[currentQuestionIndex] || "";
    
    document.getElementById("question-text").innerText = questions[currentQuestionIndex].Question;

    if (status[currentQuestionIndex] === "answered") {
        document.getElementById("submit-btn").style.display = "none";
        document.getElementById("retry-btn").style.display = "inline-block";
        if (currentQuestionIndex < questions.length - 1) {
            document.getElementById("next-btn").style.display = "inline-block";
            document.getElementById("next-btn").innerText = "Next";
        } else {
            document.getElementById("next-btn").innerText = "Submit Test";
            document.getElementById("next-btn").style.display = "inline-block";
        }
    } else {
        document.getElementById("submit-btn").style.display = "inline-block";
        document.getElementById("retry-btn").style.display = "none";
        document.getElementById("next-btn").style.display = "none";
    }
}

async function submitAnswer() {
    const studentAnswer = document.getElementById("student-answer").value.trim();

    if (!studentAnswer) {
        alert("Please enter your answer before submitting.");
        return;
    }

    userAnswers[currentQuestionIndex] = studentAnswer;

    const feedbackBox = document.getElementById("feedback");
    feedbackBox.innerHTML = '<div class="loader">🔄 Generating feedback...</div>';
    
    const submitBtn = document.getElementById("submit-btn");
    submitBtn.disabled = true;
    submitBtn.innerText = "Generating...";

    const { Question, Answer } = questions[currentQuestionIndex];

    try {
        const response = await fetch("http://127.0.0.1:5000/generate-feedback", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question: Question,
                ideal_answer: Answer,
                student_answer: studentAnswer
            })
        });

        const data = await response.json();
        feedbackBox.innerText = data.feedback || "Error getting feedback.";

        status[currentQuestionIndex] = "answered";
        renderPalette();

        document.getElementById("submit-btn").style.display = "none";
        document.getElementById("retry-btn").style.display = "inline-block";

        if (currentQuestionIndex < questions.length - 1) { // FIXED: Use questions.length
            document.getElementById("next-btn").style.display = "inline-block";
            document.getElementById("next-btn").innerText = "Next";
        } else {
            document.getElementById("next-btn").innerText = "Submit Test";
            document.getElementById("next-btn").style.display = "inline-block";
        }
    } catch (error) {
        feedbackBox.innerText = "❌ Error generating feedback. Please try again.";
        console.error("Error:", error);
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerText = "Submit Answer";
    }
}

function retryQuestion() {
    document.getElementById("feedback").innerText = "";

    document.getElementById("submit-btn").style.display = "inline-block";
    document.getElementById("retry-btn").style.display = "none";
    document.getElementById("next-btn").style.display = "none";
    
    status[currentQuestionIndex] = "not-answered";
    renderPalette();
}

async function nextQuestion() {
    userAnswers[currentQuestionIndex] = document.getElementById("student-answer").value.trim();
    
    if (currentQuestionIndex < questions.length - 1) { 
        currentQuestionIndex++;
        if (status[currentQuestionIndex] === "not-visited") {
            status[currentQuestionIndex] = "not-answered";
        }
        renderPalette();
        showQuestion();
    } else {
        // Calculate and show score before submitting
        await calculateAndShowScore();
    }
}

async function calculateAndShowScore() {
    try {
        // Show loading message
        document.getElementById("question-text").innerText = "Calculating your score...";
        document.getElementById("feedback").innerHTML = '<div class="loader">🔄 Processing your answers...</div>';
        
        // Hide action buttons
        document.getElementById("submit-btn").style.display = "none";
        document.getElementById("retry-btn").style.display = "none";
        document.getElementById("next-btn").style.display = "none";
        
        const response = await fetch("http://127.0.0.1:5000/calculate-score", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                questions: questions,
                answers: userAnswers
            })
        });

        const scoreData = await response.json();

        if (response.ok) {
            displayScoreResults(scoreData);
        } else {
            document.getElementById("feedback").innerText = `❌ Error calculating score: ${scoreData.error}`;
        }
    } catch (error) {
        console.error("Error calculating score:", error);
        document.getElementById("feedback").innerText = "❌ Error calculating score. Please try again.";
    }
}

function displayScoreResults(scoreData) {
    document.getElementById("question-text").innerHTML = `
        <div class="score-header">
            <h2>🎉 Test Completed!</h2>
            <p>Here are your results:</p>
        </div>
    `;


    const scoreHtml = `
        <div id="score-container">
            <div class="total-score">
                <h3>Final Score: ${scoreData.total_score}/${scoreData.max_score} (${scoreData.percentage}%)</h3>
                <div class="grade-badge grade-${scoreData.grade.toLowerCase().replace('+', 'plus')}">
                    Grade: ${scoreData.grade}
                </div>
            </div>
            
            <div class="question-breakdown">
                <h4>Question-wise Breakdown:</h4>
                ${scoreData.question_scores.map(q => `
                    <div class="question-score">
                        <span>Question ${q.question_number}: </span>
                        <span class="score-value">${q.score}/${q.max_score}</span>
                        <div class="score-bar">
                            <div class="score-fill" style="width: ${(q.score/q.max_score)*100}%"></div>
                        </div>
                    </div>
                `).join('')}
            </div>
            
            <div class="score-explanation">
                <h4>Scoring Criteria:</h4>
                <ul>
                    <li><strong>1 mark</strong> for including important keywords (60%+ coverage)</li>
                    <li><strong>1 mark</strong> for correct spelling of key terms</li>
                    <li><strong>Partial marks</strong> awarded for partial coverage/accuracy</li>
                </ul>
            </div>
            
            <div class="action-buttons">
                <button onclick="restartTest()" class="restart-btn">Take Another Test</button>
                <button onclick="logout()" class="logout-btn">Logout</button>
            </div>
        </div>
    `;

    document.getElementById("feedback").innerHTML = scoreHtml;
    
    // Animate score bars
    setTimeout(() => {
        const scoreFills = document.querySelectorAll('.score-fill');
        scoreFills.forEach(fill => {
            fill.style.transition = 'width 1s ease-in-out';
        });
    }, 100);
}

function restartTest() {
    // Reset all variables
    currentQuestionIndex = 0;
    status = ["not-visited", "not-visited", "not-visited", "not-visited", "not-visited"];
    userAnswers = ["", "", "", "", ""];
    
    // Reload questions and start over
    window.location.reload();
}

function jumpToQuestion(index) {
    userAnswers[currentQuestionIndex] = document.getElementById("student-answer").value.trim();
    
    currentQuestionIndex = index;
    if (status[currentQuestionIndex] === "not-visited") {
        status[currentQuestionIndex] = "not-answered";
    }
    renderPalette();
    showQuestion();
}

function logout() {
    localStorage.clear();
    window.location.href = "login.html";
}