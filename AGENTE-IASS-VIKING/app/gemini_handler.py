"""
Gemini Handler - Manejador específico para modelos Gemini con Langfuse
"""

import json
import os
import time
import logging
import threading
import requests

# Langfuse imports
from langfuse import Langfuse, observe

# Servicios n8n eliminados - se manejará con MCP
from app.utils.cost_calculator import cost_calculator

logger = logging.getLogger(__name__)

# Inicializar cliente Langfuse
langfuse = Langfuse()

# Herramientas se manejarán vía MCP
TOOL_FUNCTIONS = {}

def convert_tool_to_gemini_format(openai_tool):
    """Convierte una herramienta del formato OpenAI/Anthropic al formato Gemini."""
    return {
        "name": openai_tool["name"],
        "description": openai_tool["description"],
        "parameters": {
            "type": "object",
            "properties": openai_tool["parameters"]["properties"],
            "required": openai_tool["parameters"].get("required", [])
        }
    }

def convert_legacy_history_to_gemini(legacy_history):
    """Convierte historial del formato Anthropic/OpenAI al formato Gemini."""
    if not legacy_history:
        return []
    
    gemini_history = []
    
    for msg in legacy_history:
        role = msg.get("role")
        content = msg.get("content")
        
        # Convertir roles
        if role == "assistant":
            gemini_role = "model"
        elif role == "user":
            gemini_role = "user"
        else:
            continue  # Saltar roles no reconocidos
        
        # Convertir contenido
        if isinstance(content, list):
            # Formato complejo (Anthropic)
            gemini_parts = []
            for c in content:
                if isinstance(c, dict):
                    if c.get("type") == "text":
                        gemini_parts.append({"text": c.get("text", "")})
                    elif c.get("type") == "tool_use":
                        # Convertir tool_use de Anthropic a functionCall de Gemini
                        gemini_parts.append({
                            "functionCall": {
                                "name": c.get("name", ""),
                                "args": c.get("input", {})
                            }
                        })
                    elif c.get("type") == "tool_result":
                        # Convertir tool_result de Anthropic a functionResponse de Gemini
                        gemini_parts.append({
                            "functionResponse": {
                                "name": "unknown",  # Anthropic no almacena el nombre
                                "response": {"result": c.get("content", "")}
                            }
                        })
                else:
                    # Contenido de texto simple
                    gemini_parts.append({"text": str(c)})
            
            if gemini_parts:
                gemini_history.append({
                    "role": gemini_role,
                    "parts": gemini_parts
                })
                
        elif isinstance(content, str):
            # Formato simple de texto
            gemini_history.append({
                "role": gemini_role,
                "parts": [{"text": content}]
            })
    
    return gemini_history

@observe(as_type="generation")
def call_gemini_api(payload, api_key, thread_id, model_name="gemini-2.0-flash"):
    """
    Función separada para llamadas a Gemini API con observabilidad completa
    """
    
    # Registrar input del span de generación con detalles del modelo
    langfuse.update_current_generation(
        input=payload,
        model=model_name,
        model_parameters={
            "temperature": payload.get("generationConfig", {}).get("temperature", 0.8),
            "maxOutputTokens": payload.get("generationConfig", {}).get("maxOutputTokens", 1000)
        }
    )
    
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }

    # La URL puede cambiar según el modelo
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    
    response = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=60
    )

    if response.status_code != 200:
        try:
            error_json = response.json()
            api_message = error_json.get("error", {}).get("message", response.text)
        except Exception:
            api_message = response.text
        logger.error("Error en API de Gemini: %s - %s", response.status_code, api_message)
        raise Exception(f"Error de API: {response.status_code} - {api_message}")

    response_data = response.json()
    
    # Registrar output del span de generación
    langfuse.update_current_generation(output=response_data)
    
    # Captura y registro de métricas para Langfuse
    usage_metadata = response_data.get("usageMetadata", {})
    input_tokens = usage_metadata.get("promptTokenCount", 0)
    output_tokens = usage_metadata.get("candidatesTokenCount", 0)
    
    # Calcular nuestros costos personalizados para metadata
    custom_cost_details = cost_calculator.calculate_cost(model_name, input_tokens, output_tokens)
    
    # Registrar métricas y detalles del span de generación (implementación simple que funcionaba)
    langfuse.update_current_generation(
        model=model_name,
        usage_details={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens
        },
        metadata={
            "api_url": api_url,
            "response_status": response.status_code,
            "custom_cost_calculation": {
                "total_cost": custom_cost_details["total_cost"],
                "currency": custom_cost_details["currency"],
                "breakdown": custom_cost_details["cost_breakdown"]
            }
        }
    )
    
    logger.info(f"[LANGFUSE] Modelo: {model_name}, Input tokens: {input_tokens}, Output tokens: {output_tokens}")
    
    return response_data

@observe(as_type="span")
def execute_function_call(tool_name, tool_args, subscriber_id):
    """
    Ejecuta una función tool con observabilidad individual
    """
    
    # Log para Langfuse - ejecución de tool
    logger.info(f"[LANGFUSE] Ejecutando tool: {tool_name} para subscriber: {subscriber_id}")
    
    if tool_name in TOOL_FUNCTIONS:
        logger.info(f"Ejecutando función: {tool_name} con args: {tool_args}")
        
        result = TOOL_FUNCTIONS[tool_name](tool_args, subscriber_id)
        
        # Log resultado para Langfuse
        logger.info(f"[LANGFUSE] Tool {tool_name} ejecutado exitosamente")
        
        return result
    else:
        logger.warning("Herramienta desconocida: %s", tool_name)
        logger.warning(f"[LANGFUSE] Tool {tool_name} no encontrado")
        return f"Función {tool_name} no encontrada"

@observe(as_type="span")
def generate_response_gemini(
    message,
    assistant_content_text,
    thread_id,
    event,
    subscriber_id,
    conversation_manager=None,
    thread_locks=None,
    model_name="gemini-2.0-flash"
):
    """
    Genera respuesta usando Gemini con observabilidad completa de Langfuse
    """
    
    # Log inicio de trace para Langfuse
    logger.info(f"[LANGFUSE] Iniciando conversación - User: {subscriber_id}, Thread: {thread_id}, Modelo: {model_name}")
    
    # Registrar input de la traza (solo el mensaje del usuario)
    langfuse.update_current_trace(input={"user_message": message})
    
    logger.info("Intentando adquirir lock para thread_id (Gemini): %s", thread_id)
    lock = thread_locks.get(thread_id)
    if not lock:
        logger.error("No se encontró lock para thread_id (Gemini): %s", thread_id)
        thread_locks[thread_id] = threading.Lock()
        lock = thread_locks[thread_id]

    with lock:
        logger.info("Lock adquirido para thread_id (Gemini): %s", thread_id)
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
                
                # Log error para Langfuse
                logger.error(f"[LANGFUSE] Error: Conversación {thread_id} no encontrada")
                return

            # Configurar API key
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                logger.error("API key de Gemini no configurada")
                logger.error(f"[LANGFUSE] Error: API key de Gemini no configurada")
                raise Exception("API key de Gemini no configurada")

            # Cargar y convertir herramientas al formato Gemini
            assistant_value = conversation.get("assistant")
            assistant_str = str(assistant_value)
            
            # Cargar herramientas desde archivo único
            tools_file_path = os.path.join(os.path.dirname(__file__), '..', 'tools', 'default_tools.json')
            with open(tools_file_path, "r", encoding="utf-8") as tools_file:
                openai_tools = json.load(tools_file)

            # Preparar herramientas para Gemini
            gemini_tools = [{
                "functionDeclarations": [convert_tool_to_gemini_format(tool) for tool in openai_tools]
            }]

            # ===== GESTIÓN DEL HISTORIAL EN FORMATO GEMINI =====
            
            # Obtener historial existente (ya en formato Gemini)
            gemini_history = conversation.get("messages", [])
            
            # Si es la primera vez o el historial está en formato incorrecto, convertir
            if not gemini_history or (gemini_history and "content" in gemini_history[0]):
                logger.info("Convirtiendo historial existente a formato Gemini")
                gemini_history = convert_legacy_history_to_gemini(gemini_history)

            # Agregar mensaje actual del usuario al historial
            gemini_history.append({
                "role": "user",
                "parts": [{"text": message}]
            })

            # Actualizar conversación con mensaje del usuario
            conversation_manager.update(thread_id, {"messages": gemini_history})

            # ===== LOOP PRINCIPAL DE INTERACCIÓN =====
            iteration_count = 0
            while True:
                iteration_count += 1
                
                # Log iteración para Langfuse
                logger.info(f"[LANGFUSE] Iteración {iteration_count} iniciada")
                try:
                    # Preparar payload para Gemini
                    payload = {
                        "contents": gemini_history,
                        "systemInstruction": {
                            "parts": [{"text": assistant_content_text}]
                        },
                        "tools": gemini_tools,
                        "generationConfig": {
                            "temperature": 0.8,
                            "maxOutputTokens": 1000
                        }
                    }

                    logger.info("Enviando solicitud a Gemini API para thread_id: %s", thread_id)

                    # Usar función instrumentada para llamar a Gemini API
                    response_data = call_gemini_api(payload, api_key, thread_id, model_name)

                    # Procesar respuesta
                    candidates = response_data.get("candidates", [])
                    if not candidates:
                        raise Exception("No se recibieron candidatos en la respuesta")

                    candidate = candidates[0]
                    content = candidate.get("content", {})
                    parts = content.get("parts", [])

                    # ===== PROCESAR RESPUESTA DEL MODELO =====
                    
                    has_function_calls = False
                    function_calls_to_execute = []
                    model_response_parts = []

                    # Analizar cada parte de la respuesta
                    for part in parts:
                        if "functionCall" in part:
                            has_function_calls = True
                            function_call = part["functionCall"]
                            tool_name = function_call.get("name")
                            tool_args = function_call.get("args", {})
                            
                            model_response_parts.append({"functionCall": function_call})
                            function_calls_to_execute.append((tool_name, tool_args, function_call))
                            
                        elif "text" in part:
                            model_response_parts.append({"text": part["text"]})

                    # Agregar respuesta del modelo al historial
                    if model_response_parts:
                        gemini_history.append({
                            "role": "model", 
                            "parts": model_response_parts
                        })

                    # ===== EJECUTAR FUNCTION CALLS =====
                    
                    if has_function_calls:
                        # Ejecutar todas las funciones (soporte para parallel calling)
                        function_responses = []
                        
                        for tool_name, tool_args, original_function_call in function_calls_to_execute:
                            # Usar función instrumentada para ejecutar tools
                            result = execute_function_call(tool_name, tool_args, subscriber_id)
                            
                            function_responses.append({
                                "functionResponse": {
                                    "name": tool_name,
                                    "response": {"result": result}
                                }
                            })

                        # Agregar respuestas de funciones al historial
                        if function_responses:
                            gemini_history.append({
                                "role": "user",
                                "parts": function_responses
                            })

                        # Actualizar historial en conversation_manager después de function calls
                        conversation_manager.update(thread_id, {"messages": gemini_history})
                        
                        # Continuar el loop para procesar la siguiente respuesta
                        continue

                    else:
                        # ===== NO HAY MÁS FUNCTION CALLS - RESPUESTA FINAL =====
                        
                        # Extraer texto final de la respuesta
                        final_text = ""
                        for part in model_response_parts:
                            if "text" in part:
                                final_text += part["text"]

                        # Log de la respuesta final de la IA
                        logger.info("🤖 GEMINI RESPUESTA FINAL para thread_id %s: %s", thread_id, final_text[:200] + "..." if len(final_text) > 200 else final_text)

                        # Procesar tokens de uso
                        usage_metadata = response_data.get("usageMetadata", {})
                        usage = {
                            "input_tokens": usage_metadata.get("promptTokenCount", 0),
                            "output_tokens": usage_metadata.get("candidatesTokenCount", 0),
                            "cache_creation_input_tokens": 0,  # Gemini no tiene este concepto
                            "cache_read_input_tokens": 0       # Gemini no tiene este concepto
                        }

                        # Calcular costos totales de la conversación
                        total_cost_details = cost_calculator.calculate_cost(
                            model_name,
                            usage["input_tokens"], 
                            usage["output_tokens"]
                        )
                        
                        # Registrar output de la traza (solo la respuesta final) con costos
                        langfuse.update_current_trace(
                            output={"response": final_text},
                            metadata={
                                "total_usage": usage,
                                "total_cost_details": total_cost_details,
                                "iterations": iteration_count,
                                "model": model_name,
                                "subscriber_id": subscriber_id,
                                "thread_id": thread_id,
                                "cost_per_iteration": round(total_cost_details["total_cost"] / iteration_count, 8) if iteration_count > 0 else 0,
                                "conversation_efficiency": {
                                    "total_tokens": usage["input_tokens"] + usage["output_tokens"],
                                    "cost_per_token": round(total_cost_details["total_cost"] / (usage["input_tokens"] + usage["output_tokens"]), 10) if (usage["input_tokens"] + usage["output_tokens"]) > 0 else 0
                                }
                            }
                        )
                        
                        # Actualizar conversación con respuesta final
                        conversation_manager.update(thread_id, {
                            "response": final_text,
                            "status": "completed", 
                            "messages": gemini_history,
                            "usage": usage
                        })

                        # Log final para Langfuse
                        logger.info(f"[LANGFUSE] Conversación completada - Tokens: {usage['input_tokens']}+{usage['output_tokens']}, Iteraciones: {iteration_count}")

                        logger.info(f"Tokens utilizados - Input: {usage['input_tokens']}, Output: {usage['output_tokens']}")
                        break

                except Exception as api_error:
                    logger.exception("Error en llamada a Gemini API para thread_id %s: %s", thread_id, api_error)
                    
                    # Log error para Langfuse
                    logger.error(f"[LANGFUSE] Error en API: {str(api_error)}")
                    
                    conversation_manager.update(thread_id, {
                        "response": f"Error de comunicación con Gemini: {str(api_error)}",
                        "status": "error"
                    })
                    break

        except Exception as e:
            logger.exception("Error en generate_response_gemini para thread_id %s: %s", thread_id, e)
            
            # Log error general para Langfuse
            logger.error(f"[LANGFUSE] Error general: {str(e)}")
            
            conversation_manager.update(thread_id, {
                "response": f"Error Gemini: {str(e)}",
                "status": "error"
            })
        finally:
            event.set()
            elapsed_time = time.time() - start_time
            logger.info("Generación completada en %.2f segundos para thread_id: %s", elapsed_time, thread_id)
            
            # Log métricas de performance para Langfuse
            logger.info(f"[LANGFUSE] Performance - Tiempo: {elapsed_time:.2f}s, Clasificación: {'fast' if elapsed_time < 3 else 'slow'}")