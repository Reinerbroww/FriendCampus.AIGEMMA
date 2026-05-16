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

# ===== MODELS =====
MODEL_FAST = "models/gemma-4-26b-a4b-it"
MODEL_STRONG = "models/gemma-4-26b-a4b-it"

# ===== SYSTEM PROMPT =====
SYSTEM_PROMPT = """You are FriendCampus.AI, a smart and friendly AI study companion for university students.

FORMATTING RULES — follow strictly:
- Use plain text only. NO markdown symbols like **, *, #, __, or backticks
- For math use unicode superscripts: x² + 2x + 1 = 0, not x^2
- For fractions write: 1/2, 3/4, etc
- Use numbered lists: 1. First  2. Second  3. Third
- Use letters for sub-points: a. first  b. second
- Separate sections with a blank line
- Keep responses clear, concise, and friendly
- Always explain step by step for math or code problems
- Never give just the answer — explain the reasoning
- Respond in the same language the student uses (Indonesian or English)
"""

# ===== GENERATION CONFIG =====
FAST_CONFIG = types.GenerateContentConfig(
    temperature=0.7,
    max_output_tokens=350
)

ROADMAP_CONFIG = types.GenerateContentConfig(
    temperature=0.5,
    max_output_tokens=450
)

EVAL_CONFIG = types.GenerateContentConfig(
    temperature=0.3,
    max_output_tokens=250
)

# ===== HELPERS =====
def clean_markdown(text):
    if not text:
        return ""

    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)

    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    text = re.sub(r'```[\w]*\n?(.*?)```', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'`(.+?)`', r'\1', text)

    text = re.sub(r'^[-*]{3,}$', '', text, flags=re.MULTILINE)

    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def make_content(role, text):
    return types.Content(
        role=role,
        parts=[types.Part(text=text)]
    )


# ===== CHAT =====
def chat_with_gemma(subject_name, conversation_history, user_message):
    contents = []

    if not conversation_history:
        first_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Subject being studied: {subject_name}\n\n"
            f"Student: {user_message}"
        )

        contents.append(make_content("user", first_prompt))

    else:
        # Limit history supaya lebih ringan
        for msg in conversation_history[-6:]:
            role = "user" if msg.get("role") == "user" else "model"

            contents.append(
                make_content(role, msg.get("parts", ""))
            )

        contents.append(make_content("user", user_message))

    try:
        response = client.models.generate_content(
            model=MODEL_FAST,
            contents=contents,
            config=FAST_CONFIG
        )

        return clean_markdown(response.text)

    except Exception as e:
        print("CHAT ERROR:", e)

        return (
            "The AI is currently busy or the server connection is unstable. "
            "Please try sending your message again."
        )


# ===== ROADMAP =====
def generate_roadmap(subject_name):
    prompt = (
        f'Create a learning roadmap for the university course "{subject_name}".\n\n'

        f'Rules:\n'
        f'- Generate exactly 6 main topics\n'
        f'- Each topic must contain exactly 3 subtopics\n'
        f'- Order topics from beginner to advanced\n'
        f'- Keep topic names concise\n'
        f'- Keep subtopics specific and practical\n\n'

        f'Return ONLY valid JSON in this exact format:\n'
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

        # fallback roadmap
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
                    "Key Terminology",
                    "Problem Solving",
                    "Practical Examples"
                ]
            },
            {
                "title": "Intermediate Concepts",
                "subtopics": [
                    "System Design",
                    "Analysis Methods",
                    "Case Studies"
                ]
            },
            {
                "title": "Advanced Topics",
                "subtopics": [
                    "Optimization",
                    "Real-world Usage",
                    "Advanced Techniques"
                ]
            },
            {
                "title": "Projects",
                "subtopics": [
                    "Mini Project",
                    "Implementation",
                    "Testing"
                ]
            },
            {
                "title": "Final Review",
                "subtopics": [
                    "Comprehensive Review",
                    "Common Mistakes",
                    "Final Practice"
                ]
            }
        ]


# ===== UNDERSTANDING CHECK =====
def generate_understanding_check(subject_name, topic_name, conversation_history=None):
    prompt = (
        f'You are a study assistant for "{subject_name}".\n\n'

        f'Create ONE university-level open-ended question about:\n'
        f'"{topic_name}"\n\n'

        f'Requirements:\n'
        f'- The question must test understanding\n'
        f'- Ask for explanation or application\n'
        f'- Avoid definition-only questions\n'
        f'- Cannot be answered with yes/no\n\n'

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

        fallbacks = [
            f"Explain the concept of '{topic_name}' in your own words and provide a real-world example.",
            f"Why is '{topic_name}' important in {subject_name}?",
            f"How would you apply '{topic_name}' in a practical situation?"
        ]

        return random.choice(fallbacks)


# ===== EVALUATION =====
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
            "FEEDBACK: Your answer was received, but the evaluation service is currently unstable. Please try again later."
        )


# ===== IMAGE ANALYSIS =====
def chat_with_image(subject_name, user_message, image_base64, mime_type="image/jpeg"):
    prompt = (
        f'You are FriendCampus.AI, a study assistant for "{subject_name}".\n\n'

        f'The student uploaded an image and asks:\n'
        f'"{user_message}"\n\n'

        f'Analyze the image carefully and provide a helpful explanation.\n'

        f'Use plain text only.\n'
        f'Respond in the same language as the student.'
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
            "Please try again or describe the image in text."
        )


# ===== REFERENCES =====
def find_references(subject_name, query):
    prompt = (
        f'You are an academic assistant.\n\n'

        f'Find 5 academic references related to:\n'
        f'"{query}"\n\n'

        f'Prioritize academic papers and educational resources.\n\n'

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
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.5,
                max_output_tokens=500
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

        raise ValueError("No references")

    except Exception as e:
        print("REFERENCE ERROR:", e)

        return [{
            "title": f"Resources for {query}",
            "type": "website",
            "author": "Google Scholar",
            "year": "Online",
            "summary": f"Search academic references about {query}.",
            "url": f"https://scholar.google.com/scholar?q={query.replace(' ', '+')}",
            "tags": [query, subject_name]
        }]