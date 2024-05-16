from boto3.session import Session
from botocore.exceptions import ClientError

import os
import datetime


class KnowledgeBase:
    def __init__(self, EnvironmentName):
        self.bedrock = Session().client("bedrock-runtime")
        self.bedrock_agent = Session().client("bedrock-agent-runtime")
        self.table = (
            Session()
            .resource("dynamodb")
            .Table(f"templatestorage-atc-{EnvironmentName}")
        )
        self.s3 = Session().client("s3")

        self.KnowledgeBaseId = (
            Session()
            .client("ssm")
            .get_parameter(
                Name=f"/streamlitapp/{EnvironmentName}/KNOWLEDGEBASEID",
                WithDecryption=False,
            )["Parameter"]["Value"]
        )

    def get_kb_yaml(self, sessionId, version="v0"):
        return self.table.get_item(Key={"sessionId": sessionId, "version": version})

    def retrieve_metadata(self, sessionId, query=None):

        response = self.get_kb_yaml(sessionId=sessionId, version="METADATA")

        if "Item" in response:
            # TODO: "S" in response
            relevant_documents = response["Item"]
            print(f"Found item in dynamodb {sessionId}")
        else:
            print(f"Item with key {sessionId} not found.")
            relevant_documents = self.retrieve_relevant_documents(
                sessionId=sessionId, sessionId=query
            )

        metadata = [v for k, v in relevant_documents.items() if "document" in k]

        return metadata

    def retrieve_relevant_documents(self, sessionId, query):

        creationDate = str(
            int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())
        )
        ttl = str(
            int((datetime.datetime.now() + datetime.timedelta(seconds=900)).timestamp())
        )

        relevant_documents = self.bedrock_agent.retrieve(
            retrievalQuery={"text": query},
            knowledgeBaseId=self.KnowledgeBaseId,
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

            response = self.table.update_item(
                Key={"sessionId": sessionId, "version": "METADATA"},
                UpdateExpression=f"SET #document{idx} = :document{idx}, #creationDate = :creationDate, #ttl = :ttl, #query = :query",
                ExpressionAttributeNames={
                    f"#document{idx}": f"document{idx}",
                    "#creationDate": "creationDate",
                    "#ttl": "ttl",
                    "#query": "query",
                },
                ExpressionAttributeValues={
                    f":document{idx}": metadata,
                    ":creationDate": creationDate,
                    ":ttl": ttl,
                    ":query": query,
                },
                ReturnValues="ALL_NEW",
            )
        return response["Attributes"]
