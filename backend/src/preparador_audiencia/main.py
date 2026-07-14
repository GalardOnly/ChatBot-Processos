from __future__ import annotations

from fastapi import FastAPI

from preparador_audiencia.api import router
from preparador_audiencia.environment import load_environment

load_environment()

app = FastAPI(title="Preparador de Audiencia API", version="0.1.0")
app.include_router(router)
