"""
HubSpot API Client

This module provides a client for interacting with the HubSpot REST API v3.
It handles authentication, rate limiting, error handling, and provides methods for
major HubSpot operations including deals, contacts, and companies.

This client uses a mixed sync/async approach to avoid `asyncio` event loop conflicts
when used with synchronous frameworks like LangChain. The public methods are synchronous
and use the `run_in_new_loop` utility to execute the underlying asynchronous API calls
in a separate thread with a dedicated event loop. This prevents the "Task attached to
a different loop" error that occurs when an `async` tool is called from a sync agent.

Official API Documentation: https://developers.hubspot.com/docs/reference/api
"""

import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
import asyncio

from ...core.config import get_config, logger
from ...core.connections import ConnectionHandler
from ...utils.ai_router import create_langchain_tool
from ...utils.loop_utils import run_in_new_loop


class HubspotClient:
    """
    Client for HubSpot API v3 operations.

    Handles authentication and provides methods for:
    - Deals management
    - Contacts management
    - Companies management
    """

    def __init__(self, connection_id: str, connection_handler: ConnectionHandler):
        """
        Initialize HubSpot client.

        Args:
            connection_id: The ID of the HubSpot connection.
            connection_handler: Instance of ConnectionHandler to manage connection data.
        """
        self.connection_id = connection_id
        self.connection_handler = connection_handler
        self.connection: Optional[Dict[str, Any]] = None
        self.access_token: Optional[str] = None
        self.base_url = "https://api.hubapi.com/crm/v3"
        self.session = requests.Session()
        run_in_new_loop(self._init_client())

    async def _init_client(self):
        self.connection = await self.connection_handler.get_full_connection(self.connection_id)
        if not self.connection:
            raise ValueError(f"HubSpot connection with ID '{self.connection_id}' not found.")

        params = self.connection.get("params", {})
        decrypted_params = self.connection_handler._decrypt_sensitive_fields(params)
        self.connection["params"] = decrypted_params

        self.access_token = decrypted_params.get("access_token")
        self._update_session_headers()

    @classmethod
    def create(cls, connection_id: str, connection_handler: ConnectionHandler) -> "HubspotClient":
        """Create and initialize a new HubspotClient instance."""
        return cls(connection_id, connection_handler)

    def close(self):
        """Closes the request session."""
        self.session.close()

    def _update_session_headers(self):
        """Updates the session headers with the current access token."""
        self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})

    def _is_token_expired(self) -> bool:
        """Check if the HubSpot access token is expired."""
        if not self.connection:
            return False

        params = self.connection.get("params", {})
        expires_at_str = params.get("expires_at")
        if not expires_at_str:
            return False

        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        return datetime.utcnow() >= (expires_at - timedelta(seconds=60))

    async def _refresh_token(self):
        """Refresh the HubSpot access token and update it in the database."""
        if not self.connection:
            raise Exception("Cannot refresh token without a connection.")

        logger.info(f"HubSpot token for connection {self.connection_id} is expiring. Refreshing...")

        params = self.connection.get("params", {})
        refresh_token = params.get("refresh_token")
        if not refresh_token:
            raise Exception("Refresh token not found. Cannot refresh HubSpot token.")

        client_id = get_config("hubspot_client_id")
        client_secret = get_config("hubspot_client_secret")

        token_url = "https://api.hubapi.com/oauth/v1/token"
        payload = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        response = await asyncio.to_thread(requests.post, token_url, data=payload, headers=headers)
        response.raise_for_status()
        token_data = response.json()

        self.access_token = token_data["access_token"]
        new_refresh_token = token_data.get("refresh_token", refresh_token)
        expires_in = token_data["expires_in"]

        self.connection["params"].update(
            {
                "access_token": self.access_token,
                "refresh_token": new_refresh_token,
                "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
            }
        )

        self._update_session_headers()

        connection_id = self.connection.get("_id")
        if connection_id:
            await self.connection_handler.update_connection(str(connection_id), self.connection["params"])

        logger.info(f"Successfully refreshed HubSpot token for connection {self.connection_id}.")

    async def _make_request(
        self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make an authenticated request to the HubSpot API v3, handling token refresh.
        """
        if self._is_token_expired():
            await self._refresh_token()

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        try:
            logger.debug(f"HubSpot API v3 {method} {url}")

            def do_request():
                return self.session.request(method=method, url=url, params=params, json=data, headers=headers)

            response = await asyncio.to_thread(do_request)

            if response.status_code == 429:  # Rate limit
                logger.warning("HubSpot API rate limit hit, waiting...")
                await asyncio.sleep(2)
                return await self._make_request(method, endpoint, params, data)

            response.raise_for_status()

            if response.status_code == 204:  # No Content
                return {"success": True}

            return response.json()

        except requests.RequestException as e:
            error_message = f"HubSpot API v3 request failed: {e.response.text if e.response else str(e)}"
            logger.error(error_message)
            raise Exception(error_message) from e

    # DEALS METHODS

    def get_deals(
        self, limit: int = 100, after: Optional[str] = None, properties: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get deals from HubSpot.
        """
        async def _get_deals():
            params = {"limit": limit}
            if after:
                params["after"] = after
            if properties:
                params["properties"] = ",".join(properties)
            return await self._make_request("GET", "objects/deals", params=params)
        return run_in_new_loop(_get_deals())

    def get_deal(self, deal_id: str, properties: Optional[List[str]] = None, associations: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get a specific deal by its ID.
        """
        async def _get_deal():
            params = {}
            if properties:
                params["properties"] = ",".join(properties)
            if associations:
                params["associations"] = ",".join(associations)
            return await self._make_request("GET", f"objects/deals/{deal_id}", params=params)
        return run_in_new_loop(_get_deal())

    def search_deals(
        self, query: Optional[str] = None, properties: Optional[List[str]] = None, limit: int = 10, after: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search for deals based on a query.
        """
        async def _search_deals():
            data = {"limit": limit, "query": query, "properties": properties or []}
            if after:
                data["after"] = after
            return await self._make_request("POST", "objects/deals/search", data=data)
        return run_in_new_loop(_search_deals())

    def create_deal(
        self, properties: Dict[str, Any], associations: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Create a new deal.
        """
        async def _create_deal():
            data = {"properties": properties}
            if associations:
                data["associations"] = associations
            return await self._make_request("POST", "objects/deals", data=data)
        return run_in_new_loop(_create_deal())

    def update_deal(self, deal_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing deal.
        """
        async def _update_deal():
            return await self._make_request("PATCH", f"objects/deals/{deal_id}", data={"properties": properties})
        return run_in_new_loop(_update_deal())

    def delete_deal(self, deal_id: str) -> Dict[str, Any]:
        """
        Delete a deal.
        """
        async def _delete_deal():
            return await self._make_request("DELETE", f"objects/deals/{deal_id}")
        return run_in_new_loop(_delete_deal())

    # CONTACTS METHODS

    def get_contacts(
        self, limit: int = 100, after: Optional[str] = None, properties: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get contacts from HubSpot.
        """
        async def _get_contacts():
            params = {"limit": limit}
            if after:
                params["after"] = after
            if properties:
                params["properties"] = ",".join(properties)
            return await self._make_request("GET", "objects/contacts", params=params)
        return run_in_new_loop(_get_contacts())

    def get_contact(self, contact_id: str, properties: Optional[List[str]] = None, associations: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get a specific contact by its ID.
        """
        async def _get_contact():
            params = {}
            if properties:
                params["properties"] = ",".join(properties)
            if associations:
                params["associations"] = ",".join(associations)
            return await self._make_request("GET", f"objects/contacts/{contact_id}", params=params)
        return run_in_new_loop(_get_contact())

    def search_contacts(
        self, query: Optional[str] = None, properties: Optional[List[str]] = None, limit: int = 10, after: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search for contacts based on a query.
        """
        async def _search_contacts():
            data = {"limit": limit, "query": query, "properties": properties or []}
            if after:
                data["after"] = after
            return await self._make_request("POST", "objects/contacts/search", data=data)
        return run_in_new_loop(_search_contacts())

    def create_contact(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new contact.
        """
        async def _create_contact():
            return await self._make_request("POST", "objects/contacts", data={"properties": properties})
        return run_in_new_loop(_create_contact())

    def update_contact(self, contact_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing contact.
        """
        async def _update_contact():
            return await self._make_request("PATCH", f"objects/contacts/{contact_id}", data={"properties": properties})
        return run_in_new_loop(_update_contact())

    def delete_contact(self, contact_id: str) -> Dict[str, Any]:
        """
        Delete a contact.
        """
        async def _delete_contact():
            return await self._make_request("DELETE", f"objects/contacts/{contact_id}")
        return run_in_new_loop(_delete_contact())

    # COMPANIES METHODS

    def get_companies(
        self, limit: int = 100, after: Optional[str] = None, properties: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get companies from HubSpot.
        """
        async def _get_companies():
            params = {"limit": limit}
            if after:
                params["after"] = after
            if properties:
                params["properties"] = ",".join(properties)
            return await self._make_request("GET", "objects/companies", params=params)
        return run_in_new_loop(_get_companies())

    def get_company(self, company_id: str, properties: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get a specific company by its ID.
        """
        async def _get_company():
            params = {}
            if properties:
                params["properties"] = ",".join(properties)
            return await self._make_request("GET", f"objects/companies/{company_id}", params=params)
        return run_in_new_loop(_get_company())

    def create_company(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new company.
        """
        async def _create_company():
            return await self._make_request("POST", "objects/companies", data={"properties": properties})
        return run_in_new_loop(_create_company())

    def update_company(self, company_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing company.
        """
        async def _update_company():
            return await self._make_request("PATCH", f"objects/companies/{company_id}", data={"properties": properties})
        return run_in_new_loop(_update_company())

    def delete_company(self, company_id: str) -> Dict[str, Any]:
        """
        Delete a company.
        """
        async def _delete_company():
            return await self._make_request("DELETE", f"objects/companies/{company_id}")
        return run_in_new_loop(_delete_company())

    # TASKS METHODS

    def create_task(
        self, properties: Dict[str, Any], associations: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Create a new task and optionally associate it with other CRM objects.
        """
        async def _create_task():
            data = {"properties": properties}
            if associations:
                data["associations"] = associations
            return await self._make_request("POST", "objects/tasks", data=data)
        return run_in_new_loop(_create_task())

    # DEAL PIPELINES METHODS

    def get_deal_pipelines(self) -> Dict[str, Any]:
        """
        Get all deal pipelines and their stages.
        """
        async def _get_deal_pipelines():
            return await self._make_request("GET", "pipelines/deals")
        return run_in_new_loop(_get_deal_pipelines())

    def get_deal_pipeline(self, pipeline_id: str) -> Dict[str, Any]:
        """
        Get a single deal pipeline by its ID.
        """
        async def _get_deal_pipeline():
            return await self._make_request("GET", f"pipelines/deals/{pipeline_id}")
        return run_in_new_loop(_get_deal_pipeline())

    # PAGINATION HELPER

    def get_all_paginated(self, method_name: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Handles pagination for a given 'get' method (e.g., get_deals).

        Args:
            method_name: The name of the method to call for pagination (e.g., 'get_deals').
            **kwargs: Arguments to pass to the method.

        Returns:
            A list of all items from all pages.
        """
        method = getattr(self, method_name)
        all_results = []
        after = None
        has_more = True

        while has_more:
            kwargs["after"] = after
            response = method(**kwargs)
            results = response.get("results", [])
            all_results.extend(results)

            paging = response.get("paging")
            if paging and paging.get("next"):
                after = paging["next"]["after"]
            else:
                has_more = False

        return all_results

    # LANGCHAIN TOOL CREATION HELPERS

    def create_tools(self) -> List:
        """Create LangChain tools from HubSpot client methods."""
        try:
            from langchain.tools import Tool
        except ImportError as e:
            logger.error("LangChain not installed, cannot create tools. Run 'poetry add langchain'")
            raise e

        tool_list = [
            self.get_deals,
            self.get_deal,
            self.search_deals,
            self.create_deal,
            self.update_deal,
            self.delete_deal,
            self.get_contacts,
            self.get_contact,
            self.search_contacts,
            self.create_contact,
            self.update_contact,
            self.delete_contact,
            self.get_companies,
            self.get_company,
            self.create_company,
            self.update_company,
            self.create_task,
            self.get_deal_pipelines,
            self.get_deal_pipeline,
        ]

        return [create_langchain_tool(func) for func in tool_list] 