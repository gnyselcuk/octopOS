"""Feature flags for optional components.

This module provides feature flags to enable/disable optional components
like bot interfaces, voice, and UI automation.

Usage:
    from src.utils.feature_flags import FeatureFlags
    
    if FeatureFlags.slack_enabled():
        from src.interfaces.slack.bot import SlackBot
        # ...

Environment Variables:
    OCTOPOS_FEATURE_SLACK: Enable Slack integration (default: false)
    OCTOPOS_FEATURE_WHATSAPP: Enable WhatsApp integration (default: false)
    OCTOPOS_FEATURE_TELEGRAM: Enable Telegram integration (default: false)
    OCTOPOS_FEATURE_NOVA_ACT: Enable Nova Act UI automation (default: false)
    OCTOPOS_FEATURE_NOVA_SONIC: Enable Nova Sonic voice (default: false)
"""

import os
from typing import Optional


class FeatureFlags:
    """Feature flags for octopOS optional components."""

    @staticmethod
    def is_enabled(flag: str, default: bool = False) -> bool:
        """Check if a feature is enabled via environment variable.

        Args:
            flag: Feature flag name (without OCTOPOS_FEATURE_ prefix)
            default: Default value if environment variable is not set

        Returns:
            True if feature is enabled, False otherwise
        """
        env_var = f"OCTOPOS_FEATURE_{flag.upper()}"
        value = os.getenv(env_var, str(default).lower())
        return value.lower() in ("true", "1", "yes", "on")

    @classmethod
    def slack_enabled(cls) -> bool:
        """Check if Slack integration is enabled."""
        return cls.is_enabled("slack")

    @classmethod
    def whatsapp_enabled(cls) -> bool:
        """Check if WhatsApp integration is enabled."""
        return cls.is_enabled("whatsapp")

    @classmethod
    def telegram_enabled(cls) -> bool:
        """Check if Telegram integration is enabled."""
        return cls.is_enabled("telegram")

    @classmethod
    def nova_act_enabled(cls) -> bool:
        """Check if Nova Act UI automation is enabled."""
        return cls.is_enabled("nova_act")

    @classmethod
    def nova_sonic_enabled(cls) -> bool:
        """Check if Nova Sonic voice is enabled."""
        return cls.is_enabled("nova_sonic")

    @classmethod
    def get_all_flags(cls) -> dict:
        """Get all feature flags and their current status.

        Returns:
            Dictionary of flag names and their enabled status
        """
        return {
            "slack": cls.slack_enabled(),
            "whatsapp": cls.whatsapp_enabled(),
            "telegram": cls.telegram_enabled(),
            "nova_act": cls.nova_act_enabled(),
            "nova_sonic": cls.nova_sonic_enabled(),
        }

    @classmethod
    def get_enabled_features(cls) -> list:
        """Get list of enabled feature names.

        Returns:
            List of enabled feature flag names
        """
        return [name for name, enabled in cls.get_all_flags().items() if enabled]
