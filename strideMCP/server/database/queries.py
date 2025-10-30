from server.database.db import get_db
from sqlalchemy import func
from server.models.rolling_average_snapshots import RollingAverageSnapshots
from server.models.snapshot_metrics import SnapshotMetrics


def get_historic_average_by_metric(metric_name: str):
    db = get_db()

    result = db.query(
        func.avg(SnapshotMetrics.metric_value).label('average')
    ).filter(
        SnapshotMetrics.metric_name == metric_name
    ).first()


    return {
        'average' : result.average
    }

def get_average_by_metric_between_dates(metric_name: str, start_date, end_date):
    db = get_db()

    result = db.query(
        func.avg(SnapshotMetrics.metric_value).label('average')
    ).join(
        RollingAverageSnapshots, SnapshotMetrics.snapshot_id == RollingAverageSnapshots.id
    ).filter(
        SnapshotMetrics.metric_name == metric_name,
        RollingAverageSnapshots.date_of_run >= start_date,
        RollingAverageSnapshots.date_of_run <= end_date
    ).first()

    return {
        'average': result.average
    }