"""Fact Extractor - Automatic extraction of user facts from conversations.

This module implements the Fact Extraction System that:
- Uses LLM to extract facts from user messages
- Categorizes facts: personal, professional, preference, location, technical
- Scores confidence for each extracted fact
- Stores facts in UserProfile and SemanticMemory
- Integrates with WorkingMemory for conversation context

Example:
    >>> extractor = FactExtractor()
    >>> facts = await extractor.extract_facts(
    ...     "I live in Istanbul and work as a Python developer",
    ...     user_id="user_123"
    ... )
    >>> for fact in facts:
    ...     print(f"{fact.key}: {fact.value} ({fact.confidence:.2f})")
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.engine.memory.working_memory import WorkingMemory, ConversationTurn
from src.engine.profiles.persona import UserFact, UserProfile
from src.utils.aws_sts import get_bedrock_client
from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


class FactCategory(str, Enum):
    """Categories for extracted facts."""
    
    PERSONAL = "personal"        # Name, age, family, hobbies
    PROFESSIONAL = "professional"  # Job, company, skills, experience
    PREFERENCE = "preference"    # Likes, dislikes, favorites, style
    LOCATION = "location"        # City, country, timezone, address
    TECHNICAL = "technical"      # Stack, tools, environment, setup


class ExtractionTrigger(str, Enum):
    """What triggered the extraction."""
    
    CONVERSATION = "conversation"  # Normal message
    EXPLICIT = "explicit"          # User explicitly stated fact
    INFERRED = "inferred"          # Inferred from context
    CORRECTION = "correction"      # User corrected previous fact


@dataclass
class ExtractedFact:
    """A fact extracted from a conversation."""
    
    key: str
    value: str
    category: FactCategory
    confidence: float
    source_message: str
    evidence: str  # The specific text that supports this fact
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    trigger: ExtractionTrigger = ExtractionTrigger.CONVERSATION
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_user_fact(self) -> UserFact:
        """Convert to UserFact for storage in UserProfile."""
        return UserFact(
            key=self.key,
            value=self.value,
            category=self.category.value,
            confidence=self.confidence,
            timestamp=self.timestamp,
            source=self.trigger.value
        )


@dataclass
class ExtractionResult:
    """Result of a fact extraction operation."""
    
    facts: List[ExtractedFact]
    raw_message: str
    user_id: str
    extraction_time_ms: float
    model_used: str
    confidence_threshold: float
    
    def get_high_confidence_facts(self, min_confidence: float = 0.8) -> List[ExtractedFact]:
        """Get facts above a confidence threshold."""
        return [f for f in self.facts if f.confidence >= min_confidence]
    
    def get_by_category(self, category: FactCategory) -> List[ExtractedFact]:
        """Get facts in a specific category."""
        return [f for f in self.facts if f.category == category]


class FactExtractor:
    """Extract user facts from conversations using LLM.
    
    Uses AWS Bedrock to analyze user messages and extract structured
    facts about the user. Facts are categorized and confidence-scored.
    
    Example:
        >>> extractor = FactExtractor()
        >>> 
        >>> # Extract from a single message
        >>> result = await extractor.extract_facts(
        ...     "I live in Istanbul and prefer Python over Java",
        ...     user_id="user_123"
        ... )
        >>> 
        >>> # Extract from conversation context
        >>> result = await extractor.extract_from_conversation(
        ...     working_memory,
        ...     user_id="user_123"
        ... )
    """
    
    # LLM prompt for fact extraction
    EXTRACTION_PROMPT = """You are an expert at extracting factual information about users from their messages.

Analyze the following user message and extract any facts about the user.
For each fact, provide:
1. Key: A short identifier (e.g., "city", "job_title", "programming_language")
2. Value: The factual information
3. Category: One of [personal, professional, preference, location, technical]
4. Confidence: 0.0-1.0 score based on clarity and explicitness
5. Evidence: The exact text from the message that supports this fact

Only extract factual statements, not opinions or temporary states.
Be conservative - only include facts with confidence >= 0.5

User Message: {message}

Context (recent conversation): {context}

Respond in JSON format:
{{
    "facts": [
        {{
            "key": "location_city",
            "value": "Istanbul",
            "category": "location",
            "confidence": 0.95,
            "evidence": "I live in Istanbul"
        }}
    ],
    "reasoning": "Brief explanation of extraction decisions"
}}

If no facts can be extracted, return empty facts array."""

    # Keywords that indicate potential facts
    FACT_INDICATORS = [
        # English
        "i am", "i'm", "i work", "i live", "i use", "i prefer", "i like",
        "i don't like", "i hate", "i love", "my name is", "my job",
        "my company", "i develop", "i code", "i program", "i specialize",
        # Turkish
        "adım", "ismim", "yaşıyorum", "çalışıyorum", "kullanıyorum",
        "tercih ediyorum", "severim", "sevmem", "benim", "mesleğim",
        "geliştiriyorum", "kodluyorum", "uzmanlığım", "ben bir",
        "ilgileniyorum", "memleket", "doğumluyum", "yaşındayım",
    ]
    
    def __init__(self, confidence_threshold: float = 0.7) -> None:
        """Initialize the Fact Extractor.
        
        Args:
            confidence_threshold: Minimum confidence for storing facts
        """
        self._config = get_config()
        self._bedrock_client: Optional[Any] = None
        self._confidence_threshold = confidence_threshold
        self._model_id = self._config.aws.model_nova_lite  # Use lite model for extraction
        
        logger.info(f"FactExtractor initialized (threshold: {confidence_threshold})")
    
    async def initialize(self) -> None:
        """Initialize the Bedrock client."""
        if not self._bedrock_client:
            self._bedrock_client = get_bedrock_client()
            logger.info("FactExtractor Bedrock client initialized")
    
    def should_extract(self, message: str) -> bool:
        """Quick check if message might contain extractable facts.
        
        This is a lightweight filter to avoid unnecessary LLM calls.
        
        Args:
            message: User message to check
            
        Returns:
            True if message should be processed for fact extraction
        """
        message_lower = message.lower()
        
        # Check for fact indicators
        for indicator in self.FACT_INDICATORS:
            if indicator in message_lower:
                return True
        
        # Check for first-person statements
        first_person_patterns = [" i ", " my ", " me ", " myself "]
        for pattern in first_person_patterns:
            if pattern in f" {message_lower} ":
                return True
        
        return False
    
    async def extract_facts(
        self,
        message: str,
        user_id: str,
        context: Optional[str] = None,
        trigger: ExtractionTrigger = ExtractionTrigger.CONVERSATION
    ) -> ExtractionResult:
        """Extract facts from a user message.
        
        Args:
            message: The user message to analyze
            user_id: User identifier
            context: Optional conversation context
            trigger: What triggered this extraction
            
        Returns:
            ExtractionResult with extracted facts
        """
        import time
        
        start_time = time.time()
        
        if not self._bedrock_client:
            await self.initialize()
        
        logger.info(f"Extracting facts for user {user_id}")
        
        # Prepare prompt
        prompt = self.EXTRACTION_PROMPT.format(
            message=message,
            context=context or "No previous context"
        )
        
        try:
            # Call LLM for extraction using converse API
            response = self._bedrock_client.converse(
                modelId=self._model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt}]
                    }
                ],
                inferenceConfig={"temperature": 0.1, "maxTokens": 1000}
            )
            
            # Parse LLM response
            content = response['output']['message']['content']
            if content:
                text = content[0].get('text', '{}')
                
                # Extract JSON from response
                try:
                    extraction_data = json.loads(text)
                except json.JSONDecodeError:
                    # Try to find JSON in the text
                    import re
                    json_match = re.search(r'\{.*\}', text, re.DOTALL)
                    if json_match:
                        extraction_data = json.loads(json_match.group())
                    else:
                        extraction_data = {"facts": []}
            else:
                extraction_data = {"facts": []}
            
            # Convert to ExtractedFact objects
            facts = []
            for fact_data in extraction_data.get("facts", []):
                try:
                    confidence = float(fact_data.get("confidence", 0.5))
                    
                    # Skip low confidence facts
                    if confidence < self._confidence_threshold:
                        logger.debug(f"Skipping low confidence fact: {fact_data}")
                        continue
                    
                    fact = ExtractedFact(
                        key=fact_data.get("key", "unknown"),
                        value=fact_data.get("value", ""),
                        category=FactCategory(fact_data.get("category", "personal")),
                        confidence=confidence,
                        source_message=message,
                        evidence=fact_data.get("evidence", ""),
                        trigger=trigger
                    )
                    facts.append(fact)
                    
                except (ValueError, KeyError) as e:
                    logger.warning(f"Failed to parse fact: {fact_data}, error: {e}")
                    continue
            
            extraction_time = (time.time() - start_time) * 1000
            
            logger.info(f"Extracted {len(facts)} facts in {extraction_time:.0f}ms")
            
            return ExtractionResult(
                facts=facts,
                raw_message=message,
                user_id=user_id,
                extraction_time_ms=extraction_time,
                model_used=self._model_id,
                confidence_threshold=self._confidence_threshold
            )
            
        except Exception as e:
            logger.error(f"Fact extraction failed: {e}")
            
            return ExtractionResult(
                facts=[],
                raw_message=message,
                user_id=user_id,
                extraction_time_ms=(time.time() - start_time) * 1000,
                model_used=self._model_id,
                confidence_threshold=self._confidence_threshold
            )
    
    async def extract_from_conversation(
        self,
        working_memory: WorkingMemory,
        user_id: str,
        max_turns: int = 5
    ) -> ExtractionResult:
        """Extract facts from recent conversation history.
        
        Args:
            working_memory: WorkingMemory with conversation history
            user_id: User identifier
            max_turns: Number of recent turns to analyze
            
        Returns:
            Combined extraction results
        """
        # Get recent conversation turns
        context = working_memory.get_context_snapshot()
        history = context.conversation_history[-max_turns:]
        
        all_facts: List[ExtractedFact] = []
        total_time = 0.0
        
        # Process each user message
        for turn in history:
            if turn.role == "user":
                # Build context from previous turns
                context_str = self._build_context_string(
                    history[:history.index(turn)]
                )
                
                result = await self.extract_facts(
                    message=turn.content,
                    user_id=user_id,
                    context=context_str
                )
                
                all_facts.extend(result.facts)
                total_time += result.extraction_time_ms
        
        # Remove duplicates based on key
        seen_keys = set()
        unique_facts = []
        for fact in all_facts:
            if fact.key not in seen_keys:
                seen_keys.add(fact.key)
                unique_facts.append(fact)
        
        # Combine messages for reference
        combined_message = " | ".join([
            turn.content for turn in history if turn.role == "user"
        ])
        
        return ExtractionResult(
            facts=unique_facts,
            raw_message=combined_message[:500],  # Truncate for reference
            user_id=user_id,
            extraction_time_ms=total_time,
            model_used=self._model_id,
            confidence_threshold=self._confidence_threshold
        )
    
    def _build_context_string(self, turns: List[ConversationTurn]) -> str:
        """Build a context string from conversation turns.
        
        Args:
            turns: List of conversation turns
            
        Returns:
            Formatted context string
        """
        if not turns:
            return ""
        
        context_parts = []
        for turn in turns[-3:]:  # Last 3 turns for context
            prefix = "User: " if turn.role == "user" else "Assistant: "
            context_parts.append(f"{prefix}{turn.content[:100]}")
        
        return " | ".join(context_parts)
    
    async def store_facts(
        self,
        result: ExtractionResult,
        user_profile: UserProfile,
        semantic_memory=None
    ) -> Dict[str, Any]:
        """Store extracted facts in user profile and semantic memory.
        
        Args:
            result: Extraction result with facts
            user_profile: UserProfile to update
            semantic_memory: Optional SemanticMemory for long-term storage
            
        Returns:
            Storage summary
        """
        stored_count = 0
        stored_keys = []
        
        for fact in result.facts:
            # Store in UserProfile
            user_fact = fact.to_user_fact()
            user_profile.add_fact(user_fact)
            
            stored_keys.append(fact.key)
            stored_count += 1
            
            # Store in SemanticMemory if available
            if semantic_memory:
                try:
                    await semantic_memory.remember(
                        content=f"{fact.key}: {fact.value}",
                        category="fact",
                        source=f"extraction_{fact.trigger.value}",
                        confidence=fact.confidence,
                        metadata={
                            "user_id": result.user_id,
                            "key": fact.key,
                            "category": fact.category.value,
                            "evidence": fact.evidence
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to store fact in semantic memory: {e}")
        
        logger.info(f"Stored {stored_count} facts for user {result.user_id}")
        
        return {
            "stored_count": stored_count,
            "stored_keys": stored_keys,
            "user_id": result.user_id
        }
    
    def categorize_fact(self, key: str, value: str) -> FactCategory:
        """Categorize a fact based on key and value patterns.
        
        This is a fallback method when LLM categorization isn't available.
        
        Args:
            key: Fact key
            value: Fact value
            
        Returns:
            FactCategory
        """
        key_lower = key.lower()
        value_lower = value.lower()
        
        # Location patterns
        location_keywords = ["city", "country", "location", "live", "from", "address", "timezone"]
        if any(kw in key_lower for kw in location_keywords):
            return FactCategory.LOCATION
        
        # Professional patterns
        professional_keywords = ["job", "work", "company", "role", "title", "profession", "career", "experience"]
        if any(kw in key_lower for kw in professional_keywords):
            return FactCategory.PROFESSIONAL
        
        # Technical patterns
        technical_keywords = ["language", "framework", "tool", "stack", "platform", "software", "database", "cloud"]
        if any(kw in key_lower for kw in technical_keywords):
            return FactCategory.TECHNICAL
        
        # Preference patterns
        preference_keywords = ["like", "prefer", "favorite", "enjoy", "love", "hate", "dislike"]
        if any(kw in key_lower for kw in preference_keywords) or any(kw in value_lower for kw in preference_keywords):
            return FactCategory.PREFERENCE
        
        # Default to personal
        return FactCategory.PERSONAL
    
    def score_confidence(
        self,
        fact_text: str,
        evidence: str,
        is_explicit: bool = True
    ) -> float:
        """Score the confidence of an extracted fact.
        
        Args:
            fact_text: The extracted fact
            evidence: Supporting evidence from message
            is_explicit: Whether user explicitly stated this
            
        Returns:
            Confidence score (0.0-1.0)
        """
        score = 0.5  # Base score
        
        # Explicit statements get higher scores
        if is_explicit:
            score += 0.2
        
        # Direct evidence increases confidence
        if evidence and len(evidence) > 10:
            score += 0.15
        
        # Simple, clear facts are more confident
        if len(fact_text.split()) <= 5:
            score += 0.1
        
        # Specific values (not vague) increase confidence
        vague_terms = ["something", "some", "maybe", "probably", "i think"]
        if not any(term in fact_text.lower() for term in vague_terms):
            score += 0.1
        
        return min(1.0, max(0.0, score))


class FactExtractionPipeline:
    """Pipeline for automatic fact extraction from conversations.
    
    Integrates with WorkingMemory to automatically extract and store
    facts as conversations progress.
    
    Example:
        >>> pipeline = FactExtractionPipeline()
        >>> await pipeline.initialize()
        >>> 
        >>> # Process a new message
        >>> await pipeline.process_message(
        ...     message="I work at Google as a software engineer",
        ...     user_id="user_123",
        ...     user_profile=profile
        ... )
    """
    
    def __init__(
        self,
        confidence_threshold: float = 0.7,
        auto_store: bool = True
    ) -> None:
        """Initialize the extraction pipeline.
        
        Args:
            confidence_threshold: Minimum confidence for storing facts
            auto_store: Whether to automatically store extracted facts
        """
        self._extractor = FactExtractor(confidence_threshold)
        self._auto_store = auto_store
        self._extraction_history: List[ExtractionResult] = []
        
        logger.info("FactExtractionPipeline initialized")
    
    async def initialize(self) -> None:
        """Initialize the pipeline."""
        await self._extractor.initialize()
    
    async def process_message(
        self,
        message: str,
        user_id: str,
        user_profile: UserProfile,
        semantic_memory=None,
        working_memory=None
    ) -> ExtractionResult:
        """Process a user message and extract/store facts.
        
        Args:
            message: User message
            user_id: User identifier
            user_profile: UserProfile to update
            semantic_memory: Optional SemanticMemory for storage
            working_memory: Optional WorkingMemory for context
            
        Returns:
            Extraction result
        """
        # Quick check if extraction is worthwhile
        if not self._extractor.should_extract(message):
            logger.debug(f"Skipping extraction for message: {message[:50]}...")
            return ExtractionResult(
                facts=[],
                raw_message=message,
                user_id=user_id,
                extraction_time_ms=0,
                model_used="",
                confidence_threshold=self._extractor._confidence_threshold
            )
        
        # Build context from working memory
        context = None
        if working_memory:
            context = self._extractor._build_context_string(
                working_memory._conversation_history[-3:]
            )
        
        # Extract facts
        result = await self._extractor.extract_facts(
            message=message,
            user_id=user_id,
            context=context
        )
        
        # Store facts if enabled
        if self._auto_store and result.facts:
            await self._extractor.store_facts(
                result=result,
                user_profile=user_profile,
                semantic_memory=semantic_memory
            )
        
        # Record extraction
        self._extraction_history.append(result)
        
        return result
    
    async def process_conversation(
        self,
        working_memory: WorkingMemory,
        user_id: str,
        user_profile: UserProfile,
        semantic_memory=None
    ) -> ExtractionResult:
        """Process entire conversation history.
        
        Args:
            working_memory: WorkingMemory with conversation
            user_id: User identifier
            user_profile: UserProfile to update
            semantic_memory: Optional SemanticMemory
            
        Returns:
            Combined extraction result
        """
        result = await self._extractor.extract_from_conversation(
            working_memory=working_memory,
            user_id=user_id
        )
        
        if self._auto_store and result.facts:
            await self._extractor.store_facts(
                result=result,
                user_profile=user_profile,
                semantic_memory=semantic_memory
            )
        
        self._extraction_history.append(result)
        
        return result
    
    def get_extraction_stats(self) -> Dict[str, Any]:
        """Get statistics about extractions.
        
        Returns:
            Extraction statistics
        """
        total_extractions = len(self._extraction_history)
        total_facts = sum(len(r.facts) for r in self._extraction_history)
        avg_facts_per_extraction = total_facts / total_extractions if total_extractions > 0 else 0
        
        # Count by category
        category_counts: Dict[str, int] = {}
        for result in self._extraction_history:
            for fact in result.facts:
                cat = fact.category.value
                category_counts[cat] = category_counts.get(cat, 0) + 1
        
        return {
            "total_extractions": total_extractions,
            "total_facts_extracted": total_facts,
            "avg_facts_per_extraction": round(avg_facts_per_extraction, 2),
            "facts_by_category": category_counts,
            "avg_confidence": round(
                sum(f.confidence for r in self._extraction_history for f in r.facts) / total_facts, 2
            ) if total_facts > 0 else 0
        }


# Singleton instance for easy access
_extractor_instance: Optional[FactExtractor] = None
_pipeline_instance: Optional[FactExtractionPipeline] = None


def get_fact_extractor() -> FactExtractor:
    """Get or create the singleton FactExtractor instance.
    
    Returns:
        FactExtractor singleton
    """
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = FactExtractor()
    return _extractor_instance


def get_extraction_pipeline(
    confidence_threshold: float = 0.7,
    auto_store: bool = True
) -> FactExtractionPipeline:
    """Get or create the singleton FactExtractionPipeline.
    
    Args:
        confidence_threshold: Minimum confidence for facts
        auto_store: Auto-store extracted facts
        
    Returns:
        FactExtractionPipeline singleton
    """
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = FactExtractionPipeline(
            confidence_threshold=confidence_threshold,
            auto_store=auto_store
        )
    return _pipeline_instance
