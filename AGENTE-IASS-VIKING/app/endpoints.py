from flask import Flask, request, jsonify, redirect
import json
import requests
import threading
import uuid
import logging
from datetime import datetime
import pytz
from datetime import timedelta
import xmlrpc.client
from bs4 import BeautifulSoup
import os
import re
from threading import Thread, Event
import time

from app.utils import remove_thinking_block, create_svg_base64
from app.anthropic_handler import generate_response
from app.openai_responses_handler import generate_response_openai_mcp
from app.gemini_handler import generate_response_gemini

logger = logging.getLogger(__name__)

def get_provider_info(model_id, llm_id=None):
    """
    Determina el proveedor y modelo específico basado en model_id y llm_id
    
    Returns:
        tuple: (provider, model_name)
    """
    # Log para debugging
    logger.info(f"[PROVIDER_INFO] model_id='{model_id}', llm_id='{llm_id}'")
    
    # Validar llm_id - considerar None, cadena vacía y espacios como "no especificado"
    effective_llm_id = llm_id if llm_id and llm_id.strip() else None
    
    if model_id == 'gemini':
        model_name = effective_llm_id or "gemini-2.0-flash"
        return "Google", model_name
    elif model_id == 'openai' or model_id == 'opeanai-o3':
        model_name = effective_llm_id or "gpt-5"
        return "OpenAI", model_name
    elif model_id == 'deepseek':
        model_name = effective_llm_id or "deepseek-chat"
        return "DeepSeek", model_name
    else:  # Default Anthropic
        model_name = effective_llm_id or "gpt-5"
        return "OpenAI", model_name

def categorize_error(error_message):
    """
    Categoriza el tipo de error basado en el mensaje para determinar el código HTTP apropiado.
    
    Returns:
        tuple: (error_type, http_code, user_message)
    """
    error_message_lower = error_message.lower()
    
    # Errores de API/LLM (502 Bad Gateway)
    if any(keyword in error_message_lower for keyword in [
        'error de comunicación', 'api', 'anthropic', 'openai', 'gemini', 
        'rate limit', 'quota', 'unauthorized', 'forbidden'
    ]):
        return "API_ERROR", 502, "Error de comunicación con el servicio de IA"
    
    # Errores de N8N/servicios externos (503 Service Unavailable)
    elif any(keyword in error_message_lower for keyword in [
        'n8n', 'webhook', 'servicio no disponible', 'conexión rechazada',
        'timeout de red', 'servicio externo'
    ]):
        return "SERVICE_ERROR", 503, "Error en servicios externos"
    
    # Errores de configuración (500 Internal Server Error)
    elif any(keyword in error_message_lower for keyword in [
        'api key', 'configuración', 'archivo no encontrado', 'clave no configurada',
        'configurada', 'missing', 'not found'
    ]):
        return "CONFIG_ERROR", 500, "Error de configuración del servidor"
    
    # Errores de timeout (408 Request Timeout)
    elif any(keyword in error_message_lower for keyword in [
        'timeout', 'tiempo agotado', 'tiempo límite', 'expired'
    ]):
        return "TIMEOUT_ERROR", 408, "Tiempo de procesamiento agotado"
    
    # Error genérico (500 Internal Server Error)
    else:
        return "UNKNOWN_ERROR", 500, "Error interno del servidor"

# Mapa para asociar valores de 'assistant' con nombres de archivos de prompts
ASSISTANT_FILES = {
    0: "PROMPTS/ENERGITEL/AGENTE_ENERGITEL_INICIAL.txt",
    5: "PROMPTS/ENERGITEL/AGENTE_ENERGITEL_INICIAL.txt"  # Default/fallback
}

# Configuración MCP para cada asistente - Simple y directo
ASSISTANT_MCP_SERVERS = {
    0: {
        "type": "mcp",
        "server_url": os.environ.get("MCP_SERVER_URL_0", "https://automatizacion.ssantacruz.co/mcp/baseDatosEnergitel/sse"),
        "server_label": "mcp-sql",
        "require_approval": "never"
    }
}

def init_endpoints(app, conversation_manager, thread_locks):
    """Inicializa todos los endpoints de la aplicación Flask"""
    
    @app.route('/sendmensaje', methods=['POST'])
    def send_message():
        # Capturar tiempo de inicio para calcular duración
        start_time = time.time()
        
        logger.info("Endpoint /sendmensaje llamado")
        data = request.json

        # Extraer parámetros principales
    
        message = data.get('message')
        assistant_value = data.get('assistant')
        thread_id = data.get('thread_id')
        subscriber_id = data.get('subscriber_id')
        
        # Soportar tanto ai_provider como modelID para compatibilidad
        ai_provider = data.get('ai_provider', '').lower()
        model_id = data.get('model_id', data.get('modelID', ai_provider)).lower()
        
        telefono = data.get('telefono')
        direccionCliente = data.get('direccionCliente')
        llm_id = data.get('llm_id', data.get('llmID'))  # Soportar ambos nombres
        # authorized_mcp puede venir como int o lista
        authorized_mcp_raw = data.get('authorized_mcp', [])
        if isinstance(authorized_mcp_raw, int):
            authorized_mcp = [authorized_mcp_raw]  # Convertir int a lista
        elif isinstance(authorized_mcp_raw, list):
            authorized_mcp = authorized_mcp_raw
        else:
            authorized_mcp = []
        use_cache_control = data.get('use_cache_control', False)  # Cache control flag

        logger.info("MENSAJE CLIENTE: %s", message)
        # Extraer variables adicionales para sustitución
        variables = data.copy()
        keys_to_remove = [
            'api_key', 'message', 'assistant', 'thread_id', 'subscriber_id',
            'thinking', 'modelID', 'model_id', 'ai_provider', 'direccionCliente', 
            'use_cache_control', 'llmID', 'llm_id'
        ]
        for key in keys_to_remove:
            variables.pop(key, None)

        # Validaciones obligatorias
        if not message:
            logger.warning("Mensaje vacío recibido")
            return jsonify({"error": "El mensaje no puede estar vacío"}), 400

        if not subscriber_id:
            logger.warning("Falta subscriber_id")
            return jsonify({"error": "Falta el subscriber_id"}), 400

        # Configuración de API keys por modelo
        api_key = None
        if model_id == 'deepseek':
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                logger.error("API key de DeepSeek no configurada")
                return jsonify({"error":
                                "Configuración del servidor incompleta"}), 500
        elif model_id == 'anthropic':
            # Solo para casos específicos de Anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("API key de Anthropic no configurada")
                return jsonify({"error":
                                "Configuración del servidor incompleta"}), 500
        else:
            # Default: OpenAI (para casos vacíos y otros)
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.error("API key de OpenAI no configurada")
                return jsonify({"error":
                                "Configuración del servidor incompleta"}), 500

        # Generar o validar thread_id
        if not thread_id:
    # Solo generar nuevo UUID si NO viene thread_id
            thread_id = f"thread_{uuid.uuid4()}"
            logger.info("Nuevo thread_id generado: %s", thread_id)
        else:
    # Si viene thread_id, usar exactamente ese
            logger.info("Usando thread_id proporcionado: %s", thread_id)

        # Cargar contenido del asistente basado en el valor de 'assistant'
        assistant_content = ""
        logger.info("\n=== CARGA DE ASISTENTE ===")
        logger.info("Assistant value recibido: %s (tipo: %s)", assistant_value, type(assistant_value))
        
        if assistant_value is not None:
            assistant_file = ASSISTANT_FILES.get(assistant_value)
            logger.info("Archivo de asistente mapeado: %s", assistant_file)
            
            if assistant_file:
                try:
                    assistant_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), assistant_file)
                    logger.info("Ruta completa del archivo: %s", assistant_path)
                    logger.info("Archivo existe: %s", os.path.exists(assistant_path))
                    
                    with open(assistant_path, 'r', encoding='utf-8') as file:
                        assistant_content = file.read()
                        logger.info("Contenido del archivo cargado exitosamente - Longitud: %d caracteres", len(assistant_content))
                        logger.info("Primeras 200 caracteres del prompt: %s...", assistant_content[:200])

                        # Sustitución de variables
                        pattern = re.compile(r'\{\{(\w+)\}\}')
                        
                        def replace_placeholder(match):
                            key = match.group(1)
                            value = variables.get(key, "[UNDEFINED]")
                            logger.debug("Reemplazando variable {{%s}} con: %s", key, value)
                            return str(value)

                        assistant_content = pattern.sub(replace_placeholder, assistant_content)
                        logger.info("Variables sustituidas en el prompt")

                    logger.info("✅ ARCHIVO DE ASISTENTE CARGADO EXITOSAMENTE: %s para assistant=%s", assistant_file, assistant_value)
                except FileNotFoundError:
                    logger.error("❌ Archivo de asistente NO ENCONTRADO: %s", assistant_path)
                    logger.warning("Usando prompt por defecto debido a archivo no encontrado")
                    assistant_content = "Eres un asistente útil."
                except Exception as e:
                    logger.error("❌ Error cargando archivo de asistente: %s", str(e))
                    return jsonify(
                        {"error": f"Error al cargar el asistente: {str(e)}"}), 500
            else:
                logger.warning("⚠️ No hay archivo definido para assistant=%s en ASSISTANT_FILES", assistant_value)
                logger.info("Usando prompt por defecto")
                assistant_content = "Eres un asistente útil."
        else:
            logger.warning("⚠️ Assistant value es None, usando prompt por defecto")
            assistant_content = "Eres un asistente útil."
        
        logger.info("=== FIN CARGA DE ASISTENTE ===")
        logger.info("Prompt final tiene %d caracteres", len(assistant_content))

        # Inicializar/Mantener conversación
        if not conversation_manager.exists(thread_id):
            conversation_data = {
                "status": "processing",
                "response": None,
                "messages": [],
                "assistant": assistant_value,
                "telefono": telefono,
                "direccionCliente": direccionCliente,
                "usage": None
            }
            conversation_manager.set(thread_id, conversation_data)
            logger.info("Nueva conversación creada: %s", thread_id)
        else:
            current_conversation = conversation_manager.get(thread_id)
            updates = {
                "assistant": assistant_value or current_conversation.get("assistant"),
                "telefono": telefono,
                "direccionCliente": direccionCliente
            }
            conversation_manager.update(thread_id, updates)

        # --- Asegurar que haya un lock para este thread_id ---
        if thread_id not in thread_locks:
            thread_locks[thread_id] = threading.Lock()
            logger.info("Lock creado para thread_id: %s", thread_id)

        # Crear y ejecutar hilo según el modelo
        event = Event()

        try:
            if model_id == 'opeanai-o3':
                thread = Thread(target=generate_response_openai,
                               args=(message, assistant_content,
                                    thread_id, event, subscriber_id, llm_id))
                logger.info("Ejecutando LLM2 para thread_id: %s", thread_id)

            elif model_id == 'gemini':
                thread = Thread(target=generate_response_gemini,
                                args=(message, assistant_content,
                                      thread_id, event, subscriber_id),
                                kwargs={'conversation_manager': conversation_manager, 'thread_locks': thread_locks})
                logger.info("Ejecutando Gemini para thread_id: %s", thread_id)

            elif model_id == 'openai':
                # Preparar configuración MCP para el handler
                mcp_servers = []
                if authorized_mcp:
                    for mcp_num in authorized_mcp:
                        if mcp_num in ASSISTANT_MCP_SERVERS:
                            mcp_config = ASSISTANT_MCP_SERVERS[mcp_num]
                            mcp_servers.append({
                                'config': mcp_config,
                                'number': mcp_num
                            })
                            logger.info("Configurando MCP #%d: %s -> %s", mcp_num, mcp_config["server_label"], mcp_config["server_url"])
                        else:
                            logger.warning("Número MCP no válido: %s", mcp_num)
                
                # Usar el handler OpenAI Responses con MCP
                thread = Thread(target=generate_response_openai_mcp,
                                args=(message, assistant_content,
                                      thread_id, event, subscriber_id, llm_id),
                                kwargs={
                                    'conversation_manager': conversation_manager, 
                                    'thread_locks': thread_locks,
                                    'mcp_servers': mcp_servers,
                                    'assistant_number': assistant_value
                                })
                logger.info("Ejecutando OpenAI Responses con %d MCP(s) para thread_id: %s", len(mcp_servers), thread_id)

            else:  # Default to OpenAI
                # Preparar configuración MCP para el handler default
                mcp_servers = []
                if authorized_mcp:
                    for mcp_num in authorized_mcp:
                        if mcp_num in ASSISTANT_MCP_SERVERS:
                            mcp_config = ASSISTANT_MCP_SERVERS[mcp_num]
                            mcp_servers.append({
                                'config': mcp_config,
                                'number': mcp_num
                            })
                            logger.info("Configurando MCP default #%d: %s -> %s", mcp_num, mcp_config["server_label"], mcp_config["server_url"])
                        else:
                            logger.warning("Número MCP default no válido: %s", mcp_num)
                
                # Usar OpenAI Responses como default
                thread = Thread(target=generate_response_openai_mcp,
                                args=(message, assistant_content,
                                      thread_id, event, subscriber_id, llm_id),
                                kwargs={
                                    'conversation_manager': conversation_manager, 
                                    'thread_locks': thread_locks,
                                    'mcp_servers': mcp_servers,
                                    'assistant_number': assistant_value
                                })
                logger.info("Ejecutando OpenAI Responses default con %d MCP(s) para thread_id: %s", len(mcp_servers), thread_id)

            thread.start()
            
            # Esperar con timeout específico
            timeout_occurred = not event.wait(timeout=60)
            
            if timeout_occurred:
                logger.error(f"Timeout de 60 segundos alcanzado para thread_id: {thread_id}")
                
                # Calcular duración para el timeout
                end_time = time.time()
                request_duration = round(end_time - start_time, 3)
                provider, model_name = get_provider_info(model_id, llm_id)
                
                # Marcar la conversación como error por timeout
                conversation_manager.update(thread_id, {
                    "status": "error",
                    "response": "Timeout: Tiempo de procesamiento agotado después de 60 segundos"
                })
                
                return jsonify({
                    "error": True,
                    "error_type": "TIMEOUT_ERROR",
                    "message": "Tiempo de procesamiento agotado",
                    "details": "El procesamiento tardó más de 60 segundos y fue cancelado",
                    "thread_id": thread_id,
                    "model_info": {
                        "provider": provider,
                        "model": model_name,
                        "model_id": model_id
                    },
                    "request_duration": request_duration,
                    "request_duration_ms": round(request_duration * 1000)
                }), 408

            # Preparar respuesta final
            conversation = conversation_manager.get(thread_id)
            if not conversation:
                # Calcular duración para el error 404
                end_time = time.time()
                request_duration = round(end_time - start_time, 3)
                provider, model_name = get_provider_info(model_id, llm_id)
                
                logger.error(f"Conversación {thread_id} no encontrada para respuesta")
                return jsonify({
                    "error": True,
                    "error_type": "UNKNOWN_ERROR", 
                    "message": "Error interno del servidor",
                    "details": "Conversación no encontrada",
                    "thread_id": thread_id,
                    "model_info": {
                        "provider": provider,
                        "model": model_name,
                        "model_id": model_id
                    },
                    "request_duration": request_duration,
                    "request_duration_ms": round(request_duration * 1000)
                }), 404

            # Calcular duración de la solicitud
            end_time = time.time()
            request_duration = round(end_time - start_time, 3)  # En segundos con 3 decimales
            
            # Obtener información del modelo y proveedor
            provider, model_name = get_provider_info(model_id, llm_id)

            response_data = {
                "thread_id": thread_id,
                "usage": conversation.get("usage"),
                "model_info": {
                    "provider": provider,
                    "model": model_name,
                    "model_id": model_id
                },
                "request_duration": request_duration,
                "request_duration_ms": round(request_duration * 1000)  # También en milisegundos
            }

            if conversation.get("status") == "completed":
                original_response = conversation.get("response", "")
                logger.info(f"📦 [ENDPOINT] Status: completed")
                logger.info(f"📦 [ENDPOINT] Response from conversation: '{original_response}'")
                logger.info(f"📦 [ENDPOINT] Response length: {len(original_response)}")
                logger.info(f"📦 [ENDPOINT] Response type: {type(original_response)}")

                # SIMPLIFICADO: Usar respuesta directa sin procesamiento de thinking
                response_data["response"] = original_response
                response_data["razonamiento"] = ""  # Simplificado - sin razonamiento separado
                
                logger.info(f"📦 [ENDPOINT] Final response_data keys: {list(response_data.keys())}")
                logger.info(f"📦 [ENDPOINT] Final response_data['response']: '{response_data['response']}'")

                return jsonify(response_data)

            elif conversation.get("status") == "error":
                # Manejo detallado de errores
                error_message = conversation.get("response", "Error desconocido")
                error_type, http_code, user_message = categorize_error(error_message)
                
                logger.error(f"Error categorizado como {error_type} para thread_id {thread_id}: {error_message}")
                
                error_response = {
                    "error": True,
                    "error_type": error_type,
                    "message": user_message,
                    "details": error_message,
                    "thread_id": thread_id,
                    "usage": conversation.get("usage"),
                    "model_info": {
                        "provider": provider,
                        "model": model_name,
                        "model_id": model_id
                    },
                    "request_duration": request_duration,
                    "request_duration_ms": round(request_duration * 1000)
                }
                
                return jsonify(error_response), http_code

            else:
                # Estado en procesamiento o desconocido
                response_data["response"] = "Procesando..."
                return jsonify(response_data)

        except Exception as e:
            logger.exception("Error crítico en el endpoint: %s", str(e))
            
            # Calcular duración incluso para errores críticos
            end_time = time.time()
            request_duration = round(end_time - start_time, 3)
            
            # Categorizar el error crítico
            error_type, http_code, user_message = categorize_error(str(e))
            
            # Obtener info del modelo si las variables están disponibles
            provider, model_name = None, None
            if 'model_id' in locals() and 'llm_id' in locals():
                provider, model_name = get_provider_info(model_id, llm_id)
            
            error_response = {
                "error": True,
                "error_type": error_type,
                "message": user_message,
                "details": str(e),
                "thread_id": thread_id if 'thread_id' in locals() else None,
                "request_duration": request_duration,
                "request_duration_ms": round(request_duration * 1000)
            }
            
            # Agregar información del modelo si está disponible
            if provider and model_name:
                error_response["model_info"] = {
                    "provider": provider,
                    "model": model_name,
                    "model_id": model_id
                }
            
            return jsonify(error_response), http_code

    @app.route('/extract', methods=['POST'])
    def extract():
        logger.info("Endpoint /extract llamado")
        try:
            # Verificar si el body contiene un JSON bien formateado
            if not request.is_json:
                error_result = {
                    "status": "error",
                    "message":
                    "El body de la solicitud no está en formato JSON válido"
                }
                logger.warning("Solicitud no es JSON válida")
                return jsonify(error_result), 400

            # Obtener los datos JSON de la solicitud
            data = request.get_json()

            # Extraer los campos específicos directamente del body
            nombre = data.get('nombre', '')
            apellido = data.get('apellido', '')
            cedula = data.get('cedula', '')
            ciudad = data.get('ciudad', '')
            solicitud = data.get('solicitud', '')
            contactar = data.get('contactar', '')

            # Crear el resultado en el formato deseado
            result = {
                "nombre": nombre,
                "apellido": apellido,
                "cedula": cedula,
                "ciudad": ciudad,
                "solicitud": solicitud,
                "contactar": contactar,
                "status": "success"
            }

            logger.info("Datos extraídos correctamente: %s", result)
            return jsonify(result)

        except Exception as e:
            # Manejar cualquier error que pueda ocurrir
            error_result = {"status": "error", "message": str(e)}
            logger.exception("Error en /extract: %s", e)
            return jsonify(error_result), 400

    @app.route('/letranombre', methods=['POST'])
    def letra_nombre():
        # Obtener los datos JSON de la solicitud
        data = request.json
        name = data.get('text', '').strip()  # Eliminar espacios en blanco

        if not name:
            return jsonify({'error': 'No se proporcionó texto'}), 400

        # Extraer la primera letra y convertirla a mayúscula
        first_letter = name[0].upper()

        # Definir resoluciones
        resoluciones = [1920, 1024, 512, 256, 128]
        imagenes = {}

        # Generar SVG para cada resolución
        for resolucion in resoluciones:
            base64_img, svg_code = create_svg_base64(first_letter, resolucion,
                                                     resolucion)
            imagenes[f'avatar_{resolucion}'] = {
                'base64': base64_img,
                'svg': svg_code
            }

        # Devolver las imágenes en formato JSON
        return jsonify(imagenes)

    @app.route('/time', methods=['POST'])
    def convert_time():
        logger.info("Endpoint /time llamado")
        data = request.json
        input_time = data.get('datetime')

        if not input_time:
            logger.warning("Falta el parámetro 'datetime'")
            return jsonify({"error": "Falta el parámetro 'datetime'"}), 400

        try:
            local_time = datetime.fromisoformat(input_time)
            utc_time = local_time.astimezone(pytz.utc)
            new_time = utc_time + timedelta(hours=1)
            new_time_str = new_time.strftime('%Y-%m-%dT%H:%M:%SZ')
            result = {"original": input_time, "converted": new_time_str}
            logger.info("Tiempo convertido: %s", result)
            return jsonify(result)
        except Exception as e:
            logger.exception("Error al convertir el tiempo: %s", e)
            return jsonify({"error": str(e)}), 400

    # Agrega el nuevo endpoint /upload
    
    # Endpoint removido - funcionalidad n8n no necesaria