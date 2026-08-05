from __future__ import annotations

from fastapi import FastAPI

from preparador_audiencia.api import router as api_router
from preparador_audiencia.environment import load_environment
from preparador_audiencia.routes.defense_theses import router as defense_theses_router
from preparador_audiencia.routes.hearing_dossier import router as hearing_dossier_router
from preparador_audiencia.routes.judgment_structure import (
    router as judgment_structure_router,
)
from preparador_audiencia.routes.prescription import router as prescription_router
from preparador_audiencia.routes.procedural_nullities import (
    router as procedural_nullities_router,
)
from preparador_audiencia.routes.structured_transcription import (
    router as structured_transcription_router,
)
from preparador_audiencia.routes.testimony_comparison import (
    router as testimony_comparison_router,
)
from preparador_audiencia.routes.testimony_questions import (
    router as testimony_questions_router,
)

load_environment()

app = FastAPI(title="Preparador de Audiencia API", version="0.1.0")
app.include_router(api_router)
app.include_router(defense_theses_router)
app.include_router(hearing_dossier_router)
app.include_router(judgment_structure_router)
app.include_router(prescription_router)
app.include_router(procedural_nullities_router)
app.include_router(structured_transcription_router)
app.include_router(testimony_comparison_router)
app.include_router(testimony_questions_router)
