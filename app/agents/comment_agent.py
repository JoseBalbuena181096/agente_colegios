import os
from typing import TypedDict, List
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from app.services.llm_client import get_chat_model
from app.models.response_models import AgentResponse


# Mensaje fijo para redirección a WhatsApp
# TODO: Actualizar con el número de WhatsApp de Colegios San Ángel
WHATSAPP_REDIRECT_MESSAGE = """👋 ¡Gracias por tu interés en Colegio San Ángel!

Para brindarte una atención personalizada, continúa la conversación por WhatsApp: https://wa.me/522221691699"""

# 2. Definir Estado del Agente
class CommentAgentState(TypedDict):
    messages: List[BaseMessage]
    contact_id: str
    user_name: str
    post_context: str
    structured_response: AgentResponse | None

# 3. Definir Nodo
def comment_agent_node(state: CommentAgentState):
    """
    Nodo especializado para responder COMENTARIOS PÚBLICOS de Facebook/Instagram.
    Solo DETECTA interés y responde con mensaje fijo de WhatsApp.
    """
    messages = state["messages"]
    user_name = state.get("user_name", "Usuario")
    post_context = state.get("post_context", "")

    post_context_section = ""
    if post_context:
        post_context_section = f"""

CONTEXTO ADICIONAL DEL POST:
El usuario comentó en un post que contiene la siguiente información:
{post_context}

Usa esta información adicional para determinar mejor si hay interés.
"""

    system_prompt = f"""Eres un EXPERTO EN VENTAS Y CLASIFICACIÓN DE LEADS para Colegio San Ángel.
Tu misión es filtrar el ruido y detectar ÚNICAMENTE OPORTUNIDADES DE VENTA REALES.

ANALIZA EL COMENTARIO COMO UN VENDEDOR TIBURÓN:
¿Este usuario quiere inscribir a su hijo/a o solo está socializando?

🚨 CRITERIOS DE ACTIVACIÓN (TRUE - "ES UN LEAD"):
Marca TRUE solo si detectas una INTENCIÓN DE ACCIÓN relacionada con inscripción:
1. Petición Directa: "Info", "Información", "Precio", "Costo", "Colegiatura", "Requisitos".
2. Interés en Oferta Educativa: Menciona niveles educativos ("preescolar", "primaria", "secundaria", "bachillerato", "prepa").
3. Intención de Visita/Contacto: "¿Dónde están?", "Teléfono", "Quiero ir", "¿Tienen inscripciones abiertas?".
4. Dudas de Admisión: "¿Cuándo inician clases?", "Inscripciones", "Requisitos de ingreso".
5. Palabras clave DE VENTA: "Info", "Costos", "Informes", "Becas".
6. Horarios/Modalidad: "¿Qué horarios?", "¿Tienen turno vespertino?".

💤 CRITERIOS DE DESACTIVACIÓN (FALSE - "SOLO ENGAGEMENT"):
Marca FALSE si es interacción social sin intención de inscripción:
1. Halagos/Opiniones: "Qué bonito colegio", "Me encanta", "Excelente escuela".
2. Saludos/Etiquetas: "Hola", "@Amigo mira esto" (sin pedir info).
3. Emojis sueltos: "🔥", "😍", "👏".
4. Ex-alumnos/padres: "Yo estudié ahí", "Mi hijo estudia ahí".
5. Spam o Quejas.

REGLA DE ORO:
- "Qué bonita escuela" -> FALSE
- "Bonita escuela, ¿tienen becas?" -> TRUE
- "Info" -> TRUE
"""

    prompt_messages = [SystemMessage(content=system_prompt)] + messages

    model = get_chat_model(structured_output=AgentResponse)
    structured_response: AgentResponse = model.invoke(prompt_messages)

    final_message = WHATSAPP_REDIRECT_MESSAGE if structured_response.is_relevant_query else ""

    ai_message = AIMessage(content=final_message)
    structured_response.message = final_message

    return {
        "messages": [ai_message],
        "structured_response": structured_response
    }

# 4. Construir Grafo
workflow = StateGraph(CommentAgentState)
workflow.add_node("comment_agent", comment_agent_node)
workflow.set_entry_point("comment_agent")
workflow.add_edge("comment_agent", END)

comment_agent = workflow.compile()
