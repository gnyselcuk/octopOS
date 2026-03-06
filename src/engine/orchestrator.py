"""Main Brain (Orchestrator) - Central intelligence for octopOS.

This module implements the Main Brain agent that:
- Analyzes user intent from natural language input
- Breaks down complex tasks into subtasks
- Routes tasks to appropriate specialist agents
- Manages overall workflow and coordination
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from src.engine.base_agent import BaseAgent
from src.engine.message import (
    ApprovalPayload,
    ErrorPayload,
    ErrorSeverity,
    MessageType,
    OctoMessage,
    TaskPayload,
    TaskStatus,
    get_message_queue,
)
from src.utils.aws_sts import get_bedrock_client
from src.utils.config import get_config
from src.utils.logger import get_logger, AgentLogger
from src.engine.memory.working_memory import get_working_memory, WorkingMemory
from src.engine.memory.semantic_memory import get_semantic_memory, SemanticMemory
from src.engine.memory.fact_extractor import get_fact_extractor, FactExtractor
from src.engine.scheduler import get_scheduler

logger = get_logger()


class IntentType:
    """Types of user intents."""
    
    CHAT = "chat"  # Casual conversation
    TASK = "task"  # Operational task
    CODE = "code"  # Code generation
    DEBUG = "debug"  # Error fixing
    QUERY = "query"  # Information retrieval
    MISSION = "mission" # Browser-based complex missions
    BROWSER = "browser"  # Web browser missions (price comparison, stock check)


class IntentAnalysis:
    """Result of intent analysis."""
    
    def __init__(
        self,
        intent_type: str,
        confidence: float,
        description: str,
        required_agents: List[str],
        estimated_steps: int,
        context: Dict[str, Any]
    ):
        self.intent_type = intent_type
        self.confidence = confidence
        self.description = description
        self.required_agents = required_agents
        self.estimated_steps = estimated_steps
        self.context = context


class SubTask:
    """A subtask from a parent task."""
    
    def __init__(
        self,
        task_id: UUID,
        action: str,
        agent_type: str,
        params: Dict[str, Any],
        dependencies: List[UUID] = None,
        priority: int = 5
    ):
        self.task_id = task_id
        self.action = action
        self.agent_type = agent_type
        self.params = params
        self.dependencies = dependencies or []
        self.priority = priority
        self.status = TaskStatus.PENDING
        self.result: Optional[Dict[str, Any]] = None


class Orchestrator(BaseAgent):
    """Main Brain - Central orchestrator for octopOS.
    
    The Orchestrator is responsible for:
    1. Analyzing user input to determine intent
    2. Breaking down complex tasks into subtasks
    3. Routing tasks to appropriate specialist agents
    4. Monitoring task progress and handling completion
    5. Coordinating with Supervisor for approvals
    
    Example:
        >>> orchestrator = Orchestrator()
        >>> await orchestrator.start()
        >>> result = await orchestrator.process_user_input(
        ...     "Create a Python script that uploads files to S3"
        ... )
    """
    
    def __init__(self, context: Optional[Any] = None) -> None:
        """Initialize the Orchestrator.
        
        Args:
            context: Shared agent context
        """
        super().__init__(name="MainBrain", context=context)
        self.agent_logger = AgentLogger("MainBrain")
        self._tasks: Dict[UUID, SubTask] = {}
        self._bedrock_client = None
        self._config = get_config()
        
        # Memory components (initialized lazily in on_start)
        self._working_memory: Optional[WorkingMemory] = None
        self._semantic_memory: Optional[SemanticMemory] = None
        self._fact_extractor: Optional[FactExtractor] = None
        
        self.agent_logger.info("Orchestrator initialized")
    
    async def on_start(self) -> None:
        """Initialize Bedrock client, memory systems, and MCP servers on startup."""
        try:
            self._bedrock_client = get_bedrock_client()
            self.agent_logger.info("Bedrock client initialized")
            
            # Initialize memory systems
            try:
                self._working_memory = get_working_memory(session_id=str(uuid4()))
                self.agent_logger.info("Working memory initialized")
                
                self._semantic_memory = await get_semantic_memory()
                self.agent_logger.info("Semantic memory initialized")
                
                self._fact_extractor = get_fact_extractor()
                await self._fact_extractor.initialize()
                self.agent_logger.info("Fact extractor initialized")
            except Exception as mem_err:
                self.agent_logger.warning(f"Memory initialization partial failure (non-fatal): {mem_err}")
            
            # Initialize MCP servers
            from src.primitives.mcp_adapter import get_mcp_manager
            mcp_manager = get_mcp_manager()
            await mcp_manager.initialize_from_config()
            
            # Start Scheduler and register periodic tasks
            try:
                scheduler = get_scheduler()
                await scheduler.start()
                
                # Register memory pruning every 24 hours
                if self._semantic_memory:
                    await scheduler.schedule_interval(
                        agent_type="MainBrain",
                        action="prune_memory",
                        params={},
                        hours=24,
                        title="Daily Memory Pruning"
                    )
                self.agent_logger.info("Scheduler started with periodic memory pruning")
            except Exception as sched_err:
                self.agent_logger.warning(f"Scheduler initialization failed: {sched_err}")
            
        except Exception as e:
            self.agent_logger.error(f"Failed to initialize Orchestrator: {e}")
            raise
    
    async def execute_task(self, task: TaskPayload) -> Dict[str, Any]:
        """Execute a task assigned to the Orchestrator.
        
        This is the entry point when another agent sends a task to MainBrain.
        
        Args:
            task: The task payload
            
        Returns:
            Task execution results
        """
        self.agent_logger.info(f"Executing task: {task.action}")
        
        if task.action == "process_user_input":
            user_input = task.params.get("input", "")
            return await self.process_user_input(user_input)
        elif task.action == "analyze_intent":
            text = task.params.get("text", "")
            return await self._analyze_intent(text)
        elif task.action == "prune_memory":
            if self._semantic_memory:
                count = await self._semantic_memory.prune_decayed_memories()
                return {"status": "success", "pruned_count": count}
            return {"status": "error", "message": "Semantic memory not initialized"}
        else:
            return {"status": "error", "message": f"Unknown action: {task.action}"}
    
    async def process_user_input(self, user_input: str) -> Dict[str, Any]:
        """Process user input and orchestrate the response.
        
        This is the main entry point for user interactions.
        
        Args:
            user_input: Natural language input from user
            
        Returns:
            Processing results including any outputs
        """
        self.agent_logger.info(f"Processing user input: {user_input[:100]}...")
        
        # Step 0: Store user message in working memory
        if self._working_memory:
            self._working_memory.add_user_message(user_input)
        
        # Step 0.5: Recall relevant context from long-term memory
        memory_context = ""
        if self._semantic_memory:
            try:
                memories = await self._semantic_memory.recall(user_input, top_k=5, min_score=0.1)
                if memories:
                    memory_context = "\n".join([f"- {m.content}" for m in memories])
                    self.agent_logger.info(f"Recalled {len(memories)} relevant memories")
            except Exception as e:
                self.agent_logger.warning(f"Memory recall failed (non-fatal): {e}")
        
        # Step 1: Analyze intent
        intent = await self._analyze_intent(user_input)
        
        # Step 2: Handle based on intent type
        if intent.intent_type == IntentType.CHAT:
            result = await self._handle_chat(user_input, intent, memory_context=memory_context)
        elif intent.intent_type == IntentType.TASK:
            result = await self._handle_task(user_input, intent)
        elif intent.intent_type == IntentType.CODE:
            result = await self._handle_code_request(user_input, intent)
        elif intent.intent_type == IntentType.DEBUG:
            result = await self._handle_debug_request(user_input, intent)
        elif intent.intent_type == IntentType.QUERY:
            result = await self._handle_query(user_input, intent, memory_context=memory_context)
        elif intent.intent_type == IntentType.MISSION:
            result = await self._handle_browser_mission(user_input, intent)
        elif intent.intent_type == IntentType.BROWSER:
            result = await self._handle_browser_mission(user_input, intent)
        else:
            result = await self._handle_chat(user_input, intent, memory_context=memory_context)
        
        # Step 3: Store assistant response in working memory
        response_text = result.get("response", "")
        if self._working_memory and response_text:
            self._working_memory.add_assistant_message(response_text)
        
        # Step 4: Background fact extraction (non-blocking)
        if self._fact_extractor and self._semantic_memory:
            try:
                if self._fact_extractor.should_extract(user_input):
                    extraction_result = await self._fact_extractor.extract_facts(
                        message=user_input,
                        user_id=self._config.user.name or "default"
                    )
                    if extraction_result and extraction_result.facts:
                        for fact in extraction_result.facts:
                            await self._semantic_memory.remember(
                                content=f"{fact.key}: {fact.value}",
                                category="fact",
                                source=f"extraction_{fact.trigger.value}",
                                confidence=fact.confidence,
                                metadata={
                                    "key": fact.key,
                                    "category": fact.category.value,
                                    "evidence": fact.evidence
                                }
                            )
                        self.agent_logger.info(f"Extracted and stored {len(extraction_result.facts)} facts")
            except Exception as e:
                self.agent_logger.warning(f"Fact extraction failed (non-fatal): {e}")
        
        return result
    
    async def _analyze_intent(self, text: str) -> IntentAnalysis:
        """Analyze user input to determine intent using Nova Lite.
        
        Args:
            text: User input text
            
        Returns:
            IntentAnalysis with type, confidence, and routing info
        """
        self.agent_logger.debug(f"Analyzing intent for: {text[:100]}...")
        
        # Use Nova Lite for intent classification
        system_prompt = """You are an intent classification system for an AI agent operating system.
Analyze the user input and classify it into one of these categories:
- "chat": Casual conversation, greetings, or basic questions about the agent.
- "task": Complex operational workflows that change state, create multiple files, or require coordination between specialists.
- "code": Specific requests to write, modify, review, or debug code content.
- "debug": Analyzing error messages or fixing identified bugs in code.
- "query": Information retrieval of ANY kind (web search, system inspection, code analysis, file searching). Use this whenever the user wants to KNOW something or see current status.
- "mission": Complex browser-based tasks that require navigation, multi-step actions, price comparisons, or automated web workflows (e.g., "Find best price for X", "Check stock at Y", "Book a flight").
- "browser": Web browser missions requiring interaction with websites - price comparisons across multiple sites, checking stock availability, filling forms, or navigating complex web interfaces. Use when user wants to "find the best price", "check if X is in stock", "compare prices", or interact with e-commerce sites.

Respond with a JSON object containing:
{
    "intent_type": "one of the above categories",
    "confidence": 0.0-1.0,
    "description": "brief description of what the user wants",
    "required_agents": ["list of specialist agents needed"],
    "estimated_steps": number of steps to complete,
    "context": {
        "url": "starting URL if mentioned",
        "sites": ["list of sites to visit/compare"],
        "product_name": "extracted product name if applicable",
        "mission_type": "price_comparison, stock_check, research, or navigation",
        "schema": {"expected": "data_structure"}
    }
}"""

        try:
            response = self._bedrock_client.converse(
                modelId=self._config.aws.model_nova_lite,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": system_prompt}]
                    },
                    {
                        "role": "user",
                        "content": [{"text": f"Classify this input: {text}"}]
                    }
                ],
                inferenceConfig={"temperature": 0.1, "maxTokens": 500}
            )
            
            # Extract response text
            response_text = response['output']['message']['content'][0]['text']
            
            # Parse JSON response
            # Handle potential markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            result = json.loads(response_text.strip())
            
            intent = IntentAnalysis(
                intent_type=result.get("intent_type", "chat"),
                confidence=result.get("confidence", 0.5),
                description=result.get("description", "Unknown intent"),
                required_agents=result.get("required_agents", []),
                estimated_steps=result.get("estimated_steps", 1),
                context=result.get("context", {})
            )
            
            self.agent_logger.info(
                f"Intent classified: {intent.intent_type} "
                f"(confidence: {intent.confidence:.2f})"
            )
            return intent
            
        except Exception as e:
            self.agent_logger.error(f"Intent analysis failed: {e}")
            # Fallback to chat
            return IntentAnalysis(
                intent_type=IntentType.CHAT,
                confidence=0.5,
                description="Fallback to chat due to analysis error",
                required_agents=["MainBrain"],
                estimated_steps=1,
                context={"error": str(e)}
            )

    async def _handle_query(self, user_input: str, intent: IntentAnalysis, memory_context: str = "") -> Dict[str, Any]:
        """Handle information retrieval/query intent.
        
        Uses Bedrock Tool Calling with the primitive library.
        """
        self.agent_logger.info("Handling as tool-assisted query")
        
        from src.primitives.tool_registry import get_registry
        registry = get_registry()
        
        # Get tool definitions for Bedrock
        tools = registry.to_bedrock_tool_config()
        
        system_prompt = self._config.agent.get_system_prompt()
        if memory_context:
            system_prompt += f"\n\nHere is relevant context from your memory about the user and past interactions:\n{memory_context}\nUse this context when relevant, but don't explicitly mention 'my memory says...', just use the info naturally."
            
        messages = []
        
        # Add conversation history
        if self._working_memory:
            history = self._working_memory.get_last_n_messages(10)
            for msg in history:
                messages.append({
                    "role": msg["role"],
                    "content": [{"text": msg["content"]}]
                })
        else:
            messages.append({
                "role": "user",
                "content": [{"text": user_input}]
            })
        
        try:
            # Single-turn tool usage loop
            for _ in range(10): # Max 10 turns for complex reasoning
                response = self._bedrock_client.converse(
                    modelId=self._config.aws.model_nova_pro,
                    system=[{"text": self._config.agent.get_system_prompt()}],
                    messages=messages,
                    toolConfig={"tools": tools}
                )
                
                output_msg = response['output']['message']
                messages.append(output_msg)
                
                # Check for stop reason
                stop_reason = response.get('stopReason')
                
                if stop_reason == 'tool_use':
                    tool_results = []
                    for content in output_msg['content']:
                        if 'toolUse' in content:
                            tool_use = content['toolUse']
                            tool_name = tool_use['name']
                            tool_id = tool_use['toolUseId']
                            tool_args = tool_use['input']
                            
                            self.agent_logger.info(f"Executing tool: {tool_name}")
                            result = await registry.execute_tool(tool_name, **tool_args)
                            
                            tool_results.append({
                                "toolResult": {
                                    "toolUseId": tool_id,
                                    "content": [{"json": result.to_dict() if hasattr(result, 'to_dict') else {"success": result.success, "data": result.data, "message": result.message}}],
                                    "status": "success" if result.success else "error"
                                }
                            })
                    
                    messages.append({
                        "role": "user",
                        "content": tool_results
                    })
                else:
                    # Final response received
                    response_text = ""
                    for content in output_msg['content']:
                        if 'text' in content:
                            response_text += content['text']
                    
                    return {
                        "status": "success",
                        "intent": "query",
                        "response": response_text
                    }
            
            return {
                "status": "error",
                "message": "Too many tool execution turns"
            }
            
        except Exception as e:
            self.agent_logger.error(f"Tool execution failed: {e}")
            return {
                "status": "error",
                "message": f"Query processing failed: {str(e)}"
            }


    
    async def _handle_chat(self, user_input: str, intent: IntentAnalysis, memory_context: str = "") -> Dict[str, Any]:
        """Handle chat/conversational intent.
        
        Args:
            user_input: Original user input
            intent: Intent analysis result
            memory_context: Context string containing relevant facts
            
        Returns:
            Chat response
        """
        self.agent_logger.info("Handling as chat interaction")
        
        # Generate conversational response using Nova Pro
        system_prompt = self._config.agent.get_system_prompt()
        if memory_context:
            system_prompt += f"\n\nHere is relevant context from your memory about the user and past interactions:\n{memory_context}\nUse this context when relevant, but don't explicitly mention 'my memory says...', just use the info naturally."
        
        messages = []
        
        # Add conversation history from working memory
        if self._working_memory:
            history = self._working_memory.get_last_n_messages(10)
            for msg in history:
                messages.append({
                    "role": msg["role"],
                    "content": [{"text": msg["content"]}]
                })
        else:
            messages.append({
                "role": "user",
                "content": [{"text": user_input}]
            })
        
        try:
            response = self._bedrock_client.converse(
                modelId=self._config.aws.model_nova_pro,
                system=[{"text": system_prompt}],
                messages=messages,
                inferenceConfig={"temperature": 0.7, "maxTokens": 1000}
            )
            
            response_text = response['output']['message']['content'][0]['text']
            
            return {
                "status": "success",
                "intent": "chat",
                "response": response_text,
                "confidence": intent.confidence
            }
            
        except Exception as e:
            self.agent_logger.error(f"Chat response generation failed: {e}")
            return {
                "status": "error",
                "message": f"Failed to generate response: {e}"
            }
    
    async def _handle_browser_mission(self, user_input: str, intent: IntentAnalysis) -> Dict[str, Any]:
        """Handle browser-based mission intent.
        
        Routes to BrowserAgent for web automation tasks like price comparison,
        stock checking, or complex web interactions.
        
        Args:
            user_input: Original user input
            intent: Intent analysis result with browser mission context
            
        Returns:
            Mission execution results with comparison data
        """
        self.agent_logger.info("Handling as browser mission")
        
        try:
            from src.specialist.browser_agent import BrowserAgent, create_browser_agent
            
            # Initialize or get browser agent
            browser_agent = create_browser_agent(config=self._config)
            
            # Determine mission type from context
            context = intent.context
            mission_type = context.get("mission_type", "general")
            product_name = context.get("product_name", "")
            
            # Prepare mission parameters
            if mission_type == "price_comparison" or "price" in user_input.lower() or "cheapest" in user_input.lower():
                # Price comparison mission (e.g., RTX 5090)
                sites = context.get("sites", self._config.web.default_comparison_sites)
                
                payload = {
                    "product_name": product_name or user_input,
                    "search_query": product_name or user_input,
                    "sites": sites
                }
                
                # Send to BrowserAgent
                response = await browser_agent._handle_price_comparison(
                    type('Message', (), {
                        'payload': payload,
                        'user_id': context.get('user_id', 'default')
                    })()
                )
                
                # Format response for user
                if response.get("best_option"):
                    best = response["best_option"]
                    all_options = response.get("all_options", [])
                    
                    result_text = f"🏆 **Best Deal Found**\n\n"
                    result_text += f"**{best['site_name']}**: ${best['price']:.2f}\n"
                    result_text += f"Recommendation: {response.get('recommendation', '')}\n\n"
                    
                    if len(all_options) > 1:
                        result_text += "**All Options Found:**\n"
                        for opt in sorted(all_options, key=lambda x: x.get('price') or float('inf')):
                            if opt.get('success') and opt.get('price'):
                                result_text += f"- {opt['site_name']}: ${opt['price']:.2f}\n"
                    
                    return {
                        "status": "success",
                        "intent": "browser",
                        "mission_type": "price_comparison",
                        "response": result_text,
                        "data": response,
                        "screenshots": [opt.get('screenshot_path') for opt in all_options if opt.get('screenshot_path')]
                    }
                else:
                    return {
                        "status": "partial_success",
                        "intent": "browser",
                        "response": f"I searched for '{product_name}' but couldn't find pricing information on the checked sites.",
                        "data": response
                    }
                    
            elif mission_type == "stock_check" or "stock" in user_input.lower() or "available" in user_input.lower():
                # Stock checking mission
                sites = context.get("sites", self._config.web.default_comparison_sites)
                
                payload = {
                    "product_name": product_name or user_input,
                    "sites": sites
                }
                
                response = await browser_agent._handle_stock_check(
                    type('Message', (), {
                        'payload': payload,
                        'user_id': context.get('user_id', 'default')
                    })()
                )
                
                in_stock_sites = [r for r in response.get("results", []) if r.get("in_stock")]
                
                if in_stock_sites:
                    result_text = f"✅ **In Stock at {len(in_stock_sites)} site(s)**\n\n"
                    for site in in_stock_sites:
                        result_text += f"- {site['site']}: ${site.get('price', 'N/A')}\n"
                else:
                    result_text = f"❌ **Out of Stock**\n\n'{product_name}' is currently not in stock at any checked sites."
                
                return {
                    "status": "success",
                    "intent": "browser",
                    "mission_type": "stock_check",
                    "response": result_text,
                    "data": response
                }
            
            else:
                # Generic browser mission (research, navigation, etc.)
                payload = {
                    "description": intent.description or user_input,
                    "target_sites": context.get("sites", []),
                    "user_id": context.get("user_id", "default"),
                    "starting_url": context.get("url", "")
                }
                
                response = await browser_agent._handle_browser_mission(
                    type('Message', (), {
                        'payload': payload,
                        'user_id': context.get('user_id', 'default')
                    })()
                )
                
                # Better formatting for generic mission results
                final_data = response.get("final_data")
                result_text = ""
                
                if final_data:
                    if isinstance(final_data, dict):
                        # Join all values into a readable string
                        data_parts = []
                        for k, v in final_data.items():
                            if v: data_parts.append(f"**{k}**: {v}")
                        result_text = "\n".join(data_parts)
                    else:
                        result_text = str(final_data)
                
                # If no data extracted but mission successful, use the last reasoning
                if not result_text and response.get("success"):
                    reasoning = response.get("reasoning_log", [])
                    if reasoning:
                        result_text = f"Mission completed. {reasoning[-1]}"
                    else:
                        result_text = "Mission completed successfully, but no specific data was extracted."
                
                if not result_text:
                    result_text = f"Mission failed or returned no results. Mission ID: {response.get('mission_id')}"

                return {
                    "status": "success",
                    "intent": "browser",
                    "mission_type": "general",
                    "response": result_text,
                    "data": response
                }
                
        except Exception as e:
            self.agent_logger.error(f"Browser mission failed: {e}")
            return {
                "status": "error",
                "intent": "browser",
                "message": f"Browser mission failed: {str(e)}"
            }
    
    async def _handle_task(self, user_input: str, intent: IntentAnalysis) -> Dict[str, Any]:
        """Handle operational task intent.
        
        Args:
            user_input: Original user input
            intent: Intent analysis result
            
        Returns:
            Task execution results
        """
        self.agent_logger.info("Handling as operational task")
        
        # Check if we have the required tools/primitives
        # For now, check with IntentFinder (if available) or route to Coder
        
        # Break down into subtasks
        subtasks = await self._decompose_task(user_input, intent)
        
        # Execute subtasks
        results = await self._execute_subtasks(subtasks)
        
        return {
            "status": "success",
            "intent": "task",
            "subtasks_completed": len(results),
            "results": results
        }
    
    async def _handle_code_request(self, user_input: str, intent: IntentAnalysis) -> Dict[str, Any]:
        """Handle code generation request — runs inline for immediate chat response.
        
        Args:
            user_input: Original user input
            intent: Intent analysis result
            
        Returns:
            Code generation results with code preview
        """
        self.agent_logger.info("Handling as code request (inline)")
        
        try:
            from src.specialist.coder_agent import CoderAgent
            
            coder = CoderAgent()
            coder._bedrock_client = self._bedrock_client
            
            result = await coder.create_primitive(
                description=user_input,
                language=intent.context.get("language", "python")
            )
            
            if result.get("status") in ("pending_review", "success"):
                code = result.get("full_code", result.get("code_preview", ""))
                name = result.get("name", "generated_code")
                
                response_text = (
                    f"✅ **Kod oluşturuldu: `{name}`**\n\n"
                    f"```python\n{code}\n```\n\n"
                    f"ℹ️ Kod güvenlik incelemesi için kuyruğa alındı. "
                    f"Onaylandıktan sonra otomatik olarak sisteme kaydedilecek."
                )
                return {
                    "status": "success",
                    "intent": "code",
                    "response": response_text,
                    "name": name,
                    "code": code,
                }
            else:
                return {
                    "status": "error",
                    "intent": "code",
                    "message": result.get("message", "Kod oluşturulamadı"),
                }
        except Exception as e:
            self.agent_logger.error(f"Inline code generation failed: {e}")
            return {
                "status": "error",
                "intent": "code",
                "message": f"Kod oluşturma başarısız oldu: {e}"
            }
    
    async def _handle_debug_request(self, user_input: str, intent: IntentAnalysis) -> Dict[str, Any]:
        """Handle debug/error fixing request — runs inline.
        
        Args:
            user_input: Original user input
            intent: Intent analysis result
            
        Returns:
            Debug results
        """
        self.agent_logger.info("Handling as debug request (inline)")
        
        try:
            from src.specialist.self_healing_agent import SelfHealingAgent
            
            healer = SelfHealingAgent()
            healer._bedrock_client = self._bedrock_client
            
            task_id = uuid4()
            task = TaskPayload(
                task_id=task_id,
                action="debug_error",
                params={
                    "error_description": user_input,
                    "context": intent.context
                },
                priority=8
            )
            
            result = await healer.execute_task(task)
            
            if result.get("status") == "success":
                fixed = result.get("fixed_code", "")
                response_text = (
                    f"🔧 **Hata analiz edildi ve düzeltme önerisi:**\n\n"
                    f"```python\n{fixed}\n```"
                    if fixed else result.get("message", "Hata analiz edildi.")
                )
                return {
                    "status": "success",
                    "intent": "debug",
                    "response": response_text,
                }
            else:
                return {
                    "status": "error",
                    "intent": "debug",
                    "message": result.get("message", "Debug başarısız"),
                }
        except Exception as e:
            self.agent_logger.error(f"Inline debug failed: {e}")
            return {
                "status": "error",
                "intent": "debug",
                "message": f"Debug başarısız: {e}"
            }
    
    async def _decompose_task(
        self,
        user_input: str,
        intent: IntentAnalysis
    ) -> List[SubTask]:
        """Break down a complex task into subtasks.
        
        Args:
            user_input: Original task description
            intent: Intent analysis
            
        Returns:
            List of subtasks
        """
        self.agent_logger.debug("Decomposing task into subtasks")
        
        # Use LLM to break down task
        prompt = f"""Break down this task into specific steps:
Task: {user_input}
Context: {json.dumps(intent.context)}

Respond with a JSON array of steps:
[
    {{
        "action": "specific action name",
        "agent_type": "which agent should handle this (CoderAgent, SelfHealingAgent, etc.)",
        "params": {{"key": "value"}},
        "dependencies": []
    }}
]"""

        try:
            response = self._bedrock_client.converse(
                modelId=self._config.aws.model_nova_lite,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"temperature": 0.2, "maxTokens": 1000}
            )
            
            response_text = response['output']['message']['content'][0]['text']
            
            # Parse JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            steps = json.loads(response_text.strip())
            
            subtasks = []
            for i, step in enumerate(steps):
                subtask = SubTask(
                    task_id=uuid4(),
                    action=step["action"],
                    agent_type=step["agent_type"],
                    params=step.get("params", {}),
                    dependencies=[UUID(d) for d in step.get("dependencies", [])],
                    priority=step.get("priority", 5)
                )
                self._tasks[subtask.task_id] = subtask
                subtasks.append(subtask)
            
            self.agent_logger.info(f"Created {len(subtasks)} subtasks")
            return subtasks
            
        except Exception as e:
            self.agent_logger.error(f"Task decomposition failed: {e}")
            # Create a single fallback subtask
            subtask = SubTask(
                task_id=uuid4(),
                action="execute_task",
                agent_type="CoderAgent",
                params={"description": user_input},
                priority=5
            )
            self._tasks[subtask.task_id] = subtask
            return [subtask]
    
    async def _execute_subtasks(self, subtasks: List[SubTask]) -> List[Dict[str, Any]]:
        """Execute a list of subtasks.
        
        Args:
            subtasks: List of subtasks to execute
            
        Returns:
            Results from each subtask
        """
        results = []
        
        for subtask in subtasks:
            self.agent_logger.info(f"Executing subtask: {subtask.action}")
            
            # Check dependencies
            pending_deps = [
                dep for dep in subtask.dependencies
                if dep in self._tasks and self._tasks[dep].status != TaskStatus.COMPLETED
            ]
            
            if pending_deps:
                self.agent_logger.warning(
                    f"Subtask {subtask.task_id} has pending dependencies: {pending_deps}"
                )
                continue
            
            # Create and send task message
            task_payload = TaskPayload(
                task_id=subtask.task_id,
                action=subtask.action,
                params=subtask.params,
                priority=subtask.priority
            )
            
            self.send_message(
                receiver=subtask.agent_type,
                msg_type=MessageType.TASK,
                payload=task_payload
            )
            
            subtask.status = TaskStatus.IN_PROGRESS
            
            results.append({
                "subtask_id": str(subtask.task_id),
                "action": subtask.action,
                "agent": subtask.agent_type,
                "status": "sent"
            })
        
        return results
    
    async def on_stop(self) -> None:
        """Cleanup on orchestrator stop."""
        self.agent_logger.info("Orchestrator shutting down")
        self._tasks.clear()


# Singleton instance
_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    """Get the global Orchestrator instance.
    
    Returns:
        Singleton Orchestrator instance
    """
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator