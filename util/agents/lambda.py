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

bedrock = Session().client("bedrock-runtime")
cfn = Session().client("cloudformation")
bedrock_agent = Session().client("bedrock-agent-runtime")
s3 = Session().client("s3")
dynamodb = Session().client("dynamodb")

KnowledgeBaseId = os.environ["KnowledgeBaseId"]
EnvironmentName = os.environ["EnvironmentName"]

table_name = f"CacheStorage-A2C-{EnvironmentName}"


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
            return func(modelId, system_prompt, messages)
        except bedrock.exceptions.ThrottlingException as e:
            print(f"Retry {retries + 1}/{MAX_RETRIES}: {e}")
            time.sleep(delay + random.uniform(0, 1))  # Add a random jitter
            delay = min(delay * 2, MAX_DELAY)
            retries += 1


#########################
##### Cache and KB #####
#######################
def put_document(query, sessionId):
    documents = retrieve_relevant_documents(query=query)
    item = {
        **{"sessionId": {"S": sessionId}},
        **{f"document_{idx}": {"S": doc} for idx, doc in enumerate(documents)},
        **{
            "ttl": {
                "N": str(
                    int(
                        (
                            datetime.datetime.now() + datetime.timedelta(seconds=900)
                        ).timestamp()
                    )
                )
            },
            "creationDate": {"N": str(int(datetime.datetime.now().timestamp()))},
        },
    }
    try:
        # Put the item into the table
        response = dynamodb.put_item(TableName=table_name, Item=item)

        print(f"Item added to table")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            print(f"Conditional check failed for item")
        else:
            print(f"An error occurred: {e}")

    return documents


def cache_documents(query, sessionId):
    documents = list()
    try:
        response = dynamodb.get_item(
            TableName=table_name,
            Key={
                "sessionId": {"S": sessionId},
            },
        )

        # Check if the item was found
        if "Item" in response:
            print(f"Item with key {sessionId} exists in the table.")
            documents = [
                v["S"]
                for k, v in response["Item"].items()
                if k != "sessionId" and k != "ttl" and k != "creationDate"
            ]
        else:
            print(f"Item with key {sessionId} does not exist in the table.")
            documents = put_document(query=query, sessionId=sessionId)

    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            print(f"Item with key {sessionId} does not exist in the table.")
        else:
            print(f"An error occurred: {e}")

    return documents


def retrieve_relevant_documents(query):
    documents = list()
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

    for s3_bucket_uri in [
        result["metadata"]["cfn_stack"]
        for result in relevant_documents["retrievalResults"]
    ]:
        bucket, key = s3_bucket_uri.replace("s3://", "").split("/", 1)
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

    generated_cloudformation_stack = backoff_mechanism(
        invoke_model,
        "anthropic.claude-3-haiku-20240307-v1:0",
        _system_prompt,
        _messages,
    )

    return generated_cloudformation_stack


#########################
##### Generate CFN #####
#######################


def generate_cloudformation(event):
    architectureExplanation = get_named_parameter(event, "architectureExplanation")
    _system_prompt = """
        You are an expert AWS CloudFormation developer. Your task is to convert instuctions to valid CloudFormation template in YAML format.
        Accept step-by-step explaination of the AWS Architecture encapsulated between <explain></explain> XML tags and generate its CloudFormation code. 
    """

    documents = cache_documents(
        query=architectureExplanation, sessionId=event["sessionId"]
    )

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
    
    generated_cloudformation_stack = backoff_mechanism(
        invoke_model,
        "anthropic.claude-3-sonnet-20240229-v1:0",
        _system_prompt,
        _messages,
    )

    return generated_cloudformation_stack


#########################
##### Validate CFN #####
#######################


def validate_cloudformtaion(event):
    cloudformationTemplate = get_named_parameter(event, "cloudformationTemplate")

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
    cloudformationTemplate = get_named_parameter(event, "cloudformationTemplate")
    architectureExplanation = get_named_parameter(event, "architectureExplanation")

    documents = cache_documents(
        query=architectureExplanation, sessionId=event["sessionId"]
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
    updated_cloudformation = backoff_mechanism(
        invoke_model,
        "anthropic.claude-3-sonnet-20240229-v1:0",
        _system_prompt,
        _messages,
    )

    return updated_cloudformation


#######################
##### Update CFN #####
#####################


def update_cloudformation(event):
    updateInstruction = get_named_parameter(event, "updateInstruction")
    cloudformationTemplate = get_named_parameter(event, "cloudformationTemplate")
    architectureExplanation = get_named_parameter(event, "architectureExplanation")

    newArchitectureExplanation = get_new_architecture_explaination(
        architectureExplanation, updateInstruction
    )

    try:
        dynamodb.delete_item(
            TableName=table_name, Key={"sessionId": {"S": event["sessionId"]}}
        )
    except dynamodb.exceptions.ConditionalCheckFailedException as e:
        print(f"Conditional check failed: {e}")
    except dynamodb.exceptions.ResourceNotFoundException as e:
        print(f"Item not found: {e}")
    except Exception as e:
        print(f"Error deleting item: {e}")

    documents = cache_documents(
        query=newArchitectureExplanation, sessionId=event["sessionId"]
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

    updated_cloudformation = backoff_mechanism(
        invoke_model,
        "anthropic.claude-3-sonnet-20240229-v1:0",
        _system_prompt,
        _messages,
    )
    return updated_cloudformation


##########################
##### Resolve Error #####
########################


def resolve_error(event):
    error = get_named_parameter(event, "errorInstruction")
    cloudformationTemplate = get_named_parameter(event, "cloudformationTemplate")
    architectureExplanation = get_named_parameter(event, "architectureExplanation")

    documents = cache_documents(
            query=architectureExplanation, sessionId=event["sessionId"]
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

    updated_cloudformation = backoff_mechanism(
        invoke_model,
        "anthropic.claude-3-sonnet-20240229-v1:0",
        _system_prompt,
        _messages,
    )

    return updated_cloudformation


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
