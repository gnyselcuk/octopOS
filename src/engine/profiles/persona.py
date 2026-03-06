"""Persona Profile - Agent identity and personality management.

This module implements the persona profile system that:
- Defines agent personality and behavior
- Manages user preferences and facts
- Generates dynamic system prompts based on persona
- Stores memory snapshots and user profiles
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


class PersonaType(str, Enum):
    """Predefined persona types."""
    FRIENDLY = "friendly"
    PROFESSIONAL = "professional"
    TECHNICAL = "technical"
    CONCISE = "concise"
    CREATIVE = "creative"


@dataclass
class UserFact:
    """A fact about the user extracted from conversations."""
    
    key: str  # e.g., "location", "job", "preference"
    value: str
    category: str  # "personal", "professional", "preference"
    confidence: float = 1.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source: str = "conversation"  # Where this fact was learned


@dataclass
class UserProfile:
    """User profile with facts and preferences."""
    
    user_id: str
    name: Optional[str] = None
    preferred_name: Optional[str] = None
    timezone: str = "UTC"
    language: str = "en"
    facts: List[UserFact] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def add_fact(self, fact: UserFact) -> None:
        """Add or update a fact about the user."""
        # Remove existing fact with same key
        self.facts = [f for f in self.facts if f.key != fact.key]
        self.facts.append(fact)
        self.updated_at = datetime.utcnow().isoformat()
    
    def get_fact(self, key: str) -> Optional[str]:
        """Get a fact value by key."""
        for fact in self.facts:
            if fact.key == key:
                return fact.value
        return None
    
    def get_facts_by_category(self, category: str) -> List[UserFact]:
        """Get all facts in a category."""
        return [f for f in self.facts if f.category == category]


@dataclass
class PersonaProfile:
    """Agent persona profile defining personality and behavior."""
    
    # Identity
    name: str = "octoOS"
    persona_type: PersonaType = PersonaType.FRIENDLY
    version: str = "1.0"
    
    # Personality traits (0.0 - 1.0)
    friendliness: float = 0.8
    formality: float = 0.3
    technical_depth: float = 0.5
    verbosity: float = 0.5
    humor: float = 0.3
    
    # Communication style
    greeting_style: str = "casual"  # casual, formal, enthusiastic
    use_emojis: bool = True
    signature_phrases: List[str] = field(default_factory=list)
    
    # System prompt customization
    custom_instructions: str = ""
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaProfile":
        """Create from dictionary."""
        # Handle enum conversion
        if "persona_type" in data and isinstance(data["persona_type"], str):
            data["persona_type"] = PersonaType(data["persona_type"])
        return cls(**data)


class PersonaManager:
    """Manager for persona profiles and user profiles.
    
    Handles loading, saving, and customizing agent personas
    as well as user-specific profiles and facts.
    
    Example:
        >>> manager = PersonaManager()
        >>> persona = manager.load_persona()
        >>> user_profile = manager.get_user_profile("user_123")
        >>> system_prompt = manager.generate_system_prompt(persona, user_profile)
    """
    
    def __init__(self, profiles_dir: Optional[Path] = None) -> None:
        """Initialize persona manager.
        
        Args:
            profiles_dir: Directory to store profiles
        """
        self._config = get_config()
        
        if profiles_dir:
            self._profiles_dir = profiles_dir
        else:
            self._profiles_dir = Path.home() / ".octopos" / "profiles"
        
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        
        # Default persona file
        self._default_persona_file = self._profiles_dir / "default_persona.yaml"
        
        # User profiles directory
        self._users_dir = self._profiles_dir / "users"
        self._users_dir.mkdir(exist_ok=True)
        
        # Current persona cache
        self._current_persona: Optional[PersonaProfile] = None
        self._user_profiles: Dict[str, UserProfile] = {}
        
        logger.info(f"PersonaManager initialized with profiles at: {self._profiles_dir}")
    
    def load_persona(self, name: str = "default") -> PersonaProfile:
        """Load a persona profile.
        
        Args:
            name: Persona name (default for default persona)
            
        Returns:
            PersonaProfile
        """
        if name == "default":
            persona_file = self._default_persona_file
        else:
            persona_file = self._profiles_dir / f"{name}_persona.yaml"
        
        if persona_file.exists():
            try:
                with open(persona_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                persona = PersonaProfile.from_dict(data)
                self._current_persona = persona
                logger.info(f"Loaded persona: {persona.name}")
                return persona
            except Exception as e:
                logger.error(f"Error loading persona: {e}")
                return self._create_default_persona()
        else:
            return self._create_default_persona()
    
    def save_persona(self, persona: PersonaProfile, name: str = "default") -> bool:
        """Save a persona profile.
        
        Args:
            persona: Persona to save
            name: Persona name
            
        Returns:
            True if saved successfully
        """
        try:
            if name == "default":
                persona_file = self._default_persona_file
            else:
                persona_file = self._profiles_dir / f"{name}_persona.yaml"
            
            persona.updated_at = datetime.utcnow().isoformat()
            
            with open(persona_file, "w", encoding="utf-8") as f:
                yaml.dump(persona.to_dict(), f, default_flow_style=False)
            
            logger.info(f"Saved persona: {persona.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving persona: {e}")
            return False
    
    def get_user_profile(self, user_id: str) -> UserProfile:
        """Get or create a user profile.
        
        Args:
            user_id: User identifier
            
        Returns:
            UserProfile
        """
        if user_id not in self._user_profiles:
            profile_file = self._users_dir / f"{user_id}.yaml"
            
            if profile_file.exists():
                try:
                    with open(profile_file, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    
                    # Convert facts back to UserFact objects
                    if "facts" in data:
                        data["facts"] = [UserFact(**f) for f in data["facts"]]
                    
                    self._user_profiles[user_id] = UserProfile(**data)
                    logger.info(f"Loaded user profile: {user_id}")
                except Exception as e:
                    logger.error(f"Error loading user profile: {e}")
                    self._user_profiles[user_id] = UserProfile(user_id=user_id)
            else:
                self._user_profiles[user_id] = UserProfile(user_id=user_id)
        
        return self._user_profiles[user_id]
    
    def save_user_profile(self, profile: UserProfile) -> bool:
        """Save a user profile.
        
        Args:
            profile: User profile to save
            
        Returns:
            True if saved successfully
        """
        try:
            profile_file = self._users_dir / f"{profile.user_id}.yaml"
            profile.updated_at = datetime.utcnow().isoformat()
            
            # Convert to dict
            data = asdict(profile)
            
            with open(profile_file, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False)
            
            logger.info(f"Saved user profile: {profile.user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving user profile: {e}")
            return False
    
    def generate_system_prompt(
        self,
        persona: Optional[PersonaProfile] = None,
        user_profile: Optional[UserProfile] = None
    ) -> str:
        """Generate system prompt based on persona and user.
        
        Args:
            persona: Persona profile (uses current if None)
            user_profile: User profile (optional)
            
        Returns:
            System prompt string
        """
        if persona is None:
            persona = self._current_persona or self.load_persona()
        
        # Base identity
        parts = [
            f"You are {persona.name}, an AI assistant operating as an agentic OS.",
            ""
        ]
        
        # Personality-based instructions
        if persona.persona_type == PersonaType.FRIENDLY:
            parts.append(
                "You communicate in a warm, friendly manner. "
                "You use casual language and make the user feel comfortable. "
                "You're approachable and encouraging."
            )
        elif persona.persona_type == PersonaType.PROFESSIONAL:
            parts.append(
                "You communicate clearly and professionally. "
                "You are concise and business-appropriate in your tone. "
                "You focus on accuracy and efficiency."
            )
        elif persona.persona_type == PersonaType.TECHNICAL:
            parts.append(
                "You provide detailed, technically accurate responses. "
                "You assume the user has technical knowledge. "
                "You use precise terminology and include technical details."
            )
        elif persona.persona_type == PersonaType.CONCISE:
            parts.append(
                "You communicate very concisely. "
                "You get straight to the point with minimal fluff. "
                "You use brief, clear sentences."
            )
        elif persona.persona_type == PersonaType.CREATIVE:
            parts.append(
                "You communicate creatively and engagingly. "
                "You use vivid language and analogies. "
                "You think outside the box."
            )
        
        # Specific trait adjustments
        if persona.friendliness > 0.7:
            parts.append("You're very friendly and personable.")
        if persona.formality > 0.7:
            parts.append("You maintain a formal, respectful tone.")
        if persona.technical_depth > 0.7:
            parts.append("You provide deep technical explanations when relevant.")
        if persona.verbosity < 0.3:
            parts.append("You keep your responses brief and to the point.")
        
        # Communication style
        if persona.use_emojis:
            parts.append("You may use emojis occasionally to express yourself.")
        
        if persona.signature_phrases:
            parts.append(f"You sometimes use phrases like: {', '.join(persona.signature_phrases[:3])}")
        
        # User context
        if user_profile:
            parts.append("")
            parts.append("User Context:")
            
            if user_profile.name:
                parts.append(f"- User's name: {user_profile.name}")
            if user_profile.preferred_name:
                parts.append(f"- User prefers to be called: {user_profile.preferred_name}")
            
            # Include relevant facts
            relevant_facts = user_profile.get_facts_by_category("personal")
            if relevant_facts:
                parts.append("- Things you know about the user:")
                for fact in relevant_facts[:5]:  # Limit to 5 facts
                    parts.append(f"  * {fact.key}: {fact.value}")
        
        # Custom instructions
        if persona.custom_instructions:
            parts.append("")
            parts.append("Additional Instructions:")
            parts.append(persona.custom_instructions)
        
        return "\n".join(parts)
    
    def list_personas(self) -> List[str]:
        """List available persona names.
        
        Returns:
            List of persona names
        """
        personas = []
        for file in self._profiles_dir.glob("*_persona.yaml"):
            name = file.stem.replace("_persona", "")
            personas.append(name)
        return personas
    
    def create_persona_from_template(
        self,
        name: str,
        persona_type: PersonaType,
        custom_name: Optional[str] = None
    ) -> PersonaProfile:
        """Create a persona from a template.
        
        Args:
            name: Persona name
            persona_type: Base persona type
            custom_name: Custom agent name
            
        Returns:
            New PersonaProfile
        """
        templates = {
            PersonaType.FRIENDLY: {
                "friendliness": 0.9,
                "formality": 0.2,
                "technical_depth": 0.4,
                "verbosity": 0.6,
                "humor": 0.5,
                "greeting_style": "casual",
                "use_emojis": True,
            },
            PersonaType.PROFESSIONAL: {
                "friendliness": 0.5,
                "formality": 0.8,
                "technical_depth": 0.5,
                "verbosity": 0.4,
                "humor": 0.1,
                "greeting_style": "formal",
                "use_emojis": False,
            },
            PersonaType.TECHNICAL: {
                "friendliness": 0.5,
                "formality": 0.5,
                "technical_depth": 0.9,
                "verbosity": 0.7,
                "humor": 0.2,
                "greeting_style": "casual",
                "use_emojis": False,
            },
            PersonaType.CONCISE: {
                "friendliness": 0.4,
                "formality": 0.5,
                "technical_depth": 0.5,
                "verbosity": 0.1,
                "humor": 0.1,
                "greeting_style": "casual",
                "use_emojis": False,
            },
            PersonaType.CREATIVE: {
                "friendliness": 0.8,
                "formality": 0.2,
                "technical_depth": 0.5,
                "verbosity": 0.7,
                "humor": 0.6,
                "greeting_style": "enthusiastic",
                "use_emojis": True,
            },
        }
        
        template = templates.get(persona_type, templates[PersonaType.FRIENDLY])
        
        return PersonaProfile(
            name=custom_name or name,
            persona_type=persona_type,
            **template
        )
    
    def _create_default_persona(self) -> PersonaProfile:
        """Create and save the default persona."""
        persona = PersonaProfile(
            name="octoOS",
            persona_type=PersonaType.FRIENDLY,
            friendliness=0.8,
            formality=0.3,
            technical_depth=0.6,
            verbosity=0.5,
            humor=0.4,
            greeting_style="casual",
            use_emojis=True,
            signature_phrases=["How can I help?", "Got it!", "No problem!"]
        )
        
        self.save_persona(persona)
        return persona


# Global persona manager instance
_persona_manager: Optional[PersonaManager] = None


def get_persona_manager() -> PersonaManager:
    """Get the global persona manager instance.
    
    Returns:
        PersonaManager instance
    """
    global _persona_manager
    if _persona_manager is None:
        _persona_manager = PersonaManager()
    return _persona_manager
