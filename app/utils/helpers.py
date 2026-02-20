from typing import Dict, Any

def get_nested_value(data: Dict[str, Any], keys: list) -> Any:
    """Intenta obtener un valor navegando por una lista de claves."""
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current

def get_value_flexible(data: Dict[str, Any], field_name: str) -> Any:
    """
    Busca un valor en múltiples ubicaciones del payload, 
    manejando keys con espacios/tabs malformados de GHL.
    """
    # Lista de posibles ubicaciones donde buscar
    locations = [
        # Root level
        lambda: data.get(field_name),
        # customData (key normal)
        lambda: get_nested_value(data, ['customData', field_name]),
        # customData con tab al final (bug de GHL)
        lambda: get_nested_value(data, ['customData', f'{field_name}\t']),
        # location object (para location_id)
        lambda: get_nested_value(data, ['location', 'id']) if field_name == 'location_id' else None,
    ]
    
    for get_func in locations:
        try:
            value = get_func()
            if value:
                return value
        except:
            continue
    
    return None

def detect_channel(source: str) -> str:
    """
    Normaliza el source/canal a formato GHL API.
    Centralizado para evitar duplicación (antes copiado 5+ veces en conversations.py).
    
    Returns:
        'WhatsApp', 'FB', 'IG', 'SMS', 'GMB'
    """
    source_lower = (source or '').lower()
    
    if 'whatsapp' in source_lower or 'whats' in source_lower:
        return 'WhatsApp'
    elif 'facebook' in source_lower or 'fb' in source_lower or 'messenger' in source_lower:
        return 'FB'
    elif 'instagram' in source_lower or 'ig' in source_lower:
        return 'IG'
    elif 'sms' in source_lower:
        return 'SMS'
    elif 'gmb' in source_lower or 'google' in source_lower:
        return 'GMB'
    else:
        return 'WhatsApp'  # Default fallback
