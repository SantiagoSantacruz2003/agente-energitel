"""
Anthropic Handler - Manejador específico para Claude
"""

import json
import anthropic
import threading
import os
import time
import logging
from functools import wraps

# Servicios n8n eliminados - se manejará con MCP

logger = logging.getLogger(__name__)

# Herramientas se manejarán vía MCP
TOOL_FUNCTIONS = {}

def retry_on_exception(max_retries=3, initial_wait=1):
    """Reintenta llamadas a la API con backoff exponencial."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    wait_time = initial_wait * (2 ** retries)
                    if retries >= max_retries:
                        logger.error(f"Error definitivo tras {max_retries} intentos: {e}")
                        raise
                    logger.warning(f"Error en llamada a API (intento {retries}). Reintentando en {wait_time}s: {e}")
                    time.sleep(wait_time)
        return wrapper
    return decorator

@retry_on_exception(max_retries=3, initial_wait=1)
def call_anthropic_api(client, **kwargs):
    """Llama a la API de Anthropic con reintentos automáticos."""
    return client.messages.create(**kwargs)

def validate_conversation_history(history):
    """Valida que la estructura del historial sea correcta para Anthropic."""
    if not isinstance(history, list):
        logger.error("El historial no es una lista")
        return False

    for message in history:
        # Validar estructura básica del mensaje
        if not isinstance(message, dict):
            logger.error("Mensaje no es un diccionario: %s", message)
            return False

        if "role" not in message or message["role"] not in ["user", "assistant"]:
            logger.error("Rol inválido en mensaje: %s", message)
            return False

        if "content" not in message:
            logger.error("Falta contenido en mensaje: %s", message)
            return False

    return True

def get_field(item, key):
    """Obtiene un campo de un objeto o diccionario de forma segura."""
    if item is None:
        return None

    if isinstance(item, dict):
        return item.get(key)

    try:
        return getattr(item, key, None)
    except Exception as e:
        logger.warning("Error al acceder a atributo %s: %s", key, e)
        return None

def generate_response(
    api_key,
    message,
    assistant_content_text,
    thread_id,
    event,
    subscriber_id,
    use_cache_control,
    llm_id=None,
    conversation_manager=None,
    thread_locks=None
    ):
    if not llm_id:
        llm_id = "claude-3-5-haiku-latest"

    logger.info("Intentando adquirir lock para thread_id: %s", thread_id)
    lock = thread_locks.get(thread_id)
    if not lock:
        logger.error("No se encontró lock para thread_id: %s", thread_id)
        thread_locks[thread_id] = threading.Lock()
        lock = thread_locks[thread_id]

    with lock:
        logger.info("Lock adquirido para thread_id: %s", thread_id)
        start_time = time.time()
        
        # Log del mensaje del usuario
        logger.info("👤 USUARIO MENSAJE para thread_id %s: %s", thread_id, message[:150] + "..." if len(message) > 150 else message)

        try:
            # Obtener conversación actual
            conversation = conversation_manager.get(thread_id)
            if not conversation:
                logger.error(f"Conversación {thread_id} no encontrada")
                conversation_manager.set(thread_id, {
                    "status": "error",
                    "response": "Conversación no encontrada",
                    "messages": []
                })
                return

            client = anthropic.Anthropic(api_key=api_key)
            conversation_history = conversation.get("messages", [])

            # Agregar el mensaje del usuario al historial
            user_message_content = {"type": "text", "text": message}
            if use_cache_control:
                user_message_content["cache_control"] = {"type": "ephemeral"}
            conversation_history.append({
                "role": "user",
                "content": [user_message_content]
            })

            # Cargar herramientas
            assistant_value = conversation.get("assistant")
            assistant_str = str(assistant_value)
            
            # Cargar herramientas desde archivo único
            tools_file_path = os.path.join(os.path.dirname(__file__), '..', 'tools', 'default_tools.json')
            with open(tools_file_path, "r", encoding="utf-8") as tools_file:
                tools = json.load(tools_file)

            # Configurar sistema
            assistant_content = [{"type": "text", "text": assistant_content_text}]

            # Usar herramientas desde variable global
            tool_functions = TOOL_FUNCTIONS

            # Iniciar interacción con el modelo
            while True:
                # Validar estructura de mensajes antes de enviar
                if not validate_conversation_history(conversation_history):
                    logger.error("Estructura de mensajes inválida: %s", conversation_history)
                    raise ValueError("Estructura de conversación inválida")

                try:
                    logger.info("PAYLOAD ANTHROPIC: %s", conversation_history)
                    # Llamar a la API con reintentos
                    logger.info("Llamando a Anthropic API para thread_id: %s", thread_id)
                    response = call_anthropic_api(
                        client=client,
                        model=llm_id,
                        max_tokens=1000,
                        temperature=0.8,
                        system=assistant_content,
                        tools=tools,
                        messages=conversation_history
                    )
                    logger.info("RESPUESTA RAW ANTHROPIC: %s", response)
                    # Procesar respuesta
                    conversation_history.append({
                        "role": "assistant",
                        "content": response.content
                    })

                    # Almacenar tokens
                    usage = {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "cache_creation_input_tokens": response.usage.cache_creation_input_tokens,
                        "cache_read_input_tokens": response.usage.cache_read_input_tokens,
                    }
                    
                    # Actualizar conversación con tokens y mensajes
                    conversation_manager.update(thread_id, {
                        "usage": usage,
                        "messages": conversation_history
                    })

                    logger.info(
                        "Tokens utilizados - Input: %d, Output: %d",
                        usage["input_tokens"],
                        usage["output_tokens"]
                    )
                    logger.info("Cache Creation Input Tokens: %d", 
                                usage["cache_creation_input_tokens"])
                    logger.info("Cache Read Input Tokens: %d", 
                                usage["cache_read_input_tokens"])

                    # Procesar herramientas
                    if response.stop_reason == "tool_use":
                        tool_use_blocks = [block for block in response.content if get_field(block, "type") == "tool_use"]

                        if not tool_use_blocks:
                            # Si no hay herramientas, procesamos la respuesta final
                            assistant_response_text = ""
                            for content_block in response.content:
                                if get_field(content_block, "type") == "text":
                                    assistant_response_text += (get_field(content_block, "text") or "")
                            
                            # Log de la respuesta final de la IA
                            logger.info("🤖 ANTHROPIC RESPUESTA FINAL para thread_id %s: %s", thread_id, assistant_response_text[:200] + "..." if len(assistant_response_text) > 200 else assistant_response_text)
                            
                            conversation_manager.update(thread_id, {
                                "response": assistant_response_text,
                                "status": "completed",
                                "messages": conversation_history
                            })
                            break

                        # Procesar herramienta
                        tool_use = tool_use_blocks[0]
                        tool_name = get_field(tool_use, "name")
                        tool_input = get_field(tool_use, "input")

                        if tool_name in tool_functions:
                            result = tool_functions[tool_name](tool_input, subscriber_id)
                            result_json = json.dumps(result)

                            # Agregar resultado
                            conversation_history.append({
                                "role": "user",
                                "content": [{
                                    "type": "tool_result",
                                    "tool_use_id": get_field(tool_use, "id"),
                                    "content": result_json,
                                }],
                            })
                            
                            # Actualizar conversación con historial actualizado
                            conversation_manager.update(thread_id, {"messages": conversation_history})
                        else:
                            logger.warning("Herramienta desconocida: %s", tool_name)
                            break
                    else:
                        # Respuesta final
                        assistant_response_text = ""
                        for content_block in response.content:
                            if get_field(content_block, "type") == "text":
                                assistant_response_text += (get_field(content_block, "text") or "")
                        
                        # Log de la respuesta final de la IA
                        logger.info("🤖 ANTHROPIC RESPUESTA FINAL para thread_id %s: %s", thread_id, assistant_response_text[:200] + "..." if len(assistant_response_text) > 200 else assistant_response_text)
                        
                        conversation_manager.update(thread_id, {
                            "response": assistant_response_text,
                            "status": "completed",
                            "messages": conversation_history
                        })
                        break

                except Exception as api_error:
                    logger.exception("Error en llamada a API para thread_id %s: %s", thread_id, api_error)
                    conversation_manager.update(thread_id, {
                        "response": f"Error de comunicación: {str(api_error)}",
                        "status": "error"
                    })
                    break

        except Exception as e:
            logger.exception("Error en generate_response para thread_id %s: %s", thread_id, e)
            conversation_manager.update(thread_id, {
                "response": f"Error: {str(e)}",
                "status": "error"
            })
        finally:
            event.set()
            elapsed_time = time.time() - start_time
            logger.info("Generación completada en %.2f segundos para thread_id: %s", elapsed_time, thread_id)