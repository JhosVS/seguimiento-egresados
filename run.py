# run.py
import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Solo para desarrollo local; en el servidor se usa gunicorn (gunicorn run:app)
    debug = os.getenv('FLASK_DEBUG', '0').lower() in ('1', 'true')
    app.run(host='127.0.0.1', port=5000, debug=debug)