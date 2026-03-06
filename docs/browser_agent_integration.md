# Browser Agent Integration Documentation

## Overview

The Browser Agent integration transforms octopOS from a text-generating assistant into a full-fledged cyber assistant capable of executing complex web-based missions. Using AWS Nova Act's Computer Use capabilities and Playwright browser automation, the system can now:

- Navigate websites autonomously
- Compare prices across multiple e-commerce sites
- Check stock availability
- Extract structured data from web pages
- Maintain persistent browser sessions with login states
- Execute complex multi-step missions

## Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                    BrowserAgent                             │
│                  (Specialist Agent)                         │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │NovaActDriver │  │SessionManager│  │ScreenshotStore │  │
│  │              │  │              │  │                │  │
│  │- Observe    │  │- Sessions   │  │- Local/S3     │  │
│  │- Analyze    │  │- Cookies    │  │- Gallery      │  │
│  │- Act        │  │- Profiles   │  │- Metadata     │  │
│  │- Verify     │  │              │  │                │  │
│  └──────────────┘  └──────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
    ┌──────────────────┐   ┌──────────────────┐
    │  Playwright      │   │   AWS Bedrock    │
    │  Browser         │   │   Nova Act       │
    │                  │   │                  │
    │  - Chromium      │   │  - Computer Use  │
    │  - Automation    │   │  - Multimodal    │
    │  - Screenshots   │   │  - Decisions     │
    └──────────────────┘   └──────────────────┘
```

## Key Features

### 1. Observe-Act-Verify Loop

The core execution pattern for browser missions:

1. **OBSERVE**: Capture current browser state (screenshot, HTML, URL)
2. **ANALYZE**: Send to Nova Act model for decision
3. **ACT**: Execute browser action (click, type, scroll, navigate)
4. **VERIFY**: Check if action achieved expected outcome

```python
async def execute_step(session_id, mission_context):
    # OBSERVE
    snapshot, observation = await driver.observe(session_id, mission_context)
    
    # ANALYZE
    decision = await driver.analyze(observation, snapshot.screenshot_path)
    
    # ACT
    action_result = await driver.act(session_id, decision)
    
    # VERIFY
    verification = await driver.verify(session_id, decision, action_result, snapshot)
    
    return MissionStep(decision, action_result, verification)
```

### 2. Persistent Browser Sessions

Sessions maintain:
- Cookies and login states
- LocalStorage data
- SessionStorage data
- User preferences

```python
# Create a persistent session
session = await session_manager.create_session(
    user_id="user123",
    mission_id="price_check_rtx5090",
    metadata={"product": "RTX 5090"}
)

# Use same session across multiple sites
for site in ["amazon.com", "newegg.com", "bestbuy.com"]:
    await browser_agent.compare_prices(site, session_id=session.session_id)
```

### 3. Price Comparison Mission

Example: Find the best price for RTX 5090

```python
mission = BrowserMission(
    mission_id="rtx5090_price_check",
    description="Find the best price for RTX 5090 GPU",
    starting_url="https://amazon.com",
    target_sites=["amazon.com", "newegg.com", "bestbuy.com", "microcenter.com"],
    extraction_schema={
        "product_name": "string",
        "price": "number",
        "in_stock": "boolean"
    }
)

result = await browser_agent.compare_prices(
    mission_id="rtx5090_price_check",
    product_name="RTX 5090",
    sites=["amazon.com", "newegg.com", "bestbuy.com"]
)
```

### 4. Screenshot Storage

Screenshots are automatically captured and stored:
- Local filesystem storage
- S3 upload for persistence
- Metadata indexing
- HTML gallery generation

```python
# Store screenshot
meta = await screenshot_storage.store_screenshot(
    mission_id="rtx5090",
    step_number=5,
    local_path="/tmp/screenshot.png",
    upload_to_s3=True
)

# Generate gallery
gallery_path = await screenshot_storage.generate_mission_gallery("rtx5090")
```

### 5. Result Visualization

Results are formatted for multiple interfaces:
- CLI (rich text with emojis)
- Telegram (HTML)
- Slack (Block Kit)
- JSON (programmatic access)

```python
# Format for Telegram
message = ResultVisualizer.create_telegram_message(result)

# Format for Slack
blocks = ResultVisualizer.create_slack_message(result)

# Format for CLI
output = ResultVisualizer.format_price_comparison(result, format_type="markdown")
```

## Integration with Orchestrator

The Orchestrator now recognizes browser-related intents and routes them to the BrowserAgent:

```python
# Intent classification
if intent.intent_type == IntentType.BROWSER:
    return await self._handle_browser_mission(user_input, intent)
```

Example user queries that trigger browser missions:
- "Find the best price for RTX 5090"
- "Check stock for PS5 Pro"
- "Compare iPhone 16 prices"
- "Where can I buy XYZ cheapest?"

## Configuration

Add to `profile.yaml`:

```yaml
browser:
  headless: false  # Set to true for production
  timeout: 30000
  viewport_width: 1920
  viewport_height: 1080
  profile_dir: "~/.octopos/browser_profiles"
  persist_cookies: true
  nova_act_model: "amazon.nova-pro-v1:0"
  max_steps_per_mission: 20

aws:
  s3_bucket_name: "octopos-screenshots"
```

## Usage Examples

### 1. Simple Price Check

```python
from src.specialist import create_browser_agent

agent = create_browser_agent()

result = await agent.compare_prices(
    mission_id="rtx5090_check",
    product_name="RTX 5090",
    sites=["amazon.com", "newegg.com"]
)

print(f"Best price: ${result.best_option.price} at {result.best_option.site_name}")
```

### 2. Stock Availability

```python
result = await agent._handle_stock_check(
    type('Message', (), {
        'payload': {
            'product_name': 'PS5 Pro',
            'sites': ['amazon.com', 'bestbuy.com']
        },
        'user_id': 'user123'
    })()
)
```

### 3. Custom Mission

```python
mission = BrowserMission(
    mission_id="custom_search",
    description="Find cryptocurrency prices",
    starting_url="https://coinbase.com",
    extraction_schema={
        "coin": "string",
        "price_usd": "number",
        "change_24h": "number"
    }
)

result = await agent.execute_mission(mission)
```

## Mission Result Structure

```python
{
    "mission_id": "rtx5090_price_check",
    "success": true,
    "total_steps": 12,
    "total_duration_ms": 45000,
    "final_data": {
        "product_name": "NVIDIA RTX 5090",
        "price": 1999.99,
        "currency": "USD",
        "in_stock": true,
        "site": "newegg.com"
    },
    "steps": [
        {
            "step_number": 1,
            "decision": {
                "action": "goto",
                "target": "https://amazon.com",
                "reason": "Navigate to Amazon to search for RTX 5090"
            },
            "verification": {
                "success": true,
                "actual_outcome": "Successfully navigated to amazon.com"
            }
        },
        ...
    ],
    "reasoning_log": [
        "Starting mission to find RTX 5090 prices",
        "Navigated to Amazon, searching for product...",
        "Found product, extracting price information...",
        ...
    ]
}
```

## Best Practices

1. **Session Reuse**: Reuse sessions across related missions to maintain login states
2. **Step Limits**: Set appropriate `max_steps` to prevent runaway missions
3. **Screenshot Storage**: Enable S3 upload for persistent mission records
4. **Error Handling**: Always check `result.success` before accessing data
5. **Cleanup**: Close sessions after use to free resources

## Troubleshooting

### Common Issues

1. **Playwright Not Installed**
   ```bash
   pip install playwright
   playwright install chromium
   ```

2. **Browser Profile Issues**
   ```python
   # Clear browser profiles
   import shutil
   from pathlib import Path
   profile_dir = Path("~/.octopos/browser_profiles").expanduser()
   shutil.rmtree(profile_dir)
   ```

3. **Mission Timeouts**
   - Increase `timeout` in config
   - Reduce `max_steps_per_mission`
   - Check site availability

## Future Enhancements

- **Parallel Site Checking**: Visit multiple sites concurrently
- **Price History Tracking**: Store historical prices in LanceDB
- **Alert System**: Notify when prices drop below threshold
- **Auto-Purchase**: Supervisor approval for automated purchasing
- **CAPTCHA Handling**: Enhanced bot detection evasion

## Security Considerations

1. **Credentials**: Never hardcode credentials; use secure credential storage
2. **Rate Limiting**: Respect site rate limits to avoid blocking
3. **Data Privacy**: Screenshots may contain sensitive information
4. **Supervisor Approval**: Enable for any purchase or sensitive actions

## API Reference

### BrowserAgent

- `execute_mission(mission: BrowserMission) -> MissionResult`
- `compare_prices(mission_id, product_name, sites, user_id) -> ComparisonResult`
- `get_mission_status(mission_id) -> Dict[str, Any]`

### NovaActDriver

- `run_mission(mission_id, initial_url, mission_context, user_id) -> MissionResult`
- `execute_step(session_id, mission_context) -> MissionStep`
- `abort_mission(mission_id) -> bool`

### SessionManager

- `create_session(user_id, mission_id, metadata) -> SessionInfo`
- `get_page(session_id) -> Page`
- `take_snapshot(session_id) -> BrowserSnapshot`
- `close_session(session_id, save_state) -> bool`

### ScreenshotStorage

- `store_screenshot(mission_id, step_number, local_path) -> ScreenshotMetadata`
- `get_mission_screenshots(mission_id) -> List[ScreenshotMetadata]`
- `generate_mission_gallery(mission_id) -> str`

---

**Note**: This feature requires AWS Bedrock access with Nova Pro model enabled, and Playwright browser binaries installed.
