"""
Tools de LangChain para consultar información de planteles desde Supabase.
Adapted for Colegios San Ángel.
"""
from langchain_core.tools import tool
from app.services.campus_service import CampusService

# Instancia del servicio
_campus_service = CampusService()


@tool
def get_campus_info(campus_name: str) -> str:
    """
    Obtiene información de un plantel específico incluyendo dirección, teléfono y sitio web.

    Args:
        campus_name: Nombre del plantel (Puebla, Poza Rica, Coatzacoalcos)

    Returns:
        Información del plantel con dirección, teléfono y website.
    """
    campus = _campus_service.get_campus_by_name(campus_name)
    if not campus:
        return f"No se encontró información para el plantel: {campus_name}"

    website = campus.get('website_url', '')
    website_line = f"\nSitio web: {website}" if website else ""

    return f"""
Plantel: {campus.get('name', 'N/A')}
Dirección: {campus.get('address', 'Consultar')}
Teléfono: {campus.get('phone', 'Consultar')}{website_line}
"""


@tool
def get_careers_by_campus(campus_name: str) -> str:
    """
    Obtiene los niveles educativos disponibles en un plantel específico de Colegio San Ángel.

    Args:
        campus_name: Nombre del plantel (Puebla, Poza Rica, Coatzacoalcos)

    Returns:
        Lista de niveles educativos disponibles en ese plantel.
    """
    careers = _campus_service.get_careers_by_campus_name(campus_name)
    if not careers:
        return f"No se encontraron niveles educativos para el plantel: {campus_name}"

    # Agrupar por program_type
    grouped: dict[str, list] = {}
    for career in careers:
        name = career.get("name", str(career)) if isinstance(career, dict) else career
        url = career.get("website_url") if isinstance(career, dict) else None
        program_type = career.get("program_type", "nivel") if isinstance(career, dict) else "nivel"
        grouped.setdefault(program_type, []).append((name, url))

    type_labels = {
        "preescolar": "PREESCOLAR",
        "primaria": "PRIMARIA",
        "secundaria": "SECUNDARIA",
        "bachillerato": "BACHILLERATO",
    }
    type_order = ["preescolar", "primaria", "secundaria", "bachillerato"]

    result = f"Niveles educativos disponibles en plantel {campus_name}:\n\n"
    for ptype in type_order:
        if ptype not in grouped:
            continue
        label = type_labels.get(ptype, ptype.upper())
        result += f"{label}:\n"
        for name, url in grouped[ptype]:
            url_part = f" → {url}" if url else ""
            result += f"- {name}{url_part}\n"
        result += "\n"

    # Tipos no esperados
    for ptype, items in grouped.items():
        if ptype not in type_order:
            result += f"{ptype.upper()}:\n"
            for name, url in items:
                url_part = f" → {url}" if url else ""
                result += f"- {name}{url_part}\n"
            result += "\n"

    return result.rstrip()


# Lista de tools disponibles para exportar
campus_tools = [get_campus_info, get_careers_by_campus]
