from __future__ import annotations

from fastapi import FastAPI

from preparador_audiencia.api import router as api_router
from preparador_audiencia.environment import load_environment
from preparador_audiencia.routes.hearing_dossier import router as hearing_dossier_router
from preparador_audiencia.routes.structured_transcription import (
    router as structured_transcription_router,
)

load_environment()

app = FastAPI(title="Preparador de Audiencia API", version="0.1.0")
app.include_router(api_router)
app.include_router(hearing_dossier_router)
app.include_router(structured_transcription_router)
