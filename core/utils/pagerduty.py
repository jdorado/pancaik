"""PagerDuty async utility for reporting incidents."""
from typing import Optional, Dict, Any
import aiohttp
from datetime import datetime
from pancaik.core.config import logger, get_config

API_ALERT = "https://events.pagerduty.com/v2/enqueue"

async def send_alert(
    event: str,
    dedup_key: Optional[str] = None,
    is_resolve: bool = False,
    details: Optional[Dict[str, Any]] = None,
    severity: str = "warning"
) -> bool:
    """Send an alert to PagerDuty asynchronously.
    
    Args:
        event: Event title/summary
        dedup_key: Optional deduplication key (defaults to event)
        is_resolve: Whether this is resolving a previous alert
        details: Optional additional context/details
        severity: Alert severity level (default: warning)
        
    Returns:
        bool: True if successfully reported, False otherwise
    """
    try:
        # Get PagerDuty config
        pagerduty_key = get_config("pagerduty_key")
        if not pagerduty_key:
            logger.debug(f"PagerDuty key not configured, skipping alert: {event}")
            return True

        summary = f"ALERT: {event}"
        if not is_resolve:
            logger.warning(summary)

        # Check if alerts are disabled
        if get_config("pagerduty_inactive") and not is_resolve:
            logger.info(f"PagerDuty alerts disabled, skipping: {summary}")
            return True

        payload = {
            "summary": event,
            "source": event,
            "severity": severity,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if details:
            payload["custom_details"] = details

        body = {
            "routing_key": pagerduty_key,
            "event_action": "resolve" if is_resolve else "trigger",
            "dedup_key": dedup_key or event,
            "payload": payload
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_ALERT,
                json=body,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 202:
                    action = "resolved" if is_resolve else "triggered"
                    logger.info(f"Successfully {action} PagerDuty alert: {event}")
                    return True
                else:
                    error_body = await response.text()
                    logger.error(f"Failed to send PagerDuty alert. Status: {response.status}, Response: {error_body}")
                    return False

    except Exception as e:
        logger.error(f"Error sending PagerDuty alert: {str(e)}")
        return False 