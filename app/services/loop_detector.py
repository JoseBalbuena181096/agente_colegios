import difflib
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class LoopDetector:
    """
    Servicio UNIFICADO para detección de bucles semánticos.
    
    Dos niveles de detección:
    - HISTORY_THRESHOLD (0.70): Verifica si los últimos 2 mensajes del bot ya son repetitivos.
      Se usa ANTES de invocar al LLM para evitar gastar tokens innecesariamente.
    - PROACTIVE_THRESHOLD (0.95): Verifica si la respuesta que el bot PLANEA enviar 
      es casi idéntica a una anterior. Se usa DESPUÉS de generar la respuesta.
    """
    
    HISTORY_THRESHOLD = 0.70   # Pre-LLM: ¿los últimos 2 mensajes del bot ya se repiten?
    PROACTIVE_THRESHOLD = 0.95  # Post-LLM: ¿la respuesta nueva es idéntica a una anterior?
    
    @staticmethod
    def detect_history_loop(history: List[Dict[str, Any]]) -> bool:
        """
        Verifica si los últimos 2 mensajes del ASISTENTE en el historial son repetitivos.
        Se ejecuta ANTES de llamar al LLM.
        
        Returns:
            True si los últimos 2 mensajes del bot son >70% similares (bucle en progreso)
        """
        assistant_msgs = [m['content'] for m in history if m.get('role') == 'assistant']
        
        if len(assistant_msgs) < 2:
            return False
        
        msg_recent = assistant_msgs[-1]
        msg_previous = assistant_msgs[-2]
        
        ratio = difflib.SequenceMatcher(None, msg_recent.lower(), msg_previous.lower()).ratio()
        logger.info("Loop History Check: %.2f (threshold: %.2f)", ratio, LoopDetector.HISTORY_THRESHOLD)
        
        if ratio > LoopDetector.HISTORY_THRESHOLD:
            logger.warning("Bucle DETECTADO (Historial): '%s...'", msg_recent[:30])
            return True
        
        return False
    
    @staticmethod
    def detect_loop(history: List[Dict[str, Any]], proposed_response: str) -> bool:
        """
        Detecta si la respuesta PROPUESTA es casi idéntica a respuestas anteriores del bot.
        Se ejecuta DESPUÉS de generar la respuesta, ANTES de enviarla.
        
        Returns:
            True si la respuesta propuesta es >95% similar a alguna anterior
        """
        if not history or not proposed_response:
            return False
            
        bot_msgs = [m['content'] for m in history if m.get('role') == 'assistant']
        
        if not bot_msgs:
            return False
            
        recent_bot_msgs = bot_msgs[-3:]
        
        for past_msg in recent_bot_msgs:
            ratio = difflib.SequenceMatcher(None, proposed_response.lower(), past_msg.lower()).ratio()
            
            if ratio > LoopDetector.PROACTIVE_THRESHOLD:
                logger.warning("Loop Proactivo Detectado: '%s...' vs '%s...' (Ratio: %.2f)", proposed_response[:30], past_msg[:30], ratio)
                return True
                
        return False

