"""
LeadStateService: CRUD para la tabla lead_states.
Persiste el estado de captación de datos del lead a lo largo de la conversación.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from app.services.supabase_client import get_supabase

logger = logging.getLogger(__name__)


class LeadStateService:

    # Mapeo de campos del lead_state a pasos (1-5)
    STEP_FIELDS = ["campus", "programa", "nombre_completo", "telefono", "email"]

    def __init__(self):
        self.client = get_supabase()

    def get_or_create(self, contact_id: str, location_id: str) -> dict:
        """
        Obtiene o crea el estado del lead.
        Returns dict con todos los campos del lead_state.
        """
        if not self.client:
            return self._empty_state(contact_id, location_id)

        try:
            response = self.client.table("lead_states") \
                .select("*") \
                .eq("contact_id", contact_id) \
                .limit(1) \
                .execute()

            if response.data and len(response.data) > 0:
                return response.data[0]

            # Crear nuevo
            new_state = {
                "contact_id": contact_id,
                "location_id": location_id,
                "current_step": 1,
                "is_complete": False,
                "post_booking_count": 0,
                "score": 0,
            }
            result = self.client.table("lead_states").insert(new_state).execute()
            if result.data:
                logger.info("Lead state creado para %s", contact_id)
                return result.data[0]
            return self._empty_state(contact_id, location_id)

        except Exception as e:
            logger.error("Error en get_or_create lead_state: %s", e)
            return self._empty_state(contact_id, location_id)

    def bulk_update(self, contact_id: str, data: dict) -> bool:
        """
        Actualiza campos del lead_state.
        Mapea claves de AgentResponse.captured_data a columnas de lead_states.
        Recalcula current_step e is_complete automáticamente.
        """
        if not self.client or not data:
            return False

        try:
            # Mapeo de captured_data keys → columnas de lead_states
            field_map = {
                "campus": "campus",
                "detected_campus": "campus",
                "programa": "programa",
                "program_interest": "programa",
                "nombre_completo": "nombre_completo",
                "full_name": "nombre_completo",
                "telefono": "telefono",
                "phone": "telefono",
                "email": "email",
            }

            update_data = {}
            for key, value in data.items():
                if key in field_map and value:
                    update_data[field_map[key]] = value

            if not update_data:
                return False

            # Obtener estado actual para recalcular step
            current = self.get_or_create(contact_id, "")
            merged = {**current, **update_data}

            # Recalcular current_step e is_complete
            step = 1
            for field in self.STEP_FIELDS:
                if merged.get(field):
                    step += 1
                else:
                    break
            update_data["current_step"] = min(step, 5)
            update_data["is_complete"] = all(merged.get(f) for f in self.STEP_FIELDS)

            self.client.table("lead_states") \
                .update(update_data) \
                .eq("contact_id", contact_id) \
                .execute()

            logger.info("Lead state actualizado: %s (step=%s)", list(update_data.keys()), update_data['current_step'])
            return True

        except Exception as e:
            logger.error("Error actualizando lead_state: %s", e)
            return False

    def is_complete(self, contact_id: str) -> bool:
        """Retorna True si el lead tiene todos los 5 datos."""
        if not self.client:
            return False
        try:
            response = self.client.table("lead_states") \
                .select("is_complete") \
                .eq("contact_id", contact_id) \
                .limit(1) \
                .execute()
            if response.data:
                return response.data[0].get("is_complete", False)
            return False
        except Exception as e:
            logger.error("Error en is_complete: %s", e)
            return False

    def get_current_step(self, contact_id: str) -> int:
        """Retorna el paso actual (1-5)."""
        if not self.client:
            return 1
        try:
            response = self.client.table("lead_states") \
                .select("current_step") \
                .eq("contact_id", contact_id) \
                .limit(1) \
                .execute()
            if response.data:
                return response.data[0].get("current_step", 1)
            return 1
        except Exception as e:
            logger.error("Error en get_current_step: %s", e)
            return 1

    def set_booking_sent(self, contact_id: str) -> bool:
        """Marca que se envió el booking link con timestamp."""
        if not self.client:
            return False
        try:
            self.client.table("lead_states") \
                .update({"booking_sent_at": datetime.now(timezone.utc).isoformat()}) \
                .eq("contact_id", contact_id) \
                .execute()
            logger.info("Booking sent marcado para %s", contact_id)
            return True
        except Exception as e:
            logger.error("Error en set_booking_sent: %s", e)
            return False

    def increment_post_booking_count(self, contact_id: str) -> int:
        """Incrementa el contador post-booking y retorna el nuevo valor."""
        if not self.client:
            return 0
        try:
            # Obtener valor actual
            response = self.client.table("lead_states") \
                .select("post_booking_count") \
                .eq("contact_id", contact_id) \
                .limit(1) \
                .execute()

            current_count = 0
            if response.data:
                current_count = response.data[0].get("post_booking_count", 0) or 0

            new_count = current_count + 1
            self.client.table("lead_states") \
                .update({"post_booking_count": new_count}) \
                .eq("contact_id", contact_id) \
                .execute()

            logger.info("Post-booking count: %s para %s", new_count, contact_id)
            return new_count

        except Exception as e:
            logger.error("Error en increment_post_booking_count: %s", e)
            return 0

    def update_score(self, contact_id: str, score: int) -> bool:
        """Actualiza el score del lead."""
        if not self.client:
            return False
        try:
            self.client.table("lead_states") \
                .update({"score": score}) \
                .eq("contact_id", contact_id) \
                .execute()
            return True
        except Exception as e:
            logger.error("Error en update_score: %s", e)
            return False

    def get_booking_state(self, contact_id: str) -> dict:
        """
        Retorna estado del booking para post-booking logic.
        Returns: {"sent": bool, "post_booking_count": int}
        """
        if not self.client:
            return {"sent": False, "post_booking_count": 0}
        try:
            response = self.client.table("lead_states") \
                .select("booking_sent_at, post_booking_count") \
                .eq("contact_id", contact_id) \
                .limit(1) \
                .execute()

            if response.data:
                row = response.data[0]
                return {
                    "sent": row.get("booking_sent_at") is not None,
                    "post_booking_count": row.get("post_booking_count", 0) or 0,
                }
            return {"sent": False, "post_booking_count": 0}

        except Exception as e:
            logger.error("Error en get_booking_state: %s", e)
            return {"sent": False, "post_booking_count": 0}

    @staticmethod
    def _empty_state(contact_id: str, location_id: str) -> dict:
        """Estado vacío como fallback."""
        return {
            "contact_id": contact_id,
            "location_id": location_id,
            "campus": None,
            "programa": None,
            "nombre_completo": None,
            "telefono": None,
            "email": None,
            "current_step": 1,
            "is_complete": False,
            "booking_sent_at": None,
            "post_booking_count": 0,
            "score": 0,
            "channel": None,
        }
