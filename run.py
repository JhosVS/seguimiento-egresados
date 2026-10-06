# run.py
import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Flask/Python lee la variable FLASK_DEBUG si existe, o usa True por defecto en desarrollo
    debug_val = os.getenv('FLASK_DEBUG', 'True').lower() in ['true', '1']
    app.run(host='0.0.0.0', port=5000, debug=debug_val)