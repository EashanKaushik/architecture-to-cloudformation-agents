import sys
from pip._internal import main

main(
    [
        "install",
        "-I",
        "-q",
        "boto3",
        "--target",
        "/tmp/",
        "--no-cache-dir",
        "--disable-pip-version-check",
    ]
)
sys.path.insert(0, "/tmp/")

import json
from botocore.exceptions import ClientError
from boto3.session import Session

import random
import time
import os
import datetime

KnowledgeBaseId = os.environ["KnowledgeBaseId"]
EnvironmentName = os.environ["EnvironmentName"]

bedrock = Session().client("bedrock-runtime")
cfn = Session().client("cloudformation")
bedrock_agent = Session().client("bedrock-agent-runtime")
s3 = Session().client("s3")
table = Session().resource("dynamodb").Table(f"templatestorage-atc-{EnvironmentName}")


############################
##### Invoke Bedrock ######
##########################
def invoke_model(modelId, system_prompt, messages):

    response = bedrock.invoke_model(
        modelId=modelId,
        body=json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "temperature": 0,
                "system": system_prompt,
                "messages": messages,
            }
        ),
    )
    result = json.loads(response.get("body").read())
    response = result.get("content", [])[0]["text"]
    return response


def backoff_mechanism(func, modelId, system_prompt, messages):
    MAX_RETRIES = 5  # Maximum number of retries
    INITIAL_DELAY = 1  # Initial delay in seconds
    MAX_DELAY = 60  # Maximum delay in second

    delay = INITIAL_DELAY
    retries = 0

    while retries < MAX_RETRIES:
        try:
            return func(modelId=modelId, system_prompt=system_prompt, messages=messages)
        except bedrock.exceptions.ThrottlingException as e:
            print(f"Retry {retries + 1}/{MAX_RETRIES}: {e}")
            time.sleep(delay + random.uniform(0, 1))  # Add a random jitter
            delay = min(delay * 2, MAX_DELAY)
            retries += 1

    return False


#########################
##### Cache and KB #####
#######################
def put_generated_cloudformation(sessionId, template):
    try:
        creationDate = str(
            int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())
        )
        ttl = str(
            int((datetime.datetime.now() + datetime.timedelta(seconds=900)).timestamp())
        )

        response = table.update_item(
            Key={"sessionId": sessionId, "version": "v0"},
            # Atomic counter is used to increment the latest version
            UpdateExpression="SET Latest = if_not_exists(Latest, :defaultval) + :incrval, #creationDate = :creationDate, #template = :template, #ttl = :ttl",
            ExpressionAttributeNames={
                "#creationDate": "creationDate",
                "#template": "template",
                "#ttl": "ttl",
            },
            ExpressionAttributeValues={
                ":creationDate": creationDate,
                ":template": template,
                ":ttl": ttl,
                ":defaultval": 0,
                ":incrval": 1,
            },
            # return the affected attribute after the update
            ReturnValues="UPDATED_NEW",
        )

        # Get the updated version
        latest_version = response["Attributes"]["Latest"]

        # Add the new item with the latest version
        table.put_item(
            Item={
                "sessionId": sessionId,
                "version": "v" + str(latest_version),
                "creationDate": creationDate,
                "template": template,
                "ttl": ttl,
            }
        )
    except Exception as ex:
        print(f"Error at put_generated_cloudformation {ex}")
        return False
    else:
        return True


def get_generated_cloudformation(sessionId, version="v0"):
    return table.get_item(Key={"sessionId": sessionId, "version": version})["Item"][
        "template"
    ]


def get_kb_yaml(sessionId, version="v0"):
    return table.get_item(Key={"sessionId": sessionId, "version": version})


def retrieve_relevant_documents(sessionId, query):

    creationDate = str(int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp()))
    ttl = str(
        int((datetime.datetime.now() + datetime.timedelta(seconds=900)).timestamp())
    )

    relevant_documents = bedrock_agent.retrieve(
        retrievalQuery={"text": query},
        knowledgeBaseId=KnowledgeBaseId,
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": 3,
                "overrideSearchType": "HYBRID",
            }
        },
    )

    for idx, metadata in enumerate(
        [result["metadata"] for result in relevant_documents["retrievalResults"]]
    ):

        response = table.update_item(
            Key={"sessionId": sessionId, "version": "METADATA"},
            UpdateExpression=f"SET #document{idx} = :document{idx}, #creationDate = :creationDate, #ttl = :ttl",
            ExpressionAttributeNames={
                f"#document{idx}": f"document{idx}",
                "#creationDate": "creationDate",
                "#ttl": "ttl",
            },
            ExpressionAttributeValues={
                f":document{idx}": metadata,
                ":creationDate": creationDate,
                ":ttl": ttl,
            },
            # return the affected attribute after the update
            ReturnValues="ALL_NEW",
        )
    return response["Attributes"]


def retrieve_yaml(sessionId, query=None):

    response = get_kb_yaml(sessionId=sessionId, version="METADATA")

    if "Item" in response:
        relevant_documents = response["Item"]
        print(f"Found item in dynamodb {sessionId}")
    else:
        print(f"Item with key {sessionId} not found.")
        relevant_documents = retrieve_relevant_documents(
            sessionId=sessionId, query=query
        )

    documents = list()

    for docs in [v for k, v in relevant_documents.items() if "document" in k]:
        bucket, key = docs["cfn_stack"].replace("s3://", "").split("/", 1)

        try:
            # Retrieve the object contents
            response = s3.get_object(Bucket=bucket, Key=key)
            contents = response["Body"].read().decode("utf-8")
            documents.append(contents)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                print("The specified object does not exist.")
            else:
                print(f"An error occurred: {e}")

    return documents


###############################
##### Utility Functions  #####
#############################


def get_named_parameter(event, name):
    return next(item for item in event["parameters"] if item["name"] == name)["value"]


def get_new_architecture_explaination(architectureExplanation, updateInstruction):
    _system_prompt = """
        Summarize the below to paragraphs and make sure they are not more that 1000 characters. 
    """
    _prompt = f"""
        Summarize the below to paragraphs.

        <para1>
        {architectureExplanation}
        </para1>

        <para2>
        {updateInstruction}
        </para2>
    """

    _messages = [{"role": "user", "content": [{"type": "text", "text": _prompt}]}]

    return backoff_mechanism(
        invoke_model,
        "anthropic.claude-3-haiku-20240307-v1:0",
        _system_prompt,
        _messages,
    )


#########################
##### Generate CFN #####
#######################


def generate_cloudformation(event):

    try:
        architectureExplanation = get_named_parameter(
            event=event, name="architectureExplanation"
        )

        documents = retrieve_yaml(
            sessionId=event["sessionId"], query=architectureExplanation
        )

        _system_prompt = """
            You are an expert AWS CloudFormation developer. Your task is to convert instuctions to valid CloudFormation template in YAML format.
            Accept step-by-step explaination of the AWS Architecture encapsulated between <explain></explain> XML tags and generate its CloudFormation code. 
        """

        _prompt = f"""
                
            Create CLoudFormation code only for AWS Servies present in <explain></explain>
            
            <explain>
            {architectureExplanation}
            </explain>
            
            - Mimic the practices of example CloudFormation templates given between <example></example> XML tags.
            - Use AWS CloudFormaton Pseudo parameters where necessary.
            - Use structure of example templates.
            
            Do not return examples or explaination, only return the generated CloudFormation YAML template without ```yaml ```. Skip the preamble. Think step-by-step.

        """
        message_document = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"""Take this example CloudFormation YAML code as a refernce <example{idx}></example{idx}>:
                            <example{idx}>
                                {document}
                            </example{idx}>
                            """,
                    }
                    for idx, document in enumerate(documents)
                ],
            }
        ]
        message_document[0]["content"].append(
            {
                "type": "text",
                "text": _prompt,
            },
        )
        _messages = message_document
    except Exception as ex:
        print(f"Error at generate_cloudformation {ex}")
        return False
    else:
        generated_cloudformation_stack = backoff_mechanism(
            invoke_model,
            "anthropic.claude-3-sonnet-20240229-v1:0",
            _system_prompt,
            _messages,
        )

        if not generated_cloudformation_stack:
            return False

        return put_generated_cloudformation(
            sessionId=event["sessionId"], template=generated_cloudformation_stack
        )


#########################
##### Validate CFN #####
#######################


def validate_cloudformtaion(event):
    cloudformationTemplate = get_generated_cloudformation(sessionId=event["sessionId"])

    validation_errors = str()
    try:
        response = cfn.validate_template(
            # TemplateBody=yaml.safe_load(cloudformationTemplate),
            TemplateBody=cloudformationTemplate,
        )
    except Exception as ex:
        print(f"Cloudformation template invalid: {ex}")
        validation_errors = ex
        is_valid = False
    else:
        is_valid = True
        print("Cloudformation valid")

    response = {"isValid": is_valid, "error": str(validation_errors)}
    return response


##########################
##### Reiterate CFN #####
########################


def reiterate_cloudformation(event):
    try:
        architectureExplanation = get_named_parameter(event, "architectureExplanation")

        cloudformationTemplate = get_generated_cloudformation(
            sessionId=event["sessionId"]
        )

        documents = retrieve_yaml(
            query=architectureExplanation,
            sessionId=event["sessionId"],
        )
        _system_prompt = f"""
            You are an AWS CloudFormation expert and a master of AWS best practices. 
            Your task is to review CloudFormation template provided between <cloudformation></cloudformation> XML tags and iteratively enhance them to align with AWS recommendations and guidelines. 

            To guide you, user will provide examples encapsulated within <example></example> XML tags. These examples will showcase AWS best practices and brand voice in action, allowing you to understand and apply them effectively.

            Your output should be a revised version of the provided CloudFormation template, incorporating AWS best practices and brand voice.
        """
        _prompt = f"""
            Reiterate the CloudFormation template.
            
            <cloudformation>
                {cloudformationTemplate}
            </cloudformation>
            
            Do not return examples or explaination, only return the generated CloudFormation YAML template without ```yaml ```. Skip the preamble. Think step-by-step. 
        """

        message_document = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"""Take this example CloudFormation YAML code as a refernce <example{idx}></example{idx}>:
                            <example{idx}>
                                {document}
                            </example{idx}>
                            """,
                    }
                    for idx, document in enumerate(documents)
                ],
            }
        ]

        message_document[0]["content"].append(
            {
                "type": "text",
                "text": _prompt,
            },
        )
        _messages = message_document
    except Exception as ex:
        print(f"Error at reiterate_cloudformation {ex}")
        return False
    else:
        updated_cloudformation = backoff_mechanism(
            invoke_model,
            "anthropic.claude-3-sonnet-20240229-v1:0",
            _system_prompt,
            _messages,
        )
        if not updated_cloudformation:
            return False

        return put_generated_cloudformation(event["sessionId"], updated_cloudformation)


#######################
##### Update CFN #####
#####################


def update_cloudformation(event):
    try:
        updateInstruction = get_named_parameter(event, "updateInstruction")
        architectureExplanation = get_named_parameter(event, "architectureExplanation")

        cloudformationTemplate = get_generated_cloudformation(
            sessionId=event["sessionId"]
        )

        newArchitectureExplanation = get_new_architecture_explaination(
            architectureExplanation, updateInstruction
        )

        if not newArchitectureExplanation:
            return False

        documents = retrieve_yaml(
            sessionId=event["sessionId"], query=newArchitectureExplanation
        )

        _system_prompt = """
            You are an expert AWS CloudFormation developer tasked with updating CloudFormation code given in YAML format.
            
            1. You will receive the update instruction in <update></update> and will need to update the CloudFormation code in <cloudformation></cloudformation>.
            2. You will be provided with example AWS CloudFormation between <example></example> XML tags for reference. 
            
            Please note that you should not make any changes to the code until you receive specific instructions from the user. Your role is to accurately interpret the user's requirements and modify the CloudFormation YAML code accordingly.
        """
        _prompt = f"""
        
        I need your assistance in updating AWS CloudFormation template. Please review the following:

        <cloudformation>
        {cloudformationTemplate}
        </cloudformation>
        
        <update>
        {updateInstruction}
        </update>
                

        Once you have completed the updates, you will output only the revised CloudFormation YAML template without ```yaml ```. Skip the preamble.Think step-by-step. 
        """
        message_document = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"""Take this example CloudFormation YAML code as a refernce <example{idx}></example{idx}>:
                            <example{idx}>
                                {document}
                            </example{idx}>
                            """,
                    }
                    for idx, document in enumerate(documents)
                ],
            }
        ]

        message_document[0]["content"].append(
            {
                "type": "text",
                "text": _prompt,
            },
        )
        _messages = message_document
    except Exception as ex:
        print(f"Error at update_cloudformation {ex}")
        return False
    else:
        updated_cloudformation = backoff_mechanism(
            invoke_model,
            "anthropic.claude-3-sonnet-20240229-v1:0",
            _system_prompt,
            _messages,
        )
        if not updated_cloudformation:
            return False
        return put_generated_cloudformation(event["sessionId"], updated_cloudformation)


##########################
##### Resolve Error #####
########################


def resolve_error(event):
    try:
        error = get_named_parameter(event, "errorInstruction")
        architectureExplanation = get_named_parameter(event, "architectureExplanation")

        cloudformationTemplate = get_generated_cloudformation(
            sessionId=event["sessionId"]
        )

        documents = retrieve_yaml(
            sessionId=event["sessionId"], query=architectureExplanation
        )
        _system_prompt = """
        You are an AWS CloudFormation expert skilled in analyzing and troubleshooting CloudFormation templates. Your task is as follows:

        1. Review the provided CloudFormation template between <cloudformation></cloudformation> and error message <error></error> carefully.
        2. Identify the root cause of the error in the template.
        3. Provide a corrected version of the CloudFormation template that resolves the issue.

        To ensure a high-quality response, please:

        - Thoroughly understand the error message and its context within the template.
        - Leverage examples provided between <example></example> XML tags.
        - Validate the corrected template to ensure it resolves the error.

        Your expertise in troubleshooting CloudFormation templates is crucial for delivering an accurate and actionable solution.
        """

        _prompt = f"""
        I need your assistance in troubleshooting an issue with an AWS CloudFormation template. Please review the following:

        <cloudformation>
        {cloudformationTemplate}
        </cloudformation>

        <error>
        {error}
        </error>
        
        Once you have completed the updates, you will output only the revised CloudFormation YAML template without ```yaml ```. Skip the preamble. Think step-by-step. 
        """

        message_document = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"""Take this example CloudFormation YAML code as a refernce <example{idx}></example{idx}>:
                            <example{idx}>
                                {document}
                            </example{idx}>
                            """,
                    }
                    for idx, document in enumerate(documents)
                ],
            }
        ]

        message_document[0]["content"].append(
            {
                "type": "text",
                "text": _prompt,
            },
        )
        _messages = message_document
    except Exception as ex:
        print(f"Error at resolve_error {ex}")
        return False
    else:
        updated_cloudformation = backoff_mechanism(
            invoke_model,
            "anthropic.claude-3-sonnet-20240229-v1:0",
            _system_prompt,
            _messages,
        )
        if not updated_cloudformation:
            return False
        return put_generated_cloudformation(event["sessionId"], updated_cloudformation)


###########################
##### Lambda Handler #####
#########################


def lambda_handler(event, context):
    print(event)

    response_code = 200
    action_group = event["actionGroup"]
    api_path = event["apiPath"]
    http_method = event["httpMethod"]

    if api_path == "/generateCloudFormation":
        result = generate_cloudformation(event)
    elif api_path == "/validateCloudFormation":
        result = validate_cloudformtaion(event)
    elif api_path == "/reiterateCloudFormation":
        result = reiterate_cloudformation(event)
    elif api_path == "/updateCloudFormation":
        result = update_cloudformation(event)
    elif api_path == "/resolveError":
        result = resolve_error(event)
    else:
        response_code = 404
        result = f"Unrecognized api path: {action_group}::{api_path}"

    response_body = {"application/json": {"body": result}}

    action_response = {
        "actionGroup": action_group,
        "apiPath": api_path,
        "httpMethod": http_method,
        "httpStatusCode": response_code,
        "responseBody": response_body,
    }

    api_response = {"messageVersion": "1.0", "response": action_response}
    return api_response
