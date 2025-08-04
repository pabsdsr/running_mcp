from mcp.server.fastmcp import FastMCP
from server.tools.strava_tools import subtract
# import fastmcp


mcp = FastMCP("Stride")

@mcp.tool()
def add(a: int, b: int) -> int:
    # add two numbers
    return a + b

def main():
    mcp.add_tool(subtract)
    mcp.run(transport='stdio') 

if __name__ == "__main__":
    # mcp.run(transport='stdio') 
    main()
