import os
from stravalib import Client
from server.services.token_service import token_service
from server.services.qdrant_tool import qdrant_service
from server.utils.stravaUtility import *
from pydantic import Field
import httpx
import json
import urllib.parse
from datetime import datetime, time, timezone
from server.database.queries import *



def authenticate_with_strava() -> str:
    try:
        client = Client()
        url = client.authorization_url(
            client_id= os.getenv('CLIENT_ID'),
            redirect_uri='http://127.0.0.1:5000/authorization',
            scope='activity:read_all'
        )

        return url
    except Exception as e:
        return f"The API call failed: {e}"

def find_best_time_to_run(location: str) -> dict:
    url = "https://api.mapbox.com/search/geocode/v6/forward"
    
    params = {
        "q": location,
        "access_token": "",
        "limit": "1"
    }
    mapbox_response = httpx.get(url, params=params)

    if mapbox_response.status_code == 200:
        data = mapbox_response.json()
        data = data["features"][0]["geometry"]["coordinates"]
    else:
        data = "Error: {mapbox_response.status_code}"

    
    return {"coordinates" : mapbox_response}


def lookup_specific_run_by_date(
        date: str = Field(description="Date in format YYYY-MM-DD inferred from query")
    ) -> dict:

    runs = qdrant_service.search_runs_by_date(date)

    run = runs[0]
    run_info = run[0]
    run_payload = getattr(run_info, "payload", False)

    if run_payload:
        url = encode_run_for_charts(run_payload)

        return {
            "run_payload" : run_payload,
            "chart_url" : url
        }



    return {
        "runs" : runs
    }



# RETRIEVAL_QUERY

def lookup_by_retrieval_query(
        retrieval_query: str = Field(description= "A general user query that will allow you to create a vector embedding and search for answer")
    ) -> dict:
    
    vector = qdrant_service.embed_query(retrieval_query)

    response = qdrant_service.search_for_runs_by_embedding(vector)


    points = response.points
    sorted_points = sorted(points, key=lambda point: point.score, reverse=True)
    higest_score_point = sorted_points[0]
    payload = getattr(higest_score_point, "payload", False)

    if payload:
        url = encode_run_for_charts(payload)

        return {
            "best_match": higest_score_point,
            "matches" : points,
            "best_match_chart_url" : url,
            "chart_instructions": "IMPORTANT: Always mention that the user can view a visual chart of their mile splits by visiting the best_match_chart_url provided above."
        }

    return {"runs" : "Get attr failed"}


def look_up_last_N_runs(
        N: int = Field(description="An integer inferred from the user query")    
    ) -> dict:

    last_n_runs = qdrant_service.search_for_runs_by_n(N)

    return {"last_n_runs" : last_n_runs}


def compute_metric_historic_avg(
        metric_name = Field(
            description="""
                The name of a running metric. Map the user input to one of the metrics.
                1. distance_miles
                2. moving_time_sec
                3. average_speed
                4. pace_min_per_mile
                5. total_elevation_gain
            """
        )   
    ) -> dict:

    historic_avg = get_historic_average_by_metric(metric_name)

    key = metric_name + " historic average"

    return {
        key : historic_avg
    }

def compute_metric_by_date_range(
        metric_name: str = Field(description="""
                The name of a running metric. Map the user input to one of the metrics.
                1. distance_miles
                2. moving_time_sec
                3. average_speed
                4. pace_min_per_mile
                5. total_elevation_gain
            """
        ),
        start_date: str = Field(description="From the user query infer the start date in YYYY-MM-DD format."),
        end_date: str = Field(description="From the user query infer the end date in YYYY-MM-DD format."),
        time_range: str = Field(description="The users time range for requesting computation on metrics.")
    ) -> dict:

    # I might have to convert these to UTC, verify accuracy of this approach
    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)
    avg_between_dates = get_average_by_metric_between_dates(metric_name, start_date_obj, end_date_obj)
    key = metric_name + " average for " + time_range
    return {
        key : avg_between_dates
    }

def get_data_points_for_metric_between_dates(
        metric_name: str = Field(description="""
                The name of a running metric. Map the user input to one of the metrics.
                1. distance_miles
                2. moving_time_sec
                3. average_speed
                4. pace_min_per_mile
                5. total_elevation_gain
            """
        ),
        start_date: str = Field(description="From the user query infer the start date in YYYY-MM-DD format."),
        end_date: str = Field(description="From the user query infer the end date in YYYY-MM-DD format."),
        time_range: str = Field(description="The users time range for requesting computation on metrics.")
    ) -> dict:

    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)
    data_points = query_get_data_points_for_metric_between_dates(metric_name, start_date_obj, end_date_obj)

    formatted_points = [
        {
            "value": value,
            "date": date.strftime("%Y-%m-%d %H:%M:%S")
        }
        for value, date in data_points
    ]

    try:
        response = httpx.post(
            "http://localhost:5000/plotMetricsOverTime",
            json={"data_points": formatted_points}
        )
    except Exception as e:
        return {
            "error" : e
        }

    if response.status_code == 200:
        return {
            "data points" : data_points,
            "INSTRUCTIONS_IMPORTANT" : "RENDER THIS CHART HTML",
            "chart_html" : response.text
        }
    # data = {
    #     "data_points" : formatted_points
    # }

    # json_str = json.dumps(data)
    # encoded = urllib.parse.quote(json_str)

    # chart_url = f"http://localhost:5000/plotMetricsOverTime?payload={encoded}"
    

