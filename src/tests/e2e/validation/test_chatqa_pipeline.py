#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import allure
import json
import logging
import os
import pytest
import requests
import secrets
import statistics
import string
import time

from tests.e2e.validation.constants import DATAPREP_UPLOAD_DIR
from tests.e2e.helpers.api_request_helper import InvalidChatqnaResponseBody
from tests.e2e.validation.buildcfg import cfg

# Skip all tests if chatqna pipeline is not deployed
if cfg.get("pipeline_type") != "chatqna":
    pytestmark = pytest.mark.skip(reason="ChatQnA pipeline is not deployed")

logger = logging.getLogger(__name__)

# These tests change a parameter and assert the chatqna pipeline reflects it, so
# writes must target the scope the chatqna router reads (chatqna._global).
PIPELINE = "chatqna"
TENANT = "_global"


@allure.testcase("IEASG-T32")
def test_chatqa_timeout(chatqa_api_helper):
    """
    The aim is to check if the response is no longer than 60 seconds what may
    lead to closing the connection on the server side.
    """
    question = ("Give me a python script that does a lot of stuff using different libraries. Then do the same for the "
                "following languages: C, C++, Ruby, C#, Java, JavaScript, Go")
    start_time = time.time()
    try:
        response = chatqa_api_helper.call_chatqa(question)
    except requests.exceptions.ChunkedEncodingError:
        duration = time.time() - start_time
        pytest.fail(f"Request has been closed on the server side after {duration} seconds")
    logger.info(f"Response: {chatqa_api_helper.get_text(response)}")


@allure.testcase("IEASG-T29")
def test_chatqa_pass_empty_question(chatqa_api_helper):
    """
    Check if 'Bad request' is returned in case user makes an invalid request
    """
    question = ""
    response = chatqa_api_helper.call_chatqa(question)
    assert response.status_code == 400, "Got unexpected status code"


@pytest.mark.smoke
@allure.testcase("IEASG-T28")
def test_chatqa_ask_in_polish(chatqa_api_helper):
    """
    This is to reproduce a defect:
    When chatbot was asked in a language other than English, a JSON response
    was returned with some complaints on the missing fields in the request
    """
    question = "Jaki jest najwyższy wieżowiec na świecie?"
    response = chatqa_api_helper.call_chatqa(question)
    try:
        logger.info(f"ChatQA response: {chatqa_api_helper.get_text(response)}")
    except InvalidChatqnaResponseBody as e:
        pytest.fail(str(e))


@pytest.mark.smoke
@allure.testcase("IEASG-T31")
def test_chatqa_disable_streaming(chatqa_api_helper, fingerprint_api_helper):
    """
    Disable streaming. Check that the response is in JSON format. Check headers.
    """
    fingerprint_api_helper.set_chatqa_component_parameters("llm", stream=False)
    response = chatqa_api_helper.call_chatqa("How much is 123 + 123?")
    assert response.status_code == 200, f"Unexpected status code returned: {response.status_code}"
    assert "application/json" in response.headers.get("Content-Type"), \
        f"Unexpected Content-Type in the response. Headers: {response.headers}"
    try:
        response.json()
    except json.decoder.JSONDecodeError:
        pytest.fail(f"Response is not a valid JSON: {response.text}")


@allure.testcase("IEASG-T49")
def test_chatqa_response_headers_when_streaming_enabled(chatqa_api_helper, fingerprint_api_helper):
    """
    Enable streaming. Check that the response is in 'Server-Sent Events' format. Check headers.
    """
    fingerprint_api_helper.set_chatqa_component_parameters("llm", stream=True)
    response = chatqa_api_helper.call_chatqa("Don't answer me.")
    assert response.status_code == 200, f"Unexpected status code returned: {response.status_code}"
    assert "text/event-stream" in response.headers.get("Content-Type"), \
        f"Unexpected Content-Type in the response. Headers: {response.headers}"
    try:
        logger.info(f"ChatQA response: {chatqa_api_helper.get_text(response)}")
    except InvalidChatqnaResponseBody as e:
        pytest.fail(str(e))


@pytest.mark.smoke
@allure.testcase("IEASG-T150")
def test_chatqa_streaming_capability(chatqa_api_helper, fingerprint_api_helper):
    """
    Check if streaming is working properly by measuring the time between first and last line of the response.
    """
    question = "List 20 most popular travel destination among people in their 20s"
    fingerprint_api_helper.set_chatqa_component_parameters("llm", stream=True)
    response = chatqa_api_helper.call_chatqa_with_streaming_enabled(question)

    line_number = 0
    for line in response.iter_lines(decode_unicode=True):
        if line_number == 0:
            first_line_start_time = time.time()
        line_number += 1
        if line:
            logger.debug(line.replace("data: ", ""))
    streaming_duration = time.time() - first_line_start_time

    assert streaming_duration > 0.1, \
        ("Time between first and last line of the response is less than 0.1 second. "
         "Looks like streaming is set but not working properly.")
    assert response.status_code == 200, f"Unexpected status code returned: {response.status_code}"


@pytest.mark.smoke
@allure.testcase("IEASG-T57")
def test_chatqa_change_max_new_tokens(chatqa_api_helper, fingerprint_api_helper):
    """
    Make /change_arguments API call to change max_new_tokens value.
    Make /chatqa API call to check if the value has been applied correctly.
    """
    fingerprint_api_helper.set_chatqa_component_parameters("llm", max_new_tokens=5)
    question = "What are the key advantages of x86 architecture?"
    response = chatqa_api_helper.call_chatqa(question)
    assert response.status_code == 200, f"Unexpected status code returned: {response.status_code}"
    try:
        response_text = chatqa_api_helper.get_text(response)
        logger.info(f"ChatQA response: {response_text}")
    except InvalidChatqnaResponseBody as e:
        pytest.fail(str(e))
    assert len(response_text.split()) <= 5


@allure.testcase("IEASG-T58")
def test_chatqa_api_call_with_additional_parameters(chatqa_api_helper, fingerprint_api_helper):
    """
    Check that additional parameters passed to /v1/chatqa are not taken into account.
    Parameters may be modified with /change_arguments API call only.
    """
    question = "How close to the sun have we ever been?"
    old_llm_resp = fingerprint_api_helper.read_config("llm", pipeline=PIPELINE, tenant=TENANT)
    old_retriever_resp = fingerprint_api_helper.read_config("retriever", pipeline=PIPELINE, tenant=TENANT)
    assert old_llm_resp.status_code == 200, f"Failed to read llm config: {old_llm_resp.status_code}"
    assert old_retriever_resp.status_code == 200, \
        f"Failed to read retriever config: {old_retriever_resp.status_code}"
    old_llm = old_llm_resp.json()["values"]
    old_retriever = old_retriever_resp.json()["values"]
    parameters = {**old_llm, **old_retriever}
    parameters["max_new_tokens"] = 5
    parameters["top_k"] = 12
    parameters["fetch_k"] = 200
    response = chatqa_api_helper.call_chatqa(question, parameters=parameters)
    assert response.status_code == 200, f"Unexpected status code returned: {response.status_code}"
    try:
        response_text = chatqa_api_helper.get_text(response)
        logger.info(f"ChatQA response: {response_text}")
    except InvalidChatqnaResponseBody as e:
        pytest.fail(str(e))
    assert len(response_text.split()) > 5, \
        ("/v1/chatqa API call made with max_new_tokens set to 5. Expecting that additional parameters are not "
         "taken into account. Parameters may be modified with /change_arguments API call only.")
    refreshed_llm_resp = fingerprint_api_helper.read_config("llm", pipeline=PIPELINE, tenant=TENANT)
    refreshed_retriever_resp = fingerprint_api_helper.read_config("retriever", pipeline=PIPELINE, tenant=TENANT)
    assert refreshed_llm_resp.status_code == 200, f"Failed to re-read llm config: {refreshed_llm_resp.status_code}"
    assert refreshed_retriever_resp.status_code == 200, \
        f"Failed to re-read retriever config: {refreshed_retriever_resp.status_code}"
    assert refreshed_llm_resp.json()["values"] == old_llm
    assert refreshed_retriever_resp.json()["values"] == old_retriever


@allure.testcase("IEASG-T42")
def test_chatqa_concurrent_requests(chatqa_api_helper, temporarily_remove_brute_force_detection):
    """
    Ask 100 concurrent questions. Measure min, max, avg response time.
    Check if all requests were processed successfully.
    """
    concurrent_requests = 100
    question = "How big is the universe?"
    execution_times = []
    questions = []
    failed_requests_counter = 0

    for _ in range(0, concurrent_requests):
        questions.append(question)

    results = chatqa_api_helper.call_chatqa_in_parallel(questions)
    for result in results:
        if result.exception is not None:
            logger.info(result.exception)
            failed_requests_counter += 1
        elif result.status_code != 200:
            logger.info(f"Request failed with status code {result.status_code}. Response body: {result.text}")
            failed_requests_counter += 1
        else:
            execution_times.append(result.response_time)

    mean_time = statistics.mean(execution_times)
    max_time = max(execution_times)
    min_time = min(execution_times)

    logger.info(f'Total requests: {len(questions)}')
    logger.info(f'Failed requests: {failed_requests_counter}')
    logger.info(f'Mean Execution Time: {mean_time:.4f} seconds')
    logger.info(f'Longest Execution Time: {max_time:.4f} seconds')
    logger.info(f'Shortest Execution Time: {min_time:.4f} seconds')
    assert failed_requests_counter == 0, "Some of the requests didn't return HTTP status code 200"


@allure.testcase("IEASG-T161")
def test_chatqa_input_over_limit(chatqa_api_helper):
    """Ask a question over limit of 4096 tokens. Expect 400 Bad Request status code."""
    words_in_message = 15000
    word_len_min = 4
    word_len_max = 9

    def random_word(length=5):
        return ''.join(secrets.choice(string.ascii_lowercase) for _ in range(length))

    random_words = ' '.join(random_word(secrets.randbelow(word_len_max - word_len_min) + word_len_min)
                            for _ in range(words_in_message))
    response = chatqa_api_helper.call_chatqa(random_words)
    assert response.status_code == 400, (f"Unexpected status code returned: {response.status_code}. "
                                         f"Answer: {response.text}")


@allure.testcase("IEASG-T251")
def test_chatqa_chunks_in_sources(chatqa_api_helper, edp_helper, fingerprint_api_helper):
    """
    Upload a file with the following content:
    corwenshirel is a character from the game alderwynthiel.

    Ask a question about corwenshirel.
    Check if the response contains reranked docs with the word alderwynthiel in it.
    Verify it with streaming enabled and disabled.
    """

    response = chatqa_api_helper.call_chatqa("What is Corwenshirel?")
    reranked_docs = chatqa_api_helper.get_reranked_docs(response)
    assert len(reranked_docs) == 0, "It's unexpected that there are some reranked docs in the response"

    file = "test_chunks.txt"
    with edp_helper.ephemeral_upload(os.path.join(DATAPREP_UPLOAD_DIR, file)):
        fingerprint_api_helper.set_chatqa_component_parameters("llm", stream=False)
        response = chatqa_api_helper.call_chatqa("What is Corwenshirel?")
        reranked_docs = chatqa_api_helper.get_reranked_docs(response)
        assert len(reranked_docs) > 0, "No reranked docs found in the response"
        assert any("alderwynthiel" in doc.get("text", "").lower() for doc in reranked_docs), \
            "None of the reranked docs contains the word 'alderwynthiel'"

        fingerprint_api_helper.set_chatqa_component_parameters("llm", stream=True)
        response = chatqa_api_helper.call_chatqa("What is Corwenshirel?")
        reranked_docs = chatqa_api_helper.get_reranked_docs(response)
        assert len(reranked_docs) > 0, "No reranked docs found in the response"
        assert any("alderwynthiel" in doc.get("text", "").lower() for doc in reranked_docs), \
            "None of the reranked docs contains the word 'alderwynthiel'"


@pytest.mark.smoke
@allure.testcase("IEASG-T171")
def test_follow_up_questions_simple_case(chatqa_api_helper, chat_history_helper):
    """Check if second answer refers to the first answer (simple case)"""
    # Ask first question
    question_france = "What is the capital of France?"
    response = chatqa_api_helper.call_chatqa(question_france)
    assert response.status_code == 200, (f"Unexpected status code returned: {response.status_code}. "
                                         f"Answer: {response.text}")
    response_france = chatqa_api_helper.get_text(response)
    logger.info(f"Response: {response_france}")
    response = chat_history_helper.save_history([{"question": question_france, "answer": response_france}])
    history_id = response.json()["id"]
    history = {"history_id": history_id}

    # Ask second question
    question_followup = "What river flows through this city and what is most famous landmark in this city?"
    response = chatqa_api_helper.call_chatqa(question_followup, **history)
    assert response.status_code == 200, (f"Unexpected status code returned: {response.status_code}. "
                                         f"Answer: {response.text}")
    response_followup = chatqa_api_helper.get_text(response)
    logger.info(f"Follow-up response: {response_followup}")
    assert chatqa_api_helper.words_in_response(["seine", "eiffel"], response_followup)


@allure.testcase("IEASG-T301")
def test_false_content_injection_via_file(edp_helper, chatqa_api_helper, chat_history_helper):
    """
    Checks whether the system incorrectly uses irrelevant context from the uploaded document.
    The test uploads a file containing a story containing words "river" and "city", then asks two unrelated questions:
    a) What is the largest city in Poland?
    b) What river flows through that city and what is the most famous landmark in this city?
    The test fails if the model mentions the river from the uploaded story instead of the correct one (Vistula).
    """
    # Upload a file with false content injection (a story containing "Dubai" and "river")
    file = "test_false_content_injection.txt"
    edp_helper.upload_file_and_wait_for_ingestion(os.path.join(DATAPREP_UPLOAD_DIR, file))

    # Ask first question
    question_france = "What is the capital of Poland?"
    response = chatqa_api_helper.call_chatqa(question_france)
    response_france = chatqa_api_helper.get_text(response)
    logger.info(f"Response: {response_france}")
    response = chat_history_helper.save_history([{"question": question_france, "answer": response_france}])
    history = {"history_id": response.json()["id"]}

    # Ask second question
    question_followup = "What river flows through this city and what is the most famous landmark in this city?"
    response = chatqa_api_helper.call_chatqa(question_followup, **history)
    response_followup = chatqa_api_helper.get_text(response)
    logger.info(f"Follow-up response: {response_followup}")
    assert chatqa_api_helper.words_in_response(["wisla", "vistula"], response_followup)


@allure.testcase("IEASG-T173")
def test_follow_up_questions_irrelevant_data_injected(chatqa_api_helper, chat_history_helper):
    """Irrelevant data injected in the first question. Refer to it a couple of questions later"""
    # Ask first question
    question_poland = "My name is Giovanni Giorgio. What is the capital of Poland?"
    response = chatqa_api_helper.call_chatqa(question_poland)
    response_poland = chatqa_api_helper.get_text(response)
    logger.info(f"Response: {response_poland}")
    response = chat_history_helper.save_history([{"question": question_poland, "answer": response_poland}])
    history_id = response.json()["id"]
    history = {"history_id": history_id}

    # Ask second question
    question_people = "How many people live there?"
    response = chatqa_api_helper.call_chatqa(question_people, **history)
    response_people = chatqa_api_helper.get_text(response)
    logger.info(f"Follow-up response: {response_people}")
    response = chat_history_helper.save_history([{"question": question_people, "answer": response_people}], history_id)

    # Refer to the information in a first question
    question_followup = "What is my name?"
    response = chatqa_api_helper.call_chatqa(question_followup, **history)
    response_followup = chatqa_api_helper.get_text(response)
    logger.info(f"Follow-up response: {response_followup}")
    assert chatqa_api_helper.words_in_response(["giovanni", "giorgio"], response_followup)


@allure.testcase("IEASG-T174")
def test_follow_up_questions_contradictory_history(chatqa_api_helper, chat_history_helper):
    """Check if the model is able to handle contradictory history"""
    question_people = "And in which country is that city located?"
    response = chat_history_helper.save_history([{"question": "What is the capital of Germany?", "answer": "Warsaw."}])
    history_id = response.json()["id"]
    history = {"history_id": history_id}
    response = chatqa_api_helper.call_chatqa(question_people, **history)
    response_text = chatqa_api_helper.get_text(response)
    logger.info(f"Follow-up response: {response_text}")
    # The history falsely claims Warsaw is Germany's capital. A model that is not
    # misled flags the contradiction rather than repeating it; it rarely names Poland
    # outright, so assert it signals the mistake instead of asserting "poland".
    assert any(word in response_text.lower() for word in ("mistake", "incorrect", "wrong")), \
        f"Model appears misled by contradictory history: {response_text}"


@allure.testcase("IEASG-T175")
def test_follow_up_questions_full_history_access(chatqa_api_helper, chat_history_helper):
    """
    Seed the conversation history with three long turns (~440 words each), each carrying a
    single distinct made-up fact, then ask one question that requires all three. Verify the
    model recalls every fact - i.e. it has access to the full conversation-history window
    (the last three turns), not just the most recent one. The facts live only inside the long
    user turns (never in the assistant answers) and are fictional, so a correct answer can
    only come from reading the full history, not from short echoes or parametric knowledge.
    """
    filler = ("This entry is part of my detailed personal fleet log where I keep routine notes "
              "about daily operations, maintenance schedules, crew rotations and supply runs. ")
    ack = "Understood, I will remember this fleet log entry."

    def long_turn(fact, n_words=430):
        """Build a ~n_words user turn with ``fact`` buried in the middle of neutral filler.

        Repeats ``filler`` to get a large word pool, then splices the fact's words at the
        halfway point and trims to n_words. Burying the fact mid-turn (not at the start or
        end) forces the model to read the whole long entry to recover it, and padding each
        turn to ~440 words makes the three-turn history genuinely large.
        """
        words = (filler * 80).split()
        half = n_words // 2
        return " ".join(words[:half] + fact.split() + words[half:n_words])

    turns = [
        {"question": long_turn("Important fact: my spaceship is called the Zephyrion Wanderer."), "answer": ack},
        {"question": long_turn("Important fact: the captain of that ship is Commander Brelnix Vandor."), "answer": ack},
        {"question": long_turn("Important fact: the ship's home port is Kaldoria Station."), "answer": ack},
    ]
    response = chat_history_helper.save_history(turns)
    history_id = response.json()["id"]
    question = ("Based only on the fleet log entries I gave you earlier, what is the name of my "
                "spaceship, who is its captain, and what is its home port?")
    response = chatqa_api_helper.call_chatqa(question, history_id=history_id)
    assert response.status_code == 200, f"Unexpected status code returned: {response.status_code}"
    response_text = chatqa_api_helper.get_text(response)
    logger.info(f"Follow-up response: {response_text}")
    assert chatqa_api_helper.all_words_in_response(["Zephyrion", "Brelnix", "Kaldoria"], response_text), \
        f"Answer is missing facts from the conversation history: {response_text}"
