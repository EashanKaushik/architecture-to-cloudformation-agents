# architecture-to-cloudformation-agents

## Architecture

A high-level description of the system — including a C4 Context diagram, the four working components, the three end-to-end data flows, and the deployment order — lives in [`docs/architecture.md`](docs/architecture.md). Reviewers should consult that document when a change touches more than one component (see [CONTRIBUTING](CONTRIBUTING.md#architecture-reviews)).

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

## Usage

```
streamlit run app.py --server.port=<port> -- --environmentName <environmentName> --GitURL https://github.com/EashanKaushik/architecture-to-cloudformation-agents.git
```

## Cleanup

developmeny.yaml
aoss-access-policy-${EnvironmentName}
infrastructure.yaml