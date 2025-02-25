import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from langchain.schema import ChatMessage

from khoj.processor.conversation import prompts
from khoj.processor.conversation.openai.utils import (
    chat_completion_with_backoff,
    completion_with_backoff,
)
from khoj.processor.conversation.utils import generate_chatml_messages_with_context
from khoj.utils.constants import empty_escape_sequences
from khoj.utils.helpers import ConversationCommand, is_none_or_empty

logger = logging.getLogger(__name__)


def extract_questions(
    text,
    model: Optional[str] = "gpt-4",
    conversation_log={},
    api_key=None,
    temperature=0,
    max_tokens=100,
):
    """
    Infer search queries to retrieve relevant notes to answer user query
    """

    def _valid_question(question: str):
        return not is_none_or_empty(question) and question != "[]"

    # Extract Past User Message and Inferred Questions from Conversation Log
    chat_history = "".join(
        [
            f'Q: {chat["intent"]["query"]}\n\n{chat["intent"].get("inferred-queries") or list([chat["intent"]["query"]])}\n\n{chat["message"]}\n\n'
            for chat in conversation_log.get("chat", [])[-4:]
            if chat["by"] == "khoj" and chat["intent"].get("type") != "text-to-image"
        ]
    )

    # Get dates relative to today for prompt creation
    today = datetime.today()
    current_new_year = today.replace(month=1, day=1)
    last_new_year = current_new_year.replace(year=today.year - 1)

    prompt = prompts.extract_questions.format(
        current_date=today.strftime("%A, %Y-%m-%d"),
        last_new_year=last_new_year.strftime("%Y"),
        last_new_year_date=last_new_year.strftime("%Y-%m-%d"),
        current_new_year_date=current_new_year.strftime("%Y-%m-%d"),
        bob_tom_age_difference={current_new_year.year - 1984 - 30},
        bob_age={current_new_year.year - 1984},
        chat_history=chat_history,
        text=text,
        yesterday_date=(today - timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    messages = [ChatMessage(content=prompt, role="assistant")]

    # Get Response from GPT
    response = completion_with_backoff(
        messages=messages,
        model_name=model,
        temperature=temperature,
        max_tokens=max_tokens,
        model_kwargs={"stop": ["A: ", "\n"]},
        openai_api_key=api_key,
    )

    # Extract, Clean Message from GPT's Response
    try:
        split_questions = (
            response.content.strip(empty_escape_sequences)
            .replace("['", '["')
            .replace("']", '"]')
            .replace("', '", '", "')
            .replace('["', "")
            .replace('"]', "")
            .split('", "')
        )
        questions = []

        for question in split_questions:
            if question not in questions and _valid_question(question):
                questions.append(question)

        if is_none_or_empty(questions):
            raise ValueError("GPT returned empty JSON")
    except:
        logger.warning(f"GPT returned invalid JSON. Falling back to using user message as search query.\n{response}")
        questions = [text]

    logger.debug(f"Extracted Questions by GPT: {questions}")
    return questions


def send_message_to_model(
    message,
    api_key,
    model,
):
    """
    Send message to model
    """
    messages = [ChatMessage(content=message, role="assistant")]

    # Get Response from GPT
    return completion_with_backoff(
        messages=messages,
        model_name=model,
        temperature=0,
        max_tokens=100,
        model_kwargs={"stop": ["A: ", "\n"]},
        openai_api_key=api_key,
    )


def converse(
    references,
    user_query,
    online_results=[],
    conversation_log={},
    model: str = "gpt-3.5-turbo",
    api_key: Optional[str] = None,
    temperature: float = 0.2,
    completion_func=None,
    conversation_command=ConversationCommand.Default,
    max_prompt_size=None,
    tokenizer_name=None,
):
    """
    Converse with user using OpenAI's ChatGPT
    """
    # Initialize Variables
    current_date = datetime.now().strftime("%Y-%m-%d")
    compiled_references = "\n\n".join({f"# {item}" for item in references})

    # Get Conversation Primer appropriate to Conversation Type
    if conversation_command == ConversationCommand.Notes and is_none_or_empty(compiled_references):
        completion_func(chat_response=prompts.no_notes_found.format())
        return iter([prompts.no_notes_found.format()])
    elif conversation_command == ConversationCommand.Online and is_none_or_empty(online_results):
        completion_func(chat_response=prompts.no_online_results_found.format())
        return iter([prompts.no_online_results_found.format()])
    elif conversation_command == ConversationCommand.Online:
        conversation_primer = prompts.online_search_conversation.format(
            query=user_query, online_results=str(online_results)
        )
    elif conversation_command == ConversationCommand.General or is_none_or_empty(compiled_references):
        conversation_primer = prompts.general_conversation.format(query=user_query)
    else:
        conversation_primer = prompts.notes_conversation.format(query=user_query, references=compiled_references)

    # Setup Prompt with Primer or Conversation History
    messages = generate_chatml_messages_with_context(
        conversation_primer,
        prompts.personality.format(current_date=current_date),
        conversation_log,
        model,
        max_prompt_size,
        tokenizer_name,
    )
    truncated_messages = "\n".join({f"{message.content[:40]}..." for message in messages})
    logger.debug(f"Conversation Context for GPT: {truncated_messages}")

    # Get Response from GPT
    return chat_completion_with_backoff(
        messages=messages,
        compiled_references=references,
        online_results=online_results,
        model_name=model,
        temperature=temperature,
        openai_api_key=api_key,
        completion_func=completion_func,
        model_kwargs={"stop": ["Notes:\n["]},
    )
