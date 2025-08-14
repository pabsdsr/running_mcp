from mcp.server.fastmcp import FastMCP
from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from stravalib import Client
import uvicorn
import threading
import os
import json
from datetime import datetime

from server.tools.strava_tools import authenticate_with_strava, retrieve_strava_activities
from dotenv import load_dotenv
from server.services.token_service import token_service
from server.services.strava_service import StravaService

load_dotenv()

access_token= None

mcp_listener = FastAPI(
    title="MCP Listener"
)

mcp_listener.add_middleware(
    CORSMiddleware,
    # we have to adjust this origin to our frontend url once it is hosted
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@mcp_listener.get("/authorization")
def grab_auth_code_and_exchange_for_token(request: Request):
    # store this with the token service
    global access_token
    auth_code = request.query_params.get("code")

    cnt = 1

    if auth_code:
        client = Client()
        token_response = client.exchange_code_for_token(
            client_id=os.getenv('CLIENT_ID'),
            client_secret=os.getenv('CLIENT_SECRET'),
            code=auth_code
        )

        access_token = token_response["access_token"]
        refresh_token = token_response["refresh_token"]
        expires_at = token_response["expires_at"]
        token_service.store_token_details(access_token, expires_at, refresh_token)

        strava_service = StravaService(access_token)
        user_activities = list(strava_service._retrieve_activities())

        # fix path of json state file
        cnt = len(user_activities)

        # Get timestamp from embedding state for response
        timestamp_str = strava_service.embedding_state.get("last_sync_timestamp")
        total_embedded = strava_service.embedding_state.get("total_embedded")

        return {
            "message": f"Token Response {token_response}",
            "timestamp": timestamp_str,
            "cnt" : cnt,
            "total" : total_embedded,
            "runs" : user_activities
        }

    return {"message" : "Authorization Failed"}


mcp = FastMCP("Stride")

@mcp.tool()
def get_token() -> str:
    global access_token
    print(f"access_token from tool {access_token}")
    if access_token:
        return access_token
    return "No Access token found"

def run_listener():
    uvicorn.run(mcp_listener, host="127.0.0.1", port=5000)


def run_mcp():
    mcp.add_tool(retrieve_strava_activities)
    mcp.add_tool(authenticate_with_strava)
    mcp.run(transport='stdio') 

# I want to allow semantic search of a data base 
# for example: retrieve all of my long runs, tempo runs, farlek, etc
# This will be dependent on the activities description that the user inputs
# So i will either have to start adding descriptions to my runs or make some fake data
# 

def main():
    mcp_thread = threading.Thread(target=run_mcp)
    listener_thread = threading.Thread(target=run_listener)
    mcp_thread.start()
    listener_thread.start()
    mcp_thread.join()
    listener_thread.join()


if __name__ == "__main__":
    main()
