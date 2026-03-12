"""Jira integration tools for MCP server"""
import os
import httpx
from typing import Dict, List, Any, Optional
from mcp.server import Server
from mcp.types import Tool, TextContent
import json
import base64

class JiraClient:
    def __init__(self):
        self.base_url = os.getenv("JIRA_URL", "").rstrip('/')
        self.email = os.getenv("JIRA_EMAIL")
        self.token = os.getenv("JIRA_API_TOKEN")
        
        if not all([self.base_url, self.email, self.token]):
            raise ValueError("JIRA_URL, JIRA_EMAIL, and JIRA_API_TOKEN environment variables are required")
        
        # Create basic auth header
        auth_string = f"{self.email}:{self.token}"
        auth_bytes = base64.b64encode(auth_string.encode()).decode()
        
        self.headers = {
            "Authorization": f"Basic {auth_bytes}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make authenticated request to Jira API"""
        url = f"{self.base_url}/rest/api/3{endpoint}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    timeout=30.0,
                    **kwargs
                )
                response.raise_for_status()
                return response.json() if response.content else {}
            except httpx.HTTPError as e:
                return {"error": f"Jira API request failed: {str(e)}"}
            except Exception as e:
                return {"error": f"Unexpected error: {str(e)}"}

def register_jira_tools(server: Server):
    """Register all Jira tools with the MCP server"""
    jira = JiraClient()
    
    @server.call_tool()
    async def jira_search_issues(jql: str, max_results: Optional[int] = 50) -> List[TextContent]:
        """חיפוש issues ב-Jira באמצעות JQL
        
        Args:
            jql: שאילתת JQL (למשל: "project = PROJ AND status = Open")
            max_results: מספר תוצאות מקסימלי
        """
        params = {
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,status,assignee,reporter,created,updated,priority,issuetype,description"
        }
        
        result = await jira._make_request("GET", "/search", params=params)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]
    
    @server.call_tool()
    async def jira_get_issue(issue_key: str) -> List[TextContent]:
        """קבלת פרטי issue ספציפי
        
        Args:
            issue_key: מפתח ה-issue (למשל: PROJ-123)
        """
        endpoint = f"/issue/{issue_key}"
        params = {
            "expand": "names,renderedFields,transitions,changelog"
        }
        
        result = await jira._make_request("GET", endpoint, params=params)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]
    
    @server.call_tool()
    async def jira_list_sprints(board_id: str) -> List[TextContent]:
        """רשימת ספרינטים בלוח
        
        Args:
            board_id: מזהה הלוח
        """
        endpoint = f"/board/{board_id}/sprint"
        params = {"state": "active,future"}
        
        result = await jira._make_request("GET", endpoint, params=params)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]
    
    @server.call_tool()
    async def jira_get_sprint_issues(sprint_id: str) -> List[TextContent]:
        """קבלת כל ה-issues בספרינט
        
        Args:
            sprint_id: מזהה הספרינט
        """
        endpoint = f"/sprint/{sprint_id}/issue"
        params = {
            "fields": "summary,status,assignee,reporter,storyPoints,priority,issuetype"
        }
        
        result = await jira._make_request("GET", endpoint, params=params)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]
    
    @server.call_tool()
    async def jira_get_board(board_id: str) -> List[TextContent]:
        """סקירה של לוח Jira
        
        Args:
            board_id: מזהה הלוח
        """
        endpoint = f"/board/{board_id}"
        
        result = await jira._make_request("GET", endpoint)
        
        # Also get board configuration if available
        if not result.get("error"):
            config_endpoint = f"/board/{board_id}/configuration"
            config = await jira._make_request("GET", config_endpoint)
            if not config.get("error"):
                result["configuration"] = config
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]