import streamlit as st

from botocore.config import Config
from boto3.session import Session

import uuid
import json


class BedrockAgent:
    """BedrockAgent class for invoking an Anthropic AI agent.

    This class provides a wrapper for invoking an AI agent hosted on Anthropic's
    Bedrock platform. It handles authentication, session management, and tracing
    to simplify interacting with a Bedrock agent.

    Usage:

    agent = BedrockAgent()
    response, trace = agent.invoke_agent(input_text)

    The invoke_agent() method sends the input text to the agent and returns
    the agent's response text and trace information.

    Trace information includes the agent's step-by-step reasoning and any errors.
    This allows visibility into how the agent came up with the response.

    The class initializes session state and authentication on first run. It
    reuses the session for subsequent calls for continuity.

    Requires streamlit and boto3. Authentication requires credentials configured
    in secrets management.
    """

    def __init__(self, environmentName) -> None:
        if "BEDROCK_RUNTIME_CLIENT" not in st.session_state:

            st.session_state["BEDROCK_RUNTIME_CLIENT"] = Session().client(
                "bedrock-agent-runtime", config=Config(read_timeout=600)
            )

        if "SESSION_ID" not in st.session_state:
            st.session_state["SESSION_ID"] = str(uuid.uuid1())

        self.agent_id = (
            Session()
            .client("ssm")
            .get_parameter(
                Name=f"/streamlitapp/{environmentName}/AGENT_ID", WithDecryption=False
            )["Parameter"]["Value"]
        )
        self.agent_alias_id = (
            Session()
            .client("ssm")
            .get_parameter(
                Name=f"/streamlitapp/{environmentName}/AGENT_ALIAS_ID",
                WithDecryption=False,
            )["Parameter"]["Value"]
        )

    def new_session(self):
        st.session_state["SESSION_ID"] = str(uuid.uuid1())

    def get_session_id(self):
        return st.session_state["SESSION_ID"]

    def invoke_agent(self, text, trace, instruction):

        if instruction not in ("validate", "generate", "update"):
            raise ValueError("Instructions should be validate, generate, or update")

        if instruction == "validate":
            inputText = (
                f"Validate the the most recently generated AWS CloudFormation template."
            )
        elif instruction == "generate":
            inputText = f"Create clouformation code of following explain <explain>Here is a step-by-step description of the AWS architecture diagram:{text}</explain>"
        elif instruction == "update":
            inputText = f"Update the AWS Cloudformation template based on following update instruction: <update>{text}</update>"

        response_text = ""
        trace_text = ""
        step = 0

        response = st.session_state["BEDROCK_RUNTIME_CLIENT"].invoke_agent(
            inputText=inputText,
            agentId=self.agent_id,
            agentAliasId=self.agent_alias_id,
            sessionId=st.session_state["SESSION_ID"],
            enableTrace=True,
        )

        try:
            for event in response["completion"]:
                if "chunk" in event:

                    data = event["chunk"]["bytes"]
                    response_text = data.decode("utf8")

                elif "trace" in event:

                    trace_obj = event["trace"]["trace"]

                    if "orchestrationTrace" in trace_obj:

                        trace_dump = json.dumps(
                            trace_obj["orchestrationTrace"], indent=2
                        )

                        if "rationale" in trace_obj["orchestrationTrace"]:

                            step += 1
                            trace_text += f'\n\n\n---------- Step {step} ----------\n\n\n{trace_obj["orchestrationTrace"]["rationale"]["text"]}\n\n\n'
                            trace.markdown(
                                f'\n\n\n---------- Step {step} ----------\n\n\n{trace_obj["orchestrationTrace"]["rationale"]["text"]}\n\n\n'
                            )

                    elif "failureTrace" in trace_obj:

                        trace_text += "\n\n\n" + trace_dump + "\n\n\n"
                        trace.markdown("\n\n\n" + trace_dump + "\n\n\n")

                    elif "postProcessingTrace" in trace_obj:

                        step += 1
                        trace_text += f"\n\n\n---------- Step {step} ----------\n\n\n{json.dumps(trace_obj['postProcessingTrace']['modelInvocationOutput']['parsedResponse']['text'], indent=2)}\n\n\n"
                        trace.markdown(
                            f"\n\n\n---------- Step {step} ----------\n\n\n{json.dumps(trace_obj['postProcessingTrace']['modelInvocationOutput']['parsedResponse']['text'], indent=2)}\n\n\n"
                        )

        except Exception as e:
            trace_text += str(e)
            trace.markdown(str(e))
            raise Exception("unexpected event.", e)

        return response_text, trace_text
