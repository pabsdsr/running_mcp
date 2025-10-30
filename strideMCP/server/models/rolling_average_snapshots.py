from server.models.base import Base
from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.orm import relationship

class RollingAverageSnapshots(Base):
    __tablename__ = "rolling_average_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date_of_run = Column(DateTime, nullable=False)
    # snapshot date is the date our service runs and computes the rolling averages
    snapshot_date = Column(DateTime, nullable=False) 

    metrics = relationship("SnapshotMetrics", back_populates="snapshot")
