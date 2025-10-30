from mcp.server.fastmcp import FastMCP
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from stravalib import Client
from server.database.db import init_db
import uvicorn
import threading
import httpx
import json
import os
import matplotlib.pyplot as plt
from io import BytesIO
# from server.tools.strava_tools import authenticate_with_strava, retrieve_strava_activities, lookup_specific_run_by_date, lookup_by_retrieval_query, look_up_last_N_runs, find_best_time_to_run
from server.tools.strava_tools import *
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

def format_pace(decimal_minutes):
    """Convert 7.5 minutes to '7:30' format"""
    minutes = int(decimal_minutes)
    seconds = int((decimal_minutes - minutes) * 60)
    return f"{minutes}:{seconds:02d}"


@mcp_listener.get("/plotRunData")
async def plot_run_data(request: Request):
    body = request.query_params.get("payload")
    data = json.loads(body)

    raw_mile_splits = data["raw_mile_splits"]
    min_pace = min(raw_mile_splits)

    x_labels = []
    for i in range(1, len(raw_mile_splits) + 1):
        x_labels.append(f"{i}")
    
    bars = plt.bar(x_labels, raw_mile_splits)
    for bar, value in zip(bars, raw_mile_splits):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height(), 
            format_pace(value), ha='center', va='bottom', fontsize=9)
    plt.xlabel("Miles")
    plt.ylabel("Mins Per Mile")
    plt.ylim(bottom=min_pace - 1.0) 
    plt.title("Mile Splits")

    buf = BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()

    return StreamingResponse(buf, media_type="image/png")

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
    init_db()
    uvicorn.run(mcp_listener, host="127.0.0.1", port=5000)


def run_mcp():
    mcp.add_tool(retrieve_strava_activities)
    mcp.add_tool(authenticate_with_strava)
    mcp.add_tool(lookup_specific_run_by_date)
    mcp.add_tool(lookup_by_retrieval_query)
    mcp.add_tool(look_up_last_N_runs)
    mcp.add_tool(compute_metric_historic_avg)
    mcp.add_tool(compute_metric_by_date_range)
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
