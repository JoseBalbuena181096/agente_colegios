"""
LeadScoringService: Scoring determinista de leads basado en señales de datos.
No usa LLM — puntaje calculado con reglas fijas.
"""

import re

# Tabla de puntos por señal
SCORING_RULES = {
    "campus_mentioned": 10,
    "career_mentioned": 15,
    "name_provided": 10,
    "phone_provided": 15,
    "email_provided": 15,
    "fast_response": 10,        # Responde en < 5 min
    "lead_form_origin": 20,     # Viene de Lead Form
    "whatsapp_channel": 5,      # Canal WhatsApp
    "inscription_keywords": 20, # Keywords de inscripción
    "lead_form_complete": 30,   # Lead Form con todos los datos
}

# Keywords que indican intención de inscripción
INSCRIPTION_KEYWORDS = [
    "inscribirme", "inscripción", "inscripcion", "inscribir a mi hijo",
    "inscribir a mi hija", "me quiero inscribir", "inicio de clases",
    "cuando empiezan", "cuándo empiezan", "cuando empiezo", "cuándo empiezo",
    "próximo ciclo", "proximo ciclo", "periodo escolar", "ciclo escolar",
    "registrarme", "registrar a mi hijo", "inscripcion preescolar",
    "inscripcion primaria", "inscripcion secundaria", "inscripcion bachillerato",
    "quiero inscribir", "nuevo ingreso",
]

# Score tags
SCORE_TAGS = {
    "frio": {"min": 0, "max": 25, "tag": "Lead Frio"},
    "tibio": {"min": 26, "max": 50, "tag": "Lead Tibio"},
    "caliente": {"min": 51, "max": 80, "tag": "Lead Caliente"},
    "urgente": {"min": 81, "max": 999, "tag": "Lead Urgente"},
}

ALL_SCORE_TAGS = [v["tag"] for v in SCORE_TAGS.values()]


def calculate_score(
    lead_state: dict,
    message: str = "",
    channel: str = "",
    is_lead_form: bool = False,
    lead_form_data: dict = None,
    response_time_seconds: float = None,
) -> int:
    """
    Calcula el score del lead de forma determinista.

    Args:
        lead_state: Estado actual del lead (de lead_states table)
        message: Último mensaje del usuario
        channel: Canal de comunicación
        is_lead_form: Si el mensaje viene de un Lead Form
        lead_form_data: Datos del Lead Form (si aplica)
        response_time_seconds: Tiempo de respuesta en segundos (si disponible)

    Returns:
        Score numérico (0-150+)
    """
    score = 0

    # --- Señales desde lead_state ---
    if lead_state.get("campus"):
        score += SCORING_RULES["campus_mentioned"]

    if lead_state.get("programa"):
        score += SCORING_RULES["career_mentioned"]

    if lead_state.get("nombre_completo"):
        score += SCORING_RULES["name_provided"]

    if lead_state.get("telefono"):
        score += SCORING_RULES["phone_provided"]

    if lead_state.get("email"):
        score += SCORING_RULES["email_provided"]

    # --- Señales desde contexto ---
    if channel and channel.lower() in ["whatsapp", "sms"]:
        score += SCORING_RULES["whatsapp_channel"]

    if response_time_seconds is not None and response_time_seconds < 300:
        score += SCORING_RULES["fast_response"]

    # --- Señales desde Lead Form ---
    if is_lead_form:
        score += SCORING_RULES["lead_form_origin"]
        if lead_form_data:
            form_fields = ["full_name", "phone", "email", "campus"]
            filled = sum(1 for f in form_fields if lead_form_data.get(f))
            if filled >= 3:
                score += SCORING_RULES["lead_form_complete"]

    # --- Keywords de inscripción en mensaje ---
    if message:
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in INSCRIPTION_KEYWORDS):
            score += SCORING_RULES["inscription_keywords"]

    return score


def get_score_tag(score: int) -> str:
    """
    Retorna el tag correspondiente al score.

    Returns:
        "Lead Frio", "Lead Tibio", "Lead Caliente", o "Lead Urgente"
    """
    for tier in SCORE_TAGS.values():
        if tier["min"] <= score <= tier["max"]:
            return tier["tag"]
    return "Lead Frio"
