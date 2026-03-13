# octopOS - Architecture Supplementary Notes (Advanced Considerations)

This document contains critical operational details that strengthen the basic architecture in the `architecture_plan.md` file and should be considered before moving to the coding phase.

## 1. Security and Isolation (Deep-Dive)

In a system where agents autonomously write and execute code, security is not "optional" but "mandatory".

- **Network Isolation:** Worker containers should be launched with `--network none` or kept behind an egress firewall (e.g., AWS Network Firewall or Security Group) that only allows AWS API endpoints.
- **Secrets Management:** Instead of agents reading `.env` files, **AWS Secrets Manager** or **Parameter Store** integration should be provided through `src/utils/aws_utils.py` for "runtime-only" credential access.
- **Resource Constraints:** CPU and RAM limits (e.g., `mem_limit="512m"`, `cpu_period=100000`) must be strictly defined for each Docker container.

## 2. Cost and Token Control (Budgeting)

Nova models (especially Act and Pro) can be costly under heavy usage.

- **Token Counting:** The token amount used in each `OctoMessage` exchange should be logged and a "Session Budget" should be maintained.
- **Stop-Loss Mechanism:** If a task is estimated to exceed $5 in cost, the **Supervisor** should stop the operation and get approval from the user.
- **Cache Layer:** For similar requests, instead of going to the LLM, using "Semantic Cache" on LanceDB can reduce costs by 30-40%.

## 3. Observability (Observability & Tracing)

Debugging in asynchronous and multi-agent systems is a nightmare.

- **Trace ID:** Each user request starts with a `trace_id`. All sub-agent messages (OctoMessage) carry this ID.
- **Centralized Logging:** All logs should be sent to AWS **CloudWatch** in `(timestamp, level, agent_name, trace_id, message)` format.
- **State Visualization:** The `octo status --trace` command should visualize which agents a task is stuck on.

## 4. Multi-User and Data Isolation

If the system will serve multiple users via Telegram/Slack:

- **Tenant Isolation:** Each user should have their own LanceDB table or namespace.
- **Context Switching:** Main Brain should load the correct profile from memory based on `sender_id`.

## 5. Error Recovery (Global Error Recovery)

- **Brain Freeze:** If Main Brain (Orchestrator) encounters an unexpected error, the system should wake up in "Safe Mode" and continue from the last successful state (Check-pointing).
- **Dead Letter Queue (DLQ):** Unprocessable messages should be collected in a DLQ and **Self-Healing Agent** should periodically analyze this queue.

## 6. Development and CI/CD Strategy

- **Local Mocking:** To reduce costs during development, a local `MockBedrock` class should be used instead of Bedrock.
- **Agentic Testing:** There should be an automatic "Sandbox Unit Test" layer for the `primitives` written by the system itself. No code that doesn't pass the test should be moved under `src/primitives/`.
