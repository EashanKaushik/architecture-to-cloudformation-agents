# Architecture

This document uses a **C4-style description with Mermaid diagrams**
(option b from the architecture-decision spec) rather than a prose-only
narrative. The system has clearly separable components and three distinct
flows (`generate`, `update`, `validate`), so a Context diagram, a Container
diagram, and a sequence diagram render the design more usefully than prose
alone. Mermaid renders on GitHub for the diagram types used here; the C4
shorthand is still flagged as experimental upstream, so verify rendering on
the PR preview before relying on it.

## Overview

`architecture-to-cloudformation-agents` is a Streamlit application that
turns an uploaded architecture diagram (PNG/JPEG) into a working AWS
CloudFormation template. A vision model on Amazon Bedrock first explains the
diagram in natural language; an Amazon Bedrock Agent then generates,
updates, or validates the corresponding CloudFormation YAML. A Bedrock
Knowledge Base backed by Amazon OpenSearch Serverless supplies retrieval
context (similar templates, metadata) and stores the generated template per
session.

```mermaid
C4Context
  title "System Context - architecture-to-cloudformation-agents"
  Person(user, "Solutions Architect", "Uploads an architecture diagram and edits the explanation")
  System(app, "architecture-to-cloudformation-agents", "Streamlit app that generates / updates / validates CloudFormation from a diagram")
  System_Ext(bedrock, "Amazon Bedrock", "Vision model + Agents runtime")
  System_Ext(kb, "Bedrock Knowledge Base", "Backed by OpenSearch Serverless")
  System_Ext(cfn, "AWS CloudFormation", "Deploys generated templates")
  Rel(user, app, "Uploads diagram, reviews & edits")
  Rel(app, bedrock, "Explain diagram, invoke agent")
  Rel(app, kb, "Retrieve similar templates, store output")
  Rel(user, cfn, "Deploys generated YAML")
```

## Components

The application is composed of one frontend container, one Bedrock Agent
with a Lambda action group, and shared AWS managed services.

```mermaid
C4Container
  title Container view
  Person(user, "Solutions Architect")
  Container_Boundary(app, "Streamlit container") {
    Container(ui, "app.py", "Streamlit", "UI, sidebar inference params, file upload")
    Container(invoke, "util/invoke", "Python", "Bedrock, BedrockAgent, KnowledgeBase wrappers")
  }
  Container_Boundary(bedrock, "Amazon Bedrock") {
    Container(vision, "Vision model", "Bedrock model", "invoke_explain_model - diagram to text")
    Container(agent, "Bedrock Agent", "Bedrock Agents", "Instructions: generate, update, validate")
    Container(lambda, "Action-group Lambda", "Python", "util/agent/lambda.py + openAPI.json")
    Container(kb, "Knowledge Base", "Bedrock KB", "Retrieves and stores templates")
  }
  System_Boundary(aws, "AWS managed services") {
    ContainerDb(oss, "OpenSearch Serverless", "Vector store", "Index created by util/vector_store/create_index.py")
    ContainerDb(ssm, "SSM Parameter Store", "Config", "/streamlitapp/{env}/AGENT_ID, AGENT_ALIAS_ID, ...")
  }
  Rel(user, ui, "HTTPS")
  Rel(ui, invoke, "Python calls")
  Rel(invoke, vision, "Explain diagram")
  Rel(invoke, agent, "invoke_agent(text, trace, instruction)")
  Rel(agent, lambda, "Action group")
  Rel(invoke, kb, "Retrieve / store")
  Rel(kb, oss, "Vectors")
  Rel(invoke, ssm, "Resolve agent IDs")
```

Key source locations:

* `agents-architecture-to-cloudformation/app.py` — Streamlit entry point.
* `agents-architecture-to-cloudformation/util/invoke/` — `bedrock.py`,
  `agent.py`, `knowledgebase.py` wrappers.
* `agents-architecture-to-cloudformation/util/agent/` — `lambda.py` and
  `openAPI.json` for the Bedrock Agent action group.
* `agents-architecture-to-cloudformation/util/vector_store/create_index.py`
  — OpenSearch Serverless index creation.
* `agents-architecture-to-cloudformation/util/prompt_templates/` — prompt
  text used by the vision and agent calls.

## Data Flow

The diagram below traces the `generate` flow end-to-end. The `update` and
`validate` flows reuse the same path, differing only in the `instruction`
argument passed to `BedrockAgent.invoke_agent` and the prompt template
selected.

```mermaid
sequenceDiagram
  autonumber
  actor U as User
  participant S as Streamlit (app.py)
  participant B as Bedrock vision model
  participant A as Bedrock Agent
  participant L as Action-group Lambda
  participant K as Knowledge Base
  U->>S: Upload diagram (PNG/JPEG)
  S->>B: invoke_explain_model(image)
  B-->>S: Step-by-step explanation
  U->>S: Review / edit explanation
  S->>A: invoke_agent(text, trace, "generate")
  A->>K: Retrieve similar templates / metadata
  K-->>A: Context chunks
  A->>L: Action-group call (per openAPI.json)
  L-->>A: Tool result
  A-->>S: CloudFormation YAML + trace
  S->>K: Store generated template (per session)
  S-->>U: Render YAML + download
```

## Deployment

The app is packaged as a container and deployed on AWS via a small set of
CloudFormation stacks. Paths in this section are relative to
`agents-architecture-to-cloudformation/`.

* `cfn_stack/infrastructure.yaml` — base VPC networking (two public and two
  private subnets across two AZs, Internet Gateway, NAT Gateways, route
  tables, VPC flow logs).
* `cfn_stack/opensearch-serverless-stack.yaml` — vector store collection
  and access policy.
* `cfn_stack/kb-stack.yaml` — Bedrock Knowledge Base wired to the vector
  store.
* `cfn_stack/agents-stack.yaml` — Bedrock Agent, alias, action group, and
  the Lambda defined in `util/agent/lambda.py`.
* `cfn_stack/parameter-stack.yaml` — SSM parameters consumed by the app
  (`/streamlitapp/{environmentName}/AGENT_ID`, `AGENT_ALIAS_ID`, ...).
* `cfn_stack/development.yaml` — dev orchestration that ties the above
  together.

The container itself is built from `Dockerfile` (Python 3.12-slim, exposes
port 80, includes a Streamlit health check) and started with:

```bash
streamlit run app.py --server.port=<port> -- \
  --environmentName <environmentName> \
  --GitURL https://github.com/EashanKaushik/architecture-to-cloudformation-agents.git
```

Per-environment configuration (agent IDs, KB IDs, region) is read from SSM
at startup, so the same image runs in any environment by varying
`--environmentName`.
