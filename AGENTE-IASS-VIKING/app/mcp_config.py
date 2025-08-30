"""
Configuración MCP (Model Context Protocol) simplificada
"""

import os
import logging
import json
import requests

logger = logging.getLogger(__name__)


class SimpleMCPClient:
    """Cliente MCP simplificado para integración directa con servidor HTTP"""
    
    def __init__(self, mcp_server, assistant_number):
        self.mcp_server = mcp_server
        self.assistant_number = assistant_number
        self.server_url = mcp_server['server_url']
        self.server_label = mcp_server['server_label']
        self.tools = []
        self.is_connected = False
        
        logger.info(f"Inicializando MCP Client: {self.server_label} para assistant {assistant_number}")
        logger.info(f"URL del servidor: {self.server_url}")
        
        # Inicializar conexión
        self._initialize_connection()
    
    def _initialize_connection(self):
        """Inicializa la conexión con el servidor MCP"""
        try:
            # Probar conexión con el servidor
            response = requests.get(f"{self.server_url}/health", timeout=5)
            if response.status_code == 200:
                self.is_connected = True
                logger.info(f"MCP conectado exitosamente: {self.server_label}")
            else:
                logger.warning(f"Servidor MCP responde pero con estado {response.status_code}")
                self.is_connected = False
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"No se pudo conectar al servidor MCP {self.server_url}: {str(e)}")
            self.is_connected = False
            
        # Cargar herramientas según el assistant
        self._load_tools_for_assistant()
    
    def _load_tools_for_assistant(self):
        """Carga las herramientas específicas para este assistant"""
        # Mapeo simplificado de assistant a archivo de herramientas
        tools_mapping = {
            0: "tools_openai.json",
            5: "default_tools.json"
        }
        
        tools_file = tools_mapping.get(self.assistant_number, "default_tools.json")
        tools_path = os.path.join(os.path.dirname(__file__), '..', 'tools', tools_file)
        
        try:
            with open(tools_path, 'r', encoding='utf-8') as f:
                self.tools = json.load(f)
                logger.info(f"Cargadas {len(self.tools)} herramientas desde {tools_file} para MCP {self.server_label}")
        except FileNotFoundError:
            logger.warning(f"Archivo de herramientas no encontrado: {tools_path}")
            self.tools = []
        except Exception as e:
            logger.error(f"Error cargando herramientas: {str(e)}")
            self.tools = []
    
    def get_available_tools(self):
        """Retorna las herramientas disponibles en formato OpenAI"""
        return self.tools
    
    def execute_tool(self, tool_name, tool_args):
        """Ejecuta una herramienta vía MCP usando HTTP"""
        logger.info(f"Ejecutando tool MCP: {tool_name} en {self.server_url} (MCP #{self.assistant_number})")
        
        if not self.is_connected:
            return {
                "error": "MCP no conectado",
                "server": self.server_label,
                "tool": tool_name,
                "mcp_number": self.assistant_number
            }
        
        try:
            # Preparar payload para el servidor MCP
            payload = {
                "tool": tool_name,
                "arguments": tool_args,
                "assistant": self.assistant_number,
                "server_label": self.server_label,
                "mcp_number": self.assistant_number
            }
            
            # Enviar solicitud al servidor MCP
            response = requests.post(
                f"{self.server_url}/execute-tool",
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                # Agregar información del MCP que ejecutó la herramienta
                if isinstance(result, dict):
                    result["executed_by_mcp"] = {
                        "number": self.assistant_number,
                        "label": self.server_label,
                        "url": self.server_url
                    }
                logger.info(f"Tool {tool_name} ejecutada exitosamente vía MCP #{self.assistant_number} ({self.server_label})")
                return result
            else:
                error_msg = f"Error HTTP {response.status_code}: {response.text}"
                logger.error(f"Error ejecutando tool {tool_name} en MCP #{self.assistant_number}: {error_msg}")
                return {
                    "error": error_msg,
                    "server": self.server_label,
                    "tool": tool_name,
                    "status_code": response.status_code,
                    "mcp_number": self.assistant_number
                }
                
        except requests.exceptions.Timeout:
            error_msg = f"Timeout ejecutando herramienta MCP #{self.assistant_number}"
            logger.error(f"{error_msg}: {tool_name}")
            return {
                "error": error_msg, 
                "tool": tool_name,
                "mcp_number": self.assistant_number
            }
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Error de conexión en MCP #{self.assistant_number}: {str(e)}"
            logger.error(f"Error ejecutando tool {tool_name}: {error_msg}")
            return {
                "error": error_msg, 
                "tool": tool_name,
                "mcp_number": self.assistant_number
            }
    
    def disconnect(self):
        """Desconecta del servidor MCP"""
        if self.is_connected:
            self.is_connected = False
            logger.info(f"MCP desconectado: {self.server_label}")


def get_mcp_client(mcp_server, assistant_number):
    """
    Factory function para obtener un cliente MCP configurado
    
    Args:
        mcp_server: Diccionario con configuración del servidor MCP
        assistant_number: Número del asistente (0-5)
    
    Returns:
        SimpleMCPClient: Cliente MCP configurado
    """
    try:
        client = SimpleMCPClient(mcp_server, assistant_number)
        return client
    except Exception as e:
        logger.error(f"Error creando MCP client: {str(e)}")
        return None


def convert_mcp_tools_to_openai(mcp_tools):
    """
    Convierte herramientas del formato MCP al formato OpenAI
    
    Args:
        mcp_tools: Lista de herramientas en formato MCP
    
    Returns:
        Lista de herramientas en formato OpenAI
    """
    if not mcp_tools:
        return []
        
    openai_tools = []
    
    for tool in mcp_tools:
        try:
            # Si ya está en formato OpenAI, no convertir
            if "type" in tool and tool["type"] == "function":
                openai_tools.append(tool)
            else:
                # Convertir de formato simple a formato OpenAI
                openai_tool = {
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {})
                    }
                }
                openai_tools.append(openai_tool)
        except Exception as e:
            logger.warning(f"Error convirtiendo herramienta {tool}: {str(e)}")
            continue
    
    return openai_tools