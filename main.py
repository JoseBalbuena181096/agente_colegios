from fastapi import FastAPI
from app.logging_config import setup_logging
from app.routers import social, conversations

setup_logging()

app = FastAPI()

# Include Routers
app.include_router(social.router)
app.include_router(conversations.router)

@app.get("/")
def read_root():
    return {"message": "Agente Colegios San Angel is ready"}
