from pydantic import BaseModel, Field

class AgentResponse(BaseModel):
    """
    Modelo estructurado para la respuesta del agente.
    Adapted for Colegios San Ángel (3 planteles).
    """
    is_relevant_query: bool = Field(
        description="""True SOLO si el usuario es un PROSPECTO genuino interesado en inscribir a su hijo/a.

MARCAR TRUE si menciona:
- Interés en cualquier nivel educativo (preescolar, primaria, secundaria, bachillerato)
- Preguntas sobre colegiaturas, inscripciones, horarios, becas
- Interés en información del colegio
- Ya está en proceso de dar datos para agendar cita

MARCAR FALSE si:
- Es un NEGOCIO o EMPRESA
- Solo envía saludos vacíos ("Hola", "Hi") sin contexto previo
- Respuestas a stories sin intención de inscribir
- Spam o mensajes irrelevantes
- Dice "Gracias" después de recibir el link de cita"""
    )

    message: str = Field(
        description="Mensaje de respuesta para el usuario. Debe ser amable, informativo, conciso y terminar con pregunta de engagement."
    )
    post_context_used: bool = Field(
        default=False,
        description="Indica si se utilizó contexto adicional del post de Facebook/Instagram"
    )
    detected_campus: str = Field(
        default="",
        description="Plantel mencionado por el usuario. Valores válidos: 'puebla', 'coatzacoalcos', 'pozarica'. Vacío si no menciona ninguno."
    )

    captured_data: dict = Field(
        default={},
        description="""Datos capturados del usuario en ESTE turno de conversación.

SOLO incluir datos que el usuario haya proporcionado EXPLÍCITAMENTE en su mensaje actual.
Claves válidas:
- 'full_name': Nombre completo del padre/madre/tutor
- 'phone': Teléfono de 10 dígitos
- 'email': Correo electrónico
- 'program_interest': Nivel educativo de interés (Preescolar, Primaria, Secundaria, Bachillerato)

NO incluir datos que ya estaban en el historial o que fueron inferidos."""
    )


    def get_full_message(self) -> str:
        """Retorna el mensaje completo."""
        return self.message


class MessageAnalysis(BaseModel):
    """
    Análisis del mensaje del usuario para determinar si se necesita contexto del post.
    """
    needs_post_context: bool = Field(
        description="True si el mensaje es genérico y necesita contexto del post. False si ya menciona un nivel educativo específico."
    )
    mentioned_program: str = Field(
        default="",
        description="Nombre del nivel educativo mencionado en el mensaje, si existe."
    )
    reasoning: str = Field(
        description="Explicación breve de por qué se tomó esta decisión."
    )
