# Hosting Huddle's MCP server on Amazon Bedrock AgentCore Runtime

**Status: written from the AgentCore docs, NOT yet run.** No AWS credentials were available when this
was written. Everything below is untested; fix this file with what really happens on the first deploy.
Source: <https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html>

## Why Huddle fits
The docs say an MCP server on AgentCore Runtime must serve **`0.0.0.0:8000/mcp`**, and that stateless
Streamable HTTP (`stateless_http=True`) is the recommended mode. Huddle's server (`server/mcp_server.py`,
mounted by `server/api.py`) already does exactly that, and `deploy/Dockerfile` exposes port 8000.

## Steps (per the docs; unverified for Huddle)
1. Credentials and region: `aws configure sso` (or env vars). Pick a region where AgentCore and your Bedrock model are available.
2. Inbound auth: the docs scaffold with a JWT authorizer. They create a Cognito user pool (`setup_cognito.sh` in the
   docs appendix) and pass its discovery URL and client id.
3. Scaffold and deploy with the AgentCore CLI (`npm install -g @aws/agentcore`):
   ```
   agentcore create --project-name HuddleMcp --no-agent
   cd HuddleMcp
   agentcore add agent --name Huddle --language Python --protocol MCP \
     --authorizer-type CUSTOM_JWT --discovery-url "$DISCOVERY_URL" --allowed-clients "$CLIENT_ID" \
     --request-header-allowlist Authorization
   # copy Huddle's `server/` package into app/Huddle and set the entrypoint to serve server.api:app on 0.0.0.0:8000
   agentcore deploy
   ```
   Open question to resolve on first deploy: the docs' sample entrypoint is a single FastMCP file; Huddle is a
   FastAPI app with FastMCP mounted. Either host `server.api:app` (serves `/mcp` plus the REST routes), or
   host only `server.mcp_server.mcp`, which needs its own `run()` entry.
4. Agent model: set `HUDDLE_MODE=aws`, `HUDDLE_BEDROCK_MODEL_ID=<id from the Bedrock catalog>` and `AWS_REGION`.
   The execution role needs permission to invoke that model (`bedrock:InvokeModel`; scope it to the model).
5. Invoke the deployed server with the MCP client at
   `https://bedrock-agentcore.<region>.amazonaws.com/runtimes/<url-encoded ARN>/invocations?qualifier=DEFAULT`
   with `Authorization: Bearer <token>`. Then run `python scripts/aws_scripted_rounds.py --require-bedrock`
   against a locally running server in `aws` mode and save the table in `docs/aws-run.md`.

## Caveats to check
- **State:** Huddle keeps rounds in SQLite on local disk. AgentCore Runtime runs sessions in isolated
  environments, so I expect that data not to outlive a session. This is an inference, not something I verified.
  For the demo recording, keep a whole round inside one session, or move storage to a managed store.
- The `HUDDLE_SECRET` used to sign round tokens must be set to a real value in any hosted deployment.
- **Cost:** AWS credits are limited. Deploy only for testing and recording, then tear down:
  `agentcore destroy` (or delete the runtime in the console), and remove the Cognito pool and ECR/S3 artifacts.
