from dotenv import load_dotenv

# Cargar variables de entorno ANTES de importar la app
load_dotenv()

from app.app import app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
