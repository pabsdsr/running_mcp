from server.models.base import Base
from sqlalchemy import Column, Integer, String, ForeignKey, Double
from sqlalchemy.orm import relationship

class SnapshotMetrics(Base):
    __tablename__ = "snapshot_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, ForeignKey("rolling_average_snapshots.id"), nullable=False)
    metric_name = Column(String, nullable=False)
    metric_value = Column(Double, nullable=False)
    metric_unit = Column(String, nullable=False)

    snapshot = relationship("RollingAverageSnapshots", back_populates="metrics")