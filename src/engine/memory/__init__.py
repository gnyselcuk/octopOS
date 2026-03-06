"""Memory module - Vector storage and semantic memory."""

from src.engine.memory.intent_finder import IntentFinder, get_intent_finder, PrimitiveMatch
from src.engine.memory.semantic_memory import SemanticMemory, get_semantic_memory, MemoryEntry
from src.engine.memory.working_memory import (
    WorkingMemory,
    ConversationTurn,
    SessionVariable,
    ContextSnapshot,
    get_working_memory,
    clear_working_memory,
)
from src.engine.memory.fact_extractor import (
    FactExtractor,
    FactExtractionPipeline,
    ExtractedFact,
    ExtractionResult,
    FactCategory,
    ExtractionTrigger,
    get_fact_extractor,
    get_extraction_pipeline,
)
from src.engine.memory.semantic_cache import (
    SemanticCache,
    CacheEntry,
    get_semantic_cache,
)

__all__ = [
    "IntentFinder",
    "get_intent_finder",
    "PrimitiveMatch",
    "SemanticMemory",
    "get_semantic_memory",
    "MemoryEntry",
    "WorkingMemory",
    "ConversationTurn",
    "SessionVariable",
    "ContextSnapshot",
    "get_working_memory",
    "clear_working_memory",
    "FactExtractor",
    "FactExtractionPipeline",
    "ExtractedFact",
    "ExtractionResult",
    "FactCategory",
    "ExtractionTrigger",
    "get_fact_extractor",
    "get_extraction_pipeline",
    "SemanticCache",
    "CacheEntry",
    "get_semantic_cache",
]