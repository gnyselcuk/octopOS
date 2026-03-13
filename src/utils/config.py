"""Configuration management for octopOS.

This module handles loading configuration from multiple sources:
1. Environment variables (OCTO_*)
2. .env file
3. User profile (~/.octopos/profile.yaml)
4. Default values
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


class LogLevel(str, Enum):
    """Log level options."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogDestination(str, Enum):
    """Log destination options."""
    STDOUT = "stdout"
    FILE = "file"
    CLOUDWATCH = "cloudwatch"


class AgentPersona(str, Enum):
    """Agent personality options."""
    FRIENDLY = "friendly"
    PROFESSIONAL = "professional"
    TECHNICAL = "technical"


@dataclass
class AWSConfig:
    """AWS configuration."""
    region: str = "us-east-1"
    profile: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    session_token: Optional[str] = None
    role_arn: Optional[str] = None
    role_session_name: str = "octopos-session"
    
    # Bedrock models
    model_nova_lite: str = "amazon.nova-lite-v1:0"
    model_nova_pro: str = "amazon.nova-pro-v1:0"
    model_nova_act: str = "amazon.nova-act-v1:0"
    model_nova_sonic: str = "amazon.nova-sonic-v1:0"
    model_embedding: str = "amazon.titan-embed-text-v2:0"
    
    # Guardrails
    guardrail_id: Optional[str] = None
    guardrail_version: str = "DRAFT"


@dataclass
class AgentConfig:
    """Agent identity and behavior configuration."""
    name: str = "octoOS"
    persona: AgentPersona = AgentPersona.FRIENDLY
    language: str = "en"
    
    def get_system_prompt(self) -> str:
        """Generate system prompt based on persona."""
        prompts = {
            AgentPersona.FRIENDLY: (
                f"You are {self.name}, a helpful AI assistant. "
                "You communicate in a friendly, conversational manner. "
                "You aim to be helpful while maintaining professionalism."
            ),
            AgentPersona.PROFESSIONAL: (
                f"You are {self.name}, a professional AI assistant. "
                "You communicate clearly and concisely with a business-appropriate tone. "
                "You focus on accuracy and efficiency."
            ),
            AgentPersona.TECHNICAL: (
                f"You are {self.name}, a technical AI assistant. "
                "You provide detailed, technically accurate responses. "
                "You assume the user has technical knowledge."
            ),
        }
        return prompts.get(self.persona, prompts[AgentPersona.FRIENDLY])


@dataclass
class UserConfig:
    """User-specific configuration."""
    name: str = ""
    timezone: str = "UTC"
    workspace_path: str = "~/octopos-workspace"
    preferred_aws_services: list = field(default_factory=list)


@dataclass
class LanceDBConfig:
    """LanceDB vector store configuration."""
    path: str = "~/.octopos/data/lancedb"
    table_primitives: str = "primitives"
    table_memory: str = "memory"
    table_public_apis: str = "public_apis"


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: LogLevel = LogLevel.INFO
    destination: LogDestination = LogDestination.STDOUT
    format: str = "text"  # json or text
    cloudwatch_log_group: str = "/octopos/agents"
    cloudwatch_log_stream: str = "default"
    
    # File rotation settings
    file_path: str = "~/.octopos/logs/octopos.log"
    file_max_bytes: int = 10 * 1024 * 1024  # 10MB
    file_backup_count: int = 5
    
    # Correlation ID settings
    enable_correlation_id: bool = True
    correlation_id_header: str = "x-correlation-id"
    
    # Sensitive data masking settings
    mask_sensitive_data: bool = True
    mask_character: str = "*"
    mask_custom_patterns: List[str] = field(default_factory=list)


@dataclass
class TaskConfig:
    """Task queue configuration."""
    db_path: str = "~/.octopos/data/tasks.db"
    db_type: str = "sqlite"  # sqlite or dynamodb
    dynamodb_table_tasks: str = "octopos-tasks"
    dynamodb_table_schedule: str = "octopos-schedule"


@dataclass
class SecurityConfig:
    """Security and sandbox configuration."""
    require_approval_for_code: bool = True
    require_approval_for_deletions: bool = True
    auto_approve_safe_operations: bool = False
    docker_network: str = "octopos-sandbox"
    docker_cpu_limit: str = "1.0"
    docker_memory_limit: str = "512m"


@dataclass
class WebConfig:
    """Web search and scraping configuration."""
    brave_api_key: Optional[str] = None
    ddg_region: str = "wt-wt"
    ddg_safesearch: str = "moderate"
    nova_act_model: str = "amazon.nova-lite-v1:0"
    max_html_size: int = 500 * 1024  # 500KB
    default_comparison_sites: list = field(default_factory=lambda: ["google.com", "bing.com"]) # Fallback defaults
    default_currency: str = "TRY"
    discovery_enabled: bool = True


@dataclass
class MCPServerConfig:
    """Config for a single MCP server."""
    name: str
    transport: str = "stdio"  # stdio or sse
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None
    enabled: bool = True


@dataclass
class MCPConfig:
    """Global MCP configuration."""
    servers: Dict[str, MCPServerConfig] = field(default_factory=dict)
    auto_connect: bool = True


@dataclass
class BrowserConfig:
    """Browser automation configuration for Nova Act missions."""
    # Playwright settings
    headless: bool = False  # Set to True for production/CI
    timeout: int = 30000  # 30 seconds default timeout
    slow_mo: int = 100  # Slow down operations by 100ms for stability
    
    # Viewport settings
    viewport_width: int = 1920
    viewport_height: int = 1080
    
    # Session persistence
    profile_dir: str = "~/.octopos/browser_profiles"
    persist_cookies: bool = True
    persist_local_storage: bool = True
    default_profile: str = "default"
    
    # Nova Act settings
    nova_act_model: str = "amazon.nova-pro-v1:0"
    max_steps_per_mission: int = 20
    screenshot_on_each_step: bool = True
    screenshot_quality: int = 80  # JPEG quality
    
    # Action safety
    critical_actions: list = field(default_factory=lambda: [
        "click_purchase",
        "submit_payment",
        "confirm_deletion",
        "send_message"
    ])
    require_approval_for_critical: bool = True
    
    # Retry settings
    max_retries_per_step: int = 3
    retry_delay_ms: int = 1000


@dataclass
class OctoConfig:
    """Main configuration class aggregating all config sections."""
    aws: AWSConfig = field(default_factory=AWSConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    user: UserConfig = field(default_factory=UserConfig)
    lancedb: LanceDBConfig = field(default_factory=LanceDBConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    web: WebConfig = field(default_factory=WebConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    
    # Development flags
    mock_aws: bool = False
    debug: bool = False
    test_mode: bool = False


class ConfigLoader:
    """Load configuration from multiple sources."""
    
    def __init__(self) -> None:
        """Initialize config loader."""
        self._config: Optional[OctoConfig] = None
    
    def load(self) -> OctoConfig:
        """Load configuration from all sources.
        
        Priority (highest to lowest):
        1. Environment variables
        2. .env file (already loaded by dotenv)
        3. User profile (~/.octopos/profile.yaml)
        4. Default values
        
        Returns:
            Populated OctoConfig instance
        """
        # Start with defaults
        config = OctoConfig()
        
        # Load from user profile if exists
        profile_path = Path.home() / ".octopos" / "profile.yaml"
        if profile_path.exists():
            config = self._load_from_profile(config, profile_path)
        
        # Override with environment variables
        config = self._load_from_env(config)
        
        self._config = config
        return config
    
    def _load_from_profile(
        self,
        config: OctoConfig,
        profile_path: Path
    ) -> OctoConfig:
        """Load configuration from user profile YAML file."""
        try:
            with open(profile_path, 'r') as f:
                data = yaml.safe_load(f) or {}
            
            # Update AWS config
            if 'aws' in data:
                for key, value in data['aws'].items():
                    if hasattr(config.aws, key):
                        setattr(config.aws, key, value)
            
            # Update agent config
            if 'agent' in data:
                for key, value in data['agent'].items():
                    if key == 'persona' and isinstance(value, str):
                        value = AgentPersona(value)
                    if hasattr(config.agent, key):
                        setattr(config.agent, key, value)
            
            # Update user config
            if 'user' in data:
                for key, value in data['user'].items():
                    if hasattr(config.user, key):
                        setattr(config.user, key, value)
            
            # Update other sections
            for section in ['lancedb', 'logging', 'task', 'security', 'web', 'browser', 'mcp']:
                if section in data:
                    if section == 'mcp':
                        # Special handling for MCP servers dict
                        mcp_data = data['mcp']
                        config.mcp.auto_connect = mcp_data.get('auto_connect', config.mcp.auto_connect)
                        if 'servers' in mcp_data:
                            for s_name, s_data in mcp_data['servers'].items():
                                config.mcp.servers[s_name] = MCPServerConfig(**s_data)
                    else:
                        section_config = getattr(config, section)
                        for key, value in data[section].items():
                            if hasattr(section_config, key):
                                setattr(section_config, key, value)
            
        except Exception as e:
            print(f"Warning: Failed to load profile: {e}")
        
        return config
    
    def _load_from_env(self, config: OctoConfig) -> OctoConfig:
        """Load configuration from environment variables."""
        # AWS config
        if region := os.getenv('AWS_REGION'):
            config.aws.region = region
        if profile := os.getenv('AWS_PROFILE'):
            config.aws.profile = profile
        if access_key := os.getenv('AWS_ACCESS_KEY_ID'):
            config.aws.access_key_id = access_key
        if secret_key := os.getenv('AWS_SECRET_ACCESS_KEY'):
            config.aws.secret_access_key = secret_key
        if session_token := os.getenv('AWS_SESSION_TOKEN'):
            config.aws.session_token = session_token
        if role_arn := os.getenv('AWS_ROLE_ARN'):
            config.aws.role_arn = role_arn
        if role_session := os.getenv('AWS_ROLE_SESSION_NAME'):
            config.aws.role_session_name = role_session
        
        # Bedrock models
        if model := os.getenv('BEDROCK_MODEL_NOVA_LITE'):
            config.aws.model_nova_lite = model
        if model := os.getenv('BEDROCK_MODEL_NOVA_PRO'):
            config.aws.model_nova_pro = model
        if model := os.getenv('BEDROCK_MODEL_NOVA_ACT'):
            config.aws.model_nova_act = model
            config.web.nova_act_model = model
        if size := os.getenv('OCTO_MAX_HTML_SIZE'):
            config.web.max_html_size = int(size)
        if model := os.getenv('BEDROCK_MODEL_NOVA_SONIC'):
            config.aws.model_nova_sonic = model
        if model := os.getenv('BEDROCK_MODEL_EMBEDDING'):
            config.aws.model_embedding = model
        
        # Agent config
        if name := os.getenv('OCTO_AGENT_NAME'):
            config.agent.name = name
        if persona := os.getenv('OCTO_AGENT_PERSONA'):
            config.agent.persona = AgentPersona(persona)
        if lang := os.getenv('OCTO_AGENT_LANGUAGE'):
            config.agent.language = lang
        
        # User config
        if name := os.getenv('OCTO_USER_NAME'):
            config.user.name = name
        if tz := os.getenv('OCTO_USER_TIMEZONE'):
            config.user.timezone = tz
        if workspace := os.getenv('OCTO_WORKSPACE_PATH'):
            config.user.workspace_path = workspace
        
        # LanceDB config
        if path := os.getenv('LANCEDB_PATH'):
            config.lancedb.path = path
        
        # Logging config
        if level := os.getenv('LOG_LEVEL'):
            config.logging.level = LogLevel(level)
        if dest := os.getenv('LOG_DESTINATION'):
            config.logging.destination = LogDestination(dest)
        if fmt := os.getenv('LOG_FORMAT'):
            config.logging.format = fmt
        if log_group := os.getenv('CLOUDWATCH_LOG_GROUP'):
            config.logging.cloudwatch_log_group = log_group
        if log_stream := os.getenv('CLOUDWATCH_LOG_STREAM'):
            config.logging.cloudwatch_log_stream = log_stream
        if file_path := os.getenv('LOG_FILE_PATH'):
            config.logging.file_path = file_path
        if max_bytes := os.getenv('LOG_FILE_MAX_BYTES'):
            config.logging.file_max_bytes = int(max_bytes)
        if backup_count := os.getenv('LOG_FILE_BACKUP_COUNT'):
            config.logging.file_backup_count = int(backup_count)
        if enable_cid := os.getenv('LOG_ENABLE_CORRELATION_ID'):
            config.logging.enable_correlation_id = enable_cid.lower() == 'true'
        if cid_header := os.getenv('LOG_CORRELATION_ID_HEADER'):
            config.logging.correlation_id_header = cid_header
        
        # Sensitive data masking config
        if mask_sensitive := os.getenv('LOG_MASK_SENSITIVE_DATA'):
            config.logging.mask_sensitive_data = mask_sensitive.lower() == 'true'
        if mask_char := os.getenv('LOG_MASK_CHARACTER'):
            config.logging.mask_character = mask_char
        if mask_patterns := os.getenv('LOG_MASK_PATTERNS'):
            config.logging.mask_custom_patterns = [p.strip() for p in mask_patterns.split(',')]
        
        # Security config
        if val := os.getenv('REQUIRE_APPROVAL_FOR_CODE'):
            config.security.require_approval_for_code = val.lower() == 'true'
        if val := os.getenv('REQUIRE_APPROVAL_FOR_DELETIONS'):
            config.security.require_approval_for_deletions = val.lower() == 'true'
        
        # Development flags
        if val := os.getenv('MOCK_AWS'):
            config.mock_aws = val.lower() == 'true'
        if val := os.getenv('DEBUG'):
            config.debug = val.lower() == 'true'
        if val := os.getenv('TEST_MODE'):
            config.test_mode = val.lower() == 'true'
        
        # Web config
        if key := os.getenv('BRAVE_API_KEY'):
            config.web.brave_api_key = key
        if region := os.getenv('DDG_REGION'):
            config.web.ddg_region = region
        if safe := os.getenv('DDG_SAFE_SEARCH'):
            config.web.ddg_safesearch = safe
        if sites := os.getenv('OCTO_DEFAULT_COMPARISON_SITES'):
            config.web.default_comparison_sites = [s.strip() for s in sites.split(',')]
        if currency := os.getenv('OCTO_DEFAULT_CURRENCY'):
            config.web.default_currency = currency
        if discovery := os.getenv('OCTO_WEB_DISCOVERY_ENABLED'):
            config.web.discovery_enabled = discovery.lower() == 'true'
        
        # MCP config
        if val := os.getenv('OCTO_MCP_AUTO_CONNECT'):
            config.mcp.auto_connect = val.lower() == 'true'
        
        return config
    
    def save_profile(self, config: OctoConfig, profile_path: Optional[Path] = None) -> None:
        """Save configuration to user profile file.
        
        SECURITY: This method never saves sensitive credentials to the profile file.
        Credentials must be provided via environment variables or AWS config.
        
        Args:
            config: Configuration to save
            profile_path: Optional custom path (defaults to ~/.octopos/profile.yaml)
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
        
        # Check MCP servers for env vars with secrets
        for name, server in config.mcp.servers.items():
            if server.env:
                sensitive_fields.append(f"MCP server '{name}' env vars")
        
        if sensitive_fields:
            warnings.warn(
                f"Security: Not saving sensitive fields to profile: {', '.join(sensitive_fields)}. "
                "Use environment variables or AWS config for credentials.",
                UserWarning
            )
        
        # Build MCP servers dict without env vars (could contain secrets)
        mcp_servers = {}
        for name_s, s in config.mcp.servers.items():
            mcp_servers[name_s] = {
                'name': s.name,
                'transport': s.transport,
                'command': s.command,
                'args': s.args,
                # NEVER save 'env' - it may contain credentials
                'url': s.url,
                'enabled': s.enabled
            }
        
        # Convert to dict - NEVER include credentials
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
                'servers': mcp_servers
            }
        }
        
        with open(profile_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    def get_config(self) -> OctoConfig:
        """Get loaded config, loading if necessary."""
        if self._config is None:
            return self.load()
        return self._config


# Global config instance
_config_loader = ConfigLoader()


def get_config() -> OctoConfig:
    """Get the global configuration instance.
    
    Returns:
        The singleton OctoConfig instance
    """
    return _config_loader.get_config()


def load_config() -> OctoConfig:
    """Force reload configuration from all sources.
    
    Returns:
        Fresh OctoConfig instance
    """
    return _config_loader.load()


def save_config(config: OctoConfig) -> None:
    """Save configuration to user profile.
    
    Args:
        config: Configuration to save
    """
    _config_loader.save_profile(config)
