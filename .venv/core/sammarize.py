from langchain_mistralai import ChatMistralAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

import os
from functools import lru_cache

from core.llm_utils import invoke_with_rate_limit_retry

MAX_SUMMARY_INPUT_CHARS = 24000


@lru_cache(maxsize=1)
def get_llm():
    return ChatMistralAI(
        model_name="mistral-small-latest",
        api_key=os.getenv("MISTRAL_API_KEY"),
        temperature=0.3,
        max_retries=6,
        timeout=120,
        max_concurrent_requests=1,
    )


def split_transcript(transcript: str) -> list:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=3000,
        chunk_overlap=200,
        )

    return splitter.split_text(transcript)

def summarize(transcript: str) -> str:
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert meeting summarizer. Summarize the transcript into "
                "clear professional bullet points covering the main topics, decisions, "
                "and outcomes. Be concise and do not invent details.",
            ),
            ("human", "{text}"),
        ]
    )
    chain = prompt | llm | StrOutputParser()
    return invoke_with_rate_limit_retry(
        lambda: chain.invoke({"text": transcript[:MAX_SUMMARY_INPUT_CHARS]})
    )


def generate_title(transcipt: str) -> str:
    llm = get_llm()

    title_chain = (
        RunnablePassthrough()
        | RunnableLambda(lambda x: {"text": x})
        | ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Based on the meeting transcript, generate a short professional meeting title. "
                    "(max 8 words). Only return the title, nothing else.",
                ),
                ("human", "{text}"),
            ]
        )
        | llm
        | StrOutputParser()
    )

    return invoke_with_rate_limit_retry(lambda: title_chain.invoke(transcipt[:2000]))