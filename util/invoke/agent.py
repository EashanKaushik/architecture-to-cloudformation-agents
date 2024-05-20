import streamlit as st

from botocore.config import Config
from boto3.session import Session

import uuid
import json


class BedrockAgent:
    """BedrockAgent class for invoking an Amazon Bedrock agents.

    This class provides a wrapper for invoking an AI agent hosted on Amazon Bedrock platform.

    Usage:

    agent = BedrockAgent(environmentName=environmentName)

    # The invoke_agent() method sends the input text to the agent and returnsthe agent's response text and trace information.
    response_text, trace_text = agent.invoke_agent(text, trace, instruction)

    # Get the current session id.
    session_id = agent.get_session_id()

    # Reset the session.
    agent.new_session()

    The class initializes session state on first run. It reuses the session for subsequent calls for continuity.
    """

    def __init__(self, environmentName) -> None:
        if "AGENT_RUNTIME_CLIENT" not in st.session_state:

            st.session_state["AGENT_RUNTIME_CLIENT"] = Session().client(
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
        if "INVOCATION_ID" not in st.session_state:
            st.session_state["INVOCATION_ID"] = None

    def new_session(self):
        """
        Resets the session.
        """
        if st.session_state["INVOCATION_ID"]:
            st.session_state["AGENT_RUNTIME_CLIENT"].invoke_agent(
                agentId=self.agent_id,
                agentAliasId=self.agent_alias_id,
                sessionId=st.session_state["SESSION_ID"],
                endSession=True,
                sessionState={"invocationId": st.session_state["INVOCATION_ID"]},
            )
            del st.session_state["INVOCATION_ID"]
        st.session_state["SESSION_ID"] = str(uuid.uuid1())
        del st.session_state["AGENT_RUNTIME_CLIENT"]

    def get_session_id(self):
        """
        Returns the session id.
        """
        return st.session_state["SESSION_ID"]

    def invoke_agent(self, text, trace, instruction):
        """
        Invokes the agent and returns the response text and trace information.

        Args:
            text (str): The input text.
            trace  (instanceof st.empty): Placeholder to stream the trace.
            instruction (str): The instruction to send to the agent. Can be one of ("validate", "generate", "update")

        Returns:
            tuple: The response text and trace information.
        """
        if instruction not in ("validate", "generate", "update"):
            raise ValueError("Instructions should be validate, generate, or update")

        if instruction == "validate":
            inputText = (
                f"Validate the the most recently generated AWS CloudFormation template."
            )
        elif instruction == "generate":
            inputText = f"Create clouformation code of following explain <explain>{text}</explain>"
        elif instruction == "update":
            inputText = f"Update the AWS Cloudformation template based on following update instruction: <update>{text}</update>"

        response_text = ""
        trace_text = ""
        step = 0

        response = st.session_state["AGENT_RUNTIME_CLIENT"].invoke_agent(
            inputText=inputText,
            agentId=self.agent_id,
            agentAliasId=self.agent_alias_id,
            sessionId=st.session_state["SESSION_ID"],
            enableTrace=True,
        )
        try:
            for event in response["completion"]:
                if (
                    "returnControl" in event
                    and "invocationId" in event["returnControl"]
                ):
                    st.session_state["INVOCATION_ID"] = response["completion"][
                        "returnControl"
                    ]["invocationId"]

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
                            if trace:
                                trace.markdown(
                                    f'\n\n\n---------- Step {step} ----------\n\n\n{trace_obj["orchestrationTrace"]["rationale"]["text"]}\n\n\n'
                                )
                        elif (
                            "modelInvocationInput"
                            not in trace_obj["orchestrationTrace"]
                        ):

                            trace_text += "\n\n\n" + trace_dump + "\n\n\n"
                            if trace:
                                trace.markdown("\n\n\n" + trace_dump + "\n\n\n")

                    elif "failureTrace" in trace_obj:

                        trace_text += "\n\n\n" + trace_dump + "\n\n\n"
                        if trace:
                            trace.markdown("\n\n\n" + trace_dump + "\n\n\n")

                    elif "postProcessingTrace" in trace_obj:

                        step += 1
                        trace_text += f"\n\n\n---------- Step {step} ----------\n\n\n{json.dumps(trace_obj['postProcessingTrace']['modelInvocationOutput']['parsedResponse']['text'], indent=2)}\n\n\n"
                        trace.markdown(
                            f"\n\n\n---------- Step {step} ----------\n\n\n{json.dumps(trace_obj['postProcessingTrace']['modelInvocationOutput']['parsedResponse']['text'], indent=2)}\n\n\n"
                        )

        except Exception as e:
            trace_text += str(e)
            if trace:
                trace.markdown(str(e))
            raise Exception("unexpected event.", e)

        return response_text, trace_text
