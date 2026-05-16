import os
import re
import json
import random
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables.")

client = genai.Client(api_key=api_key)

# =========================================================
# MODELS
# =========================================================

MODEL_FAST = "models/gemma-4-26b-a4b-it"
MODEL_STRONG = "models/gemma-4-26b-a4b-it"

# =========================================================
# CONFIGS
# =========================================================

FAST_CONFIG = types.GenerateContentConfig(
    temperature=0.7,
    max_output_tokens=150
)

ROADMAP_CONFIG = types.GenerateContentConfig(
    temperature=0.5,
    max_output_tokens=250
)

EVAL_CONFIG = types.GenerateContentConfig(
    temperature=0.3,
    max_output_tokens=120
)

REFERENCE_CONFIG = types.GenerateContentConfig(
    temperature=0.5,
    max_output_tokens=300
)

# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """You are FriendCampus.AI, a smart and friendly AI study companion for university students.

FORMATTING RULES — follow strictly:
- Use plain text only
- No markdown symbols
- Explain clearly and concisely
- Respond in the same language as the student
- Explain step by step for math or code
"""

# =========================================================
# HELPERS
# =========================================================

def clean_markdown(text):
    if not text:
        return ""

    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)

    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    text = re.sub(
        r'```[\w]*\n?(.*?)```',
        r'\1',
        text,
        flags=re.DOTALL
    )

    text = re.sub(r'`(.+?)`', r'\1', text)

    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def make_content(role, text):
    return types.Content(
        role=role,
        parts=[types.Part(text=text)]
    )


# =========================================================
# CHAT
# =========================================================

def chat_with_gemma(subject_name, conversation_history, user_message):
    contents = []

    try:
        if not conversation_history:

            first_prompt = (
                f"{SYSTEM_PROMPT}\n\n"
                f"Subject: {subject_name}\n\n"
                f"Student: {user_message}"
            )

            contents.append(make_content("user", first_prompt))

        else:
            # LIMIT HISTORY BIAR RINGAN
            for msg in conversation_history[-2:]:

                role = (
                    "user"
                    if msg.get("role") == "user"
                    else "model"
                )

                contents.append(
                    make_content(
                        role,
                        msg.get("parts", "")
                    )
                )

            contents.append(
                make_content("user", user_message)
            )

        response = client.models.generate_content(
            model=MODEL_FAST,
            contents=contents,
            config=FAST_CONFIG
        )

        return clean_markdown(response.text)

    except Exception as e:

        print("CHAT ERROR:", e)

        return (
            "The AI is currently busy or the connection is unstable. "
            "Please try again."
        )


# =========================================================
# ROADMAP
# =========================================================

def generate_roadmap(subject_name):

    prompt = (
        f'Create a learning roadmap for "{subject_name}".\n\n'

        f'Rules:\n'
        f'- Generate exactly 6 main topics\n'
        f'- Each topic must have exactly 3 subtopics\n'
        f'- Order from beginner to advanced\n'
        f'- Keep topics concise\n\n'

        f'Return ONLY valid JSON:\n\n'

        f'{{\n'
        f'  "topics": [\n'
        f'    {{\n'
        f'      "title": "Topic Name",\n'
        f'      "subtopics": [\n'
        f'        "Subtopic 1",\n'
        f'        "Subtopic 2",\n'
        f'        "Subtopic 3"\n'
        f'      ]\n'
        f'    }}\n'
        f'  ]\n'
        f'}}'
    )

    try:

        response = client.models.generate_content(
            model=MODEL_FAST,
            contents=[make_content("user", prompt)],
            config=ROADMAP_CONFIG
        )

        raw = response.text.strip()

        raw = re.sub(r'```json|```', '', raw).strip()

        json_match = re.search(r'\{.*\}', raw, re.DOTALL)

        if json_match:
            raw = json_match.group()

        data = json.loads(raw)

        topics = data.get("topics", [])

        if topics:
            return topics

        return []

    except Exception as e:

        print("ROADMAP ERROR:", e)

        return [
            {
                "title": "Introduction",
                "subtopics": [
                    "Basic Concepts",
                    "Core Principles",
                    "Simple Applications"
                ]
            },
            {
                "title": "Fundamentals",
                "subtopics": [
                    "Important Terms",
                    "Problem Solving",
                    "Examples"
                ]
            },
            {
                "title": "Intermediate Concepts",
                "subtopics": [
                    "Analysis",
                    "Implementation",
                    "Case Study"
                ]
            },
            {
                "title": "Advanced Topics",
                "subtopics": [
                    "Optimization",
                    "Advanced Methods",
                    "Real World Usage"
                ]
            },
            {
                "title": "Projects",
                "subtopics": [
                    "Mini Project",
                    "Testing",
                    "Evaluation"
                ]
            },
            {
                "title": "Final Review",
                "subtopics": [
                    "Summary",
                    "Common Mistakes",
                    "Practice"
                ]
            }
        ]


# =========================================================
# UNDERSTANDING CHECK
# =========================================================

def generate_understanding_check(
    subject_name,
    topic_name,
    conversation_history=None
):

    prompt = (
        f'Create ONE university-level open-ended question about "{topic_name}" '
        f'for the subject "{subject_name}".\n\n'

        f'Rules:\n'
        f'- Must test understanding\n'
        f'- Must ask for explanation or application\n'
        f'- No yes/no questions\n'
        f'- No definition-only questions\n\n'

        f'Write ONLY the question.'
    )

    try:

        response = client.models.generate_content(
            model=MODEL_FAST,
            contents=[make_content("user", prompt)],
            config=FAST_CONFIG
        )

        result = clean_markdown(response.text.strip())

        if not result or len(result) < 10:
            raise ValueError("Invalid question")

        result = re.sub(
            r'^(Question:|Q:)\s*',
            '',
            result,
            flags=re.IGNORECASE
        )

        return result.strip()

    except Exception as e:

        print("QUESTION ERROR:", e)

        fallback_questions = [
            f"Explain the concept of '{topic_name}' and provide a real-world example.",
            f"Why is '{topic_name}' important in {subject_name}?",
            f"How would you apply '{topic_name}' in practice?"
        ]

        return random.choice(fallback_questions)


# =========================================================
# EVALUATE ANSWER
# =========================================================

def evaluate_answer(subject_name, question, user_answer):

    prompt = (
        f'You are evaluating a student answer for "{subject_name}".\n\n'

        f'Question:\n{question}\n\n'

        f'Student Answer:\n{user_answer}\n\n'

        f'Respond ONLY in this format:\n\n'

        f'SKOR: [0-100]\n'
        f'TOPIK: [topic]\n'
        f'FEEDBACK: [short constructive feedback]\n\n'

        f'Rules:\n'
        f'- Give fair scoring\n'
        f'- Feedback must be constructive\n'
        f'- Use the same language as the student answer\n'
        f'- Do not add extra text'
    )

    try:

        response = client.models.generate_content(
            model=MODEL_STRONG,
            contents=[make_content("user", prompt)],
            config=EVAL_CONFIG
        )

        return response.text.strip()

    except Exception as e:

        print("EVALUATION ERROR:", e)

        return (
            "SKOR: 40\n"
            "TOPIK: General\n"
            "FEEDBACK: Your answer was received, but the evaluation system is currently unstable."
        )


# =========================================================
# IMAGE ANALYSIS
# =========================================================

def chat_with_image(
    subject_name,
    user_message,
    image_base64,
    mime_type="image/jpeg"
):

    prompt = (
        f'You are FriendCampus.AI for "{subject_name}".\n\n'

        f'The student uploaded an image and asked:\n'
        f'"{user_message}"\n\n'

        f'Analyze the image and explain clearly.\n'
        f'Use plain text only.'
    )

    try:

        response = client.models.generate_content(
            model=MODEL_FAST,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                mime_type=mime_type,
                                data=image_base64
                            )
                        ),
                        types.Part(text=prompt)
                    ]
                )
            ],
            config=FAST_CONFIG
        )

        return clean_markdown(response.text)

    except Exception as e:

        print("IMAGE ERROR:", e)

        return (
            "I could not analyze the image right now. "
            "Please try again later."
        )


# =========================================================
# REFERENCES
# =========================================================

def find_references(subject_name, query):

    prompt = (
        f'Find 5 academic references about "{query}" '
        f'for the subject "{subject_name}".\n\n'

        f'Prioritize papers and educational resources.\n\n'

        f'Return ONLY valid JSON:\n\n'

        f'{{\n'
        f'  "references": [\n'
        f'    {{\n'
        f'      "title": "Reference Title",\n'
        f'      "type": "paper",\n'
        f'      "author": "Author",\n'
        f'      "year": "2024",\n'
        f'      "summary": "Short explanation",\n'
        f'      "url": "https://...",\n'
        f'      "tags": ["tag1", "tag2"]\n'
        f'    }}\n'
        f'  ]\n'
        f'}}'
    )

    try:

        response = client.models.generate_content(
            model=MODEL_FAST,
            contents=[make_content("user", prompt)],
            config=types.GenerateContentConfig(
                tools=[
                    types.Tool(
                        google_search=types.GoogleSearch()
                    )
                ],
                temperature=0.5,
                max_output_tokens=300
            )
        )

        raw = response.text.strip()

        raw = re.sub(r'```json|```', '', raw).strip()

        json_match = re.search(r'\{.*\}', raw, re.DOTALL)

        if json_match:
            raw = json_match.group()

        data = json.loads(raw)

        refs = data.get("references", [])

        if refs:
            return refs

        raise ValueError("No references found")

    except Exception as e:

        print("REFERENCE ERROR:", e)

        return [
            {
                "title": f"Resources for {query}",
                "type": "website",
                "author": "Google Scholar",
                "year": "Online",
                "summary": f"Search references about {query}.",
                "url": f"https://scholar.google.com/scholar?q={query.replace(' ', '+')}",
                "tags": [query, subject_name]
            }
        ]