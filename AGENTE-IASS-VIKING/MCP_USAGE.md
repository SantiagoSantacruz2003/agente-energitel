# 📖 **Guía de uso de MCP con authorized_mcp**

La nueva implementación permite usar múltiples servidores MCP mediante el parámetro `authorized_mcp` en lugar de depender del número de `assistant`.

## 🔧 **Cómo usar la nueva lógica**

### **1. Estructura del Request**

```json
{
    "message": "Hola, necesito ayuda",
    "assistant": 0,
    "modelID": "openai",
    "llmID": "gpt-4o",
    "subscriber_id": "12345",
    "thread_id": "thread_123",
    "authorized_mcp": [0, 2, 4],
    "telefono": "3001234567",
    "direccionCliente": "Calle 123 #45-67"
}
```

### **2. Parámetro authorized_mcp**

- **Tipo**: Array de números enteros
- **Descripción**: Lista de números que identifican qué servidores MCP están autorizados para esta conversación
- **Ejemplo**: `[0, 2, 4]` habilitará los MCPs 0, 2 y 4

### **3. Mapeo de números MCP**

Los números corresponden a la configuración en `endpoints.py`:

```python
ASSISTANT_MCP_SERVERS = {
    0: {  # MCP para ventas/inicial
        "type": "mcp",
        "server_url": "https://n8niass.cocinandosonrisas.co/mcp/baseDatosEnergitel/sse",
        "server_label": "mcp-ventas",
        "require_approval": "never"
    },
    1: {  # MCP para domicilio
        "type": "mcp", 
        "server_url": "https://n8niass.cocinandosonrisas.co/mcp/baseDatosEnergitel/sse",
        "server_label": "mcp-domicilio",
        "require_approval": "never"
    },
    2: {  # MCP para recoger
        "type": "mcp",
        "server_url": "https://n8niass.cocinandosonrisas.co/mcp/baseDatosEnergitel/sse", 
        "server_label": "mcp-recoger",
        "require_approval": "never"
    },
    3: {  # MCP para forma de pago
        "type": "mcp",
        "server_url": "https://n8niass.cocinandosonrisas.co/mcp/baseDatosEnergitel/sse",
        "server_label": "mcp-pagos",
        "require_approval": "never"
    },
    4: {  # MCP para postventa
        "type": "mcp",
        "server_url": "https://n8niass.cocinandosonrisas.co/mcp/baseDatosEnergitel/sse",
        "server_label": "mcp-postventa", 
        "require_approval": "never"
    },
    5: {  # MCP por defecto
        "type": "mcp",
        "server_url": "https://n8niass.cocinandosonrisas.co/mcp/baseDatosEnergitel/sse",
        "server_label": "mcp-default",
        "require_approval": "never"
    }
}
```

## 📊 **Ejemplos de uso**

### **Ejemplo 1: Un solo MCP**
```json
{
    "authorized_mcp": [0]
}
```
Solo habilitará el MCP de ventas (#0).

### **Ejemplo 2: Múltiples MCPs**
```json
{
    "authorized_mcp": [0, 3, 4]
}
```
Habilitará los MCPs de ventas (#0), pagos (#3) y postventa (#4).

### **Ejemplo 3: Array vacío (fallback)**
```json
{
    "authorized_mcp": []
}
```
Usará el valor de `assistant` como fallback, o el MCP por defecto (#5).

### **Ejemplo 4: Sin parámetro authorized_mcp**
```json
{}
```
Se comportará igual que el array vacío - usará el fallback.

## 🔍 **Funcionamiento interno**

1. **Validación**: El sistema valida que `authorized_mcp` sea una lista
2. **Conexión**: Se conecta a cada servidor MCP especificado en la lista
3. **Herramientas**: Carga herramientas de todos los MCPs conectados
4. **Ejecución**: Al ejecutar una herramienta, busca en qué MCP está disponible
5. **Respuesta**: Incluye información sobre qué MCP ejecutó cada herramienta

## 📝 **Logs de ejemplo**

```
INFO: Usando 3 servidor(es) MCP autorizados: ['mcp-ventas', 'mcp-pagos', 'mcp-postventa']
INFO: MCP 'mcp-ventas' (#0) conectado a https://n8niass.cocinandosonrisas.co/mcp/baseDatosEnergitel/sse
INFO: Cargadas 5 herramientas desde MCP #0
INFO: Total de 12 herramientas cargadas desde 3 MCP(s): ['crear_pedido', 'enviar_menu', ...]
INFO: Herramienta crear_pedido encontrada en MCP mcp-ventas
INFO: Tool crear_pedido ejecutada exitosamente vía MCP #0 (mcp-ventas)
```

## ⚙️ **Configuración en variables de entorno**

Cada MCP puede tener su propia URL configurada:

```bash
# En tu archivo .env
MCP_SERVER_URL_0=https://servidor-ventas.com/mcp
MCP_SERVER_URL_1=https://servidor-domicilios.com/mcp  
MCP_SERVER_URL_2=https://servidor-pickup.com/mcp
MCP_SERVER_URL_3=https://servidor-pagos.com/mcp
MCP_SERVER_URL_4=https://servidor-soporte.com/mcp
MCP_SERVER_URL_DEFAULT=https://servidor-default.com/mcp
```

## 🎯 **Ventajas de la nueva implementación**

- ✅ **Flexibilidad**: Puedes habilitar solo los MCPs necesarios para cada conversación
- ✅ **Escalabilidad**: Fácil agregar nuevos servidores MCP
- ✅ **Control granular**: Autorización específica por request
- ✅ **Fallback robusto**: Si no se especifica, usa la lógica anterior
- ✅ **Trazabilidad**: Los logs muestran qué MCP ejecutó cada herramienta
- ✅ **Rendimiento**: Solo conecta a los MCPs autorizados