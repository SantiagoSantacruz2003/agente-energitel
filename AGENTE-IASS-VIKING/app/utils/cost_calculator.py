"""
Calculadora de costos para modelos LLM
Calcula costos basados en tokens usando precios por millón de tokens
"""

import json
import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class CostCalculator:
    def __init__(self):
        self.costs = self._load_costs()
    
    def _load_costs(self) -> Dict:
        """Carga la configuración de costos desde el archivo JSON"""
        try:
            costs_file = os.path.join(
                os.path.dirname(__file__), '..', '..', 'config', 'model_costs.json'
            )
            with open(costs_file, 'r', encoding='utf-8') as f:
                costs_data = json.load(f)
                logger.info(f"Costos de modelos cargados exitosamente: {len(costs_data)} modelos")
                return costs_data
        except FileNotFoundError:
            logger.error(f"Archivo de costos no encontrado: {costs_file}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Error al parsear archivo de costos JSON: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error inesperado cargando costos de modelos: {e}")
            return {}
    
    def calculate_cost(self, model_name: str, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> Dict:
        """
        Calcula el costo basado en tokens de entrada, salida y cache
        
        Args:
            model_name: Nombre del modelo (ej: "gpt-4o")
            input_tokens: Número de tokens de entrada
            output_tokens: Número de tokens de salida
            cached_input_tokens: Número de tokens de entrada desde cache (opcional)
        
        Returns:
            Dict con total_cost, input_cost, output_cost, cached_cost, currency, etc.
        """
        if not self.costs:
            logger.warning("No hay configuración de costos disponible")
            return self._get_fallback_cost_response(model_name, input_tokens, output_tokens, cached_input_tokens)
        
        if model_name not in self.costs:
            logger.warning(f"Modelo '{model_name}' no encontrado en configuración de costos")
            return self._get_fallback_cost_response(model_name, input_tokens, output_tokens, cached_input_tokens)
        
        model_config = self.costs[model_name]
        
        try:
            # Calcular costos basados en millones de tokens
            input_cost = (input_tokens / 1_000_000) * model_config["input_cost_per_1m_tokens"]
            output_cost = (output_tokens / 1_000_000) * model_config["output_cost_per_1m_tokens"]
            
            # Calcular costo de tokens de cache si aplica
            cached_cost = 0.0
            if cached_input_tokens > 0 and "cached_input_cost_per_1m_tokens" in model_config:
                cached_cost = (cached_input_tokens / 1_000_000) * model_config["cached_input_cost_per_1m_tokens"]
            
            total_cost = input_cost + output_cost + cached_cost
            
            # Construir cost_breakdown dinámicamente
            cost_breakdown_parts = [
                f"Input: {input_tokens:,} tokens × ${model_config['input_cost_per_1m_tokens']}/1M = ${input_cost:.8f}",
                f"Output: {output_tokens:,} tokens × ${model_config['output_cost_per_1m_tokens']}/1M = ${output_cost:.8f}"
            ]
            
            if cached_input_tokens > 0:
                cost_breakdown_parts.append(
                    f"Cached: {cached_input_tokens:,} tokens × ${model_config.get('cached_input_cost_per_1m_tokens', 0)}/1M = ${cached_cost:.8f}"
                )
            
            return {
                "total_cost": round(total_cost, 8),  # Más precisión para costos pequeños
                "input_cost": round(input_cost, 8),
                "output_cost": round(output_cost, 8),
                "cached_cost": round(cached_cost, 8),
                "currency": model_config.get("currency", "USD"),
                "cost_breakdown": ", ".join(cost_breakdown_parts),
                "pricing_model": "per_1m_tokens",
                "model_info": {
                    "provider": model_config.get("provider", "Unknown"),
                    "description": model_config.get("description", "")
                }
            }
            
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Error calculando costo para modelo {model_name}: {e}")
            return self._get_fallback_cost_response(model_name, input_tokens, output_tokens, cached_input_tokens)
    
    def _get_fallback_cost_response(self, model_name: str, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> Dict:
        """Respuesta de fallback cuando no se puede calcular el costo"""
        cached_info = f" + {cached_input_tokens:,} cached tokens" if cached_input_tokens > 0 else ""
        return {
            "total_cost": 0.0,
            "input_cost": 0.0,
            "output_cost": 0.0,
            "cached_cost": 0.0,
            "currency": "USD",
            "cost_breakdown": f"Costos no configurados para modelo '{model_name}'",
            "pricing_model": "unavailable",
            "model_info": {
                "provider": "Unknown",
                "description": f"Modelo no reconocido: {model_name}"
            },
            "warning": f"No se pudo calcular costo para {input_tokens:,} input tokens + {output_tokens:,} output tokens{cached_info}"
        }
    
    def get_model_info(self, model_name: str) -> Optional[Dict]:
        """
        Obtiene información completa de un modelo
        
        Args:
            model_name: Nombre del modelo
            
        Returns:
            Diccionario con información del modelo o None si no existe
        """
        return self.costs.get(model_name)
    
    def get_available_models(self) -> list:
        """Retorna lista de modelos disponibles en la configuración"""
        return list(self.costs.keys())
    
    def reload_costs(self) -> bool:
        """
        Recarga la configuración de costos desde el archivo
        Útil para cambios en tiempo real sin reiniciar la aplicación
        
        Returns:
            True si la recarga fue exitosa, False en caso contrario
        """
        old_count = len(self.costs)
        self.costs = self._load_costs()
        new_count = len(self.costs)
        
        if new_count > 0:
            logger.info(f"Configuración de costos recargada exitosamente: {old_count} → {new_count} modelos")
            return True
        else:
            logger.error("Error al recargar configuración de costos")
            return False
    
    def estimate_conversation_cost(self, model_name: str, message_length: int, expected_response_length: int = None) -> Dict:
        """
        Estima el costo de una conversación basado en longitud de mensaje
        
        Args:
            model_name: Nombre del modelo
            message_length: Longitud aproximada del mensaje en caracteres
            expected_response_length: Longitud esperada de respuesta (si no se proporciona, se estima)
            
        Returns:
            Estimación de costo
        """
        # Estimación aproximada: 1 token ≈ 4 caracteres para texto en español
        estimated_input_tokens = max(1, message_length // 4)
        estimated_output_tokens = expected_response_length // 4 if expected_response_length else estimated_input_tokens // 2
        
        cost_result = self.calculate_cost(model_name, estimated_input_tokens, estimated_output_tokens)
        cost_result["estimation_note"] = "Estimación basada en ~4 caracteres por token"
        cost_result["estimated_input_tokens"] = estimated_input_tokens
        cost_result["estimated_output_tokens"] = estimated_output_tokens
        
        return cost_result

# Instancia global para uso en toda la aplicación
cost_calculator = CostCalculator()