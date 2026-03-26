from sqlalchemy import (
    Column, Integer, String, Float, DateTime, JSON, Text, ForeignKey, Boolean
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    port = Column(Integer, nullable=False)
    description = Column(Text)
    dependencies = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChaosExperiment(Base):
    __tablename__ = "chaos_experiments"

    id = Column(Integer, primary_key=True, index=True)
    scenario_name = Column(String(200), nullable=False)
    fault_type = Column(String(50), nullable=False)
    target_service = Column(String(100))
    parameters = Column(JSON, default=dict)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="running")  # running, completed, aborted
    blast_radius_score = Column(Float, default=0.0)

    metrics = relationship("ExperimentMetric", back_populates="experiment")
    cascade_events = relationship("CascadeEvent", back_populates="experiment")
    post_mortem = relationship("PostMortem", back_populates="experiment", uselist=False)


class ExperimentMetric(Base):
    __tablename__ = "experiment_metrics"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("chaos_experiments.id"), nullable=False)
    service_name = Column(String(100), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    error_rate = Column(Float, default=0.0)
    latency_p99 = Column(Float, default=0.0)
    request_rate = Column(Float, default=0.0)
    status = Column(String(20), default="healthy")

    experiment = relationship("ChaosExperiment", back_populates="metrics")


class CascadeEvent(Base):
    __tablename__ = "cascade_events"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("chaos_experiments.id"), nullable=False)
    source_service = Column(String(100), nullable=False)
    affected_service = Column(String(100), nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow)
    delay_seconds = Column(Float, default=0.0)
    impact_description = Column(Text)

    experiment = relationship("ChaosExperiment", back_populates="cascade_events")


class PostMortem(Base):
    __tablename__ = "post_mortems"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("chaos_experiments.id"), nullable=False)
    severity = Column(String(10), nullable=False)
    title = Column(String(300), nullable=False)
    summary = Column(Text)
    full_report = Column(JSON, default=dict)
    resilience_score = Column(Float, default=0.0)
    generated_at = Column(DateTime, default=datetime.utcnow)

    experiment = relationship("ChaosExperiment", back_populates="post_mortem")


class NotificationLog(Base):
    __tablename__ = "notifications_log"

    id = Column(Integer, primary_key=True, index=True)
    service = Column(String(100), nullable=False)
    event_type = Column(String(100), nullable=False)
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    full_name = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    category = Column(String(100))
    stock_quantity = Column(Integer, default=100)
    created_at = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    product_id = Column(Integer, nullable=False)
    quantity = Column(Integer, default=1)
    total_price = Column(Float, nullable=False)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
