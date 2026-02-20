"""
Service for querying campus and career information from Supabase.
"""
import logging
from app.services.supabase_client import get_supabase

logger = logging.getLogger(__name__)

class CampusService:
    def __init__(self):
        self.client = get_supabase()

    def get_campus_by_name(self, campus_name: str) -> dict | None:
        """
        Obtiene información del campus por nombre.
        Incluye fallback: si ILIKE falla, compara sin espacios para matchear
        variantes como 'pozarica' → 'Poza Rica'.
        """
        if not self.client or not campus_name:
            return None

        try:
            # Intento 1: ILIKE directo
            response = self.client.table("campuses").select("*").ilike("name", f"%{campus_name}%").limit(1).execute()
            if response.data:
                return response.data[0]

            # Intento 2: Fallback — comparar sin espacios
            normalized = campus_name.replace(" ", "").lower()
            all_campuses = self.client.table("campuses").select("*").execute()
            if all_campuses.data:
                for campus in all_campuses.data:
                    if campus["name"].replace(" ", "").lower() == normalized:
                        return campus
        except Exception as e:
            logger.error("Error obteniendo campus: %s", e)

        return None

    def get_campus_by_location_id(self, location_id: str) -> dict | None:
        """
        Obtiene información del campus por location_id de GHL.
        """
        if not self.client or not location_id:
            return None

        try:
            response = self.client.table("campuses").select("*").eq("location_id", location_id).limit(1).execute()
            if response.data:
                return response.data[0]
        except Exception as e:
            logger.error("Error obteniendo campus por location_id: %s", e)

        return None

    def get_careers_by_campus_name(self, campus_name: str) -> list[dict]:
        """
        Obtiene lista de carreras para un campus.
        Retorna list[dict] con keys: name, website_url, program_type.
        """
        if not self.client or not campus_name:
            return []

        try:
            campus = self.get_campus_by_name(campus_name)
            if not campus:
                return []

            response = self.client.table("careers").select("name, website_url, program_type").eq("campus_id", campus["id"]).execute()
            if response.data:
                return response.data
        except Exception as e:
            logger.error("Error obteniendo carreras: %s", e)

        return []

    def get_careers_by_location_id(self, location_id: str) -> list[dict]:
        """
        Obtiene lista de carreras para un campus por location_id.
        Retorna list[dict] con keys: name, website_url, program_type.
        """
        if not self.client or not location_id:
            return []

        try:
            campus = self.get_campus_by_location_id(location_id)
            if not campus:
                return []

            response = self.client.table("careers").select("name, website_url, program_type").eq("campus_id", campus["id"]).execute()
            if response.data:
                return response.data
        except Exception as e:
            logger.error("Error obteniendo carreras por location_id: %s", e)

        return []

    def get_campus_context(self, location_id: str) -> str:
        """
        Genera un contexto simplificado para el agente.
        Incluye: nombre del campus, dirección, teléfono, website y lista de carreras.
        """
        campus = self.get_campus_by_location_id(location_id)
        if not campus:
            return "Información del campus no disponible."

        careers = self.get_careers_by_location_id(location_id)

        website = campus.get('website_url', '')
        website_line = f"\nWEBSITE: {website}" if website else ""

        context = f"""
CAMPUS: {campus.get('name', 'N/A')}
DIRECCIÓN: {campus.get('address', 'Consultar')}
TELÉFONO: {campus.get('phone', 'Consultar')}{website_line}

NIVELES EDUCATIVOS DISPONIBLES:
"""
        for career in careers:
            name = career.get("name", career) if isinstance(career, dict) else career
            url = career.get("website_url") if isinstance(career, dict) else None
            program_type = career.get("program_type", "nivel") if isinstance(career, dict) else "nivel"
            url_part = f" → {url}" if url else ""
            context += f"- {name} ({program_type}){url_part}\n"

        return context.strip()
