"""
Result Visualizer for Browser Missions

Formats browser mission results for various output interfaces:
- CLI (rich text with colors)
- Telegram (markdown/html)
- Slack (markdown)
- JSON (for programmatic use)

Author: octopOS Team
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .nova_act_driver import MissionResult
from ...utils.logger import get_logger

logger = get_logger()


class ResultVisualizer:
    """
    Visualizes browser mission results in various formats.
    """
    
    # Emoji mappings
    EMOJI = {
        "success": "✅",
        "error": "❌",
        "warning": "⚠️",
        "info": "ℹ️",
        "search": "🔍",
        "price": "💰",
        "cart": "🛒",
        "browser": "🌐",
        "best": "🏆",
        "money": "💵",
        "clock": "⏱️",
        "step": "👣",
        "photo": "📸"
    }
    
    @staticmethod
    def format_price_comparison(
        result: Dict[str, Any],
        format_type: str = "markdown",
        include_screenshots: bool = True
    ) -> str:
        """
        Format price comparison result for display.
        
        Args:
            result: Dict with comparison data
            format_type: Output format ("markdown", "html", "text", "json")
            include_screenshots: Whether to include screenshot references
            
        Returns:
            Formatted string
        """
        
        if format_type == "json":
            return json.dumps(result.to_dict(), indent=2, default=str)
        
        lines = []
        
        # Header
        if format_type == "html":
            lines.append(f"<h1>{ResultVisualizer.EMOJI['best']} Price Comparison Result</h1>")
        else:
            lines.append(f"{ResultVisualizer.EMOJI['best']} **Price Comparison Result**")
            lines.append("")
        
        # Best option highlight
        if result.best_option:
            best = result.best_option if isinstance(result.best_option, dict) else asdict(result.best_option)
            
            if format_type == "html":
                lines.append("<div class='best-deal' style='background: #d4edda; padding: 15px; border-radius: 8px; margin: 10px 0;'>"
                           f"<h2>🏆 Best Deal: {best.get('site_name', 'Unknown')}</h2>"
                           f"<p style='font-size: 24px; font-weight: bold; color: #155724;'>"
                           f"${best.get('price', 0):.2f}</p>"
                           f"<p>{result.recommendation}</p>"
                           "</div>")
            else:
                price = best.get('price', 0)
                site = best.get('site_name', 'Unknown')
                lines.append(f"{ResultVisualizer.EMOJI['best']} **Best Deal: {site}**")
                lines.append(f"{ResultVisualizer.EMOJI['money']} **${price:.2f}**")
                lines.append("")
                lines.append(f"*{result.recommendation}*")
                lines.append("")
        
        # All options table
        if result.all_options:
            valid_options = [
                opt for opt in result.all_options
                if (opt.get('success') if isinstance(opt, dict) else opt.success)
            ]
            
            if valid_options:
                if format_type == "html":
                    lines.append("<h3>All Options</h3>")
                    lines.append("<table style='width: 100%; border-collapse: collapse;'>")
                    lines.append("<tr style='background: #f8f9fa;'>"
                               "<th style='padding: 10px; text-align: left;'>Site</th>"
                               "<th style='padding: 10px; text-align: left;'>Price</th>"
                               "<th style='padding: 10px; text-align: left;'>Status</th>"
                               "</tr>")
                    
                    for opt in sorted(valid_options, key=lambda x: x.get('price', float('inf')) if isinstance(x, dict) else (x.price or float('inf'))):
                        if isinstance(opt, dict):
                            site = opt.get('site_name', 'Unknown')
                            price = opt.get('price')
                            success = opt.get('success', False)
                        else:
                            site = opt.site_name
                            price = opt.price
                            success = opt.success
                        
                        is_best = result.best_option and (
                            (isinstance(result.best_option, dict) and result.best_option.get('site_name') == site) or
                            (not isinstance(result.best_option, dict) and result.best_option.site_name == site)
                        )
                        
                        bg_color = "#d4edda" if is_best else "white"
                        price_str = f"${price:.2f}" if price else "N/A"
                        status = "✅ In Stock" if success else "❌ Error"
                        
                        lines.append(f"<tr style='background: {bg_color};'>"
                                   f"<td style='padding: 10px; border-bottom: 1px solid #dee2e6;'>{site}</td>"
                                   f"<td style='padding: 10px; border-bottom: 1px solid #dee2e6; font-weight: bold;'>{price_str}</td>"
                                   f"<td style='padding: 10px; border-bottom: 1px solid #dee2e6;'>{status}</td>"
                                   "</tr>")
                    
                    lines.append("</table>")
                else:
                    lines.append("**All Options Found:**")
                    lines.append("")
                    
                    for opt in sorted(valid_options, key=lambda x: x.get('price', float('inf')) if isinstance(x, dict) else (x.price or float('inf'))):
                        if isinstance(opt, dict):
                            site = opt.get('site_name', 'Unknown')
                            price = opt.get('price')
                            success = opt.get('success', False)
                        else:
                            site = opt.site_name
                            price = opt.price
                            success = opt.success
                        
                        is_best = result.best_option and (
                            (isinstance(result.best_option, dict) and result.best_option.get('site_name') == site) or
                            (not isinstance(result.best_option, dict) and result.best_option.site_name == site)
                        )
                        
                        price_str = f"${price:.2f}" if price else "N/A"
                        best_marker = f" {ResultVisualizer.EMOJI['best']}" if is_best else ""
                        
                        lines.append(f"- {site}: **{price_str}**{best_marker}")
                    
                    lines.append("")
        
        # Screenshots
        if include_screenshots and result.all_options:
            screenshot_lines = []
            for opt in result.all_options:
                if isinstance(opt, dict):
                    screenshot = opt.get('screenshot_path')
                    site = opt.get('site_name', 'Unknown')
                else:
                    screenshot = opt.screenshot_path
                    site = opt.site_name
                
                if screenshot:
                    if format_type == "html":
                        screenshot_lines.append(
                            f"<div style='margin: 10px 0;'>"
                            f"<p><strong>{site}:</strong></p>"
                            f"<img src='file://{screenshot}' style='max-width: 100%; border: 1px solid #ddd; border-radius: 4px;'>"
                            f"</div>"
                        )
                    else:
                        screenshot_lines.append(f"{ResultVisualizer.EMOJI['photo']} {site}: `{screenshot}`")
            
            if screenshot_lines:
                if format_type == "html":
                    lines.append("<h3>Screenshots</h3>")
                    lines.extend(screenshot_lines)
                else:
                    lines.append(f"{ResultVisualizer.EMOJI['photo']} **Screenshots:**")
                    lines.extend(screenshot_lines)
                    lines.append("")
        
        # Price range
        if result.price_range and result.price_range[0] and result.price_range[1]:
            min_price, max_price = result.price_range
            savings = max_price - min_price
            
            if format_type == "html":
                lines.append(f"<p style='color: #666; font-size: 14px;'>"
                           f"Price range: ${min_price:.2f} - ${max_price:.2f} "
                           f"(Save up to ${savings:.2f})</p>")
            else:
                lines.append(f"💡 Price range: ${min_price:.2f} - ${max_price:.2f} (Save up to ${savings:.2f})")
        
        # Footer
        if format_type == "html":
            lines.append("<hr style='margin-top: 20px;'>"
                       f"<p style='color: #999; font-size: 12px;'>Mission ID: {result.mission_id}</p>")
        else:
            lines.append("")
            lines.append(f"_Mission ID: `{result.mission_id}`_")
        
        if format_type == "html":
            return "\n".join(lines)
        else:
            return "\n".join(lines)
    
    @staticmethod
    def format_mission_result(
        result: Union[MissionResult, Dict[str, Any]],
        format_type: str = "markdown",
        verbose: bool = False
    ) -> str:
        """
        Format mission result with step-by-step breakdown.
        
        Args:
            result: MissionResult or dict
            format_type: Output format
            verbose: Include detailed step information
            
        Returns:
            Formatted string
        """
        if isinstance(result, dict):
            from .nova_act_driver import MissionResult
            result = MissionResult(
                mission_id=result.get("mission_id", "unknown"),
                success=result.get("success", False),
                steps=[],  # Would need to parse steps
                final_data=result.get("final_data"),
                reasoning_log=result.get("reasoning_log", []),
                total_steps=result.get("total_steps", 0),
                total_duration_ms=result.get("total_duration_ms", 0),
                session_id=result.get("session_id")
            )
        
        if format_type == "json":
            return json.dumps(result.to_dict(), indent=2, default=str)
        
        lines = []
        
        # Status header
        status_emoji = ResultVisualizer.EMOJI["success"] if result.success else ResultVisualizer.EMOJI["error"]
        status_text = "Success" if result.success else "Failed"
        
        if format_type == "html":
            status_color = "#28a745" if result.success else "#dc3545"
            lines.append(f"<h1><span style='color: {status_color};'>{status_emoji} {status_text}</span></h1>")
        else:
            lines.append(f"{status_emoji} **Mission {status_text}**")
            lines.append("")
        
        # Summary
        duration_sec = result.total_duration_ms / 1000
        
        if format_type == "html":
            lines.append("<div style='background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0;'>"
                       f"<p><strong>Mission ID:</strong> {result.mission_id}</p>"
                       f"<p><strong>Steps:</strong> {len(result.steps)}</p>"
                       f"<p><strong>Duration:</strong> {duration_sec:.1f}s</p>"
                       "</div>")
        else:
            lines.append(f"{ResultVisualizer.EMOJI['browser']} Mission: `{result.mission_id}`")
            lines.append(f"{ResultVisualizer.EMOJI['step']} Steps: {len(result.steps)}")
            lines.append(f"{ResultVisualizer.EMOJI['clock']} Duration: {duration_sec:.1f}s")
            lines.append("")
        
        # Final data
        if result.final_data:
            if format_type == "html":
                lines.append("<h3>Extracted Data</h3>")
                lines.append(f"<pre style='background: #f8f9fa; padding: 10px; border-radius: 4px; overflow-x: auto;'>"
                           f"{json.dumps(result.final_data, indent=2)}</pre>")
            else:
                lines.append("**Extracted Data:**")
                lines.append(f"```json\n{json.dumps(result.final_data, indent=2)}\n```")
                lines.append("")
        
        # Steps breakdown (if verbose)
        if verbose and result.steps:
            if format_type == "html":
                lines.append("<h3>Step-by-Step</h3>")
                lines.append("<ol>")
                
                for step in result.steps:
                    decision = step.decision
                    lines.append(f"<li style='margin: 10px 0;'>"
                               f"<strong>{decision.action.value}</strong> "
                               f"<span style='color: #666;'>({step.duration_ms:.0f}ms)</span><br>"
                               f"<span style='color: #555;'>{decision.reason[:100]}...</span>")
                    
                    if step.verification:
                        status = "✅" if step.verification.success else "❌"
                        lines.append(f"<br><span>{status} {step.verification.actual_outcome[:100]}...</span>")
                    
                    lines.append("</li>")
                
                lines.append("</ol>")
            else:
                lines.append("**Step-by-Step Breakdown:**")
                lines.append("")
                
                for step in result.steps:
                    decision = step.decision
                    lines.append(f"**Step {step.step_number}:** {decision.action.value}")
                    lines.append(f"- Reason: {decision.reason[:80]}...")
                    lines.append(f"- Duration: {step.duration_ms:.0f}ms")
                    
                    if step.verification:
                        emoji = ResultVisualizer.EMOJI["success"] if step.verification.success else ResultVisualizer.EMOJI["error"]
                        lines.append(f"- Result: {emoji} {step.verification.actual_outcome[:80]}...")
                    
                    lines.append("")
        
        # Reasoning log
        if result.reasoning_log and not verbose:
            if format_type == "html":
                lines.append("<details><summary>Reasoning Log</summary>")
                lines.append("<ul>")
                for reason in result.reasoning_log:
                    lines.append(f"<li>{reason[:100]}...</li>")
                lines.append("</ul></details>")
            else:
                lines.append("**Reasoning Summary:**")
                for reason in result.reasoning_log[:3]:  # First 3 entries
                    lines.append(f"- {reason[:80]}...")
                if len(result.reasoning_log) > 3:
                    lines.append(f"- ... and {len(result.reasoning_log) - 3} more")
                lines.append("")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_stock_check(
        results: List[Dict[str, Any]],
        product_name: str,
        format_type: str = "markdown"
    ) -> str:
        """Format stock check results."""
        
        in_stock = [r for r in results if r.get("in_stock")]
        out_of_stock = [r for r in results if not r.get("in_stock")]
        
        if format_type == "json":
            return json.dumps({
                "product": product_name,
                "in_stock_count": len(in_stock),
                "out_of_stock_count": len(out_of_stock),
                "results": results
            }, indent=2, default=str)
        
        lines = []
        
        # Header
        if format_type == "html":
            lines.append(f"<h1>{ResultVisualizer.EMOJI['search']} Stock Check: {product_name}</h1>")
        else:
            lines.append(f"{ResultVisualizer.EMOJI['search']} **Stock Check: {product_name}**")
            lines.append("")
        
        # Summary
        if in_stock:
            if format_type == "html":
                lines.append(f"<div style='background: #d4edda; padding: 15px; border-radius: 8px;'>"
                           f"<h3>✅ In Stock at {len(in_stock)} site(s)</h3>")
            else:
                lines.append(f"{ResultVisualizer.EMOJI['success']} **In Stock at {len(in_stock)} site(s)**")
                lines.append("")
            
            for site in sorted(in_stock, key=lambda x: x.get("price") or float("inf")):
                site_name = site.get("site", "Unknown")
                price = site.get("price")
                details = site.get("details", {})
                
                if format_type == "html":
                    price_str = f"${price:.2f}" if price else "Price unavailable"
                    lines.append(f"<p><strong>{site_name}:</strong> {price_str}</p>")
                else:
                    price_str = f" - ${price:.2f}" if price else ""
                    lines.append(f"- {site_name}{price_str}")
            
            if format_type == "html":
                lines.append("</div>")
            else:
                lines.append("")
        else:
            if format_type == "html":
                lines.append(f"<div style='background: #f8d7da; padding: 15px; border-radius: 8px;'>"
                           f"<h3>{ResultVisualizer.EMOJI['error']} Out of Stock</h3>"
                           f"<p>Not available at any checked sites.</p>"
                           "</div>")
            else:
                lines.append(f"{ResultVisualizer.EMOJI['error']} **Out of Stock**")
                lines.append(f"'{product_name}' is not available at any checked sites.")
                lines.append("")
        
        # All results table (verbose)
        if format_type == "html":
            lines.append("<h3>All Sites</h3>")
            lines.append("<table style='width: 100%; border-collapse: collapse;'>")
            lines.append("<tr style='background: #f8f9fa;'>"
                       "<th>Site</th><th>Status</th><th>Price</th>"
                       "</tr>")
            
            for site in results:
                site_name = site.get("site", "Unknown")
                in_stock = site.get("in_stock", False)
                price = site.get("price")
                
                status = "✅ In Stock" if in_stock else "❌ Out of Stock"
                price_str = f"${price:.2f}" if price else "N/A"
                bg_color = "#d4edda" if in_stock else "#f8d7da"
                
                lines.append(f"<tr style='background: {bg_color};'>"
                           f"<td style='padding: 8px;'>{site_name}</td>"
                           f"<td style='padding: 8px;'>{status}</td>"
                           f"<td style='padding: 8px;'>{price_str}</td>"
                           "</tr>")
            
            lines.append("</table>")
        
        return "\n".join(lines)
    
    @staticmethod
    def create_telegram_message(result: Dict[str, Any]) -> str:
        """Create Telegram-compatible HTML message."""
        return ResultVisualizer.format_price_comparison(result, format_type="html", include_screenshots=True)
    
    @staticmethod
    def create_slack_message(result: Dict[str, Any]) -> Dict[str, Any]:
        """Create Slack-compatible block kit message."""
        blocks = []
        
        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🏆 Best Price Found: {result.best_option.site_name if result.best_option else 'N/A'}",
                "emoji": True
            }
        })
        
        # Best deal section
        if result.best_option:
            price = result.best_option.price
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*${price:.2f}* at {result.best_option.site_name}\n{result.recommendation}"
                }
            })
        
        # Add divider
        blocks.append({"type": "divider"})
        
        # All options
        if result.all_options:
            options_text = "*All Options:*\n"
            for opt in sorted(result.all_options, key=lambda x: x.price or float('inf')):
                if opt.price:
                    marker = "🏆 " if opt == result.best_option else "• "
                    options_text += f"{marker}{opt.site_name}: ${opt.price:.2f}\n"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": options_text
                }
            })
        
        return {"blocks": blocks}


# Convenience functions
def format_price_comparison(*args, **kwargs) -> str:
    """Convenience function for formatting price comparison."""
    return ResultVisualizer.format_price_comparison(*args, **kwargs)


def format_mission_result(*args, **kwargs) -> str:
    """Convenience function for formatting mission result."""
    return ResultVisualizer.format_mission_result(*args, **kwargs)


def format_stock_check(*args, **kwargs) -> str:
    """Convenience function for formatting stock check."""
    return ResultVisualizer.format_stock_check(*args, **kwargs)
