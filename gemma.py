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

MODEL_FAST   = "models/gemma-4-26b-a4b-it"
MODEL_STRONG = "models/gemma-4-26b-a4b-it"

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
- Respond in the same language the student uses (Indonesian or English)"""


# =========================================================
# HELPERS
# =========================================================

def clean_markdown(text):
    """Remove markdown symbols from Gemma responses"""
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


def safe_generate(model, contents, use_search=False):
    """
    Stable wrapper for generate_content
    Better for deployment hosting environments
    """

    config = types.GenerateContentConfig(
        temperature=0.7,
        max_output_tokens=700
    )

    if use_search:
        config.tools = [types.Tool(google_search=types.GoogleSearch())]

    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config
        )

        if not response:
            return None

        if not getattr(response, "text", None):
            return None

        return response.text.strip()

    except Exception as e:
        print("GEMMA ERROR:", str(e))
        return None


# =========================================================
# CHAT
# =========================================================

def chat_with_gemma(subject_name, conversation_history, user_message):
    """Chat with Gemma using conversation history"""

    contents = []

    if not conversation_history:
        first = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Subject being studied: {subject_name}\n\n"
            f"Student: {user_message}"
        )

        contents = [make_content("user", first)]

    else:
        # Limit history to reduce server load
        for msg in conversation_history[-6:]:
            role = "user" if msg.get("role") == "user" else "model"

            contents.append(
                make_content(role, msg.get("parts", ""))
            )

        contents.append(
            make_content("user", user_message)
        )

    result = safe_generate(
        MODEL_FAST,
        contents
    )

    if not result:
        return (
            "The AI is currently busy or the server connection is slow. "
            "Please try sending your message again."
        )

    return clean_markdown(result)


# =========================================================
# ROADMAP
# =========================================================

def generate_roadmap(subject_name):
    """Generate hierarchical roadmap with subtopics"""

    prompt = (
        f'Create a detailed learning roadmap for the university course "{subject_name}".\n\n'
        f'Generate exactly 8-10 main topics, each with exactly 3-4 subtopics.\n\n'
        f'Return ONLY valid JSON in this exact format, absolutely no other text before or after:\n'
        f'{{\n'
        f'  "topics": [\n'
        f'    {{\n'
        f'      "title": "Main Topic Name",\n'
        f'      "subtopics": [\n'
        f'        "Specific subtopic 1",\n'
        f'        "Specific subtopic 2",\n'
        f'        "Specific subtopic 3"\n'
        f'      ]\n'
        f'    }}\n'
        f'  ]\n'
        f'}}\n\n'
        f'Order topics from most basic to most advanced.\n'
        f'Make subtopics specific and actionable.'
    )

    result = safe_generate(
        MODEL_FAST,
        [make_content("user", prompt)]
    )

    if not result:
        return []

    raw = re.sub(r'```json|```', '', result).strip()

    json_match = re.search(r'\{.*\}', raw, re.DOTALL)

    if json_match:
        raw = json_match.group()

    try:
        data = json.loads(raw)

        topics = data.get("topics", [])

        if topics and isinstance(topics[0], dict):
            return topics

    except Exception:
        pass

    # Manual fallback parser
    lines = result.split("\n")

    topics = []
    current = None

    for line in lines:
        line = line.strip()

        if not line:
            continue

        main_match = re.match(r'^\d+[\.\)]\s*(.+)$', line)
        sub_match = re.match(r'^[-•*]\s*(.+)$|^[a-z][\.\)]\s*(.+)$', line)

        if main_match:
            if current:
                topics.append(current)

            current = {
                "title": main_match.group(1).strip(),
                "subtopics": []
            }

        elif sub_match and current:
            sub_text = (
                sub_match.group(1)
                or sub_match.group(2)
                or ""
            ).strip()

            if sub_text:
                current["subtopics"].append(sub_text)

    if current:
        topics.append(current)

    return topics


# =========================================================
# UNDERSTANDING CHECK
# =========================================================

def generate_understanding_check(subject_name, topic_name, conversation_history=None):
    """Generate one open-ended understanding question"""

    prompt = (
        f'You are a study assistant for the subject "{subject_name}".\n\n'
        f'Create ONE open-ended question to test a student\'s understanding of: "{topic_name}"\n\n'
        f'Requirements:\n'
        f'1. The question must be specifically about "{topic_name}"\n'
        f'2. Ask the student to explain in their own words\n'
        f'3. Cannot be answered with just yes or no\n'
        f'4. Should be at university level difficulty\n'
        f'5. Do not ask for a definition — ask for explanation or application\n\n'
        f'Write ONLY the question itself. No introduction, no explanation, no numbering.'
    )

    result = safe_generate(
        MODEL_FAST,
        [make_content("user", prompt)]
    )

    if not result:
        fallbacks = [
            f"Explain the concept of '{topic_name}' in your own words and provide a real-world example of how it is applied.",
            f"Describe the key principles of '{topic_name}' and explain why it is important in the context of {subject_name}.",
            f"How would you explain '{topic_name}' to someone who has never studied {subject_name} before? What are the most important points to cover?"
        ]

        return random.choice(fallbacks)

    result = clean_markdown(result)

    result = re.sub(
        r'^(Question:|Q:|Here\'s a question:|Sure,?|Of course,?)\s*',
        '',
        result,
        flags=re.IGNORECASE
    )

    return result.strip()


# =========================================================
# ANSWER EVALUATION
# =========================================================

def evaluate_answer(subject_name, question, user_answer):
    """Evaluate student answer"""

    prompt = (
        f'You are evaluating a student answer for the subject "{subject_name}".\n\n'
        f'Question asked: {question}\n\n'
        f'Student answer: {user_answer}\n\n'
        f'Evaluate the answer carefully and respond in EXACTLY this format:\n'
        f'SKOR: [a number from 0 to 100]\n'
        f'TOPIK: [the topic being tested, 1-4 words]\n'
        f'FEEDBACK: [2-3 sentences of specific, constructive feedback]\n\n'
        f'Scoring guide:\n'
        f'90-100: Answer is complete, accurate, and well-explained\n'
        f'70-89: Mostly correct with minor gaps or inaccuracies\n'
        f'50-69: Partially correct, missing key concepts\n'
        f'30-49: Shows some understanding but significant gaps\n'
        f'10-29: Mostly incorrect but shows some effort\n'
        f'5-9: Completely off-topic or irrelevant\n\n'
        f'CRITICAL RULES:\n'
        f'- ALWAYS give score above 0 if the student wrote any relevant content\n'
        f'- Give score above 50 if the answer shows basic understanding\n'
        f'- Write FEEDBACK in the same language as the student answer\n'
        f'- Do not add any extra text outside the format above'
    )

    result = safe_generate(
        MODEL_STRONG,
        [make_content("user", prompt)]
    )

    if not result:
        return (
            "SKOR: 40\n"
            "TOPIK: General\n"
            "FEEDBACK: Your answer was received but the AI evaluator is currently busy. Please try again later."
        )

    return result


# =========================================================
# IMAGE ANALYSIS
# =========================================================

def chat_with_image(subject_name, user_message, image_base64, mime_type="image/jpeg"):
    """Analyze image and answer user question"""

    prompt = (
        f'You are FriendCampus.AI, a study assistant for the subject "{subject_name}".\n\n'
        f'The student uploaded an image and asks: "{user_message}"\n\n'
        f'Please analyze the image carefully and provide a helpful, detailed response:\n'
        f'- If it contains a math problem: solve it completely, step by step\n'
        f'- If it contains a diagram or chart: explain what it shows and its significance\n'
        f'- If it contains text or notes: summarize the key concepts clearly\n'
        f'- If it contains code: explain what the code does and identify any issues\n'
        f'- For anything else: describe what you see and explain its relevance\n\n'
        f'Use plain text only, no markdown symbols.\n'
        f'Respond in the same language the student uses.'
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
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=700
            )
        )

        if not response or not response.text:
            return (
                "The AI failed to analyze the image. "
                "Please try uploading a smaller image."
            )

        return clean_markdown(response.text)

    except Exception as e:
        print("IMAGE ERROR:", str(e))

        return (
            "The AI could not analyze the image at the moment. "
            "Please try again later."
        )


# =========================================================
# REFERENCES
# =========================================================

def find_references(subject_name, query):
    """Find academic references"""

    prompt = (
        f'You are an academic research assistant helping a student studying "{subject_name}".\n\n'
        f'Find 6-7 high quality academic references about: "{query}"\n\n'
        f'Include a mix of: textbooks, academic papers, educational websites, and online courses, but prioritize academic papers.\n\n'
        f'The reference links must be available.\n\n'
        f'Return ONLY a valid JSON object, absolutely no other text:\n'
        f'{{\n'
        f'  "references": [\n'
        f'    {{\n'
        f'      "title": "Full title of the reference",\n'
        f'      "type": "paper OR book OR article OR website OR course",\n'
        f'      "author": "Author name or organization",\n'
        f'      "year": "Publication year or Online",\n'
        f'      "summary": "2-3 sentences describing what this covers and why it is useful",\n'
        f'      "url": "Direct URL if available, empty string if not",\n'
        f'      "tags": ["tag1", "tag2", "tag3"]\n'
        f'    }}\n'
        f'  ]\n'
        f'}}'
    )

    result = safe_generate(
        MODEL_FAST,
        [make_content("user", prompt)],
        use_search=True
    )

    if not result:
        return [{
            "title": f"Academic resources for {query}",
            "type": "website",
            "author": "Google Scholar",
            "year": "Online",
            "summary": (
                f"Search Google Scholar for peer-reviewed papers and academic resources "
                f"about {query} in the context of {subject_name}."
            ),
            "url": f"https://scholar.google.com/scholar?q={query.replace(' ', '+')}+{subject_name.replace(' ', '+')}",
            "tags": [query, subject_name, "academic"]
        }]

    raw = re.sub(r'```json|```', '', result).strip()

    json_match = re.search(r'\{.*\}', raw, re.DOTALL)

    if json_match:
        raw = json_match.group()

    try:
        data = json.loads(raw)

        refs = data.get("references", [])

        if refs:
            return refs

    except Exception:
        pass

    return [{
        "title": f"Academic resources for {query}",
        "type": "website",
        "author": "Google Scholar",
        "year": "Online",
        "summary": (
            f"Search Google Scholar for peer-reviewed papers and academic resources "
            f"about {query} in the context of {subject_name}."
        ),
        "url": f"https://scholar.google.com/scholar?q={query.replace(' ', '+')}+{subject_name.replace(' ', '+')}",
        "tags": [query, subject_name, "academic"]
    }]