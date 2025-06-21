"""
HubSpot API Client

This module provides a client for interacting with the HubSpot REST API v3.
It handles authentication, rate limiting, error handling, and provides methods for
major HubSpot operations including deals, contacts, and companies.

Official API Documentation: https://developers.hubspot.com/docs/api/crm/overview
"""

import json
import time
from typing import Any, Dict, List, Optional

import requests

from ...core.config import logger
from ...utils.ai_router import create_langchain_tool


class HubspotClient:
    """
    Client for HubSpot API v3 operations.

    Handles authentication and provides methods for:
    - Deals management
    - Contacts management
    - Companies management
    """

    def __init__(self, access_token: str):
        """
        Initialize HubSpot client.

        Args:
            access_token: HubSpot private app access token.
        """
        self.access_token = access_token
        self.base_url = "https://api.hubapi.com/crm/v3"
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.session.close()

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make an authenticated request to the HubSpot API v3.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            data: Request body data

        Returns:
            API response data

        Raises:
            Exception: If the API request fails
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        try:
            logger.debug(f"HubSpot API v3 {method} {url}")

            response = self.session.request(method=method, url=url, params=params, json=data, headers=headers)

            if response.status_code == 429:  # Rate limit
                logger.warning("HubSpot API rate limit hit, waiting...")
                time.sleep(2)
                return self._make_request(method, endpoint, params, data)

            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

            if response.status_code == 204:  # No Content
                return {"success": True}

            response_data = response.json()
            logger.debug(f"HubSpot API v3 response: {response.status_code}")
            return response_data

        except requests.RequestException as e:
            logger.error(f"HubSpot API v3 request failed: {e.response.text if e.response else str(e)}")
            raise Exception(f"HubSpot API v3 request failed: {e.response.text if e.response else str(e)}")

    # DEALS METHODS

    def get_deals(self, limit: int = 100, after: Optional[str] = None, properties: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get deals from HubSpot.

        Args:
            limit: The maximum number of results to return.
            after: The paging cursor token to get the next page of results.
            properties: A list of properties to be returned in the response.

        Returns:
            A dictionary containing the deals and pagination information.
        """
        params = {"limit": limit}
        if after:
            params["after"] = after
        if properties:
            params["properties"] = ",".join(properties)

        return self._make_request("GET", "objects/deals", params=params)

    def get_deal(self, deal_id: str, properties: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get a specific deal by its ID.

        Args:
            deal_id: The ID of the deal.
            properties: A list of properties to be returned in the response.

        Returns:
            The deal object.
        """
        params = {}
        if properties:
            params["properties"] = ",".join(properties)
        return self._make_request("GET", f"objects/deals/{deal_id}", params=params)

    def create_deal(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new deal.

        Args:
            properties: A dictionary of properties for the new deal.

        Returns:
            The newly created deal object.
        """
        return self._make_request("POST", "objects/deals", data={"properties": properties})

    def update_deal(self, deal_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing deal.

        Args:
            deal_id: The ID of the deal to update.
            properties: A dictionary of properties to update.

        Returns:
            The updated deal object.
        """
        return self._make_request("PATCH", f"objects/deals/{deal_id}", data={"properties": properties})

    def delete_deal(self, deal_id: str) -> Dict[str, Any]:
        """
        Delete a deal.

        Args:
            deal_id: The ID of the deal to delete.
        """
        return self._make_request("DELETE", f"objects/deals/{deal_id}")

    # CONTACTS METHODS

    def get_contacts(self, limit: int = 100, after: Optional[str] = None, properties: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get contacts from HubSpot.

        Args:
            limit: The maximum number of results to return.
            after: The paging cursor token to get the next page of results.
            properties: A list of properties to be returned in the response.

        Returns:
            A dictionary containing the contacts and pagination information.
        """
        params = {"limit": limit}
        if after:
            params["after"] = after
        if properties:
            params["properties"] = ",".join(properties)
        return self._make_request("GET", "objects/contacts", params=params)

    def get_contact(self, contact_id: str, properties: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get a specific contact by its ID.

        Args:
            contact_id: The ID of the contact.
            properties: A list of properties to be returned in the response.

        Returns:
            The contact object.
        """
        params = {}
        if properties:
            params["properties"] = ",".join(properties)
        return self._make_request("GET", f"objects/contacts/{contact_id}", params=params)

    def create_contact(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new contact.

        Args:
            properties: A dictionary of properties for the new contact.

        Returns:
            The newly created contact object.
        """
        return self._make_request("POST", "objects/contacts", data={"properties": properties})

    def update_contact(self, contact_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing contact.

        Args:
            contact_id: The ID of the contact to update.
            properties: A dictionary of properties to update.

        Returns:
            The updated contact object.
        """
        return self._make_request("PATCH", f"objects/contacts/{contact_id}", data={"properties": properties})

    def delete_contact(self, contact_id: str) -> Dict[str, Any]:
        """
        Delete a contact.

        Args:
            contact_id: The ID of the contact to delete.
        """
        return self._make_request("DELETE", f"objects/contacts/{contact_id}")

    # COMPANIES METHODS

    def get_companies(self, limit: int = 100, after: Optional[str] = None, properties: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get companies from HubSpot.

        Args:
            limit: The maximum number of results to return.
            after: The paging cursor token to get the next page of results.
            properties: A list of properties to be returned in the response.

        Returns:
            A dictionary containing the companies and pagination information.
        """
        params = {"limit": limit}
        if after:
            params["after"] = after
        if properties:
            params["properties"] = ",".join(properties)
        return self._make_request("GET", "objects/companies", params=params)

    def get_company(self, company_id: str, properties: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get a specific company by its ID.

        Args:
            company_id: The ID of the company.
            properties: A list of properties to be returned in the response.

        Returns:
            The company object.
        """
        params = {}
        if properties:
            params["properties"] = ",".join(properties)
        return self._make_request("GET", f"objects/companies/{company_id}", params=params)

    def create_company(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new company.

        Args:
            properties: A dictionary of properties for the new company.

        Returns:
            The newly created company object.
        """
        return self._make_request("POST", "objects/companies", data={"properties": properties})

    def update_company(self, company_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing company.

        Args:
            company_id: The ID of the company to update.
            properties: A dictionary of properties to update.

        Returns:
            The updated company object.
        """
        return self._make_request("PATCH", f"objects/companies/{company_id}", data={"properties": properties})

    def delete_company(self, company_id: str) -> Dict[str, Any]:
        """
        Delete a company.

        Args:
            company_id: The ID of the company to delete.
        """
        return self._make_request("DELETE", f"objects/companies/{company_id}")

    # PAGINATION HELPER

    def get_all_paginated(self, method_name: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Helper to get all items using cursor-based pagination.

        Args:
            method_name: Name of the method to call (e.g., 'get_deals').
            **kwargs: Additional arguments for the method.

        Returns:
            List of all items across all pages.
        """
        all_items = []
        after = None
        method = getattr(self, method_name)

        while True:
            if after:
                kwargs["after"] = after

            response = method(**kwargs)

            results = response.get("results", [])
            if not results:
                break

            all_items.extend(results)

            paging = response.get("paging")
            if paging and "next" in paging:
                after = paging["next"]["after"]
            else:
                break

        return all_items

    # LANGCHAIN TOOL CREATION HELPERS

    def create_tools(self) -> List:
        """
        Create LangChain tools from the client methods.

        Returns:
            List of LangChain tools for agent use.
        """
        tools = []

        get_deals_tool = create_langchain_tool(
            func=self.get_deals,
            description="Get a list of deals from HubSpot. Can be filtered by properties.",
        )
        tools.append(get_deals_tool)

        get_contacts_tool = create_langchain_tool(
            func=self.get_contacts,
            description="Get a list of contacts from HubSpot. Can be filtered by properties.",
        )
        tools.append(get_contacts_tool)

        get_companies_tool = create_langchain_tool(
            func=self.get_companies,
            description="Get a list of companies from HubSpot. Can be filtered by properties.",
        )
        tools.append(get_companies_tool)

        create_deal_tool = create_langchain_tool(
            func=self.create_deal,
            description="Create a new deal in HubSpot. Takes a dictionary of properties.",
        )
        tools.append(create_deal_tool)

        update_deal_tool = create_langchain_tool(
            func=self.update_deal,
            description="Update an existing deal in HubSpot. Takes a deal_id and a dictionary of properties to update.",
        )
        tools.append(update_deal_tool)

        create_contact_tool = create_langchain_tool(
            func=self.create_contact,
            description="Create a new contact in HubSpot. Takes a dictionary of properties.",
        )
        tools.append(create_contact_tool)

        update_contact_tool = create_langchain_tool(
            func=self.update_contact,
            description="Update an existing contact in HubSpot. Takes a contact_id and a dictionary of properties to update.",
        )
        tools.append(update_contact_tool)

        return tools 