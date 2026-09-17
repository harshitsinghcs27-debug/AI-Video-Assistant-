import re
from collections import Counter


_STOPWORDS = {
    "about", "after", "again", "also", "been", "being", "could", "from",
    "have", "into", "just", "more", "should", "some", "such", "than",
    "that", "their", "there", "these", "they", "this", "what", "when",
    "where", "which", "will", "with", "would", "your", "you",
}
_ACTION_TERMS = (
    "action", "todo", "task", "follow up", "follow-up", "need to", "will ", "assign",
    "सीखो", "सीखना", "सीखने पड़ेंगे", "बना लो", "करना है", "करना पड़ेगा",
    "कर सकते हो", "फोकस करो", "फोकस करना है", "इग्नोर करना पड़ेगा", "ढूंढना",
    "पढ़ना", "सेटअप बना", "अकाउंट बना",
)
_DECISION_TERMS = (
    "decided", "decision", "agreed", "approved", "selected", "final", "we will",
    "चुनो", "चूज़", "चॉइस", "जा सकते हो", "जरूरत नहीं", "नहीं करना", "सही चीज",
    "बेहतर है", "काम आती है", "यूज़ होती है",
)
_QUESTION_TERMS = (
    "?", "open question", "unclear", "need to confirm", "tbd", "follow up",
    "क्यों", "कैसे", "कौन सी", "कौन से", "कौन", "कहां", "कहां पे", "फिगर आउट",
)


def _sentences(transcript: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?؟।॥])\s+|\n+", transcript or "")
        if sentence.strip()
    ]


def _unique(items: list[str], limit: int = 8) -> list[str]:
    seen = set()
    result = []
    for item in items:
        normalized = re.sub(r"\W+", " ", item.lower()).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(item)
        if len(result) == limit:
            break
    return result


def summarize_locally(transcript: str) -> str:
    sentences = _sentences(transcript)
    if not sentences:
        return "No transcript content available for summary."
    words = re.findall(r"[^\W\d_]{3,}", transcript.lower(), flags=re.UNICODE)
    frequent = Counter(word for word in words if word not in _STOPWORDS).most_common(12)
    keywords = {word for word, _ in frequent}
    ranked = sorted(
        enumerate(sentences),
        key=lambda pair: (
            sum(word in keywords for word in re.findall(r"[^\W\d_]{3,}", pair[1].lower(), flags=re.UNICODE)),
            -pair[0],
        ),
        reverse=True,
    )
    selected = sorted((index, sentence) for index, sentence in ranked[:5])
    lines = [f"- {sentence}" for _, sentence in selected]
    return "**Local extractive summary**\n\n" + "\n".join(lines)


def title_locally(transcript: str) -> str:
    sentence = _sentences(transcript)
    if not sentence:
        return "Meeting transcript"
    words = re.findall(r"[^\W\d_]+", sentence[0], flags=re.UNICODE)
    return " ".join(words[:8]).strip(" .,?!") or "Meeting transcript"


def extract_locally(transcript: str, terms: tuple[str, ...], empty: str) -> str:
    matches = [sentence for sentence in _sentences(transcript) if any(term in sentence.lower() for term in terms)]
    matches = _unique(matches)
    if not matches:
        return empty
    return "\n".join(f"{index}. {sentence}" for index, sentence in enumerate(matches, 1))


def action_items_locally(transcript: str) -> str:
    return extract_locally(transcript, _ACTION_TERMS, "No likely action items found in the transcript.")


def decisions_locally(transcript: str) -> str:
    return extract_locally(transcript, _DECISION_TERMS, "No likely decisions found in the transcript.")


def questions_locally(transcript: str) -> str:
    return extract_locally(transcript, _QUESTION_TERMS, "No likely open questions found in the transcript.")


def answer_locally(transcript: str, question: str) -> str:
    sentences = _sentences(transcript)
    terms = [
        word
        for word in re.findall(r"[^\W\d_]{3,}", question.lower(), flags=re.UNICODE)
        if word not in _STOPWORDS
    ]
    matches = sorted(
        sentences,
        key=lambda sentence: sum(term in sentence.lower() for term in terms),
        reverse=True,
    )
    matches = [sentence for sentence in matches if any(term in sentence.lower() for term in terms)][:3]
    if not matches:
        return "I could not find this information in the meeting transcript."
    return "Based on the transcript:\n\n" + "\n".join(f"- {sentence}" for sentence in matches)