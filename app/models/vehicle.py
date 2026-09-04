import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)

    name = Column(String, nullable=False)  # Ex: Civic 2022, Onix Plus
    plate = Column(String, nullable=True)  # Ex: ABC-1234
    current_km = Column(Float, default=0.0)
    fuel_type = Column(String, default="Flex")  # Gasolina, Etanol, Diesel, Flex, Elétrico
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    workspace = relationship("Workspace", back_populates="vehicles")
    maintenances = relationship("VehicleMaintenance", back_populates="vehicle", cascade="all, delete-orphan")

class VehicleMaintenance(Base):
    __tablename__ = "vehicle_maintenances"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False)

    type = Column(String, nullable=False)  # 'oil_change', 'revision', 'fuel', 'tires', 'brakes', 'repair'
    description = Column(String, nullable=False)
    amount = Column(Float, default=0.0)
    km = Column(Float, nullable=False)
    next_due_km = Column(Float, nullable=True)
    next_due_date = Column(DateTime, nullable=True)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    notes = Column(Text, nullable=True)

    vehicle = relationship("Vehicle", back_populates="maintenances")
