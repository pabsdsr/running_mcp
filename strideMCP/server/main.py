from mcp.server.fastmcp import FastMCP
from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from stravalib import Client
import uvicorn
import threading
import os

from server.tools.strava_tools import authenticate_with_strava, retrieve_strava_activities, lookup_specific_run_by_date, lookup_by_retrieval_query, look_up_last_N_runs
from dotenv import load_dotenv
from server.services.token_service import token_service
from server.services.strava_service import StravaService

load_dotenv()


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

    auth_code = request.query_params.get("code")

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
        strava_service.run()

        return {
            "message": "strava service ran"
        }


    return {"message" : "Authorization Failed"}


mcp = FastMCP("Stride")


def run_listener():
    uvicorn.run(mcp_listener, host="127.0.0.1", port=5000)


def run_mcp():
    mcp.add_tool(retrieve_strava_activities)
    mcp.add_tool(authenticate_with_strava)
    mcp.add_tool(lookup_specific_run_by_date)
    mcp.add_tool(lookup_by_retrieval_query)
    mcp.add_tool(look_up_last_N_runs)
    mcp.run(transport='stdio') 


def main():
    mcp_thread = threading.Thread(target=run_mcp)
    listener_thread = threading.Thread(target=run_listener)
    mcp_thread.start()
    listener_thread.start()
    mcp_thread.join()
    listener_thread.join()


if __name__ == "__main__":
    main()
