"""
LLM Handlers - Versión actualizada con ConversationManager
Funciones para manejar diferentes modelos LLM con almacenamiento unificado
"""

import json
import openai
import requests
import threading
import random
import google.genai as genai
from google.genai import types
import base64
import os
import re
import anthropic
from threading import Thread, Event
import uuid
import logging
from datetime import datetime
import pytz
from datetime import timedelta
import xmlrpc.client
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
import time
from functools import wraps

# Servicios n8n eliminados - se manejará con MCP
from app.utils import remove_thinking_block, create_svg_base64

logger = logging.getLogger(__name__)

# Herramientas se manejarán vía MCP
TOOL_FUNCTIONS = {}

# Función get_tools_file_name eliminada - ahora se usa un solo prompt del sistema

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

# Las funciones de los handlers se importan bajo demanda para evitar imports circulares
# from app.anthropic_handler import generate_response
# from app.openai_handler import generate_response_openai  
# from app.gemini_handler import generate_response_gemini


# ===== PREPARACIÓN PARA MCP =====
# 
# Para agregar soporte MCP más adelante, solo necesitarás:
# 
# 1. Agregar esta función:
# 
# def load_mcp_tools(mcp_server_config):
#     """
#     Carga herramientas desde un servidor MCP.
#     
#     Args:
#         mcp_server_config: Configuración del servidor MCP
#     
#     Returns:
#         Lista de herramientas en formato Gemini
#     """
#     # Implementar conexión MCP aquí
#     pass
# 
# 2. Modificar la sección de herramientas:
# 
# # En lugar de solo cargar desde archivo JSON:
# file_tools = [convert_tool_to_gemini_format(tool) for tool in openai_tools]
# 
# # Agregar herramientas MCP:
# mcp_tools = load_mcp_tools(mcp_config) if mcp_config else []
# 
# gemini_tools = [{
#     "functionDeclarations": file_tools + mcp_tools
# }]
# 
# 3. El resto del código ya está preparado para manejar cualquier tipo de función!