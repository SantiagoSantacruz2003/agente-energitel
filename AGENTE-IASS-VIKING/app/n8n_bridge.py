import os
import json
import logging
from datetime import datetime, timezone
import requests

logger = logging.getLogger(__name__)

# Mapea cada function tool a su webhook/config de n8n.
# Las herramientas MCP NO usan este bridge y mantienen su flujo original.
N8N_WEBHOOKS = {
    "cambiar_nombre": {
        "url": os.getenv("N8N_CAMBIAR_NOMBRE_URL", "https://automatizacion.ssantacruz.co/webhook/cambiarNombreEnergitelApi"),
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "timeout": 60
    },
    # Agrega aquí más herramientas, p.ej.:
    # "crear_direccion": {
    #     "url": "https://TU-N8N/webhook/crear_direccion",
    #     "method": "POST",
    #     "headers": {"Content-Type": "application/json"},
    #     "timeout": 30
    # },
}

def execute_n8n_function_tool(tool_name, tool_args, assistant_number, subscriber_id, thread_id):
    """
    Bridge específico para FUNCTION TOOLS hacia n8n.
    Las herramientas MCP mantienen su flujo original sin modificaciones.
    
    NO hace validaciones de negocio: eso vive en el Schema (OpenAI) o en n8n.
    Devuelve dict (JSON) o {"ok": True, "data": "..."} si la respuesta es texto.
    """
    cfg = N8N_WEBHOOKS.get(tool_name)
    if not cfg:
        return {"error": f"Tool '{tool_name}' no configurada en N8N_WEBHOOKS"}

    url = cfg.get("url")
    if not url:
        return {"error": f"Tool '{tool_name}' sin URL en N8N_WEBHOOKS"}

    method = (cfg.get("method") or "POST").upper()
    headers = cfg.get("headers") or {"Content-Type": "application/json"}
    timeout = int(cfg.get("timeout") or 30)

    # Payload específico para function tools con datos completos del contexto
    payload = {
        "ai_data": tool_args or {},
        "subscriber_id": subscriber_id,
        "thread_id": thread_id,
        "assistant": assistant_number,
        "tool_name": tool_name,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    try:
        logger.info(f"🔗 [N8N BRIDGE] Enviando {tool_name} a {url}")
        logger.info(f"🔗 [N8N BRIDGE] Payload: {json.dumps(payload, indent=2)}")
        
        resp = requests.request(method, url, json=payload, headers=headers, timeout=timeout)
        
    except requests.Timeout:
        logger.error(f"🔗 [N8N BRIDGE] Timeout llamando webhook n8n para {tool_name}")
        return {"error": "timeout llamando webhook n8n", "tool_name": tool_name}
    except requests.RequestException as e:
        logger.error(f"🔗 [N8N BRIDGE] Error de red: {str(e)} para {tool_name}")
        return {"error": f"error de red: {str(e)}", "tool_name": tool_name}

    if 200 <= resp.status_code < 300:
        logger.info(f"🔗 [N8N BRIDGE] ✅ Respuesta exitosa de {tool_name}: HTTP {resp.status_code}")
        logger.info(f"🔗 [N8N BRIDGE] ✅ Status Code: {resp.status_code}")
        logger.info(f"🔗 [N8N BRIDGE] ✅ Response Headers: {dict(resp.headers)}")
        logger.info(f"🔗 [N8N BRIDGE] ✅ Response Size: {len(resp.text)} characters")
        
        # Log del contenido completo de la respuesta
        if resp.text:
            logger.info(f"🔗 [N8N BRIDGE] ✅ Raw Response Body: {resp.text}")
        else:
            logger.info(f"🔗 [N8N BRIDGE] ⚠️ Empty response body")
        
        try:
            result = resp.json()
            logger.info(f"🔗 [N8N BRIDGE] ✅ Parsed JSON Response:")
            logger.info(f"🔗 [N8N BRIDGE] {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            # Log de campos específicos si existen
            if isinstance(result, dict):
                if 'success' in result:
                    logger.info(f"🔗 [N8N BRIDGE] ✅ Success: {result['success']}")
                if 'message' in result:
                    logger.info(f"🔗 [N8N BRIDGE] ✅ Message: {result['message']}")
                if 'data' in result:
                    logger.info(f"🔗 [N8N BRIDGE] ✅ Data: {result['data']}")
            
            return result
        except ValueError as json_error:
            logger.info(f"🔗 [N8N BRIDGE] ⚠️ Response no es JSON válido: {str(json_error)}")
            logger.info(f"🔗 [N8N BRIDGE] ✅ Text Response: {resp.text}")
            return {"ok": True, "data": resp.text, "raw_response": resp.text}
    else:
        # Log detallado de errores HTTP
        logger.error(f"🔗 [N8N BRIDGE] ❌ Error HTTP {resp.status_code} para {tool_name}")
        logger.error(f"🔗 [N8N BRIDGE] ❌ Error Headers: {dict(resp.headers)}")
        
        body_preview = (resp.text or "")[:1000]
        logger.error(f"🔗 [N8N BRIDGE] ❌ Error Body (first 1000 chars): {body_preview}")
        
        if len(resp.text) > 1000:
            logger.error(f"🔗 [N8N BRIDGE] ❌ Full Error Body: {resp.text}")
        
        return {"error": f"HTTP {resp.status_code}", "body": body_preview, "tool_name": tool_name, "full_body": resp.text}