import httpx
from fastmcp import FastMCP
from fastmcp.server.openapi import HTTPRoute, OpenAPITool, RouteMap, MCPType
import logging, sys

# Configure logging
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

# Create an HTTP client for your API
client = httpx.AsyncClient(base_url="http://localhost:8080")

# Load your OpenAPI spec
spec = httpx.get("http://localhost:8080/v3/api-docs").json()

# Define routes to exclude
route_maps = [
    RouteMap(pattern=r"^/api/v1/schools/search/name", mcp_type=MCPType.EXCLUDE),
    # RouteMap(pattern=r"^/api/v1/schools/search/type", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/api/v1/schools/search/location", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/api/v1/schools/search/capacity", mcp_type=MCPType.EXCLUDE),
    # Add more patterns to exclude other endpoints if needed
]

def fix_all_outputs(route: HTTPRoute, component):
    """Replace the flattened 'array' schema with the real wrapper object."""
    if isinstance(component, OpenAPITool) and route.method.upper() == "GET":
        component.output_schema = {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "string"},
                "data": {"type": "object"},       # PagedResponse wrapper
                "timestamp": {"type": "string", "format": "date-time"}
            },
            "required": ["success", "message", "data", "timestamp"]
        }

# Create the MCP server
mcp = FastMCP.from_openapi(
    openapi_spec=spec,
    client=client,
    route_maps=route_maps,
    mcp_component_fn=fix_all_outputs,
    name="My EMIS Server",
)

if __name__ == "__main__":
    mcp.run(transport="http")