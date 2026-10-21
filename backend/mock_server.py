"""Run the local API for frontend integration.

Usage: ..\\.venv\\Scripts\\python.exe mock_server.py

Despite the historical filename, Agent endpoints use the real model configured
in the project .env. Tests inject their own fake adapters separately.
"""

import uvicorn

from app.main import app


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
