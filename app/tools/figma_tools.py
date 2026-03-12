"""Figma integration tools for MCP server"""
import os
import httpx
from typing import Dict, List, Any, Optional
from mcp.server import Server
from mcp.types import Tool, TextContent
import json

class FigmaClient:
    def __init__(self):
        self.token = os.getenv("FIGMA_TOKEN")
        if not self.token:
            raise ValueError("FIGMA_TOKEN environment variable is required")
        
        self.headers = {
            "X-Figma-Token": self.token,
            "Content-Type": "application/json"
        }
        self.base_url = "https://api.figma.com/v1"
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make authenticated request to Figma API"""
        url = f"{self.base_url}{endpoint}"
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
                return {"error": f"Figma API request failed: {str(e)}"}
            except Exception as e:
                return {"error": f"Unexpected error: {str(e)}"}

def register_figma_tools(server: Server):
    """Register all Figma tools with the MCP server"""
    figma = FigmaClient()
    
    @server.call_tool()
    async def figma_get_file(file_key: str, depth: Optional[int] = 1) -> List[TextContent]:
        """קבלת מבנה קובץ Figma (עמודים ופריימים)
        
        Args:
            file_key: מזהה הקובץ ב-Figma (מה-URL)
            depth: עומק הנתונים (1-2, ברירת מחדל: 1)
        """
        params = {"depth": str(depth)}
        endpoint = f"/files/{file_key}"
        
        result = await figma._make_request("GET", endpoint, params=params)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]
    
    @server.call_tool()
    async def figma_get_comments(file_key: str) -> List[TextContent]:
        """קבלת הערות על קובץ Figma
        
        Args:
            file_key: מזהה הקובץ ב-Figma
        """
        endpoint = f"/files/{file_key}/comments"
        
        result = await figma._make_request("GET", endpoint)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]
    
    @server.call_tool()
    async def figma_search_components(team_id: str, query: Optional[str] = None) -> List[TextContent]:
        """חיפוש רכיבים בצוות
        
        Args:
            team_id: מזהה הצוות
            query: מונח חיפוש (אופציונלי)
        """
        params = {}
        if query:
            params["q"] = query
        
        endpoint = f"/teams/{team_id}/components"
        
        result = await figma._make_request("GET", endpoint, params=params)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]
    
    @server.call_tool()
    async def figma_get_frame_image(file_key: str, node_ids: str, format: Optional[str] = "png", scale: Optional[str] = "1") -> List[TextContent]:
        """יצוא תמונה של פריים/רכיב
        
        Args:
            file_key: מזהה הקובץ ב-Figma
            node_ids: מזהי הצמתים (מופרדים בפסיק)
            format: פורמט התמונה (png, jpg, svg, pdf)
            scale: רמת זום (1-4)
        """
        params = {
            "ids": node_ids,
            "format": format,
            "scale": scale
        }
        
        endpoint = f"/images/{file_key}"
        
        result = await figma._make_request("GET", endpoint, params=params)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]
    
    @server.call_tool()
    async def figma_get_file_nodes(file_key: str, node_ids: str, depth: Optional[int] = 1) -> List[TextContent]:
        """קבלת פרטי צמתים ספציפיים בקובץ
        
        Args:
            file_key: מזהה הקובץ ב-Figma
            node_ids: מזהי הצמתים (מופרדים בפסיק)
            depth: עומק הנתונים (1-2)
        """
        params = {
            "ids": node_ids,
            "depth": str(depth)
        }
        
        endpoint = f"/files/{file_key}/nodes"
        
        result = await figma._make_request("GET", endpoint, params=params)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]