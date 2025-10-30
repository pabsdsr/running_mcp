import os
import json
import asyncio
import httpx
from datetime import datetime
from stravalib import Client
from google import genai
from google.genai import types
from server.services.qdrant_tool import qdrant_service
from server.models.rolling_average_snapshots import RollingAverageSnapshots
from server.models.snapshot_metrics import SnapshotMetrics
from server.database.db import get_db

class StravaService:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.embedding_state_file_path = os.path.join(os.path.dirname(__file__), "embedding_state.json")
        self.embedding_state = self._load_embedding_state()
        self.client = Client(access_token=access_token)
        self.db = get_db()

    def _load_embedding_state(self):
        if os.path.exists(self.embedding_state_file_path):
            with open(self.embedding_state_file_path, "r") as f:
                return json.load(f)
        # Default state if file doesn't exist
        return {
            "total_embedded": 0,
            "last_sync_timestamp": ""
        }

    def _save_embedding_state(self):
        with open(self.embedding_state_file_path, "w") as f:
            json.dump(self.embedding_state, f, indent=4)

    def run(self):
        user_activites = self._retrieve_activities()
        if len(user_activites) < 1:
            return
        points = []
        for a in user_activites:
            meaningful_text = self._convert_activity_to_paragraph(a)
            points.append((a, meaningful_text))

        # here we have all the points to run the metrics service
        self._store_snapshots_and_metrics(points)

        qdrant_service.insert_points(points)

    def _get_units_from_metric_name(self, metric_name: str) -> str:
        units = {
            "distance_miles": "",            # raw double (no explicit unit)
            "moving_time_sec": "seconds",
            "average_speed": "m/s",
            "pace_min_per_mile": "",         # raw double (no explicit unit)
            "total_elevation_gain": ""       # raw double (no explicit unit)
        }
        return units.get(metric_name, None)

    def _store_snapshots_and_metrics(self, points):
        snap_shots = []
        metrics = []
        metrics_to_gather = ["distance_miles", "moving_time_sec", "average_speed", "pace_min_per_mile", "total_elevation_gain"]
        for p in points:
            run_data = p[0]
            run_date = run_data.get("date", "")

            snapshot = RollingAverageSnapshots(
                date_of_run=run_date,
                snapshot_date=datetime.now(),
            )

            
            for metric_name in metrics_to_gather:
                metric  = SnapshotMetrics(
                    snapshot = snapshot,
                    metric_name = metric_name,
                    metric_value = run_data.get(metric_name, ""),
                    metric_unit= self._get_units_from_metric_name(metric_name)
                )

                metrics.append(metric)

                snapshot.metrics.append(metric)

            snap_shots.append(snapshot)

        try:
            self.db.add_all(snap_shots)
            self.db.commit()
        except Exception as e:
            print(f"Error: {e}")
       




    def _convert_activity_to_paragraph(self, activity):

        # Handle missing optional fields gracefully
        name = activity.get("name", "Unnamed Activity")
        description = activity.get("description", "No description provided.")
        distance = activity.get("distance_miles", 0)
        moving_time = activity.get("moving_time_sec", 0)
        avg_speed = activity.get("average_speed", 0)
        pace = activity.get("pace_min_per_mile", 0)
        paces_list = activity.get("paces_per_mile", [])
        gear = activity.get("gear_name", "Unknown gear")
        elevation = activity.get("total_elevation_gain", 0)
        location = activity.get("time_zone_location", "Unknown location")
        pr_count = activity.get("pr_count", 0)

        # Format paces list
        paces_str = ", ".join(f"{p:.2f} min/mi" for p in paces_list) if paces_list else "N/A"

        # Format time into minutes/seconds
        minutes = moving_time // 60
        seconds = moving_time % 60
        time_str = f"{minutes} minutes {seconds} seconds"

        # Build paragraph
        paragraph = (
            f"Activity titled '{name}' took place in {location}. "
            f"It was described as: {description}. "
            f"The run covered a distance of {distance:.2f} miles "
            f"with a total moving time of {time_str}. "
            f"The average speed was {avg_speed:.2f} miles per hour, "
            f"corresponding to a pace of {pace:.2f} minutes per mile. "
            f"Paces for each mile were: {paces_str}. "
            f"The run was completed using {gear}. "
            f"Total elevation gain was {elevation} feet. "
            f"This activity recorded {pr_count} personal records."
        )

        return paragraph
    

    async def _get_activity_details(self, activity_id: int):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://www.strava.com/api/v3/activities/{activity_id}",
                headers={"Authorization": f"Bearer {self.access_token}"}
            )
            return response.json()
    
            
    async def _get_all_activity_details(self, activities):
        details = []
        for a in activities:
            details.append(self._get_activity_details(a.id))
        return await asyncio.gather(*details)



    def _retrieve_activities(self):
        timestamp_str = datetime.now().strftime("%Y-%m-%d")
        # strava_client = Client(access_token=self.access_token)
        # ...existing code...
        if self.embedding_state['total_embedded'] == 0:
            try:
                # user_activities = self.client.get_activities()
                user_activities = self.client.get_activities(after="2025-06-01")
                # user_activities = self.client.get_activities(after="2025-10-29")

                descriptive_activities = []

                descriptive_activities = asyncio.run(
                    self._get_all_activity_details(user_activities)
                )

                # for a in user_activities:
                #     descriptive_activity = self.client.get_activity(a.id)
                #     descriptive_activities.append(descriptive_activity)
                
                parsed_activities = self._parse_activities(descriptive_activities)

                # user_activities = parsed_activities
            except Exception as e:
                return f"Retrieving activities failed: {e}"
            self.embedding_state["last_sync_timestamp"] = timestamp_str
            self.embedding_state["total_embedded"] += len(list(user_activities))
            self._save_embedding_state()
        else:
            last_sync = self.embedding_state["last_sync_timestamp"]
            try:
                user_activities = self.client.get_activities(after=last_sync)
                descriptive_activities = []

                descriptive_activities = asyncio.run(
                    self._get_all_activity_details(user_activities)
                )

                # for a in user_activities:
                #     descriptive_activity = self.client.get_activity(a.id)
                #     descriptive_activities.append(descriptive_activity)
                
                parsed_activities = self._parse_activities(descriptive_activities)
                # user_activities = parsed_activities
            except Exception as e:
                return f"Retrieving activities after last sync failed: {e}"
            self.embedding_state["last_sync_timestamp"] = timestamp_str
            self.embedding_state["total_embedded"] += len(list(user_activities))
            self._save_embedding_state()
        # return user_activities
        return parsed_activities
    
    def _convert_km_splits_to_mile_paces(self, activity):
        """
        Convert kilometer splits from Strava to mile-by-mile paces.
        
        Approach: Use cumulative distance and time to calculate mile markers,
        then interpolate between km splits to get mile paces.
        """
        # splits = getattr(activity, "splits_metric", [])
        splits = activity.get("splits_metric", [])
        if not splits:
            return []
        
        # Build cumulative data from km splits
        cumulative_distance_m = 0
        cumulative_time_s = 0
        km_data = [(0, 0)]  # (distance_meters, time_seconds)
        
        for split in splits:
            split_distance = split.get("distance", 0)
            split_moving_time = split.get("moving_time", 0)
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
            mile_time = self._interpolate_time_at_distance(km_data, mile_distance_m)
            prev_mile_time = self._interpolate_time_at_distance(km_data, (mile_num - 1) * meters_per_mile)
            
            # Calculate pace for this mile
            mile_time_diff = mile_time - prev_mile_time
            pace_min_per_mile = mile_time_diff / 60  # convert to minutes
            mile_paces.append(pace_min_per_mile)
        
        return mile_paces


    def _interpolate_time_at_distance(self, km_data, target_distance):
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
    
    def _format_pace(self, pace_decimal_minutes):
        """Convert decimal minutes to MM:SS format"""
        if pace_decimal_minutes is None:
            return None
    
        minutes = int(pace_decimal_minutes)
        seconds = int((pace_decimal_minutes - minutes) * 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def _parse_activities(self,activities):
        parsed = []
        for a in activities:
            # IF I EVER GET A WATCH, ADD HEART RATE INFORMATION
            # print(type(a))
            # name = getattr(a, "name", None)
            # distance_miles = getattr(a, "distance", 0) / 1609.34  # meters to miles
            # moving_time_sec = getattr(a, "moving_time", 0)
            # avg_speed = getattr(a, "average_speed", 0)
            # description = getattr(a, "description", None)
            name = a.get("name", "Unnamed Activity")
            distance_miles = a.get("distance", 0) / 1609.34
            moving_time_sec = a.get("moving_time", 0)
            avg_speed = a.get("average_speed", 0)
            description = a.get("description", "No Description")

            pace_min_per_mile= (moving_time_sec / 60) / distance_miles if distance_miles else None

            # Convert km splits to mile paces
            paces_per_mile_raw= self._convert_km_splits_to_mile_paces(a)
            paces_per_mile_min = [self._format_pace(pace) for pace in paces_per_mile_raw]
            # gear_object = getattr(a, "gear", None)
            # gear_name = getattr(gear_object, "name", None)
            # total_elevation_gain = getattr(a,"total_elevation_gain", None)
            # time_zone_location = getattr(a,"timezone", None)
            # pr_count = getattr(a,"pr_count", None)
            # date = getattr(a, "start_date", None)
            gear_name = a.get("gear", {}).get("name", "Unknown gear")
            total_elevation_gain = a.get("total_elevation_gain", 0)
            time_zone_location = a.get("timezone", "Unknown location")
            pr_count = a.get("pr_count", 0)
            date = a.get("start_date", None)


            activity_json = {
                "name": name,
                "description": description,
                "distance_miles": distance_miles,
                "moving_time_sec": moving_time_sec,
                "average_speed": avg_speed,
                "pace_min_per_mile": pace_min_per_mile,
                "paces_per_mile_raw": paces_per_mile_raw,
                "paces_per_mile_mins": paces_per_mile_min,
                "gear_name" : gear_name,
                "total_elevation_gain" : total_elevation_gain,
                "time_zone_location" : time_zone_location,
                "pr_count": pr_count,
                "date" : date
            }
            parsed.append(activity_json)

        return parsed




