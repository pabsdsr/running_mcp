import json
import urllib.parse

def encode_run_for_charts(payload):
    raw_mile_splits = payload["run"]["paces_per_mile_raw"]

    data = {
        "raw_mile_splits" : raw_mile_splits
    }

    json_str = json.dumps(data)
    encoded = urllib.parse.quote(json_str)

    return f"http://localhost:5000/plotRunData?payload={encoded}"

# def plot_metrics_from_db():