from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth, RequestError

import boto3

import sys

boto3_session = boto3.session.Session()
region_name = boto3_session.region_name

credentials = boto3.Session().get_credentials()
awsauth = auth = AWSV4SignerAuth(credentials, region_name, "aoss")

host = sys.argv[1]

index_name = f"cfn-knowledge-index"
body_json = {
   "settings": {
      "index.knn": "true",
       "number_of_shards": 1,
       "knn.algo_param.ef_search": 512,
       "number_of_replicas": 0,
   },
   "mappings": {
      "properties": {
        "vector": {
        "type": "knn_vector",
        "dimension": 1536,
            "method": {
                "name": "hnsw",
                "engine": "faiss",
                "space_type": "l2"
            },
        },
        "text": {
        "type": "text"
        },
        "text-metadata": {
        "type": "text"         
    }
      }
   }
}

# Build the OpenSearch client
oss_client = OpenSearch(
    hosts=[{'host': host, 'port': 443}],
    http_auth=awsauth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
    timeout=300
)