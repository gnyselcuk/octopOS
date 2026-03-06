# Security Action Plan

This document outlines the prioritized action items for addressing the security findings identified in the security audit.

## Priority 1: Critical (This Week)

### 1.1 Fix Slack Replay Attack Vulnerability
**File:** `src/interfaces/slack/event_handler.py`

**Changes needed:**
- Add timestamp validation before signature verification
- Reject requests older than 5 minutes

### 1.2 Remove Hardcoded Secrets
**File:** `src/primitives/mcp_adapter/mcp_transport.py`

**Changes needed:**
- Remove `headers={"Authorization": "Bearer token"}` example
- Use secure configuration for credentials

### 1.3 Fix Telegram Token Comparison
**File:** `src/interfaces/telegram/webhook_handler.py`

**Changes needed:**
- Use constant-time comparison for bot token

### 1.4 Disable YAML Credential Storage
**File:** `src/utils/config.py`

**Changes needed:**
- Never save credentials to YAML
- Add warning when credentials would be saved
- Use OS keychain for credentials

---

## Priority 2: High (This Month)

### 2.1 Add Rate Limiting
**Files:**
- `src/interfaces/telegram/webhook_handler.py`
- `src/interfaces/whatsapp/webhook_handler.py`
- `src/interfaces/slack/event_handler.py`

**Changes needed:**
- Add rate limiting middleware to all webhook endpoints

### 2.2 Environment Variable Whitelist
**File:** `src/primitives/mcp_adapter/mcp_transport.py`

**Changes needed:**
- Implement explicit whitelist for environment variables
- Remove inherited credentials from subprocess environment

### 2.3 Expand Bash Executor Patterns
**File:** `src/primitives/native/bash_executor.py`

**Changes needed:**
- Add more dangerous patterns to block list
- Add process substitution patterns: `$(...)`, `| xargs`
- Add command chaining: `&&`, `||`, `;`

### 2.4 MCP Server Config Validation
**File:** `src/utils/config.py`

**Changes needed:**
- Add schema validation for MCP server configs
- Whitelist allowed commands and arguments

### 2.5 Sandbox Network Enforcement
**File:** `sandbox/config/security.conf`

**Changes needed:**
- Hardcode `NETWORK_MODE="none"`
- Remove configuration option

---

## Priority 3: Medium (This Quarter)

### 3.1 Automatic Credential Rotation
**File:** `src/utils/aws_sts.py`

**Changes needed:**
- Implement automatic refresh for long-running sessions
- Add credential expiration monitoring

### 3.2 Dependency Version Pinning
**File:** `pyproject.toml`

**Changes needed:**
- Change `>=` to `~=` for compatible release pinning
- Add pip-audit to CI/CD pipeline

### 3.3 Security Headers
**Files:**
- `src/interfaces/telegram/webhook_handler.py`
- `src/interfaces/whatsapp/webhook_handler.py`
- `src/interfaces/slack/event_handler.py`

**Changes needed:**
- Add CORS middleware
- Add X-Content-Type-Options
- Add X-Frame-Options

### 3.4 Audit Logging
**Files:** Multiple

**Changes needed:**
- Add immutable audit trail for approval decisions
- Add security event logging

---

## Priority 4: Best Practice (Future)

### 4.1 Container Image Hardening
- Pin base image to specific digest
- Add CVE scanning to CI/CD

### 4.2 Secrets Management Integration
- Integrate with AWS Secrets Manager
- Add HashiCorp Vault support

### 4.3 Browser Session Security
- Restrict bypass_csp to sandboxed environments
- Limit browser permissions

---

## Implementation Notes

### Testing Requirements
After implementing each fix:
1. Run existing test suite
2. Add specific security tests for the fix
3. Manual penetration testing if applicable

### CI/CD Integration
Consider adding:
- `pip-audit` for dependency scanning
- `bandit` for Python security analysis
- `semgrep` for custom security rules

### Monitoring
After deployment:
- Monitor for authentication failures
- Track credential usage patterns
- Alert on unusual API activity

---

## Progress Tracking

| Item | Status | Assigned | Completed |
|------|--------|----------|----------|
| 1.1 Slack replay protection | DONE | - | ✓ |
| 1.2 Remove hardcoded secrets | DONE | - | ✓ |
| 1.3 Telegram token comparison | DONE | - | ✓ |
| 1.4 YAML credential storage | DONE | - | ✓ |
| 2.1 Rate limiting | DONE | - | ✓ |
| 2.2 Env var whitelist | DONE | - | ✓ |
| 2.3 Bash patterns | DONE | - | ✓ |
| 2.4 MCP config validation | TODO | - | - |
| 2.5 Sandbox network | TODO | - | - |
| 3.1 Credential rotation | DONE | - | ✓ |
| 3.2 Dependency pinning | DONE | - | ✓ |
| 3.3 Security headers | TODO | - | - |
| 3.4 Audit logging | TODO | - | - |
