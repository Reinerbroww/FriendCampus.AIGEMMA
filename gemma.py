import os
import re
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("API key not found! Check your .env file.")

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


def clean_markdown(text):
    """Hapus simbol markdown dari response Gemma"""
    if not text:
        return ""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*',     r'\1', text)
    text = re.sub(r'__(.+?)__',     r'\1', text)
    text = re.sub(r'_(.+?)_',       r'\1', text)
    text = re.sub(r'^#{1,6}\s+',    '',    text, flags=re.MULTILINE)
    text = re.sub(r'```[\w]*\n?(.*?)```', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'`(.+?)`',       r'\1', text)
    text = re.sub(r'^[-*]{3,}$',    '',    text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}',        '\n\n', text)
    return text.strip()


def make_content(role, text):
    """Helper bikin Content object"""
    return types.Content(
        role=role,
        parts=[types.Part(text=text)]
    )


def chat_with_gemma(subject_name, conversation_history, user_message):
    """Chat biasa — return string"""
    contents = []

    if not conversation_history:
        first = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Subject being studied: {subject_name}\n\n"
            f"Student: {user_message}"
        )
        contents = [make_content("user", first)]
    else:
        for msg in conversation_history:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append(make_content(role, msg.get("parts", "")))
        contents.append(make_content("user", user_message))

    try:
        response = client.models.generate_content(
            model=MODEL_FAST,
            contents=contents
        )
        return clean_markdown(response.text)
    except Exception as e:
        raise Exception(f"Chat failed: {str(e)}")


def chat_with_gemma_stream(subject_name, conversation_history, user_message):
    """Chat dengan streaming — return generator"""
    contents = []

    if not conversation_history:
        first = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Subject being studied: {subject_name}\n\n"
            f"Student: {user_message}"
        )
        contents = [make_content("user", first)]
    else:
        for msg in conversation_history:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append(make_content(role, msg.get("parts", "")))
        contents.append(make_content("user", user_message))

    try:
        response = client.models.generate_content_stream(
            model=MODEL_FAST,
            contents=contents
        )
        return response
    except Exception as e:
        raise Exception(f"Stream failed: {str(e)}")


def generate_roadmap(subject_name):
    """Generate roadmap hierarki dengan sub-topik dalam format JSON"""
    prompt = (
        f'Create a detailed learning roadmap for the university course "{subject_name}".\n\n'
        f'Generate exactly 8-10 main topics, each with exactly 3-4 subtopics.\n\n'
        f'Return ONLY valid JSON in this exact format, absolutely no other text:\n'
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
        f'Make subtopics specific and actionable.\n'
        f'Do not include any explanation or text outside the JSON.'
    )

    try:
        response = client.models.generate_content(
            model=MODEL_FAST,
            contents=[make_content("user", prompt)]
        )

        raw = response.text.strip()
        raw = re.sub(r'```json|```', '', raw).strip()

        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            raw = json_match.group()

        try:
            data   = json.loads(raw)
            topics = data.get("topics", [])
            if topics and isinstance(topics[0], dict):
                return topics
        except json.JSONDecodeError:
            pass

        # Fallback — parse sebagai numbered list
        lines   = response.text.strip().split('\n')
        topics  = []
        current = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            main_match = re.match(r'^\d+[\.\)]\s*(.+)$', line)
            sub_match  = re.match(r'^[-•*]\s*(.+)$|^[a-z][\.\)]\s*(.+)$', line)

            if main_match:
                if current:
                    topics.append(current)
                current = {
                    "title":     main_match.group(1).strip(),
                    "subtopics": []
                }
            elif sub_match and current:
                sub_text = (sub_match.group(1) or sub_match.group(2) or "").strip()
                if sub_text:
                    current["subtopics"].append(sub_text)

        if current:
            topics.append(current)

        return topics if topics else []

    except Exception as e:
        raise Exception(f"Roadmap generation failed: {str(e)}")


def generate_understanding_check(subject_name, topic_name, conversation_history=None):
    """Generate satu pertanyaan open-ended untuk cek pemahaman"""
    prompt = (
        f'You are a study assistant for the subject "{subject_name}".\n\n'
        f'Create ONE open-ended question to test a student\'s understanding of: "{topic_name}"\n\n'
        f'Requirements:\n'
        f'1. The question must be specifically about "{topic_name}"\n'
        f'2. Ask the student to explain in their own words\n'
        f'3. Cannot be answered with just yes or no\n'
        f'4. Should be at university level difficulty\n'
        f'5. Do not ask for a definition — ask for explanation or application\n\n'
        f'Write ONLY the question itself.\n'
        f'No introduction, no explanation, no numbering, no extra text.'
    )

    try:
        response = client.models.generate_content(
            model=MODEL_FAST,
            contents=[make_content("user", prompt)]
        )
        result = clean_markdown(response.text.strip())

        if not result or len(result) < 10:
            raise ValueError("Question too short or empty")

        result = re.sub(
            r'^(Question:|Q:|Here\'s a question:|Sure,?|Of course,?|Certainly,?)\s*',
            '', result, flags=re.IGNORECASE
        )
        return result.strip()

    except Exception as e:
        import random
        fallbacks = [
            f"Explain the concept of '{topic_name}' in your own words and provide a real-world example of how it is applied.",
            f"Describe the key principles of '{topic_name}' and explain why it is important in the context of {subject_name}.",
            f"How would you explain '{topic_name}' to someone who has never studied {subject_name} before? What are the most important points?",
            f"What are the main challenges or common misconceptions related to '{topic_name}'? How would you address them?"
        ]
        return random.choice(fallbacks)


def evaluate_answer(subject_name, question, user_answer):
    """Evaluasi jawaban user dan kasih skor + feedback"""
    prompt = (
        f'You are evaluating a student answer for the subject "{subject_name}".\n\n'
        f'Question asked:\n{question}\n\n'
        f'Student answer:\n{user_answer}\n\n'
        f'Evaluate the answer and respond in EXACTLY this format, no other text:\n'
        f'SKOR: [number 0-100]\n'
        f'TOPIK: [topic in 1-4 words]\n'
        f'FEEDBACK: [2-3 sentences of specific constructive feedback]\n\n'
        f'Scoring guide:\n'
        f'90-100: Complete, accurate, well-explained\n'
        f'70-89: Mostly correct, minor gaps\n'
        f'50-69: Partially correct, missing key concepts\n'
        f'30-49: Some understanding but significant gaps\n'
        f'10-29: Mostly incorrect but shows effort\n'
        f'5-9: Completely off-topic\n\n'
        f'CRITICAL:\n'
        f'- Always give score above 0 if student wrote relevant content\n'
        f'- Give above 50 if answer shows basic understanding\n'
        f'- Write FEEDBACK in the same language as the student answer\n'
        f'- Never leave FEEDBACK empty\n'
        f'- Use exactly the format above, nothing else'
    )

    try:
        response = client.models.generate_content(
            model=MODEL_STRONG,
            contents=[make_content("user", prompt)]
        )
        return response.text.strip()
    except Exception as e:
        raise Exception(f"Evaluation failed: {str(e)}")


def chat_with_image(subject_name, user_message, image_base64, mime_type="image/jpeg"):
    """Analisis gambar + jawab pertanyaan user"""
    prompt = (
        f'You are FriendCampus.AI, a study assistant for the subject "{subject_name}".\n\n'
        f'The student uploaded an image and asks: "{user_message}"\n\n'
        f'Analyze the image carefully and provide a helpful response:\n'
        f'- Math problem: solve completely, step by step\n'
        f'- Diagram or chart: explain what it shows and its significance\n'
        f'- Text or notes: summarize the key concepts clearly\n'
        f'- Code: explain what it does and identify any issues\n'
        f'- Other: describe what you see and explain its relevance\n\n'
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
            ]
        )
        return clean_markdown(response.text)

    except Exception as e:
        error_str = str(e).lower()

        if any(kw in error_str for kw in ["image", "vision", "multimodal", "unsupported"]):
            try:
                fallback_prompt = (
                    f'A student studying "{subject_name}" uploaded an image '
                    f'and asks: "{user_message}"\n\n'
                    f'Provide a helpful explanation about this topic.\n'
                    f'Use plain text only, respond in the same language as the question.'
                )
                response = client.models.generate_content(
                    model=MODEL_FAST,
                    contents=[make_content("user", fallback_prompt)]
                )
                return (
                    "Note: I could not process the image directly. "
                    "Here is a relevant explanation:\n\n"
                    + clean_markdown(response.text)
                )
            except Exception:
                return (
                    "Sorry, I was unable to analyze the image. "
                    "Please try describing your question in text instead."
                )

        raise Exception(f"Image analysis failed: {str(e)}")


def find_references(subject_name, query):
    """Cari referensi akademik menggunakan Gemma + web search"""
    prompt = (
        f'You are an academic research assistant for a student studying "{subject_name}".\n\n'
        f'Find 6-7 high quality academic references about: "{query}"\n\n'
        f'Include: textbooks, academic papers, educational websites, online courses.\n\n'
        f'paper must 2024, 2025, 2026, and the link can be access.\n\n'
        f'Return ONLY a valid JSON object, no other text before or after:\n'
        f'{{\n'
        f'  "references": [\n'
        f'    {{\n'
        f'      "title": "Full title of the reference",\n'
        f'      "type": "paper OR book OR article OR website OR course",\n'
        f'      "author": "Author name or organization",\n'
        f'      "year": "Publication year or Online",\n'
        f'      "summary": "2-3 sentences about what this covers and why useful",\n'
        f'      "url": "Direct URL if available, empty string if not",\n'
        f'      "tags": ["tag1", "tag2", "tag3"]\n'
        f'    }}\n'
        f'  ]\n'
        f'}}'
    )

    # Coba dengan web search dulu
    try:
        response = client.models.generate_content(
            model=MODEL_FAST,
            contents=[make_content("user", prompt)],
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
    except Exception:
        # Fallback tanpa web search
        try:
            response = client.models.generate_content(
                model=MODEL_FAST,
                contents=[make_content("user", prompt)]
            )
        except Exception as e:
            raise Exception(f"Reference search failed: {str(e)}")

    raw = response.text.strip()
    raw = re.sub(r'```json|```', '', raw).strip()

    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if json_match:
        raw = json_match.group()

    try:
        data = json.loads(raw)
        refs = data.get("references", [])
        if refs:
            return refs
    except json.JSONDecodeError:
        pass

    # Fallback kalau parsing gagal
    return [{
        "title":   f"Academic resources for {query}",
        "type":    "website",
        "author":  "Google Scholar",
        "year":    "Online",
        "summary": (
            f"Search Google Scholar for peer-reviewed papers and academic "
            f"resources about {query} in the context of {subject_name}."
        ),
        "url":  (
            f"https://scholar.google.com/scholar?q="
            f"{query.replace(' ', '+')}+{subject_name.replace(' ', '+')}"
        ),
        "tags": [query, subject_name, "academic"]
    }]