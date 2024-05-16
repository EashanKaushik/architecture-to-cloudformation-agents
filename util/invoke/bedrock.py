import streamlit as st

from botocore.exceptions import EventStreamError
from boto3.session import Session

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.chat_models import BedrockChat

import time
import random
import base64


def invoke_model(model, messages, data_placeholder=None):

    cfn_code = str()
    for chunk in model.stream(messages):
        cfn_code += chunk.content
        with data_placeholder.container():
            st.write(cfn_code)

    return cfn_code


def backoff_mechanism(func, model, messages, data_placeholder=None):
    MAX_RETRIES = 5  # Maximum number of retries
    INITIAL_DELAY = 1  # Initial delay in seconds
    MAX_DELAY = 60  # Maximum delay in second

    delay = INITIAL_DELAY
    retries = 0

    while retries < MAX_RETRIES:
        try:
            return func(model, messages, data_placeholder)
        except EventStreamError as e:
            print(f"Retry {retries + 1}/{MAX_RETRIES}: {e}")
            time.sleep(delay + random.uniform(0, 1))  # Add a random jitter
            delay = min(delay * 2, MAX_DELAY)
            retries += 1


class Bedrock:
    def __init__(self, inference_params):
        self._inference_params = inference_params

        self._explain_prompt = """
            You are an AWS Certified Solutions Architect with extensive experience in interpreting and explaining AWS Architecture diagrams. Given an architecture diagram as input, your task is to provide a detailed, step-by-step description of the components and their interactions within the architecture.

            When describing the architecture, follow these guidelines:

            1. Identify the main components and services depicted in the diagram.
            2. Explain the flow of data and requests through the architecture, starting from the client or user interface and tracing the path through various components.
            3. Describe the purpose and role of each component in the architecture, highlighting its responsibilities and how it contributes to the overall system.

            Output the explanation in a concise and understandable format in no more than 1000 characters.
            """

        self._sys_explain_prompt = "Your goal is to provide a concise and easily understandable step-by-step explaination of the AWS Architecture diagram. Skip the preamble."

    def get_explain_messages(self, image, image_type):
        human_message = [
            {"type": "text", "text": self._explain_prompt},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_type,
                    "data": base64.b64encode(image.getvalue()).decode("utf-8"),
                },
            },
        ]

        return [
            SystemMessage(content=self._sys_explain_prompt),
            HumanMessage(content=human_message),
        ]

    def invoke_explain_model(self, image, image_type, data_placeholder):

        explain_model = self.get_llm()

        messages = self.get_explain_messages(image, image_type)

        explain = backoff_mechanism(
            func=invoke_model,
            model=explain_model,
            messages=messages,
            data_placeholder=data_placeholder,
        )
        return explain
        # if "explain" in st.session_state:
        #     del st.session_state["explain"]
        # else:
        #     st.session_state["explain"] = explain

    def get_llm(self, streaming=True):
        model_kwargs = {
            "max_tokens": 4096,
            "temperature": self._inference_params["temperature"],
            "top_k": self._inference_params["top_k"],
            "top_p": self._inference_params["top_p"],
            "stop_sequences": ["\n\nHuman:"],
        }

        return BedrockChat(
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            model_kwargs=model_kwargs,
            client=Session().client("bedrock-runtime"),
            streaming=streaming,
        )
