import logging
from datetime import datetime
from app.services.supabase_client import get_supabase

logger = logging.getLogger(__name__)

class AdvisorService:
    """
    Servicio para gestionar la rotación de asesores por campus.
    Usa round-robin basado en assigned_count para distribución equitativa.
    Consulta por location_id para evitar problemas de nombres.
    """

    def __init__(self, campus_registry=None):
        self._registry = campus_registry
        self.supabase = get_supabase()

    def get_next_advisor(self, location_id: str) -> dict:
        """
        Obtiene el siguiente asesor para un campus usando round-robin.
        Consulta por location_id para evitar problemas de nombres.

        Args:
            location_id: ID de la ubicación en GHL

        Returns:
            dict con: id, name, booking_link o None si no hay asesores
        """
        if not self.supabase:
            logger.warning("Supabase no disponible para AdvisorService")
            return None

        try:
            # Buscar asesor activo con menor asignaciones por location_id
            response = self.supabase.table("advisors") \
                .select("id, name, booking_link, assigned_count, campus") \
                .eq("location_id", location_id) \
                .eq("is_active", True) \
                .order("assigned_count", desc=False) \
                .limit(1) \
                .execute()

            if response.data and len(response.data) > 0:
                advisor = response.data[0]
                logger.info("Asesor seleccionado: %s (campus: %s, location: %s)", advisor['name'], advisor.get('campus', '?'), location_id)
                return advisor
            else:
                logger.warning("No hay asesores activos para location_id: %s", location_id)
                return None

        except Exception as e:
            logger.error("Error obteniendo asesor: %s", e)
            return None

    def get_next_advisor_by_campus(self, campus_name: str) -> dict:
        """
        Fallback: Obtiene asesor resolviendo campus name → location_id.
        Útil cuando solo se tiene el nombre del campus.
        """
        loc_id = self._registry.get_location_id(campus_name) if self._registry else None

        if loc_id:
            return self.get_next_advisor(loc_id)
        else:
            logger.warning("Campus '%s' no mapeado a location_id", campus_name)
            return None

    def get_advisor_by_ghl_user(self, ghl_user_id: str) -> dict:
        """
        Busca un asesor por su GHL user ID (assignedTo del contacto).
        Esto permite enviar el booking link del vendedor que ya tiene
        asignado el lead en GHL.

        Returns:
            dict con: id, name, booking_link o None si no se encuentra
        """
        if not self.supabase or not ghl_user_id:
            return None

        try:
            response = self.supabase.table("advisors") \
                .select("id, name, booking_link, campus, assigned_count") \
                .eq("ghl_user_id", ghl_user_id) \
                .eq("is_active", True) \
                .limit(1) \
                .execute()

            if response.data and len(response.data) > 0:
                advisor = response.data[0]
                logger.info("Asesor por GHL user ID: %s (ghl_user: %s)", advisor['name'], ghl_user_id)
                return advisor
            else:
                logger.warning("No hay asesor con ghl_user_id: %s", ghl_user_id)
                return None

        except Exception as e:
            logger.error("Error buscando asesor por ghl_user_id: %s", e)
            return None

    def increment_advisor_count(self, advisor_id: str) -> bool:
        """
        Incrementa el contador de leads asignados al asesor.
        """
        if not self.supabase:
            return False

        try:
            response = self.supabase.table("advisors") \
                .select("assigned_count") \
                .eq("id", advisor_id) \
                .single() \
                .execute()

            current_count = response.data.get("assigned_count", 0) if response.data else 0

            self.supabase.table("advisors") \
                .update({
                    "assigned_count": current_count + 1,
                    "last_assigned_at": datetime.now().isoformat()
                }) \
                .eq("id", advisor_id) \
                .execute()

            logger.info("Asesor %s: asignaciones = %s", advisor_id, current_count + 1)
            return True

        except Exception as e:
            logger.error("Error incrementando contador: %s", e)
            return False

    def get_default_booking_link(self) -> str:
        """Retorna el link de booking por defecto (fallback)."""
        return "https://link.superleads.mx/widget/booking/o33ctHxdbcr7Q7wmarJY"
