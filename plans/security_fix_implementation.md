# Security Fix Implementation Guide

This document provides detailed implementation instructions for fixing each security vulnerability identified in the audit.

---

## Priority 1: Critical Fixes (This Week)

### 1.1 Slack Replay Attack Protection

**File:** `src/interfaces/slack/event_handler.py`

**Current Code (lines 21-29):**
```python
def _verify_signature(self, body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack request signature."""
    sig_basestring = f"v0:{timestamp}:{body.decode()}"
    my_signature = "v0=" + hmac.new(
        self.bot.config.signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(my_signature, signature)
```

**Fixed Code:**
```python
def _verify_signature(self, body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack request signature with replay attack protection."""
    import time
    
    # Validate timestamp to prevent replay attacks (5 minute window)
    try:
        request_time = int(timestamp)
        current_time = int(time.time())
        if abs(current_time - request_time) > 300:  # 5 minutes
            logger.warning("Slack request timestamp out of range - possible replay attack")
            return False
    except (ValueError, TypeError):
        logger.warning("Invalid Slack timestamp format")
        return False
    
    # Compute expected signature
    sig_basestring = f"v0:{timestamp}:{body.decode()}"
    my_signature = "v0=" + hmac.new(
        self.bot.config.signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(my_signature, signature)
```

**Testing:** Add unit test to verify old timestamps are rejected.

---

### 1.2 Remove Hardcoded Secrets from MCP Transport

**File:** `src/primitives/mcp_adapter/mcp_transport.py`

**Current Code (lines 309-311):**
```python
Example:
    >>> from src.primitives.mcp_adapter.mcp_transport import SSETransport
    >>> transport = SSETransport(
    ...     url="http://localhost:3000/sse",
    ...     headers={"Authorization": "Bearer token"}
    ... )
```

**Fixed Code:**
```python
Example:
    >>> from src.primitives.mcp_adapter.mcp_transport import SSETransport
    >>> transport = SSETransport(
    ...     url="http://localhost:3000/sse",
    ...     headers={"Authorization": "Bearer YOUR_TOKEN_HERE"}
    ... )
    >>> # Or use environment variable:
    >>> import os
    >>> transport = SSETransport(
    ...     url="http://localhost:3000/sse",
    ...     headers={"Authorization": f"Bearer {os.environ['MCP_TOKEN']}"}
    ... )
```

**Also update the docstring (line 301-312):**
```python
class SSETransport(MCPTransport):
    """HTTP Server-Sent Events transport for MCP.
    
    Connects to remote MCP servers via HTTP/SSE.
    Used for hosted MCP servers.
    
    Example:
        transport = SSETransport(
            url="http://localhost:3000/sse",
            headers={"Authorization": f"Bearer {os.environ.get('MCP_TOKEN')}"}
        )
    """
```

---

### 1.3 Fix Telegram Token Comparison

**File:** `src/interfaces/telegram/webhook_handler.py`

**Current Code (line 25):**
```python
if bot_token != self.bot.config.bot_token.split(":")[1]:
    raise HTTPException(status_code=403, detail="Invalid token")
```

**Fixed Code:**
```python
import hmac

# Extract expected token from config
expected_token = self.bot.config.bot_token.split(":")[1]

# Use constant-time comparison to prevent timing attacks
if not hmac.compare_digest(bot_token, expected_token):
    raise HTTPException(status_code=403, detail="Invalid token")
```

---

### 1.4 Disable YAML Credential Storage

**File:** `src/utils/config.py`

**Current Code (lines 451-516):**
```python
def save_profile(self, config: OctoConfig, profile_path: Optional[Path] = None) -> None:
    """Save configuration to user profile file."""
    if profile_path is None:
        profile_path = Path.home() / ".octopos" / "profile.yaml"
    
    # Ensure directory exists
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to dict - THIS IS THE PROBLEM
    data = {
        'aws': {
            'region': config.aws.region,
            'profile': config.aws.profile,
            # Credentials included below!
        },
        ...
    }
```

**Fixed Code:**
```python
def save_profile(self, config: OctoConfig, profile_path: Optional[Path] = None) -> None:
    """Save configuration to user profile file.
    
    SECURITY: Never saves credentials to the profile file.
    Credentials must be provided via environment variables or AWS config.
    """
    import warnings
    
    if profile_path is None:
        profile_path = Path.home() / ".octopos" / "profile.yaml"
    
    # Ensure directory exists
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check for sensitive data - warn and exclude
    sensitive_fields = []
    if config.aws.access_key_id:
        sensitive_fields.append("AWS_ACCESS_KEY_ID")
    if config.aws.secret_access_key:
        sensitive_fields.append("AWS_SECRET_ACCESS_KEY")
    if config.aws.session_token:
        sensitive_fields.append("AWS_SESSION_TOKEN")
    if config.aws.role_arn:
        sensitive_fields.append("AWS_ROLE_ARN")
    if config.web.brave_api_key:
        sensitive_fields.append("BRAVE_API_KEY")
    
    if sensitive_fields:
        warnings.warn(
            f"Security: Not saving sensitive fields to profile: {', '.join(sensitive_fields)}. "
            "Use environment variables or AWS config for credentials.",
            UserWarning
        )
    
    # Convert to dict - EXCLUDE all credentials
    data = {
        'aws': {
            'region': config.aws.region,
            'profile': config.aws.profile,
            # NEVER include: access_key_id, secret_access_key, session_token, role_arn
        },
        'agent': {
            'name': config.agent.name,
            'persona': getattr(config.agent.persona, 'value', config.agent.persona),
            'language': config.agent.language,
        },
        'user': {
            'name': config.user.name,
            'timezone': config.user.timezone,
            'workspace_path': config.user.workspace_path,
        },
        'lancedb': {
            'path': config.lancedb.path,
            'table_primitives': config.lancedb.table_primitives,
            'table_memory': config.lancedb.table_memory,
            'table_public_apis': config.lancedb.table_public_apis,
        },
        'logging': {
            'level': getattr(config.logging.level, 'value', config.logging.level),
            'destination': getattr(config.logging.destination, 'value', config.logging.destination),
            'format': config.logging.format,
        },
        'web': {
            # NEVER include: brave_api_key
            'ddg_region': config.web.ddg_region,
            'ddg_safesearch': config.web.ddg_safesearch,
            'default_comparison_sites': config.web.default_comparison_sites,
            'default_currency': config.web.default_currency,
            'discovery_enabled': config.web.discovery_enabled
        },
        'mcp': {
            'auto_connect': config.mcp.auto_connect,
        },
    }
    
    # Save without credentials
    with open(profile_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
```

---

## Priority 2: High Priority Fixes

### 2.1 Add Rate Limiting to Webhooks

**File:** Create new file `src/utils/rate_limiter.py`

```python
"""Rate limiting middleware for webhook endpoints."""

import time
import asyncio
from collections import defaultdict
from typing import Dict, Tuple
import threading


class RateLimiter:
    """Token bucket rate limiter."""
    
    def __init__(self, requests_per_minute: int = 60, burst: int = 10):
        self.rate = requests_per_minute / 60.0  # per second
        self.burst = burst
        self._buckets: Dict[str, Tuple[float, float]] = {}  # key -> (tokens, last_update)
        self._lock = threading.Lock()
    
    def _refill(self, key: str) -> None:
        now = time.time()
        if key not in self._buckets:
            self._buckets[key] = (self.burst, now)
            return
        
        tokens, last_update = self._buckets[key]
        elapsed = now - last_update
        tokens = min(self.burst, tokens + elapsed * self.rate)
        self._buckets[key] = (tokens, now)
    
    def allow(self, key: str, cost: int = 1) -> bool:
        with self._lock:
            self._refill(key)
            tokens, _ = self._buckets[key]
            
            if tokens >= cost:
                self._buckets[key] = (tokens - cost, time.time())
                return True
            return False


# Global rate limiter instance
_rate_limiter: RateLimiter = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(requests_per_minute=60, burst=10)
    return _rate_limiter


async def check_rate_limit(key: str, requests_per_minute: int = 60) -> bool:
    """Check if request is within rate limit.
    
    Args:
        key: Identifier for rate limit (IP, user ID, etc.)
        requests_per_minute: Maximum requests allowed
        
    Returns:
        True if allowed, False if rate limited
    """
    limiter = get_rate_limiter()
    return limiter.allow(key)
```

**Integration in webhook handlers:**
```python
# Add to each webhook endpoint
from src.utils.rate_limiter import check_rate_limit

@app.post("/webhook/telegram")
async def webhook(request: Request):
    # Get client IP for rate limiting
    client_ip = request.client.host
    
    if not await check_rate_limit(f"telegram:{client_ip}", requests_per_minute=30):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
```

---

### 2.2 Environment Variable Whitelist for MCP

**File:** `src/primitives/mcp_adapter/mcp_transport.py`

**Current Code (lines 186-189):**
```python
# Prepare environment
env = dict(os.environ) if self.env else None
if self.env:
    env.update(self.env)
```

**Fixed Code:**
```python
# Whitelist of allowed environment variables
ALLOWED_ENV_VARS = {
    'PATH', 'HOME', 'USER', 'WORKDIR', 'LANG', 'LC_ALL',
    'PYTHONPATH', 'PYTHONUNBUFFERED', 'TERM',
}

# Prepare sanitized environment for subprocess
if self.env:
    # Start with allowed parent env vars only
    env = {k: v for k, v in os.environ.items() if k in ALLOWED_ENV_VARS}
    # Add explicitly provided env vars
    env.update(self.env)
else:
    # Use only allowed parent env vars
    env = {k: v for k, v in os.environ.items() if k in ALLOWED_ENV_VARS}
```

---

### 2.3 Expand Bash Executor Patterns

**File:** `src/primitives/native/bash_executor.py`

**Current Code (lines 217-229):**
```python
dangerous_patterns = [
    r'\$\(',           # Command substitution
    r'`[^`]*`',        # Backtick substitution
    r'\|\s*bash',     # Piping to bash
    r'\|\s*sh',       # Piping to sh
    r'eval\s',         # Eval usage
    r'exec\s',         # Exec usage
    r'>&\s*/dev',      # Output redirection to devices
]
```

**Fixed Code:**
```python
dangerous_patterns = [
    # Command substitution
    r'\$\(',
    r'`[^`]*`',
    # Process substitution
    r'\$\{?\w+\}?\|\s*\w+',
    # Piping to shells
    r'\|\s*bash',
    r'\|\s*sh',
    r'\|\s*zsh',
    # Dangerous functions
    r'\beval\s',
    r'\bexec\s',
    # Output redirection
    r'>&/dev/',
    r'>>/dev/',
    r'</dev/',
    # File destruction
    r'rm\s+-rf\s+/',
    r'rmdir\s+',
    # Command chaining (potential bypass)
    r'&&\s*\w+',
    r'\|\|\s*\w+',
    r';\s*\w+',
    # Network connections
    r'\bcurl\s+',
    r'\bwget\s+',
    # Process control
    r'\bkill\s+',
    r'\bpkill\s+',
    # Privilege escalation
    r'\bsudo\s+',
    r'\bchmod\s+777',
]
```

---

### 2.4 MCP Server Config Validation

**File:** `src/utils/config.py`

**Add new validation method:**
```python
# Add after MCPServerConfig class definition

# Whitelist of allowed commands for MCP servers
ALLOWED_MCP_COMMANDS = {
    'python', 'python3', 'node', 'npx',
    'docker', 'kubectl',
}

def validate_mcp_server_config(config: MCPServerConfig) -> Tuple[bool, Optional[str]]:
    """Validate MCP server configuration for security.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Validate command
    if config.command:
        cmd_name = os.path.basename(config.command)
        if cmd_name not in ALLOWED_MCP_COMMANDS:
            return False, f"MCP command '{cmd_name}' not in allowed list"
    
    # Validate transport
    if config.transport not in ['stdio', 'sse']:
        return False, f"Invalid transport: {config.transport}"
    
    # For stdio transport, require command
    if config.transport == 'stdio' and not config.command:
        return False, "stdio transport requires command"
    
    # For SSE transport, require URL
    if config.transport == 'sse' and not config.url:
        return False, "sse transport requires url"
    
    # Validate args don't contain dangerous patterns
    if config.args:
        dangerous_args = ['-i', '--interactive', '-t', '-tty']
        for arg in config.args:
            if any(arg.startswith(d) for d in dangerous_args):
                return False, f"Potentially dangerous argument: {arg}"
    
    return True, None
```

**Apply validation in _load_from_profile:**
```python
# In _load_from_profile method, after creating MCPServerConfig
for s_name, s_data in mcp_data['servers'].items():
    server_config = MCPServerConfig(**s_data)
    
    # Validate before adding
    is_valid, error = validate_mcp_server_config(server_config)
    if not is_valid:
        warnings.warn(f"Skipping MCP server '{s_name}': {error}", UserWarning)
        continue
    
    config.mcp.servers[s_name] = server_config
```

---

### 2.5 Enforce Sandbox Network Mode

**File:** `sandbox/config/security.conf`

**Current (line 10):**
```
NETWORK_MODE="none"  # Options: none, bridge, host (not recommended)
```

**Fixed:**
```
# Network security - MUST be none for security
# This setting is hardcoded and cannot be overridden
NETWORK_MODE="none"
```

**Also update the code that reads this:**
Create a new file or add to existing sandbox config reader:
```python
# src/workers/sandbox_config.py

class SandboxSecurityConfig:
    """Security configuration for sandbox - values are hardcoded."""
    
    # These values are security-critical and cannot be configured
    NETWORK_MODE = "none"  # Always none - no network access
    FORBIDDEN_PATHS = ["/proc", "/sys", "/dev", "/root", "/home"]
    FORBIDDEN_SYSCALLS = ["execve", "ptrace", "process_vm_writev", "mount", "umount"]
    
    @classmethod
    def get_allowed_paths(cls) -> list:
        return ["/workspace", "/tmp"]
    
    @classmethod
    def get_env_whitelist(cls) -> list:
        return ["PATH", "HOME", "USER", "WORKDIR", "PYTHONPATH", "LANG", "LC_ALL"]
```

---

## Priority 3: Medium Priority Fixes

### 3.1 AWS Credential Rotation

**File:** `src/utils/aws_sts.py`

**Add credential refresh method:**
```python
# Add to AWSAuthManager class

def _is_credentials_expiring(self) -> bool:
    """Check if credentials are about to expire."""
    if not self._credentials:
        return True
    
    # Check if using temporary credentials
    if not self._credentials.expiration:
        return False  # Long-term credentials don't expire
    
    # Refresh if expiring within 5 minutes
    from datetime import datetime, timezone
    exp_time = datetime.fromisoformat(self._credentials.expiration)
    now = datetime.now(timezone)
    
    return (exp_time - now).total_seconds() < 300

def get_credentials(self) -> AWSCredentials:
    """Get AWS credentials with automatic refresh."""
    # Check if we need to refresh
    if self._credentials and self._is_credentials_expiring():
        logger.info("Credentials expiring, refreshing...")
        self.refresh_credentials()
    
    # ... rest of existing method
```

---

### 3.2 Dependency Version Pinning

**File:** `pyproject.toml`

**Current:**
```toml
dependencies = [
    "boto3>=1.28.0",
    "pydantic>=2.0.0",
    ...
]
```

**Fixed:**
```toml
dependencies = [
    # Use ~= for compatible release pinning
    "boto3~=1.34.0",
    "botocore~=1.34.0",
    "pydantic~=2.6.0",
    ...
]
```

---

## Testing Checklist

After implementing fixes, verify:

1. [ ] Slack webhook rejects requests > 5 minutes old
2. [ ] Telegram webhook uses constant-time comparison
3. [ ] MCP transport doesn't expose parent environment variables
4. [ ] Bash executor blocks more dangerous patterns
5. [ ] YAML profile never contains credentials
6. [ ] Rate limiting returns 429 when exceeded
7. [ ] All existing tests still pass

---

## CI/CD Integration Recommendations

Add to your CI pipeline:

```yaml
# .github/workflows/security.yml
- name: Security Audit
  run: |
    pip install pip-audit safety bandit
    pip-audit || true
    safety check || true
    bandit -r src/ || true
```

---

*Implementation guide version 1.0*
