"""
OpenAI Handler - VERSIÓN SIMPLIFICADA PARA TEST MÍNIMO  
"""

import json
import os
import time
import logging
import threading
from openai import OpenAI

# Langfuse imports
from langfuse import Langfuse, observe

from app.utils.cost_calculator import cost_calculator
from app.mcp_config import get_mcp_client, convert_mcp_tools_to_openai

logger = logging.getLogger(__name__)

# Inicializar cliente Langfuse
langfuse = Langfuse()


def clean_conversation_history(history):
    """
    Limpia el historial de conversación removiendo tool calls y mensajes intermedios
    que pueden confundir a OpenAI en llamadas posteriores.
    """
    if not history:
        return []
    
    cleaned_history = []
    
    for message in history:
        role = message.get('role', '')
        content = message.get('content', '')
        tool_calls = message.get('tool_calls')
        
        # Mantener mensajes de usuario
        if role == 'user' and content:
            cleaned_history.append({
                'role': 'user',
                'content': content
            })
        
        # Mantener solo mensajes de assistant con contenido real (sin tool calls)
        elif role == 'assistant' and content and not tool_calls:
            cleaned_history.append({
                'role': 'assistant', 
                'content': content
            })
    
    return cleaned_history


def get_model_parameters(model_name):
    """Obtiene los parámetros adecuados para cada modelo específico."""
    if model_name.lower().startswith("gpt-5"):
        return {
            "temperature": 1.0,
            "max_completion_tokens": 4096  # Aumentado de 1000 a 4096
        }
    else:
        return {
            "temperature": 0.8,
            "max_completion_tokens": 4096  # Aumentado de 1000 a 4096
        }


def call_openai_responses_api(client, input_messages, tools, model_name, thread_id, model_parameters, previous_response_id=None):
    """Llamada a OpenAI Responses API con MCP support y observabilidad."""
    logger.info(f"🔥 [RESPONSES API] Llamando OpenAI Responses API - Modelo: {model_name}")
    logger.info(f"🔥 [RESPONSES API] Input messages: {len(input_messages)}, Tools: {len(tools) if tools else 0}")

    responses_payload = {
        "model": model_name,
        "input": input_messages,
        "tools": tools or None,
        "temperature": model_parameters.get("temperature"),
        "max_output_tokens": model_parameters.get("max_completion_tokens"),  # Cambio: max_output_tokens en lugar de max_completion_tokens
    }
    
    # Agregar previous_response_id si existe (para conversaciones)
    if previous_response_id:
        responses_payload["previous_response_id"] = previous_response_id
        logger.info(f"🔥 [RESPONSES API] Using previous_response_id: {previous_response_id}")
    
    try:
        logger.info(f"🔥 [RESPONSES API] Enviando payload keys: {list(responses_payload.keys())}")
        logger.info(f"🔥 [RESPONSES API] Input messages count: {len(input_messages)}")
        for i, msg in enumerate(input_messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                text_content = content[0].get("text", "") if isinstance(content[0], dict) else str(content[0])
                content_preview = text_content[:50] + "..." if len(text_content) > 50 else text_content
            else:
                content_preview = str(content)[:50]
            logger.info(f"🔥 [RESPONSES API] Input {i+1}: {role} = '{content_preview}'")
        
        # Logging de tools
        if tools:
            for i, tool in enumerate(tools):
                tool_type = tool.get("type", "unknown")
                if tool_type == "mcp":
                    logger.info(f"🔥 [RESPONSES API] Tool {i+1}: MCP server '{tool.get('server_label')}' -> {tool.get('server_url')}")
                else:
                    logger.info(f"🔥 [RESPONSES API] Tool {i+1}: {tool_type}")
        
        response = client.responses.create(**responses_payload)
        logger.info(f"🔥 [RESPONSES API] Respuesta recibida exitosamente")
        logger.info(f"🔥 [RESPONSES API] Response ID: {response.id}")
        logger.info(f"🔥 [RESPONSES API] Output text length: {len(response.output_text) if hasattr(response, 'output_text') else 'No output_text'}")
        if hasattr(response, 'output_text') and response.output_text:
            logger.info(f"🔥 [RESPONSES API] Output preview: '{response.output_text[:200]}...'")
            
    except Exception as api_error:
        logger.error(f"🔥 [RESPONSES API ERROR] Error en llamada OpenAI: {str(api_error)}")
        raise api_error

    # Langfuse tracking now handled manually in parent function

    return response


@observe(as_type="generation")
def generate_response_openai_mcp(
    message,
    assistant_content_text,
    thread_id,
    event,
    subscriber_id,
    llm_id=None,
    conversation_manager=None,
    thread_locks=None,
    mcp_servers=None,
    assistant_number=None
):
    """Genera respuesta usando TEST MÍNIMO SIMPLIFICADO."""
    
    if not llm_id:
        llm_id = "gpt-5"
    
    logger.info(f"🚀 [HANDLER START] Iniciando Responses API - User: {subscriber_id}, Thread: {thread_id}, Modelo: {llm_id}")
    logger.info(f"🚀 [HANDLER START] Mensaje del usuario: {message[:100]}...")
    
    # Capturar input y metadata para Langfuse
    langfuse.update_current_trace(
        input=message,  # Solo el mensaje del usuario
        metadata={
            "model": llm_id,
            "assistant_number": assistant_number,
            "mcp_servers_count": len(mcp_servers) if mcp_servers else 0,
            "thread_id": thread_id,
            "subscriber_id": subscriber_id
        }
    )

    logger.info("Intentando adquirir lock para thread_id (OpenAI MCP): %s", thread_id)
    lock = thread_locks.get(thread_id)
    if not lock:
        logger.error("No se encontró lock para thread_id (OpenAI MCP): %s", thread_id)
        thread_locks[thread_id] = threading.Lock()
        lock = thread_locks[thread_id]

    with lock:
        logger.info("Lock adquirido para thread_id (OpenAI MCP): %s", thread_id)
        start_time = time.time()

        try:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                logger.error("API key de OpenAI no configurada")
                raise Exception("API key de OpenAI no configurada")

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

            client = OpenAI(api_key=api_key)

            # ===== OBTENER HISTORIAL REAL DE LA CONVERSACIÓN =====
            messages_history = conversation.get("messages", [])
            
            # Construir input para Responses API: formato diferente
            responses_input = []
            
            # Agregar system message
            responses_input.append({
                "role": "system", 
                "content": [{"type": "input_text", "text": assistant_content_text}]
            })
            
            # Agregar historial limpio (sin tool calls) - convertir formato
            if messages_history:
                cleaned_history = clean_conversation_history(messages_history)
                for hist_msg in cleaned_history:
                    # Para Responses API: user usa "input_text", assistant usa "output_text"
                    if hist_msg["role"] == "user":
                        content_type = "input_text"
                    elif hist_msg["role"] == "assistant":
                        content_type = "output_text"
                    else:
                        content_type = "input_text"  # Fallback para otros roles
                    
                    responses_input.append({
                        "role": hist_msg["role"],
                        "content": [{"type": content_type, "text": hist_msg["content"]}]
                    })
                logger.info(f"🔄 [HISTORY] Agregando {len(cleaned_history)} mensajes del historial")
            
            # Agregar mensaje actual del usuario
            responses_input.append({
                "role": "user", 
                "content": [{"type": "input_text", "text": message}]
            })
            
            logger.info(f"📝 [RESPONSES INPUT] Total input messages: {len(responses_input)}")
            logger.info(f"📝 [RESPONSES INPUT] System: 1, Historial: {len(messages_history)}, Usuario actual: 1")
            logger.info(f"📝 [RESPONSES INPUT] Mensaje usuario: '{message[:100]}...'")
            logger.info(f"📝 [RESPONSES INPUT] System length: {len(assistant_content_text)} chars")

            # ===== HABILITAR MCP: CARGAR HERRAMIENTAS =====
            openai_tools = []
            mcp_clients = []
            
            if mcp_servers:
                logger.info("🛠️ [MCP TOOLS] Configurando servidores MCP para Responses API")
                for mcp_server_info in mcp_servers:
                    mcp_config = mcp_server_info['config']
                    mcp_number = mcp_server_info['number']
                    
                    # Para Responses API: agregar servidor MCP directamente
                    mcp_server_config = {
                        "type": "mcp",
                        "server_url": mcp_config["server_url"],
                        "server_label": mcp_config["server_label"],
                        "require_approval": mcp_config.get("require_approval", "never")
                    }
                    
                    # Opcional: especificar herramientas permitidas para optimización
                    # Cargar herramientas disponibles para generar allowed_tools
                    mcp_client = get_mcp_client(mcp_config, mcp_number)
                    if mcp_client:
                        tools = mcp_client.get_available_tools()
                        if tools:
                            # Extraer nombres de herramientas para allowed_tools
                            allowed_tools = []
                            for tool in tools:
                                if isinstance(tool, dict):
                                    if "function" in tool and "name" in tool["function"]:
                                        allowed_tools.append(tool["function"]["name"])
                                    elif "name" in tool:
                                        allowed_tools.append(tool["name"])
                            
                            if allowed_tools:
                                mcp_server_config["allowed_tools"] = allowed_tools
                                logger.info(f"🛠️ [MCP CONFIG] Allowed tools: {allowed_tools}")
                        else:
                            logger.warning(f"🛠️ [MCP TOOLS] No se encontraron herramientas para MCP #{mcp_number}")
                    else:
                        logger.warning(f"🛠️ [MCP CLIENT] No se pudo crear cliente MCP #{mcp_number}")
                    
                    openai_tools.append(mcp_server_config)
                    logger.info(f"🛠️ [MCP SERVER] Agregado servidor MCP #{mcp_number}: {mcp_config['server_label']} -> {mcp_config['server_url']}")
            else:
                logger.info("🛠️ [MCP TOOLS] No hay servidores MCP configurados")

            logger.info(f"🛠️ [MCP TOOLS] Total herramientas disponibles: {len(openai_tools)}")
            
            model_parameters = get_model_parameters(llm_id)
            logger.info(f"🔧 [PARAMETERS] temperature={model_parameters['temperature']}, max_tokens={model_parameters['max_completion_tokens']}")

            # LLAMADA A RESPONSES API CON MCP
            logger.info(f"🔥 [RESPONSES API] Llamando Responses API con {len(openai_tools)} servidores MCP")
            
            # Obtener previous_response_id si existe en el historial
            previous_response_id = conversation.get("previous_response_id")
            
            # Crear generation manual para Langfuse
            with langfuse.start_as_current_generation(
                name="openai-responses-call",
                model=llm_id,
                input=responses_input,
                metadata={
                    "api_type": "responses",
                    "tools_count": len(openai_tools),
                    "has_mcp": any(t.get("type") == "mcp" for t in openai_tools),
                    "mcp_servers": [t.get("server_label") for t in openai_tools if t.get("type") == "mcp"],
                    "previous_response_id": previous_response_id
                }
            ) as generation:
                response = call_openai_responses_api(
                    client, 
                    responses_input, 
                    openai_tools, 
                    llm_id, 
                    thread_id, 
                    model_parameters,
                    previous_response_id
                )
                
                # DEBUG: Análisis detallado del response para output
                logger.info(f"📊 [OUTPUT DEBUG] === DEBUGGING OUTPUT PARA LANGFUSE ===")
                logger.info(f"📊 [OUTPUT DEBUG] response object: {type(response)}")
                logger.info(f"📊 [OUTPUT DEBUG] response attributes: {dir(response)}")
                logger.info(f"📊 [OUTPUT DEBUG] hasattr output_text: {hasattr(response, 'output_text')}")
                
                output_text = ""
                if hasattr(response, 'output_text'):
                    raw_output = response.output_text
                    logger.info(f"📊 [OUTPUT DEBUG] raw output_text: {repr(raw_output)}")
                    logger.info(f"📊 [OUTPUT DEBUG] output_text type: {type(raw_output)}")
                    logger.info(f"📊 [OUTPUT DEBUG] output_text is None: {raw_output is None}")
                    logger.info(f"📊 [OUTPUT DEBUG] output_text == '': {raw_output == ''}")
                    output_text = raw_output if raw_output is not None else ""
                else:
                    logger.error(f"📊 [OUTPUT DEBUG] response NO TIENE output_text attribute!")
                
                logger.info(f"📊 [OUTPUT DEBUG] final output_text: {repr(output_text)}")
                logger.info(f"📊 [OUTPUT DEBUG] final output length: {len(output_text)}")
                logger.info(f"📊 [OUTPUT DEBUG] === FIN DEBUG OUTPUT ===")
                
                # Usage data
                usage_data = {}
                if hasattr(response, 'usage') and response.usage:
                    usage = response.usage
                    usage_data = {
                        "input_tokens": getattr(usage, 'input_tokens', getattr(usage, 'prompt_tokens', 0)),
                        "output_tokens": getattr(usage, 'output_tokens', getattr(usage, 'completion_tokens', 0)),
                        "total_tokens": getattr(usage, 'total_tokens', 0),
                    }
                
                # LANGFUSE UPDATE CORRECTO PARA FUNCIÓN DECORADA
                try:
                    logger.info(f"📊 [LANGFUSE] Actualizando generation con output...")
                    simple_output = str(output_text) if output_text else "Sin respuesta"
                    
                    generation.update(
                        output=simple_output,
                        usage=usage_data,
                        metadata={
                            "response_id": getattr(response, 'id', None),
                            "api_type": "responses",
                            "output_length": len(simple_output),
                            "function_name": "call_openai_responses_api"
                        }
                    )
                    logger.info(f"📊 [LANGFUSE] ✅ Update exitoso - Output: {repr(simple_output[:50])}...")
                    
                except Exception as e:
                    logger.error(f"📊 [LANGFUSE] ❌ Error en update: {str(e)}")
                    
                    # Fallback: solo metadata
                    try:
                        generation.update(
                            usage=usage_data,
                            metadata={
                                "final_output": simple_output,
                                "output_length": len(simple_output),
                                "api_type": "responses",
                                "error": "No se pudo enviar output directamente"
                            }
                        )
                        logger.info(f"📊 [LANGFUSE] ✅ Fallback exitoso (output en metadata)")
                    except Exception as fallback_error:
                        logger.error(f"📊 [LANGFUSE] ❌ Fallback también falló: {str(fallback_error)}")

            # ===== LOGGING GRANULAR DEL RESPONSE =====
            logger.info("🔍 [RESPONSE DEBUG] Analizando respuesta de Responses API:")
            logger.info(f"🔍 [RESPONSE DEBUG] Response object type: {type(response)}")
            logger.info(f"🔍 [RESPONSE DEBUG] Response ID: {getattr(response, 'id', 'No ID')}")
            logger.info(f"🔍 [RESPONSE DEBUG] Has output_text: {hasattr(response, 'output_text')}")
            
            if hasattr(response, 'output_text'):
                output_text = response.output_text
                logger.info(f"🔍 [RESPONSE DEBUG] Output text type: {type(output_text)}")
                logger.info(f"🔍 [RESPONSE DEBUG] Output text length: {len(output_text) if output_text else 'None'}")
                logger.info(f"🔍 [RESPONSE DEBUG] Output text preview: '{str(output_text)[:200]}...'")
            else:
                logger.error("🔍 [RESPONSE DEBUG] NO output_text EN RESPONSE!")
            
            # ===== MANEJAR RESPONSE DE RESPONSES API =====
            total_input_tokens = 0
            total_output_tokens = 0
            final_text = ""
            
            # Extraer usage de Responses API
            if hasattr(response, 'usage') and response.usage:
                total_input_tokens = getattr(response.usage, 'input_tokens', 0)
                total_output_tokens = getattr(response.usage, 'output_tokens', 0)
                logger.info(f"📊 [USAGE] Input tokens: {total_input_tokens}, Output tokens: {total_output_tokens}")
            
            # En Responses API, el texto final ya viene procesado con MCP
            if hasattr(response, 'output_text') and response.output_text:
                final_text = response.output_text
                logger.info(f"🎯 [FINAL RESPONSE] Respuesta de Responses API: '{final_text[:200]}...'")
            else:
                final_text = ""
                logger.warning(f"🎯 [FINAL RESPONSE] No se encontró output_text en la respuesta")
            
            logger.info(f"🎯 [RESPONSE] Length: {len(final_text)}")
            logger.info(f"📊 [TOKENS] Total - Input: {total_input_tokens}, Output: {total_output_tokens}")
            
            # ===== LANGFUSE UPDATE PARA GENERATE_RESPONSE_OPENAI_MCP (MISMA LÓGICA QUE INPUT) =====
            try:
                logger.info(f"📊 [LANGFUSE MCP] Actualizando observación con output...")
                
                # Usar la misma lógica que funciona para el input
                langfuse.update_current_observation(
                    output=final_text,  # La respuesta final
                    usage={
                        "input_tokens": total_input_tokens,
                        "output_tokens": total_output_tokens,
                        "total_tokens": total_input_tokens + total_output_tokens
                    },
                    metadata={
                        "model": llm_id,
                        "assistant_number": assistant_number,
                        "mcp_servers_count": len(mcp_servers) if mcp_servers else 0,
                        "thread_id": thread_id,
                        "subscriber_id": subscriber_id,
                        "api_type": "responses",
                        "function_name": "generate_response_openai_mcp",
                        "response_id": getattr(response, 'id', None),
                        "output_length": len(final_text)
                    }
                )
                
                logger.info(f"📊 [LANGFUSE MCP] ✅ Observación actualizada exitosamente")
                logger.info(f"📊 [LANGFUSE MCP] Output enviado: {repr(final_text[:50])}...")
                
            except Exception as langfuse_error:
                logger.error(f"📊 [LANGFUSE MCP] ❌ Error en update_current_observation: {str(langfuse_error)}")
                logger.error(f"📊 [LANGFUSE MCP] ❌ Exception details: {type(langfuse_error).__name__}: {str(langfuse_error)}")
            
            # ===== GUARDAR RESULTADO FINAL =====
            current_history = conversation.get("messages", [])
            current_history.append({"role": "user", "content": message})
            current_history.append({"role": "assistant", "content": final_text})
            
            # Guardar response_id para conversaciones continuadas
            update_data = {
                "response": final_text,
                "status": "completed", 
                "messages": current_history,
                "usage": {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            }
            
            # Agregar response_id si está disponible
            if hasattr(response, 'id') and response.id:
                update_data["previous_response_id"] = response.id
                logger.info(f"💾 [SAVE] Guardando response_id para próxima conversación: {response.id}")
            
            # FLUSH LANGFUSE ANTES DE GUARDAR
            try:
                from langfuse import Langfuse
                langfuse_instance = Langfuse()
                langfuse_instance.flush()
                logger.info(f"📊 [LANGFUSE] ✅ Flush manual ejecutado exitosamente")
            except Exception as flush_error:
                logger.error(f"📊 [LANGFUSE] ❌ Error en flush manual: {str(flush_error)}")
            
            conversation_manager.update(thread_id, update_data)
            
            logger.info(f"✅ [COMPLETED] OpenAI MCP handler completado exitosamente")
                
        except Exception as e:
            logger.exception("🧪 [MINIMAL TEST] ❌ Error en test mínimo: %s", e)
            conversation_manager.update(thread_id, {
                "response": f"Error en test mínimo: {str(e)}",
                "status": "error",
                "messages": [{"role": "user", "content": message}]
            })
        finally:
            event.set()
            elapsed_time = time.time() - start_time
            logger.info("⏰Test mínimo completado en %.2f segundos para thread_id: %s", elapsed_time, thread_id)
            logger.debug("Finalizando handler OpenAI MCP")