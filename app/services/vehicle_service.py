import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models import Vehicle, VehicleMaintenance

class VehicleService:
    @staticmethod
    def get_or_create_vehicle(db: Session, workspace_id: int, name: str = "Meu Veículo", plate: Optional[str] = None) -> Vehicle:
        vehicle = db.query(Vehicle).filter(Vehicle.workspace_id == workspace_id).first()
        if not vehicle:
            vehicle = Vehicle(
                workspace_id=workspace_id,
                name=name,
                plate=plate or "ABC-1234",
                current_km=0.0
            )
            db.add(vehicle)
            db.commit()
            db.refresh(vehicle)
        return vehicle

    @staticmethod
    def add_maintenance(
        db: Session,
        vehicle_id: int,
        type: str,
        description: str,
        amount: float,
        km: float,
        next_due_km: Optional[float] = None,
        notes: Optional[str] = None
    ) -> VehicleMaintenance:
        vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        if vehicle and km > vehicle.current_km:
            vehicle.current_km = km

        # Se for troca de óleo e não informou next_due_km, calcula +10.000km padrão
        if type == "oil_change" and not next_due_km:
            next_due_km = km + 10000.0

        maint = VehicleMaintenance(
            vehicle_id=vehicle_id,
            type=type,
            description=description.strip(),
            amount=amount,
            km=km,
            next_due_km=next_due_km,
            notes=notes
        )
        db.add(maint)
        db.commit()
        db.refresh(maint)
        return maint

    @staticmethod
    def get_vehicle_summary(db: Session, vehicle_id: int) -> Dict[str, Any]:
        vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        if not vehicle:
            return {}

        maintenances = db.query(VehicleMaintenance).filter(
            VehicleMaintenance.vehicle_id == vehicle_id
        ).order_by(VehicleMaintenance.km.desc()).all()

        total_spent = sum(m.amount for m in maintenances)
        oil_changes = [m for m in maintenances if m.type == "oil_change"]
        last_oil = oil_changes[0] if oil_changes else None

        # Alerta se estiver perto ou passou do KM de revisão / troca de óleo
        oil_alert = None
        if last_oil and last_oil.next_due_km:
            km_remaining = last_oil.next_due_km - vehicle.current_km
            if km_remaining <= 0:
                oil_alert = f"⚠️ Troca de óleo VENCIDA há {abs(km_remaining):.0f} km!"
            elif km_remaining <= 1000:
                oil_alert = f"🔔 Troca de óleo próxima! Faltam apenas {km_remaining:.0f} km."

        return {
            "vehicle": vehicle,
            "total_spent": total_spent,
            "last_oil_change": last_oil,
            "oil_alert": oil_alert,
            "history": maintenances[:10]
        }
