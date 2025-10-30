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


def parse_activities(activities):
    parsed = []
    for a in activities:
        # Use dot notation for attributes, not subscript
        # IF I EVER GET A WATCH, ADD HEART RATE INFORMATION
        name = getattr(a, "name", None)
        distance_miles = getattr(a, "distance", 0) / 1609.34  # meters to miles
        moving_time_sec = getattr(a, "moving_time", 0)
        avg_speed = getattr(a, "average_speed", 0)
        description = getattr(a, "description", None)

        pace_min_per_mile = (moving_time_sec / 60) / distance_miles if distance_miles else None

        # Convert km splits to mile paces
        paces_per_mile = convert_km_splits_to_mile_paces(a)
        gear_object = getattr(a, "gear", None)
        gear_name = getattr(gear_object, "name", None)
        total_elevation_gain = getattr(a,"total_elevation_gain", None)
        time_zone_location = getattr(a,"timezone", None)
        pr_count = getattr(a,"pr_count", None)


        activity_json = {
            "name": name,
            "description": description,
            "distance_miles": distance_miles,
            "moving_time_sec": moving_time_sec,
            "average_speed": avg_speed,
            "pace_min_per_mile": pace_min_per_mile,
            "paces_per_mile": paces_per_mile,
            "gear_name" : gear_name,
            "total_elevation_gain" : total_elevation_gain,
            "time_zone_location" : time_zone_location,
            "pr_count": pr_count
        }
        parsed.append(activity_json)

    return parsed


def convert_km_splits_to_mile_paces(activity):
    """
    Convert kilometer splits from Strava to mile-by-mile paces.
    
    Approach: Use cumulative distance and time to calculate mile markers,
    then interpolate between km splits to get mile paces.
    """
    splits = getattr(activity, "splits_metric", [])
    if not splits:
        return []
    
    # Build cumulative data from km splits
    cumulative_distance_m = 0
    cumulative_time_s = 0
    km_data = [(0, 0)]  # (distance_meters, time_seconds)
    
    for split in splits:
        split_distance = getattr(split, "distance", 0)
        split_moving_time = getattr(split, "moving_time", 0)
        cumulative_distance_m += split_distance
        cumulative_time_s += split_moving_time
        km_data.append((cumulative_distance_m, cumulative_time_s))
    
    # Calculate mile paces
    mile_paces = []
    meters_per_mile = 1609.34
    
    for mile_num in range(1, int(cumulative_distance_m / meters_per_mile) + 2):
        mile_distance_m = mile_num * meters_per_mile
        
        # Don't calculate pace for miles beyond the actual run distance
        if mile_distance_m > cumulative_distance_m:
            break
            
        # Find time at this mile marker using interpolation
        mile_time = interpolate_time_at_distance(km_data, mile_distance_m)
        prev_mile_time = interpolate_time_at_distance(km_data, (mile_num - 1) * meters_per_mile)
        
        # Calculate pace for this mile
        mile_time_diff = mile_time - prev_mile_time
        pace_min_per_mile = mile_time_diff / 60  # convert to minutes
        mile_paces.append(pace_min_per_mile)
    
    return mile_paces


def interpolate_time_at_distance(km_data, target_distance):
    """
    Interpolate the time at a specific distance using km split data.
    km_data is a list of (distance_meters, cumulative_time_seconds) tuples.
    """
    if target_distance <= 0:
        return 0
    
    # Find the two km points that bracket our target distance
    for i in range(len(km_data) - 1):
        dist1, time1 = km_data[i]
        dist2, time2 = km_data[i + 1]
        
        if dist1 <= target_distance <= dist2:
            if dist2 == dist1:  # Avoid division by zero
                return time1
            
            # Linear interpolation
            ratio = (target_distance - dist1) / (dist2 - dist1)
            interpolated_time = time1 + ratio * (time2 - time1)
            return interpolated_time
    
    # If target distance is beyond our data, extrapolate from the last segment
    if len(km_data) >= 2:
        dist1, time1 = km_data[-2]
        dist2, time2 = km_data[-1]
        if dist2 != dist1:
            pace_per_meter = (time2 - time1) / (dist2 - dist1)
            return time2 + pace_per_meter * (target_distance - dist2)
    
    return km_data[-1][1] if km_data else 0

def find_best_time_to_run(location: str) -> dict:
    url = "https://api.mapbox.com/search/geocode/v6/forward"
    
    params = {
        "q": location,
        "access_token": "pk.eyJ1IjoicGFic2RzciIsImEiOiJjbTVia3dscng0d21tMnJwdG1sNWh5dDcwIn0.tvH5Eo99g0JPQeKQMYMc4w",
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


def retrieve_strava_activities() -> dict:
    access_token = token_service.get_token()

    while access_token == None:
        continue

    try:
        client = Client(
            access_token=access_token,
        )

        activities = client.get_activities(after="2025-06-28", limit = 1)

        descriptive_activities = []

        for a in activities:
            descriptive_activity = client.get_activity(a.id)
            descriptive_activities.append(descriptive_activity)

        parsed_activities = parse_activities(descriptive_activities)
        
        return parsed_activities

    except Exception as e:
        return f"Retrieving activities failed: {e}"
    

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
    
