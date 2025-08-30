# Utils package
from .cost_calculator import cost_calculator

# Importar funciones del módulo utils original
import random
import re
import base64
import logging

logger = logging.getLogger(__name__)

def remove_thinking_block(text: str) -> str:
    """Remove <thinking> blocks from text."""
    pattern = re.compile(r'<thinking>.*?</thinking>', re.DOTALL | re.IGNORECASE)
    return pattern.sub('', text).strip()

def get_random_hsl() -> str:
    """Generate a random HSL color."""
    h = random.randint(0, 360)
    s = random.randint(0, 100)
    l = random.randint(0, 100)
    return f'hsl({h}, {s}%, {l}%)'

def create_svg_base64(letter: str, width: int, height: int):
    """Create a base64 encoded SVG with a random background."""
    background_color = get_random_hsl()
    svg_string = (
        f"<svg height='{height}' width='{width}' xmlns='http://www.w3.org/2000/svg' "
        f"xmlns:xlink='http://www.w3.org/1999/xlink'><rect fill='{background_color}' "
        f"height='{height}' width='{width}'/><text fill='#ffffff' font-size='{height * 0.53}' "
        f"text-anchor='middle' x='{width / 2}' y='{height * 0.7}' font-family='sans-serif'>{letter}</text></svg>"
    )
    base64_bytes = base64.b64encode(svg_string.encode('utf-8'))
    base64_string = base64_bytes.decode('utf-8')
    return base64_string, svg_string