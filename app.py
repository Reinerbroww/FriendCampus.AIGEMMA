import json
import os
import base64
import re

from flask import Flask, render_template, request, redirect, url_for, jsonify, session, Response, stream_with_context
from database import (
    init_db, get_all_subjects, add_subject,
    get_subject_by_id, delete_subject,
    save_message, get_conversations, clear_conversations,
    get_completed_topics_count, get_total_topics_count, get_chat_count,
    get_roadmap, save_roadmap, toggle_topic,
    save_weakness, get_weakness_report,
    create_user, login_user, get_user_by_id,
    save_reference, get_saved_references, delete_reference,
    log_recent_subject, get_recent_subjects,
    save_roadmap_with_subtopics, get_roadmap_structured
)
from gemma import (
    chat_with_gemma, generate_roadmap,
    generate_understanding_check, evaluate_answer,
    find_references, chat_with_image, chat_with_gemma_stream, clean_markdown
)

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)
app.secret_key = os.getenv("SECRET_KEY", "fc2026xK9mPqRvNwLjTsYbDhUeAzCgFi")

with app.app_context():
    init_db()

# ===== HELPERS =====
def format_user(user):
    if not user:
        return None
    u = dict(user)
    if u.get('created_at') and not isinstance(u['created_at'], str):
        u['created_at'] = u['created_at'].strftime('%Y-%m-%d')
    return u

def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    user = get_user_by_id(user_id)
    return format_user(user)

def get_sidebar_data(user_id):
    try:
        recent = get_recent_subjects(user_id)
        return recent
    except Exception as e:
        print("Sidebar Error:", e)
        return []

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('landing'))
        return f(*args, **kwargs)
    return decorated

# ===== AUTH ROUTES =====
@app.route("/landing")
def landing():
    if session.get('user_id'):
        return redirect(url_for('index'))
    return render_template("landing.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get('user_id'):
        return redirect(url_for('index'))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = login_user(username, password)
        if user:
            session['user_id'] = user['id']
            return redirect(url_for('index'))
        else:
            error = "Invalid username or password."
    return render_template("login.html", error=error)

@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get('user_id'):
        return redirect(url_for('index'))
    error = None
    if request.method == "POST":
        username   = request.form.get("username", "").strip()
        password   = request.form.get("password", "").strip()
        display_name = request.form.get("display_name", "").strip()
        if not username or not password or not display_name:
            error = "All fields are required."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        else:
            success = create_user(username, password, display_name)
            if success:
                user = login_user(username, password)
                session['user_id'] = user['id']
                return redirect(url_for('index'))
            else:
                error = "Username already taken. Try another one."
    return render_template("register.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('landing'))

# ===== MAIN ROUTES =====
@app.route("/")
@login_required
def index():
    user = get_current_user()
    try:
        subjects = get_all_subjects(user['id'])
    except Exception as e:
        print("Index subject error:", e)
        subjects = []
    total_completed = 0
    total_topics    = 0
    total_chats     = 0
    subjects_with_stats = []

    for subject in subjects:
        completed = get_completed_topics_count(subject['id'])
        total     = get_total_topics_count(subject['id'])
        chats     = get_chat_count(subject['id'])
        percent   = round((completed / total * 100)) if total > 0 else 0
        total_completed += completed
        total_topics    += total
        total_chats     += chats
        subjects_with_stats.append({
            'id':        subject['id'],
            'name':      subject['name'],
            'completed': completed,
            'total':     total,
            'percent':   percent
        })

    return render_template(
        "index.html",
        user=user,
        subjects=subjects_with_stats,
        total_completed=total_completed,
        total_topics=total_topics,
        total_chats=total_chats,
        recent=get_sidebar_data(user['id'])
    )

@app.route("/add-subject", methods=["POST"])
@login_required
def add_subject_route():
    user = get_current_user()
    name = request.form.get("name", "").strip()
    if name:
        add_subject(name, user['id'])
    return redirect(url_for("index"))

@app.route("/delete-subject/<int:subject_id>", methods=["POST"])
@login_required
def delete_subject_route(subject_id):
    delete_subject(subject_id)
    return redirect(url_for("index"))

@app.route("/subject/<int:subject_id>")
@login_required
def subject_page(subject_id):
    user = get_current_user()

    subject = get_subject_by_id(subject_id)

    if not subject:
        return redirect(url_for("index"))

    # SECURITY CHECK
    if subject["user_id"] != user["id"]:
        return redirect(url_for("index"))

    try:
        log_recent_subject(user['id'], subject_id)
    except Exception as e:
        print("Recent subject error:", e)

    try:
        conversations = get_conversations(subject_id)
    except Exception as e:
        print("Conversation error:", e)
        conversations = []

    return render_template(
        "subject.html",
        subject=subject,
        conversations=conversations,
        user=user,
        recent=get_sidebar_data(user['id'])
    )

@app.route("/profile")
@login_required
def profile():
    user     = get_current_user()
    subjects = get_all_subjects(user['id'])
    total_chats     = sum(get_chat_count(s['id']) for s in subjects)
    total_completed = sum(get_completed_topics_count(s['id']) for s in subjects)
    return render_template(
        "profile.html",
        user=user,
        total_subjects=len(subjects),
        total_chats=total_chats,
        total_completed=total_completed,
        recent=get_sidebar_data(user['id'])
    )

# ===== CHAT ROUTES =====
@app.route("/chat/<int:subject_id>", methods=["POST"])
@login_required
def chat(subject_id):
    subject = get_subject_by_id(subject_id)
    if not subject:
        return jsonify({"error": "Subject not found"}), 404

    user_message = request.json.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    raw_history = get_conversations(subject_id)
    conversation_history = [
        {
            "role":  "user" if msg["role"] == "user" else "model",
            "parts": msg["message"]
        }
        for msg in raw_history
    ]

    save_message(subject_id, "user", user_message)

    def generate():
        full_response = ""
        try:
            stream = chat_with_gemma_stream(
                subject["name"],
                conversation_history,
                user_message
            )
            for chunk in stream:
                if chunk.text:
                    cleaned = clean_markdown(chunk.text)
                    full_response += cleaned
                    # Kirim chunk ke browser
                    yield f"data: {json.dumps({'chunk': cleaned})}\n\n"

            # Simpan ke database setelah selesai
            save_message(subject_id, "assistant", full_response)
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control':               'no-cache',
            'X-Accel-Buffering':           'no',
            'Access-Control-Allow-Origin': '*'
        }
    )

@app.route("/analyze-image/<int:subject_id>", methods=["POST"])
@login_required
def analyze_image(subject_id):
    subject = get_subject_by_id(subject_id)
    if not subject:
        return jsonify({"error": "Subject not found"}), 404

    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image_file   = request.files['image']
    user_message = request.form.get("message", "Please analyze this image and explain what you see.")

    allowed_types = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
    if image_file.mimetype not in allowed_types:
        return jsonify({"error": "Invalid file type. Use JPG, PNG, or WebP."}), 400

    image_file.seek(0, 2)
    file_size = image_file.tell()
    image_file.seek(0)
    if file_size > 5 * 1024 * 1024:
        return jsonify({"error": "Image too large. Max 5MB."}), 400

    try:
        image_data   = image_file.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        mime_type    = image_file.mimetype

        response = chat_with_image(subject["name"], user_message, image_base64, mime_type)
        save_message(subject_id, "user",      f"[Image] {user_message}")
        save_message(subject_id, "assistant", response)
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/clear-chat/<int:subject_id>", methods=["POST"])
@login_required
def clear_chat(subject_id):
    clear_conversations(subject_id)
    return jsonify({"status": "ok"})

# ===== ROADMAP ROUTES =====
@app.route("/roadmap/<int:subject_id>", methods=["GET"])
@login_required
def get_roadmap_route(subject_id):
    subject = get_subject_by_id(subject_id)
    if not subject:
        return jsonify({"error": "Subject not found"}), 404

    try:
        topics = get_roadmap_structured(subject_id)

        # Kalau belum ada roadmap, generate dulu
        if not topics:
            roadmap_data = generate_roadmap(subject["name"])

            if not roadmap_data:
                return jsonify({"error": "Failed to generate roadmap"}), 500

            # Handle kalau masih format lama (list of string)
            if isinstance(roadmap_data[0], str):
                roadmap_data = [
                    {"title": t, "subtopics": []}
                    for t in roadmap_data
                ]

            save_roadmap_with_subtopics(subject_id, roadmap_data)
            topics = get_roadmap_structured(subject_id)

        return jsonify({"topics": topics})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/reset-roadmap/<int:subject_id>", methods=["POST"])
@login_required
def reset_roadmap(subject_id):
    try:
        save_roadmap_with_subtopics(subject_id, [])
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/toggle-topic/<int:topic_id>", methods=["POST"])
@login_required
def toggle_topic_route(topic_id):
    toggle_topic(topic_id)
    return jsonify({"status": "ok"})

@app.route("/topics-for-check/<int:subject_id>", methods=["GET"])
@login_required
def topics_for_check(subject_id):
    structured = get_roadmap_structured(subject_id)
    flat_topics = []
    for parent in structured:
        flat_topics.append({
            "id":           parent["id"],
            "topic_name":   parent["topic_name"],
            "is_completed": parent["is_completed"],
            "level":        0
        })
        for sub in parent.get("subtopics", []):
            flat_topics.append({
                "id":           sub["id"],
                "topic_name":   sub["topic_name"],
                "is_completed": sub["is_completed"],
                "level":        1
            })
    return jsonify({"topics": flat_topics})

# ===== CHECK UNDERSTANDING ROUTES =====
@app.route("/understanding-check/<int:subject_id>", methods=["POST"])
@login_required
def understanding_check(subject_id):
    try:
        subject = get_subject_by_id(subject_id)
        if not subject:
            return jsonify({"error": "Subject not found"}), 404

        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400

        topic_name = data.get("topic_name", "").strip()
        if not topic_name:
            return jsonify({"error": "Topic name is required"}), 400

        try:
            raw_history = get_conversations(subject_id)
            conversation_history = [
                {"role": msg["role"], "message": msg["message"]}
                for msg in raw_history
            ]
        except Exception:
            conversation_history = []

        try:
            question = generate_understanding_check(
                subject["name"],
                topic_name,
                conversation_history
            )
            if not question or len(question.strip()) < 5:
                raise ValueError("Question too short")
        except Exception as gemma_err:
            # Fallback question kalau Gemma gagal
            question = (
                f"Please explain the concept of '{topic_name}' "
                f"in your own words and provide a real-world example."
            )

        return jsonify({"question": question, "topic": topic_name})

    except Exception as e:
        # Log error tapi tetap return 200 dengan fallback
        print(f"[understanding-check ERROR] {str(e)}")
        topic_name = request.json.get("topic_name", "this topic") if request.json else "this topic"
        fallback   = f"Explain '{topic_name}' in your own words and give an example."
        return jsonify({"question": fallback, "topic": topic_name})

@app.route("/evaluate/<int:subject_id>", methods=["POST"])
@login_required
def evaluate(subject_id):
    try:
        subject = get_subject_by_id(subject_id)
        if not subject:
            return jsonify({"error": "Subject not found"}), 404

        data     = request.json
        question = data.get("question", "")
        answer   = data.get("answer",   "")
        topic    = data.get("topic",    "General")

        if not question or not answer:
            return jsonify({"error": "Incomplete data"}), 400

        raw_result = evaluate_answer(subject["name"], question, answer)
        print(f"[EVALUATE RAW] {repr(raw_result)}")  # Debug log

        score        = None
        feedback     = ""
        parsed_topic = topic
        lines        = raw_result.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            upper = line.upper()

            # Parse SKOR — handle berbagai format
            if "SKOR" in upper or "SCORE" in upper:
                nums = re.findall(r'\d+', line)
                if nums:
                    score = min(int(nums[0]), 100)

            # Parse TOPIK
            elif "TOPIK" in upper or "TOPIC" in upper:
                colon_idx = line.find(":")
                if colon_idx != -1:
                    parsed_topic = line[colon_idx + 1:].strip()
                    if not parsed_topic:
                        parsed_topic = topic

            # Parse FEEDBACK
            elif "FEEDBACK" in upper:
                colon_idx = line.find(":")
                if colon_idx != -1:
                    feedback = line[colon_idx + 1:].strip()

        # Kalau feedback masih kosong — ambil semua teks yang bukan SKOR/TOPIK
        if not feedback:
            feedback_lines = []
            skip_next = False
            for line in lines:
                line = line.strip()
                upper = line.upper()
                if not line:
                    continue
                if "SKOR" in upper or "SCORE" in upper:
                    continue
                if "TOPIK" in upper or "TOPIC" in upper:
                    continue
                if "FEEDBACK" in upper:
                    colon_idx = line.find(":")
                    if colon_idx != -1 and len(line) > colon_idx + 2:
                        feedback_lines.append(line[colon_idx + 1:].strip())
                    continue
                feedback_lines.append(line)
            feedback = " ".join(feedback_lines).strip()

        # Default kalau masih kosong
        if not feedback:
            feedback = "Good attempt! Keep studying this topic to strengthen your understanding."

        # Default score — jangan pernah 0 kalau user nulis sesuatu
        if score is None:
            score = 40
            feedback = "Your answer was received but couldn't be fully evaluated. " + feedback

        score = max(5, min(score, 100))

        # Simpan ke weakness report
        print(f"[EVALUATE] Score={score}, Topic={parsed_topic}")
        save_weakness(subject_id, parsed_topic, score)

        return jsonify({
            "score":    score,
            "topic":    parsed_topic,
            "feedback": feedback
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[EVALUATE ERROR] {str(e)}")

        # Jangan return 500 — kasih hasil default
        try:
            save_weakness(subject_id, topic, 40)
        except Exception:
            pass

        return jsonify({
            "score":    40,
            "topic":    topic,
            "feedback": "Your answer was received. There was an issue with evaluation, but your progress has been saved."
        })

# ===== WEAKNESS ROUTES =====
@app.route("/weakness-report/<int:subject_id>", methods=["GET"])
@login_required
def weakness_report(subject_id):
    results = get_weakness_report(subject_id)
    data    = [
        {
            "topic_name":    r["topic_name"],
            "avg_score":     r["avg_score"],
            "attempt_count": r["attempt_count"],
            "last_attempt":  str(r["last_attempt"])
        }
        for r in results
    ]
    return jsonify({"report": data})

# ===== REFERENCES ROUTES =====
@app.route("/references/<int:subject_id>", methods=["POST"])
@login_required
def search_references(subject_id):
    subject = get_subject_by_id(subject_id)
    if not subject:
        return jsonify({"error": "Subject not found"}), 404

    query = request.json.get("query", "").strip()
    if not query:
        query = subject["name"]

    try:
        refs = find_references(subject["name"], query)
        return jsonify({"references": refs, "query": query})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/save-reference/<int:subject_id>", methods=["POST"])
@login_required
def save_reference_route(subject_id):
    ref_data = request.json
    if not ref_data:
        return jsonify({"error": "No data"}), 400
    try:
        save_reference(subject_id, ref_data)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/saved-references/<int:subject_id>", methods=["GET"])
@login_required
def get_saved_references_route(subject_id):
    import json as json_lib
    refs   = get_saved_references(subject_id)
    result = []
    for r in refs:
        result.append({
            "id":      r["id"],
            "title":   r["title"],
            "type":    r["type"],
            "author":  r["author"],
            "year":    r["year"],
            "summary": r["summary"],
            "url":     r["url"],
            "tags":    json_lib.loads(r["tags"]) if r["tags"] else []
        })
    return jsonify({"references": result})

@app.route("/delete-reference/<int:ref_id>", methods=["POST"])
@login_required
def delete_reference_route(ref_id):
    delete_reference(ref_id)
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True)
