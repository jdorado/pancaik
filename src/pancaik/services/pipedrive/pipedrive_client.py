"""
Pipedrive API Client

This module provides a comprehensive client for interacting with the Pipedrive REST API v2.
It handles authentication, rate limiting, error handling, and provides methods for all
major Pipedrive operations including deals, contacts, organizations, activities, and pipelines.

Official API Documentation: https://developers.pipedrive.com/docs/api/v2
"""

import json
import time
from typing import Any, Dict, List, Optional

import requests

from ...core.config import logger
from ...utils.ai_router import create_langchain_tool


class PipedriveClient:
    """
    Synchronous client for Pipedrive API v2 operations compatible with LangChain tools.

    Handles authentication, rate limiting, and provides methods for:
    - Deals management
    - Contacts (Persons) management
    - Organizations management
    - Activities management
    - Pipelines and stages management
    - Users management
    - Bulk operations
    - Cache-friendly bulk data loading
    """

    def __init__(self, api_token: str, domain: str = "api.pipedrive.com"):
        """
        Initialize Pipedrive client.

        Args:
            api_token: Pipedrive API token
            domain: Pipedrive API domain (default: api.pipedrive.com)
        """
        self.api_token = api_token
        self.base_url = f"https://{domain}/api/v2"  # Updated to v2
        self.session = requests.Session()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.session.close()

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make authenticated request to Pipedrive API v2.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            data: Request body data

        Returns:
            API response data

        Raises:
            Exception: If API request fails
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        # Add API token to params
        if not params:
            params = {}
        params["api_token"] = self.api_token

        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        try:
            logger.debug(f"Pipedrive API v2 {method} {url}")

            response = self.session.request(method=method, url=url, params=params, json=data, headers=headers)

            if response.status_code == 429:  # Rate limit
                logger.warning("Pipedrive API rate limit hit, waiting...")
                time.sleep(2)
                return self._make_request(method, endpoint, params, data)

            response_data = response.json()

            if not response_data.get("success", False):
                error_msg = response_data.get("error", f"HTTP {response.status_code}")
                logger.error(f"Pipedrive API v2 error: {error_msg}")
                raise Exception(f"Pipedrive API v2 error: {error_msg}")

            logger.debug(f"Pipedrive API v2 response: {response.status_code}")
            return response_data

        except requests.RequestException as e:
            logger.error(f"Pipedrive API v2 request failed: {str(e)}")
            raise Exception(f"Pipedrive API v2 request failed: {str(e)}")

    def _make_v1_request(self, endpoint: str) -> Dict[str, Any]:
        """
        Make authenticated request to Pipedrive API v1 for legacy endpoints.

        Args:
            endpoint: API endpoint (without base URL)

        Returns:
            API response data

        Raises:
            Exception: If API request fails
        """
        url = f"https://api.pipedrive.com/v1/{endpoint.lstrip('/')}"
        params = {"api_token": self.api_token}

        try:
            logger.debug(f"Pipedrive API v1 GET {url}")

            response = self.session.request(method="GET", url=url, params=params, headers={"Accept": "application/json"})

            if response.status_code == 429:  # Rate limit
                logger.warning("Pipedrive API rate limit hit, waiting...")
                time.sleep(2)
                return self._make_v1_request(endpoint)

            response_data = response.json()

            if not response_data.get("success", False):
                error_msg = response_data.get("error", f"HTTP {response.status_code}")
                logger.error(f"Pipedrive API v1 error: {error_msg}")
                raise Exception(f"Pipedrive API v1 error: {error_msg}")

            logger.debug(f"Pipedrive API v1 response: {response.status_code}")
            return response_data

        except requests.RequestException as e:
            logger.error(f"Pipedrive API v1 request failed: {str(e)}")
            raise Exception(f"Pipedrive API v1 request failed: {str(e)}")

    # DEALS METHODS

    def get_deals(
        self,
        status: Optional[str] = None,
        stage_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        person_id: Optional[int] = None,
        org_id: Optional[int] = None,
        pipeline_id: Optional[int] = None,
        filter_id: Optional[int] = None,
        ids: Optional[List[int]] = None,
        limit: int = 1,
        cursor: Optional[str] = None,
    ) -> str:
        """
        Get deals from Pipedrive CRM with optional filtering.

        Args:
            status: Deal status filter ('open', 'won', 'lost', 'deleted', 'all_not_deleted')
            stage_id: Filter by specific stage ID (numeric ID, not stage name)
            owner_id: Filter by deal owner/user ID
            person_id: Filter by associated person ID
            org_id: Filter by associated organization ID
            pipeline_id: Filter by pipeline ID
            filter_id: Filter by Pipedrive filter ID
            ids: List of deal IDs to filter (comma-separated in API)
            limit: Maximum number of deals to return (default: 100)
            cursor: Cursor for pagination

        Returns:
            JSON string with deal data and metadata
        """
        params = {"limit": limit}
        if status:
            params["status"] = status
        if stage_id:
            params["stage_id"] = stage_id
        if owner_id:
            params["owner_id"] = owner_id
        if person_id:
            params["person_id"] = person_id
        if org_id:
            params["org_id"] = org_id
        if pipeline_id:
            params["pipeline_id"] = pipeline_id
        if filter_id:
            params["filter_id"] = filter_id
        if ids:
            if isinstance(ids, str):
                params["ids"] = ids
            elif isinstance(ids, list):
                params["ids"] = ids
            else:
                params["ids"] = ",".join(str(i) for i in ids)
        if cursor:
            params["cursor"] = cursor

        try:
            response = self._make_request("GET", "deals", params=params)

            # Format for LangChain tool usage
            deals = response.get("data", [])

            result = {
                "success": True,
                "total_deals": len(deals),
                "deals": deals[:limit],  # Ensure we don't exceed limit
                "filters_applied": {
                    "status": status,
                    "stage_id": stage_id,
                    "owner_id": owner_id,
                    "person_id": person_id,
                    "org_id": org_id,
                    "pipeline_id": pipeline_id,
                    "filter_id": filter_id,
                    "ids": ids,
                    "limit": limit,
                },
            }

            logger.info(f"Retrieved {len(deals)} deals from Pipedrive")
            return json.dumps(result, indent=2)

        except Exception as e:
            # Return error as JSON string for tool usage
            error_result = {"success": False, "error": str(e), "message": "Failed to retrieve deals from Pipedrive"}
            logger.error(f"Failed to get deals: {str(e)}")
            return json.dumps(error_result, indent=2)

    def get_deal(self, deal_id: int) -> Dict[str, Any]:
        """Get specific deal by ID."""
        response = self._make_request("GET", f"deals/{deal_id}")
        return response.get("data", {})

    def create_deal(self, deal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new deal."""
        response = self._make_request("POST", "deals", data=deal_data)
        return response.get("data", {})

    def update_deal(self, deal_id: int, deal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing deal using PATCH method (v2 change)."""
        response = self._make_request("PATCH", f"deals/{deal_id}", data=deal_data)
        return response.get("data", {})

    def delete_deal(self, deal_id: int) -> bool:
        """Delete deal."""
        response = self._make_request("DELETE", f"deals/{deal_id}")
        return response.get("success", False)

    def move_deal(self, deal_id: int, stage_id: int) -> Dict[str, Any]:
        """Move deal to different stage."""
        data = {"stage_id": stage_id}
        return self.update_deal(deal_id, data)

    # CONTACTS (PERSONS) METHODS

    def get_persons(
        self, person_id: Optional[int] = None, org_id: Optional[int] = None, limit: int = 100, cursor: Optional[str] = None
    ) -> str:
        """
        Get persons/contacts from Pipedrive CRM with optional filtering.

        Args:
            person_id: Get specific person by ID (if provided, returns single person)
            org_id: Filter by associated organization ID
            limit: Maximum number of persons to return (default: 100)
            cursor: Cursor for pagination

        Returns:
            JSON string with person data and metadata
        """
        try:
            # If person_id is provided, get single person
            if person_id:
                response = self._make_request("GET", f"persons/{person_id}")
                person_data = response.get("data", {})

                result = {
                    "success": True,
                    "total_persons": 1 if person_data else 0,
                    "persons": [person_data] if person_data else [],
                    "filters_applied": {"person_id": person_id},
                }
            else:
                # Get multiple persons with filtering
                params = {"limit": limit}
                if org_id:
                    params["org_id"] = org_id
                if cursor:
                    params["cursor"] = cursor

                response = self._make_request("GET", "persons", params=params)
                persons = response.get("data", [])

                result = {
                    "success": True,
                    "total_persons": len(persons),
                    "persons": persons[:limit],  # Ensure we don't exceed limit
                    "filters_applied": {"org_id": org_id, "limit": limit},
                }

            logger.info(f"Retrieved {result['total_persons']} persons from Pipedrive")
            return json.dumps(result, indent=2)

        except Exception as e:
            # Return error as JSON string for tool usage
            error_result = {"success": False, "error": str(e), "message": "Failed to retrieve persons from Pipedrive"}
            logger.error(f"Failed to get persons: {str(e)}")
            return json.dumps(error_result, indent=2)

    def get_person(self, person_id: int) -> Dict[str, Any]:
        """Get specific person by ID."""
        response = self._make_request("GET", f"persons/{person_id}")
        return response.get("data", {})

    def create_person(self, person_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new person/contact."""
        response = self._make_request("POST", "persons", data=person_data)
        return response.get("data", {})

    def update_person(self, person_id: int, person_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing person using PATCH method (v2 change)."""
        response = self._make_request("PATCH", f"persons/{person_id}", data=person_data)
        return response.get("data", {})

    def delete_person(self, person_id: int) -> bool:
        """Delete person."""
        response = self._make_request("DELETE", f"persons/{person_id}")
        return response.get("success", False)

    def search_persons(self, term: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search persons by name or email."""
        params = {"term": term, "limit": limit}
        response = self._make_request("GET", "persons/search", params=params)
        return response.get("data", {}).get("items", [])

    # ORGANIZATIONS METHODS

    def get_organizations(self, limit: int = 100, cursor: Optional[str] = None) -> Dict[str, Any]:
        """Get all organizations using v2 API with cursor pagination."""
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        response = self._make_request("GET", "organizations", params=params)
        return response

    def get_organization(self, org_id: int) -> Dict[str, Any]:
        """Get specific organization by ID."""
        response = self._make_request("GET", f"organizations/{org_id}")
        return response.get("data", {})

    def create_organization(self, org_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new organization."""
        response = self._make_request("POST", "organizations", data=org_data)
        return response.get("data", {})

    def update_organization(self, org_id: int, org_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing organization using PATCH method (v2 change)."""
        response = self._make_request("PATCH", f"organizations/{org_id}", data=org_data)
        return response.get("data", {})

    def delete_organization(self, org_id: int) -> bool:
        """Delete organization."""
        response = self._make_request("DELETE", f"organizations/{org_id}")
        return response.get("success", False)

    def search_organizations(self, term: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search organizations by name."""
        params = {"term": term, "limit": limit}
        response = self._make_request("GET", "organizations/search", params=params)
        return response.get("data", {}).get("items", [])

    # ACTIVITIES METHODS

    def get_activities(
        self,
        deal_id: Optional[int] = None,
        person_id: Optional[int] = None,
        org_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        filter_id: Optional[int] = None,
        sort_by: Optional[str] = "due_date",
        sort_direction: Optional[str] = "asc",
        limit: int = 1,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get activities with optional filtering using v2 API.

        Args:
            deal_id: Filter by deal ID
            person_id: Filter by person ID
            org_id: Filter by organization ID
            start_date: Filter by start date (YYYY-MM-DD)
            end_date: Filter by end date (YYYY-MM-DD)
            filter_id: Filter by Pipedrive filter ID
            sort_by: Sort by field
            sort_direction: Sort direction
            limit: Maximum number of activities to return (default: 100)
            cursor: Cursor for pagination

        Returns:
            Dictionary with activity data and metadata
        """
        params = {"limit": limit}
        if deal_id:
            params["deal_id"] = deal_id
        if person_id:
            params["person_id"] = person_id
        if org_id:
            params["org_id"] = org_id
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if filter_id:
            params["filter_id"] = filter_id
        if sort_by:
            params["sort_by"] = sort_by
        if sort_direction:
            params["sort_direction"] = sort_direction
        if cursor:
            params["cursor"] = cursor

        response = self._make_request("GET", "activities", params=params)
        return response

    def get_activity(self, activity_id: int) -> Dict[str, Any]:
        """Get specific activity by ID."""
        response = self._make_request("GET", f"activities/{activity_id}")
        return response.get("data", {})

    def create_activity(self, activity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new activity."""
        response = self._make_request("POST", "activities", data=activity_data)
        return response.get("data", {})

    def update_activity(self, activity_id: int, activity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing activity using PATCH method (v2 change)."""
        response = self._make_request("PATCH", f"activities/{activity_id}", data=activity_data)
        return response.get("data", {})

    def delete_activity(self, activity_id: int) -> bool:
        """Delete activity."""
        response = self._make_request("DELETE", f"activities/{activity_id}")
        return response.get("success", False)

    def mark_activity_done(self, activity_id: int) -> Dict[str, Any]:
        """Mark activity as done."""
        data = {"done": True}  # v2 uses boolean instead of 1/0
        return self.update_activity(activity_id, data)

    # PIPELINES AND STAGES METHODS

    def get_pipelines(self, limit: int = 100, cursor: Optional[str] = None) -> Dict[str, Any]:
        """Get all pipelines using v2 API."""
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        response = self._make_request("GET", "pipelines", params=params)
        return response

    def get_pipeline(self, pipeline_id: int) -> Dict[str, Any]:
        """Get specific pipeline by ID."""
        response = self._make_request("GET", f"pipelines/{pipeline_id}")
        return response.get("data", {})

    def get_stages(self, pipeline_id: Optional[int] = None, limit: int = 100, cursor: Optional[str] = None) -> Dict[str, Any]:
        """Get all stages, optionally filtered by pipeline using v2 API."""
        params = {"limit": limit}
        if pipeline_id:
            params["pipeline_id"] = pipeline_id
        if cursor:
            params["cursor"] = cursor

        response = self._make_request("GET", "stages", params=params)
        return response

    def get_stage(self, stage_id: int) -> Dict[str, Any]:
        """Get specific stage by ID."""
        response = self._make_request("GET", f"stages/{stage_id}")
        return response.get("data", {})

    # UTILITY METHODS

    def get_users(self) -> List[Dict[str, Any]]:
        """Get all users in the account."""
        # Users endpoint uses v1 API
        response = self._make_v1_request("users")
        return response.get("data", [])

    # CACHE-FRIENDLY BULK METHODS

    def get_all_cache_data(self) -> Dict[str, Any]:
        """
        Get all essential cache data for optimal performance.

        Returns:
            Dictionary with all cached reference data
        """
        cache_results = {}

        # Get core cache data
        cache_items = {
            "pipelines": lambda: self.get_all_paginated("get_pipelines"),
            "stages": lambda: self.get_all_paginated("get_stages"),
            "users": lambda: self.get_users(),
        }

        for key, func in cache_items.items():
            try:
                cache_results[key] = func()
                logger.debug(f"Cached {key}: {len(cache_results[key])} items")
            except Exception as e:
                logger.warning(f"Failed to cache {key}: {str(e)}")
                cache_results[key] = []

        return cache_results

    def get_essential_cache_data(self) -> Dict[str, Any]:
        """
        Get only the most essential cache data for basic operations.

        Returns:
            Dictionary with core cached reference data
        """
        cache_results = {}

        # Get only essential cache data
        essential_items = {
            "pipelines": lambda: self.get_all_paginated("get_pipelines"),
            "stages": lambda: self.get_all_paginated("get_stages"),
            "users": lambda: self.get_users(),
        }

        for key, func in essential_items.items():
            try:
                cache_results[key] = func()
                logger.debug(f"Cached {key}: {len(cache_results[key])} items")
            except Exception as e:
                logger.warning(f"Failed to cache {key}: {str(e)}")
                cache_results[key] = []

        return cache_results

    # PAGINATION HELPER

    def get_all_paginated(self, method_name: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Helper method to get all items using cursor-based pagination (v2).

        Args:
            method_name: Name of the method to call (e.g., 'get_deals')
            **kwargs: Additional arguments for the method

        Returns:
            List of all items across all pages
        """
        all_items = []
        cursor = None
        method = getattr(self, method_name)

        while True:
            if cursor:
                kwargs["cursor"] = cursor

            response = method(**kwargs)

            # v2 API structure
            data = response.get("data", [])
            if not data:
                break

            all_items.extend(data)

            # Check for next cursor
            additional_data = response.get("additional_data", {})
            pagination = additional_data.get("pagination", {})
            cursor = pagination.get("next_cursor")

            if not cursor:
                break

        return all_items

    # BULK OPERATIONS

    def bulk_update_deals(self, updates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Bulk update multiple deals.

        Args:
            updates: List of dicts with 'id' and update data

        Returns:
            List of update results
        """
        results = []
        for update in updates:
            deal_id = update.pop("id")
            try:
                result = self.update_deal(deal_id, update)
                results.append({"id": deal_id, "success": True, "data": result})
            except Exception as e:
                results.append({"id": deal_id, "success": False, "error": str(e)})

        return results

    def bulk_create_persons(self, persons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Bulk create multiple persons.

        Args:
            persons: List of person data dicts

        Returns:
            List of creation results
        """
        results = []
        for person_data in persons:
            try:
                result = self.create_person(person_data)
                results.append({"success": True, "data": result})
            except Exception as e:
                results.append({"success": False, "error": str(e), "data": person_data})

        return results

    # REPORTS AND ANALYTICS

    def get_deals_timeline(self, start_date: str, end_date: str, interval: str = "day") -> Dict[str, Any]:
        """
        Get deals timeline for reporting.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Interval (day, week, month)

        Returns:
            Timeline data
        """
        params = {"start_date": start_date, "end_date": end_date, "interval": interval}
        response = self._make_request("GET", "deals/timeline", params=params)
        return response.get("data", {})

    def get_deals_summary(self, owner_id: Optional[int] = None) -> Dict[str, Any]:
        """Get deals summary/statistics."""
        params = {}
        if owner_id:  # v2 uses owner_id instead of user_id
            params["owner_id"] = owner_id

        response = self._make_request("GET", "deals/summary", params=params)
        return response.get("data", {})

    # LANGCHAIN TOOL CREATION HELPERS

    def create_tools(self) -> List:
        """
        Create LangChain tools from the client methods.

        Returns:
            List of LangChain tools
        """
        tools = []

        # Create get_deals tool - only pass description, not name
        get_deals_tool = create_langchain_tool(
            func=self.get_deals,
            description="Get deals from Pipedrive CRM with optional filtering by status ('open', 'won', 'lost', 'deleted'), stage_id (numeric), owner_id, person_id, org_id, pipeline_id, filter_id (Pipedrive filter ID), or ids[] (list of deal IDs)",
        )
        tools.append(get_deals_tool)

        # Create get_persons tool - only pass description, not name
        get_persons_tool = create_langchain_tool(
            func=self.get_persons,
            description="Get persons/contacts from Pipedrive CRM with optional filtering by person_id (specific person) or org_id (organization ID)",
        )
        tools.append(get_persons_tool)

        # Create update_deal tool - allows updating a deal's fields such as pipeline_id and stage_id
        update_deal_tool = create_langchain_tool(
            func=self.update_deal,
            description="Update an existing deal in Pipedrive CRM. Provide deal_id and the fields to update (e.g., pipeline_id, stage_id, value, title).",
        )
        tools.append(update_deal_tool)

        # Create create_activity tool - allows adding an activity to a deal
        create_activity_tool = create_langchain_tool(
            func=self.create_activity,
            description=(
                "Add an activity to a deal in Pipedrive CRM (v2 API). Provide activity_data with at least: "
                "deal_id (required), subject (required), type (required), due_date (string), due_time (string), "
                "done (boolean: finished or scheduled), note (body/description). Uses POST /api/v2/activities."
            ),
        )
        tools.append(create_activity_tool)

        # Create get_activities tool - allows retrieving activities with due_date filtering
        get_activities_tool = create_langchain_tool(
            func=self.get_activities,
            description="Get activities from Pipedrive CRM with optional filtering by deal_id, person_id, org_id, start_date, end_date, filter_id, limit. Use this tool to get activities that are due soon, due today, or overdue by filtering on due_date. If the user asks for 'activities due', use this tool with due_date filters."
        )
        tools.append(get_activities_tool)

        # Create update_activity tool - allows updating an activity's fields
        update_activity_tool = create_langchain_tool(
            func=self.update_activity,
            description="Update an existing activity in Pipedrive CRM. Provide activity_id and the fields to update (e.g., subject, type, due_date, done, note). Uses PATCH /api/v2/activities/{activity_id}.",
        )
        tools.append(update_activity_tool)

        return tools
