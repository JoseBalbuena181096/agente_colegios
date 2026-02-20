import os
import logging
import requests
import json
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class GHLService:
    """
    Servicio GHL con soporte multi-campus.
    Selecciona automáticamente las credenciales correctas según location_id.
    """

    def __init__(self, campus_registry=None):
        self.base_url = "https://services.leadconnectorhq.com"
        self._registry = campus_registry
        # Token por defecto (CSA Puebla) para compatibilidad hacia atrás
        self.default_token = os.getenv("token_csa_puebla")

        if not self.default_token:
            logger.warning("GHL 'token_csa_puebla' not found in env")
    
    def get_token_for_location(self, location_id: str) -> str:
        """
        Obtiene el token correcto para una locación específica.
        Si no encuentra la locación, usa el token por defecto (Puebla).
        """
        if location_id and self._registry:
            cfg = self._registry.get_config(location_id)
            if cfg:
                token = os.getenv(cfg["token_key"])
                if token:
                    logger.info(f"Usando credenciales de: {cfg['name']}")
                    return token
                else:
                    logger.warning(f"Token no encontrado para {cfg['name']}, usando default")
            else:
                logger.warning(f"Location ID '{location_id}' no reconocido, usando default (Puebla)")
        elif location_id:
            logger.warning(f"Location ID '{location_id}' no reconocido, usando default (Puebla)")

        return self.default_token
            
    def get_conversation_id(self, contact_id: str, location_id: str = None) -> str:
        """
        Busca el ID de la conversación activa para un contacto.
        Esto es crítico para canales como Instagram/Facebook que requieren conversationId.
        """
        token = self.get_token_for_location(location_id)
        url = f"{self.base_url}/conversations/search"
        headers = {
            'Authorization': f'Bearer {token}',
            'Version': '2021-04-15',
            'Content-Type': 'application/json'
        }
        params = {'contactId': contact_id, 'limit': 1}
        
        try:
            logger.info(f"Buscando conversación en GHL para contact_id: {contact_id}...")
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Debug rápido de la respuesta
            # print(f"   Response search: {json.dumps(data)}") 
            
            if data.get('conversations') and len(data['conversations']) > 0:
                conv_id = data['conversations'][0]['id']
                logger.info(f"Conversation ID encontrado en GHL: {conv_id}")
                return conv_id
            
            logger.warning(f"No se encontró ninguna conversación para este contacto en GHL.")
            return None
        except Exception as e:
            logger.error(f"Error buscando conversation_id en API GHL: {e}")
            return None

    def get_conversation_messages(self, conversation_id: str, location_id: str = None, limit: int = 20) -> list:
        """
        Obtiene los últimos N mensajes de una conversación.
        """
        token = self.get_token_for_location(location_id)
        url = f"{self.base_url}/conversations/{conversation_id}/messages"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Version': '2021-04-15',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        params = {'limit': limit}
        
        try:
            logger.info(f"Obteniendo mensajes de conversación {conversation_id}...")
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('messages', [])
            
        except Exception as e:
            logger.error(f"Error obteniendo mensajes de GHL: {e}")
            return []

    def send_message(self, contact_id: str, message: str, message_type: str = "Facebook", conversation_id: str = None, location_id: str = None):
        """
        Envía un mensaje a un contacto via GHL API V2
        Prioriza conversation_id si está disponible (mejor para IG/FB).
        """
        token = self.get_token_for_location(location_id)
        url = f"{self.base_url}/conversations/messages"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Version': '2021-04-15',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Payload dinámico: enviar SIEMPRE contactId, y conversationId opcionalmente
        payload = {
            "type": message_type, 
            "contactId": contact_id,
            "message": message,
            "subject": "Respuesta IA"
        }
        
        if conversation_id:
            payload["conversationId"] = conversation_id
        
        try:
            logger.info(f"Enviando mensaje ({message_type}) via GHL...")
            if conversation_id:
                logger.info(f"Using Contact ID: {contact_id} + Conversation ID: {conversation_id}")
            else:
                logger.info(f"Using Contact ID: {contact_id}")
            
            # Usar json.dumps con ensure_ascii=False para preservar acentos
            import json
            response = requests.post(url, headers=headers, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'))
            response.raise_for_status()
            logger.info(f"Mensaje enviado: {response.json()}")
            return response.json()

        except Exception as e:
            logger.error(f"Error enviando mensaje a GHL: {e}")
            if 'response' in locals():
                logger.error(f"Detalle: {response.text}")
            return None

    def update_contact_field(self, contact_id: str, field_key: str, value: str, location_id: str = None):
        """
        Actualiza un campo personalizado de un contacto para disparar un Workflow de respuesta.
        Estrategia Híbrida para evitar limitaciones de la API de Conversaciones.
        
        Args:
            contact_id: ID del contacto en GHL
            field_key: Key del custom field (ej: 'response_content')
            value: Valor a asignar (la respuesta de la IA)
            location_id: ID de la locación para usar credenciales correctas
        """
        token = self.get_token_for_location(location_id)
        url = f"{self.base_url}/contacts/{contact_id}"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Version': '2021-07-28',  # Versión más reciente para Contacts
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Nota: La estructura para actualizar customFields puede variar según la versión
        # En API V2 suele ser 'customFields': [{'key': 'key_name', 'value': 'val'}] 
        # o un objeto directo dependiendo del endpoint.
        # Asumiremos la estructura flexible de key-value o la lista estándar.
        # Para mayor robustez, intentaremos la estructura estándar de V2:
        
        payload = {
            "customFields": [
                {
                    "key": field_key,
                    "value": value
                }
            ]
        }
        
        try:
            logger.info(f"Actualizando contacto {contact_id} campo '{field_key}'...")
            response = requests.put(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"Contacto actualizado: {response.status_code}")
            return response.json()
        except Exception as e:
            logger.error(f"Error actualizando contacto en GHL: {e}")
            if 'response' in locals():
                logger.error(f"Detalle: {response.text}")
            return None

    def update_contact_fields(self, contact_id: str, fields: dict, location_id: str = None):
        """
        Actualiza múltiples campos de un contacto (estándar y personalizados).
        
        Args:
            contact_id: ID del contacto en GHL
            fields: Diccionario con los campos a actualizar.
                    Claves soportadas:
                    - 'full_name': Se divide en firstName y lastName
                    - 'phone': Número de teléfono
                    - 'email': Correo electrónico
                    - 'program_interest': Campo personalizado para carrera de interés
            location_id: ID de la locación para credenciales
        """
        if not fields:
            return None
            
        token = self.get_token_for_location(location_id)
        url = f"{self.base_url}/contacts/{contact_id}"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Version': '2021-07-28',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        payload = {}
        custom_fields = []
        
        for key, value in fields.items():
            if not value:
                continue
                
            if key == 'full_name':
                # Dividir nombre completo en firstName y lastName
                parts = value.strip().split(' ', 1)
                payload['firstName'] = parts[0]
                if len(parts) > 1:
                    payload['lastName'] = parts[1]
            elif key == 'phone':
                # Asegurar formato de teléfono
                phone = ''.join(filter(str.isdigit, value))
                if len(phone) == 10:
                    payload['phone'] = f"+52{phone}"
                elif len(phone) > 10:
                    payload['phone'] = f"+{phone}"
            elif key == 'email':
                payload['email'] = value
            elif key == 'program_interest':
                # Campo personalizado para carrera de interés
                custom_fields.append({
                    "key": "Oferta Educativa De Interés",
                    "value": value
                })
        
        if custom_fields:
            payload['customFields'] = custom_fields
        
        if not payload:
            logger.info(f"No hay campos válidos para actualizar")
            return None
        
        try:
            logger.info(f"Actualizando contacto {contact_id} con campos: {list(fields.keys())}...")
            response = requests.put(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"Campos actualizados en GHL: {list(payload.keys())}")
            return response.json()
        except Exception as e:
            logger.error(f"Error actualizando campos en GHL: {e}")
            if 'response' in locals():
                logger.error(f"Detalle: {response.text}")
            return None

    def add_tag(self, contact_id: str, tag: str, location_id: str = None):
        """
        Agrega una etiqueta/tag a un contacto.
        Útil para clasificar leads como 'Proceso de Ventas' o 'No es Ventas'.
        """
        token = self.get_token_for_location(location_id)
        url = f"{self.base_url}/contacts/{contact_id}/tags"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Version': '2021-07-28',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        payload = {
            "tags": [tag]
        }
        
        try:
            logger.info(f"Agregando tag '{tag}' a contacto {contact_id}...")
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"Tag agregado: {tag}")
            return response.json()
        except Exception as e:
            logger.error(f"Error agregando tag: {e}")
            if 'response' in locals():
                logger.error(f"Detalle: {response.text}")
            return None

    def remove_tag(self, contact_id: str, tag: str, location_id: str = None):
        """
        Elimina una etiqueta/tag de un contacto.
        """
        token = self.get_token_for_location(location_id)
        url = f"{self.base_url}/contacts/{contact_id}/tags"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Version': '2021-07-28',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        payload = {
            "tags": [tag]
        }
        
        try:
            logger.info(f"Quitando tag '{tag}' de contacto {contact_id}...")
            response = requests.delete(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"Tag eliminado: {tag}")
            return response.json()
        except Exception as e:
            logger.warning(f"Error quitando tag (puede que no existiera): {e}")
            return None

    def add_note(self, contact_id: str, note_body: str, location_id: str = None) -> dict:
        """
        Agrega una nota a un contacto.
        Útil para preservar historial de conversación en transferencias FB/IG.
        
        Args:
            contact_id: ID del contacto en GHL
            note_body: Contenido de la nota
            location_id: ID de la locación para credenciales
        
        Returns:
            dict con la nota creada o None si falla
        """
        token = self.get_token_for_location(location_id)
        url = f"{self.base_url}/contacts/{contact_id}/notes"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Version': '2021-07-28',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        payload = {
            "body": note_body
        }
        
        try:
            logger.info(f"Agregando nota al contacto {contact_id}...")
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"Nota agregada exitosamente")
            return response.json()
        except Exception as e:
            logger.error(f"Error agregando nota: {e}")
            if 'response' in locals():
                logger.error(f"Detalle: {response.text}")
            return None

    def get_location_id_for_campus(self, campus_name: str) -> str:
        """
        Convierte nombre de campus a location_id.
        """
        if not campus_name:
            return None
        if self._registry:
            return self._registry.get_location_id(campus_name)
        return None

    def get_campus_name(self, location_id: str) -> str:
        """
        Obtiene el nombre del campus basado en el location_id.
        """
        if self._registry:
            return self._registry.get_campus_name(location_id)
        return "Puebla"


    def get_contact(self, contact_id: str, location_id: str = None) -> dict:
        """
        Obtiene los datos completos de un contacto.
        """
        token = self.get_token_for_location(location_id)
        url = f"{self.base_url}/contacts/{contact_id}"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Version': '2021-07-28',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json().get('contact', {})
        except Exception as e:
            logger.error(f"Error obteniendo contacto: {e}")
            return None

    def create_contact(self, contact_data: dict, location_id: str) -> str:
        """
        Crea un contacto en la locación especificada.
        Retorna el nuevo contact_id.
        """
        token = self.get_token_for_location(location_id)
        url = f"{self.base_url}/contacts"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Version': '2021-07-28',
            'Content-Type': 'application/json'
        }
        
        # Preparar payload - solo incluir campos con valores
        payload = {"locationId": location_id}
        
        if contact_data.get("firstName"):
            payload["firstName"] = contact_data["firstName"]
        if contact_data.get("lastName"):
            payload["lastName"] = contact_data["lastName"]
        if contact_data.get("name"):
            payload["name"] = contact_data["name"]
        if contact_data.get("email"):
            payload["email"] = contact_data["email"]
        if contact_data.get("phone"):
            payload["phone"] = contact_data["phone"]
        
        # Tags
        tags = contact_data.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        if "Transferido" not in tags:
            tags.append("Transferido")
        payload["tags"] = tags
        
        try:
            logger.info(f"Creando contacto en nueva locación...")
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            new_contact = response.json().get('contact', {})
            new_id = new_contact.get('id')
            logger.info(f"Contacto creado: {new_id}")
            return new_id
        except Exception as e:
            logger.error(f"Error creando contacto: {e}")
            if 'response' in locals():
                logger.error(f"Detalle: {response.text}")
            return None

    def delete_contact(self, contact_id: str, location_id: str = None) -> bool:
        """
        Elimina un contacto de la locación.
        """
        token = self.get_token_for_location(location_id)
        url = f"{self.base_url}/contacts/{contact_id}"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Version': '2021-07-28'
        }
        
        try:
            logger.info(f"Eliminando contacto de locación origen...")
            response = requests.delete(url, headers=headers)
            response.raise_for_status()
            logger.info(f"Contacto eliminado de origen")
            return True
        except Exception as e:
            logger.error(f"Error eliminando contacto: {e}")
            return False

    def transfer_contact_to_campus(self, contact_id: str, source_location_id: str, target_campus: str) -> tuple:
        """
        Transfiere un contacto de una locación a otra (copia + elimina).
        
        Returns:
            tuple: (new_contact_id, target_location_id) o (None, None) si falla
        """
        # 1. Obtener location_id destino
        target_location_id = self.get_location_id_for_campus(target_campus)
        if not target_location_id:
            logger.error(f"Campus '{target_campus}' no reconocido")
            return None, None
        
        # 2. Verificar que no sea la misma locación
        if target_location_id == source_location_id:
            logger.info(f"El contacto ya está en el campus correcto")
            return contact_id, source_location_id
        
        # 3. Obtener datos del contacto origen
        target_name = self.get_campus_name(target_location_id) if target_location_id else target_campus
        logger.info(f"Iniciando transferencia a {target_name}...")
        contact_data = self.get_contact(contact_id, source_location_id)
        if not contact_data:
            logger.error(f"No se pudo obtener datos del contacto")
            return None, None
        
        # 4. Crear contacto en destino
        new_contact_id = self.create_contact(contact_data, target_location_id)
        if not new_contact_id:
            logger.error(f"No se pudo crear contacto en destino")
            return None, None
        
        # 5. Eliminar contacto de origen
        deleted = self.delete_contact(contact_id, source_location_id)
        if not deleted:
            logger.warning(f"Contacto creado en destino pero no se pudo eliminar del origen")
        
        logger.info(f"Transferencia completada a {target_name}")
        return new_contact_id, target_location_id
