"""
Tool de LangChain para consultar el playbook de objeciones.
El agente lo invoca cuando detecta una objeción del prospecto.
"""

from langchain_core.tools import tool


# Referencia al servicio — se inyecta desde dependencies
_objection_service = None


def init_objection_tool(objection_service):
    """Inyecta el servicio de objeciones (llamado desde dependencies)."""
    global _objection_service
    _objection_service = objection_service


@tool
def get_objection_response(topic: str) -> str:
    """
    Busca una respuesta estandarizada para una objeción o duda del prospecto.
    Usar cuando el usuario pregunta sobre: colegiaturas, becas, horarios,
    transporte escolar, modelo educativo, instalaciones, proceso de inscripción,
    uniformes/materiales, o ubicación del plantel.

    Args:
        topic: El tema de la objeción o duda del usuario (ej: "colegiaturas", "becas", "horarios", "transporte")

    Returns:
        Respuesta estandarizada para manejar la objeción, o mensaje de fallback.
    """
    if not _objection_service:
        return "Esa es una excelente pregunta. En la cita con tu asesor podrás resolver todas tus dudas. ¿Te gustaría agendar?"

    result = _objection_service.match_objection(topic)
    if result:
        response = result["response_template"]
        if result.get("redirect_to_booking"):
            response += " ¿Te gustaría agendar tu cita para conocer todos los detalles?"
        return response

    return "Esa es una excelente pregunta. En la cita con tu asesor podrás resolver todas tus dudas. ¿Te gustaría agendar?"


# Lista de tools para exportar
objection_tools = [get_objection_response]
