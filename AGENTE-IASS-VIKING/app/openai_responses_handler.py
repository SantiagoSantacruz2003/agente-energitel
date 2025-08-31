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


def execute_function_tool(tool_name, tool_args, assistant_number):
    """Ejecuta una herramienta tipo function basada en ASSISTANT_TOOLS"""
    try:
        logger.info(f"🔧 [FUNCTION EXEC] Ejecutando {tool_name} para assistant {assistant_number}")
        logger.info(f"🔧 [FUNCTION EXEC] Argumentos: {tool_args}")
        
        # Ejecutar herramientas específicas con validación
        if tool_name == "cambiar_nombre":
            nombre = tool_args.get('nombre', '').strip()
            if not nombre:
                result = {
                    "ok": False,
                    "error": "Nombre es requerido",
                    "message": "Por favor proporciona tu nombre completo (nombre y apellido)"
                }
            else:
                result = {
                    "ok": True,
                    "mensaje": f"Nombre cambiado exitosamente a: {nombre}",
                    "nombre_anterior": "Usuario sin nombre",
                    "nombre_nuevo": nombre
                }
        elif tool_name == "crear_direccion":
            # Validar argumentos requeridos para crear_direccion
            required_fields = ['sede', 'nombre_cliente', 'direccion_cliente', 'ciudad_cliente', 'tipo_pedido']
            missing_fields = [field for field in required_fields if not tool_args.get(field, '').strip()]
            
            if missing_fields:
                result = {
                    "ok": False,
                    "error": "Campos requeridos faltantes",
                    "message": f"Los siguientes campos son obligatorios: {', '.join(missing_fields)}",
                    "missing_fields": missing_fields
                }
            else:
                result = {
                    "ok": True,
                    "direccion_id": f"dir_{int(time.time())}",
                    "mensaje": f"Dirección creada para {tool_args.get('nombre_cliente')} en {tool_args.get('sede')}",
                    "detalles": {
                        "sede": tool_args.get('sede'),
                        "cliente": tool_args.get('nombre_cliente'),
                        "direccion": tool_args.get('direccion_cliente'),
                        "ciudad": tool_args.get('ciudad_cliente'),
                        "tipo": tool_args.get('tipo_pedido')
                    }
                }
        else:
            result = {
                "ok": True,
                "mensaje": f"Herramienta {tool_name} ejecutada exitosamente",
                "args_recibidos": tool_args
            }
            
        logger.info(f"🔧 [FUNCTION EXEC] Resultado: {result}")
        return result
        
    except Exception as e:
        logger.error(f"🔧 [FUNCTION EXEC] Error ejecutando {tool_name}: {e}")
        return {
            "ok": False,
            "error": str(e),
            "tool_name": tool_name
        }


def execute_mcp_tool(tool_name, tool_args, mcp_servers):
    """Ejecuta una herramienta MCP vía HTTP"""
    try:
        logger.info(f"🛠️ [MCP EXEC] Ejecutando {tool_name} via MCP")
        logger.info(f"🛠️ [MCP EXEC] Argumentos: {tool_args}")
        
        # Buscar el servidor MCP apropiado
        for mcp_server_info in mcp_servers:
            mcp_config = mcp_server_info['config']
            mcp_number = mcp_server_info['number']
            
            # Usar el primer servidor MCP disponible (pueden expandirse con lógica específica)
            from app.mcp_config import get_mcp_client
            mcp_client = get_mcp_client(mcp_config, mcp_number)
            
            if mcp_client:
                result = mcp_client.execute_tool(tool_name, tool_args)
                logger.info(f"🛠️ [MCP EXEC] Resultado de MCP #{mcp_number}: {result}")
                return result
        
        # Si no se encontró servidor MCP
        logger.warning(f"🛠️ [MCP EXEC] No se encontró servidor MCP para {tool_name}")
        return {
            "error": f"No MCP server available for {tool_name}",
            "tool_name": tool_name
        }
        
    except Exception as e:
        logger.error(f"🛠️ [MCP EXEC] Error ejecutando {tool_name}: {e}")
        return {
            "error": str(e),
            "tool_name": tool_name
        }


def _fallback_route_b(client, responses_input, openai_tools, llm_id, 
                     thread_id, model_parameters, response_id, tool_outputs):
    """
    ELIMINADA: En Responses API NO existe role:"tool" - solo submit_tool_outputs es válido
    """
    logger.error(f"🔧 [ROUTE B] ERROR: Ruta B eliminada - role:'tool' no es válido en Responses API")
    logger.error(f"🔧 [ROUTE B] Solo submit_tool_outputs es válido para cerrar el bucle de herramientas")
    raise ValueError("Ruta B eliminada: role:'tool' no es válido en Responses API. Solo usar submit_tool_outputs.")


def handle_tool_calls_responses_api(client, initial_response, responses_input, openai_tools, 
                                   llm_id, thread_id, model_parameters, assistant_number, mcp_servers=None, function_tool_calls=None):
    """Maneja tool calls y hace segunda llamada a Responses API"""
    try:
        logger.info(f"🔧 [TOOL HANDLER] Iniciando manejo de tool calls")
        
        # Usar function_tool_calls si está disponible, sino usar initial_response.tool_calls (fallback)
        tool_calls_to_process = function_tool_calls if function_tool_calls else getattr(initial_response, 'tool_calls', [])
        
        if not tool_calls_to_process:
            logger.warning(f"🔧 [TOOL HANDLER] No se encontraron tool calls para procesar")
            return initial_response
        
        logger.info(f"🔧 [TOOL HANDLER] Procesando {len(tool_calls_to_process)} tool calls")
        
        # NO agregamos mensaje assistant con tool_calls - esto causa error 400
        # En Responses API, 'tool_call' NO es un tipo válido en la entrada
        logger.info(f"🔧 [TOOL HANDLER] Saltando mensaje assistant inválido (previene error 400)")
        
        # Preparar tool_outputs para submit_tool_outputs
        tool_outputs = []
        response_id = getattr(initial_response, 'id', None)
        logger.info(f"🔧 [TOOL HANDLER] Response ID para submit_tool_outputs: {response_id}")
        
        # 1. Ejecutar cada herramienta y recolectar outputs
        for tool_call in tool_calls_to_process:
            # Manejar diferencias entre ResponseFunctionToolCall y formato anterior
            tool_name = getattr(tool_call, 'name', 'unknown')
            tool_id = getattr(tool_call, 'call_id', getattr(tool_call, 'id', 'unknown'))
            
            # Para ResponseFunctionToolCall, los argumentos vienen como string JSON
            if hasattr(tool_call, 'arguments') and isinstance(tool_call.arguments, str):
                try:
                    tool_args = json.loads(tool_call.arguments)
                except json.JSONDecodeError:
                    tool_args = {}
            else:
                tool_args = getattr(tool_call, 'arguments', {})
            
            logger.info(f"🔧 [TOOL HANDLER] Ejecutando herramienta: {tool_name}")
            
            # Determinar si es herramienta Function o MCP
            is_function_tool = False
            is_mcp_tool = False
            
            # Verificar si está en herramientas Function
            function_tools = load_function_tools_for_assistant(assistant_number)
            for func_tool in function_tools:
                if func_tool.get('name') == tool_name:
                    is_function_tool = True
                    break
            
            # Si no es Function, asumir que es MCP
            if not is_function_tool:
                is_mcp_tool = True
            
            # Ejecutar herramienta según su tipo
            if is_function_tool:
                result = execute_function_tool(tool_name, tool_args, assistant_number)
            elif is_mcp_tool:
                # Usar mcp_servers pasados como parámetro
                if mcp_servers:
                    result = execute_mcp_tool(tool_name, tool_args, mcp_servers)
                else:
                    result = {
                        "error": "No MCP servers configured",
                        "tool_name": tool_name
                    }
            else:
                result = {"error": f"Unknown tool type: {tool_name}"}
            
            # Agregar a tool_outputs para submit_tool_outputs
            tool_outputs.append({
                "tool_call_id": tool_id,
                "output": json.dumps(result, ensure_ascii=False)
            })
            logger.info(f"🔧 [TOOL HANDLER] Tool output preparado para {tool_name} (call_id: {tool_id})")
        
        # ÚNICA RUTA VÁLIDA: submit_tool_outputs
        if not response_id:
            logger.error(f"🔧 [TOOL HANDLER] ERROR CRÍTICO: Sin response_id para submit_tool_outputs")
            raise ValueError("response_id es requerido para submit_tool_outputs en Responses API")
        
        if not tool_outputs:
            logger.error(f"🔧 [TOOL HANDLER] ERROR CRÍTICO: Sin tool_outputs para submit_tool_outputs")
            raise ValueError("tool_outputs es requerido para submit_tool_outputs en Responses API")
        
        try:
            logger.info(f"🔧 [TOOL HANDLER] ===== USANDO submit_tool_outputs =====")
            logger.info(f"🔧 [TOOL HANDLER] Response ID: {response_id}")
            logger.info(f"🔧 [TOOL HANDLER] Tool outputs ({len(tool_outputs)}): {json.dumps(tool_outputs, indent=2)}")
            
            final_response = client.responses.submit_tool_outputs(
                response_id=response_id,
                tool_outputs=tool_outputs
            )
            
            logger.info(f"🔧 [TOOL HANDLER] ✅ submit_tool_outputs completado exitosamente")
            logger.info(f"🔧 [TOOL HANDLER] Final response ID: {getattr(final_response, 'id', 'No ID')}")
            logger.info(f"🔧 [TOOL HANDLER] Final output_text length: {len(getattr(final_response, 'output_text', '')) if hasattr(final_response, 'output_text') else 0}")
            return final_response
            
        except Exception as submit_error:
            logger.error(f"🔧 [TOOL HANDLER] ❌ ERROR CRÍTICO en submit_tool_outputs: {str(submit_error)}")
            logger.error(f"🔧 [TOOL HANDLER] No hay fallback disponible - solo submit_tool_outputs es válido en Responses API")
            raise submit_error
        
    except Exception as e:
        logger.error(f"🔧 [TOOL HANDLER] Error en handle_tool_calls: {e}")
        # Retornar respuesta de error
        class ErrorResponse:
            def __init__(self, error_msg):
                self.output_text = f"Error ejecutando herramientas: {error_msg}"
                self.usage = None
                
        return ErrorResponse(str(e))


def load_function_tools_for_assistant(assistant_number):
    """Carga herramientas function basadas en ASSISTANT_TOOLS"""
    from app.endpoints import ASSISTANT_TOOLS
    
    tools_file = ASSISTANT_TOOLS.get(assistant_number, ASSISTANT_TOOLS[5])
    tools_path = os.path.join(os.path.dirname(__file__), '..', tools_file)
    
    try:
        with open(tools_path, 'r', encoding='utf-8') as f:
            tools = json.load(f)
            logger.info(f"🔧 [FUNCTION TOOLS] Cargadas {len(tools)} herramientas desde {tools_file} para assistant {assistant_number}")
            return tools
    except FileNotFoundError:
        logger.warning(f"🔧 [FUNCTION TOOLS] Archivo no encontrado: {tools_path}")
        return []
    except Exception as e:
        logger.error(f"🔧 [FUNCTION TOOLS] Error cargando {tools_path}: {e}")
        return []


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
        logger.info(f"🔥 [RESPONSES API] ===== PAYLOAD COMPLETO A OPENAI =====\n")
        logger.info(f"🔥 [RESPONSES API] Payload keys: {list(responses_payload.keys())}")
        logger.info(f"🔥 [RESPONSES API] Modelo: {responses_payload.get('model')}")
        logger.info(f"🔥 [RESPONSES API] Temperature: {responses_payload.get('temperature')}")
        logger.info(f"🔥 [RESPONSES API] Max tokens: {responses_payload.get('max_output_tokens')}")
        logger.info(f"🔥 [RESPONSES API] Previous response ID: {responses_payload.get('previous_response_id')}")
        
        # Log completo del payload
        logger.info(f"🔥 [RESPONSES API] PAYLOAD COMPLETO: {json.dumps(responses_payload, indent=2, ensure_ascii=False)}")
        
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
        
        # Logging detallado de tools
        if tools:
            logger.info(f"🔥 [RESPONSES API] ===== HERRAMIENTAS ENVIADAS ({len(tools)}) =====")
            for i, tool in enumerate(tools):
                logger.info(f"🔥 [RESPONSES API] Tool {i+1} COMPLETA: {json.dumps(tool, indent=2, ensure_ascii=False)}")
                
                tool_type = tool.get("type", "unknown")
                if tool_type == "mcp":
                    logger.info(f"🔥 [RESPONSES API] Tool {i+1}: MCP server '{tool.get('server_label')}' -> {tool.get('server_url')}")
                    allowed_tools = tool.get('allowed_tools', [])
                    logger.info(f"🔥 [RESPONSES API] Tool {i+1}: Herramientas permitidas ({len(allowed_tools)}): {allowed_tools}")
                    logger.info(f"🔥 [RESPONSES API] Tool {i+1}: Require approval: {tool.get('require_approval')}")
                else:
                    logger.info(f"🔥 [RESPONSES API] Tool {i+1}: {tool_type}")
            logger.info(f"🔥 [RESPONSES API] =======================================\n")
        else:
            logger.warning(f"🔥 [RESPONSES API] ❌ NO HAY HERRAMIENTAS CONFIGURADAS")
        
        logger.info(f"🔥 [RESPONSES API] ===========================================\n")
        
        response = client.responses.create(**responses_payload)
        logger.info(f"🔥 [RESPONSES API] Respuesta recibida exitosamente")
        logger.info(f"🔥 [RESPONSES API] Response ID: {response.id}")
        logger.info(f"🔥 [RESPONSES API] Output text length: {len(response.output_text) if hasattr(response, 'output_text') else 'No output_text'}")
        if hasattr(response, 'output_text') and response.output_text:
            logger.info(f"🔥 [RESPONSES API] Output preview: '{response.output_text[:200]}...'")
            
    except Exception as api_error:
        # Manejo específico de errores 400 relacionados con tool_calls
        error_str = str(api_error)
        if "400" in error_str and "tool_call" in error_str:
            logger.error(f"🔥 [RESPONSES API ERROR 400] Error de tool_call detectado: {error_str}")
            logger.error(f"🔥 [RESPONSES API ERROR 400] Este error indica uso incorrecto de 'tool_call' en input")
            logger.error(f"🔥 [RESPONSES API ERROR 400] Payload problemático: {json.dumps(responses_payload, indent=2)}")
            raise ValueError(f"Error en formato de tool_calls para OpenAI Responses API: {error_str}")
        else:
            logger.error(f"🔥 [RESPONSES API ERROR] Error en llamada OpenAI: {str(api_error)}")
            raise api_error

    # Logging de caché automático de OpenAI
    if hasattr(response, 'usage') and response.usage:
        usage = response.usage
        # OpenAI reporta tokens cacheados en cached_tokens
        cached_tokens = getattr(usage, 'cached_tokens', 0)
        total_input_tokens = getattr(usage, 'input_tokens', getattr(usage, 'prompt_tokens', 0))
        
        if cached_tokens > 0:
            cache_hit_rate = (cached_tokens / total_input_tokens * 100) if total_input_tokens > 0 else 0
            savings = cached_tokens * 0.5  # 50% descuento en tokens cacheados
            logger.info(f"💰 [OPENAI CACHE] ✅ Cache automático activo: {cached_tokens}/{total_input_tokens} tokens ({cache_hit_rate:.1f}%)")
            logger.info(f"💰 [OPENAI SAVINGS] 50% descuento aplicado a {cached_tokens} tokens cacheados")
        else:
            logger.info(f"💰 [OPENAI CACHE] ❌ Sin tokens cacheados en esta llamada")
            if total_input_tokens < 1024:
                logger.info(f"💰 [OPENAI CACHE] ℹ️ Caché requiere >1024 tokens (actual: {total_input_tokens})")
    else:
        logger.info(f"💰 [OPENAI CACHE] ❓ Sin información de usage disponible")

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
            
            # Agregar system message (OpenAI tiene caché automático)
            responses_input.append({
                "role": "system", 
                "content": [{
                    "type": "input_text", 
                    "text": assistant_content_text
                }]
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
                logger.info(f"🛠️ [MCP TOOLS] Total de servidores MCP a procesar: {len(mcp_servers)}")
                
                for i, mcp_server_info in enumerate(mcp_servers):
                    mcp_config = mcp_server_info['config']
                    mcp_number = mcp_server_info['number']
                    
                    logger.info(f"🛠️ [MCP SERVER #{i+1}] Procesando MCP #{mcp_number}")
                    logger.info(f"🛠️ [MCP SERVER #{i+1}] Config: {mcp_config}")
                    
                    # Para Responses API: agregar servidor MCP directamente
                    mcp_server_config = {
                        "type": "mcp",
                        "server_url": mcp_config["server_url"],
                        "server_label": mcp_config["server_label"],
                        "require_approval": mcp_config.get("require_approval", "never")
                    }
                    
                    logger.info(f"🛠️ [MCP SERVER #{i+1}] Configuración base MCP: {mcp_server_config}")
                    
                    # MCP servers tienen acceso completo sin restricciones
                    logger.info(f"🛠️ [MCP SERVER #{i+1}] Configurando servidor MCP sin restricciones de herramientas")
                    
                    openai_tools.append(mcp_server_config)
                    logger.info(f"🛠️ [MCP SERVER #{i+1}] ✅ Servidor MCP agregado: {mcp_config['server_label']} -> {mcp_config['server_url']}")
                    logger.info(f"🛠️ [MCP SERVER #{i+1}] Configuración MCP: {mcp_server_config}")
            else:
                logger.info("🛠️ [MCP TOOLS] No hay servidores MCP configurados")

            # Cargar herramientas function para este assistant
            function_tools = load_function_tools_for_assistant(assistant_number)
            if function_tools:
                logger.info(f"🔧 [FUNCTION TOOLS] Agregando {len(function_tools)} herramientas function")
                openai_tools.extend(function_tools)
            else:
                logger.info("🔧 [FUNCTION TOOLS] No hay herramientas function configuradas")

            logger.info(f"🛠️ [TOOLS SUMMARY] ===== RESUMEN FINAL =====\n")
            logger.info(f"🛠️ [TOOLS SUMMARY] Total herramientas configuradas: {len(openai_tools)}")
            
            mcp_count = sum(1 for tool in openai_tools if tool.get('type') == 'mcp')
            function_count = sum(1 for tool in openai_tools if tool.get('type') == 'function')
            
            logger.info(f"🛠️ [TOOLS SUMMARY] Servidores MCP: {mcp_count}")
            logger.info(f"🔧 [TOOLS SUMMARY] Herramientas Function: {function_count}")
            
            for i, tool_config in enumerate(openai_tools):
                tool_type = tool_config.get('type', 'unknown')
                if tool_type == 'mcp':
                    logger.info(f"🛠️ [MCP #{i+1}] {tool_config.get('server_label', 'Sin etiqueta')} -> {tool_config.get('server_url', 'Sin URL')}")
                elif tool_type == 'function':
                    function_name = tool_config.get('name', tool_config.get('function', {}).get('name', 'Sin nombre'))
                    logger.info(f"🔧 [FUNCTION #{i+1}] {function_name}")
            
            logger.info(f"🛠️ [TOOLS SUMMARY] ================================\n")
            
            model_parameters = get_model_parameters(llm_id)
            logger.info(f"🔧 [PARAMETERS] temperature={model_parameters['temperature']}, max_tokens={model_parameters['max_completion_tokens']}")

            # LLAMADA A RESPONSES API CON HERRAMIENTAS
            logger.info(f"🔥 [RESPONSES API] Llamando Responses API con {len(openai_tools)} herramientas total ({mcp_count} MCP + {function_count} Function)")
            
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
                
                # DEBUG: Response RAW completo de OpenAI
                logger.info(f"🔥 [OPENAI RAW] ===== RESPONSE COMPLETO =====")
                logger.info(f"🔥 [OPENAI RAW] Response object: {response}")
                logger.info(f"🔥 [OPENAI RAW] Response type: {type(response)}")
                logger.info(f"🔥 [OPENAI RAW] Response dict: {response.__dict__ if hasattr(response, '__dict__') else 'No dict'}")
                logger.info(f"🔥 [OPENAI RAW] Atributos disponibles: {dir(response)}")
                
                # Verificar output_text
                if hasattr(response, 'output_text'):
                    logger.info(f"🔥 [OPENAI RAW] output_text existe: {repr(response.output_text)}")
                else:
                    logger.warning(f"🔥 [OPENAI RAW] ❌ NO TIENE output_text attribute")
                
                # Verificar choices (Chat Completions)
                if hasattr(response, 'choices'):
                    logger.info(f"🔥 [OPENAI RAW] choices: {response.choices}")
                    if response.choices:
                        for i, choice in enumerate(response.choices):
                            logger.info(f"🔥 [OPENAI RAW] choice[{i}]: {choice}")
                            logger.info(f"🔥 [OPENAI RAW] choice[{i}] dict: {choice.__dict__ if hasattr(choice, '__dict__') else 'No dict'}")
                else:
                    logger.info(f"🔥 [OPENAI RAW] No choices attribute")
                
                # Verificar tool_calls
                if hasattr(response, 'tool_calls'):
                    logger.info(f"🔥 [OPENAI RAW] tool_calls: {response.tool_calls}")
                else:
                    logger.info(f"🔥 [OPENAI RAW] No tool_calls attribute")
                
                # Verificar output para tool calls
                if hasattr(response, 'output'):
                    logger.info(f"🔥 [OPENAI RAW] output length: {len(response.output) if response.output else 0}")
                    if response.output:
                        for i, item in enumerate(response.output):
                            logger.info(f"🔥 [OPENAI RAW] output[{i}]: {item}, type: {type(item)}")
                            if hasattr(item, 'type'):
                                logger.info(f"🔥 [OPENAI RAW] output[{i}].type: {item.type}")
                else:
                    logger.info(f"🔥 [OPENAI RAW] No output attribute")
                
                # Verificar finish_reason
                if hasattr(response, 'finish_reason'):
                    logger.info(f"🔥 [OPENAI RAW] finish_reason: {response.finish_reason}")
                else:
                    logger.info(f"🔥 [OPENAI RAW] No finish_reason attribute")
                
                # Verificar usage data
                if hasattr(response, 'usage'):
                    logger.info(f"🔥 [OPENAI RAW] usage: {response.usage}")
                    logger.info(f"🔥 [OPENAI RAW] usage dict: {response.usage.__dict__ if hasattr(response.usage, '__dict__') else 'No dict'}")
                else:
                    logger.info(f"🔥 [OPENAI RAW] No usage attribute")
                
                logger.info(f"🔥 [OPENAI RAW] ===== FIN RESPONSE DEBUG =====\n")
                
                # ===== VERIFICAR SI HAY TOOL CALLS EN response.output =====
                function_tool_calls = []
                if hasattr(response, 'output') and response.output:
                    logger.info(f"🔧 [TOOL CALLS] Analizando response.output para tool calls")
                    logger.info(f"🔧 [TOOL CALLS] Elementos en response.output: {len(response.output)}")
                    for i, item in enumerate(response.output):
                        logger.info(f"🔧 [TOOL CALLS] Output item[{i}]: {item}, type: {type(item)}")
                        logger.info(f"🔧 [TOOL CALLS] Output item[{i}] attributes: {dir(item) if hasattr(item, '__dict__') else 'No attributes'}")
                        
                        # Verificar si es un ResponseFunctionToolCall
                        if hasattr(item, 'type') and item.type == 'function_call':
                            function_tool_calls.append(item)
                            logger.info(f"🔧 [TOOL CALLS] ✅ Found function_call: {item.name} with call_id: {item.call_id}")
                            logger.info(f"🔧 [TOOL CALLS] ✅ Arguments: {item.arguments}")
                        else:
                            logger.info(f"🔧 [TOOL CALLS] ❌ Item[{i}] is not a function_call (type: {getattr(item, 'type', 'No type')})")
                else:
                    logger.info(f"🔧 [TOOL CALLS] No response.output disponible")
                
                if function_tool_calls:
                    logger.info(f"🔧 [TOOL CALLS] ========== RESUMEN DE TOOL CALLS ==========")
                    logger.info(f"🔧 [TOOL CALLS] Detectadas {len(function_tool_calls)} herramientas a ejecutar en response.output")
                    for i, tool_call in enumerate(function_tool_calls):
                        logger.info(f"🔧 [TOOL CALLS] Tool {i+1}: {tool_call.name} (call_id: {tool_call.call_id})")
                    logger.info(f"🔧 [TOOL CALLS] =======================================")
                    
                    # Manejar tool calls y hacer submit_tool_outputs
                    # Necesitamos pasar mcp_servers para la ejecución de herramientas MCP
                    logger.info(f"🔧 [TOOL CALLS] Iniciando procesamiento con submit_tool_outputs (única ruta válida en Responses API)")
                    
                    response = handle_tool_calls_responses_api(
                        client, response, responses_input, openai_tools, 
                        llm_id, thread_id, model_parameters, assistant_number, 
                        mcp_servers=mcp_servers, function_tool_calls=function_tool_calls
                    )
                    
                    # Continuar con el response de la segunda llamada
                    logger.info(f"🔧 [TOOL CALLS] ✅ Procesamiento de tool calls completado exitosamente")
                    logger.info(f"🔧 [TOOL CALLS] Procesando respuesta final del modelo")
                else:
                    logger.info(f"🔧 [TOOL CALLS] ❌ No se encontraron tool calls en response.output - continuando con respuesta normal")
                
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
                    
                    # Monitoreo de caché automático de OpenAI
                    cached_tokens = getattr(usage, 'cached_tokens', 0)
                    if cached_tokens > 0:
                        total_input = usage_data.get("input_tokens", 0)
                        cache_rate = (cached_tokens / total_input * 100) if total_input > 0 else 0
                        logger.info(f"💰 [OPENAI CACHE FINAL] ✅ {cached_tokens} tokens cacheados ({cache_rate:.1f}% del input)")
                        logger.info(f"💰 [COST SAVINGS] 50% descuento en {cached_tokens} tokens = ~${cached_tokens * 0.0000025:.6f} USD ahorrados")
                        usage_data["cached_tokens"] = cached_tokens
                    else:
                        logger.info(f"💰 [OPENAI CACHE FINAL] ❌ Sin caché automático aplicado")
                        usage_data["cached_tokens"] = 0
                
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
            
            # Validar que tenemos texto final antes de marcar como completado
            if final_text and final_text.strip():
                update_data["status"] = "completed"
                conversation_manager.update(thread_id, update_data)
                logger.info(f"✅ [COMPLETED] OpenAI MCP handler completado exitosamente con respuesta: '{final_text[:100]}...'")
            else:
                # Sin texto final válido - marcar como error
                conversation_manager.update(thread_id, {
                    "response": "No se pudo generar una respuesta final válida",
                    "status": "error",
                    "messages": current_history
                })
                logger.warning(f"⚠️ [NO OUTPUT] Handler completado pero sin texto final válido")
                
        except Exception as e:
            logger.exception("🧪 [MINIMAL TEST] ❌ Error en test mínimo: %s", e)
            conversation_manager.update(thread_id, {
                "response": f"Error en test mínimo: {str(e)}",
                "status": "error",
                "messages": [{"role": "user", "content": message}]
            })
        finally:
            # MOVER event.set() al final - solo después de guardar estado final
            event.set()
            elapsed_time = time.time() - start_time
            logger.info("⏰Test mínimo completado en %.2f segundos para thread_id: %s", elapsed_time, thread_id)
            logger.debug("Finalizando handler OpenAI MCP")