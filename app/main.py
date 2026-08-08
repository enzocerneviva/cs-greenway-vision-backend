from fastapi import FastAPI

app = FastAPI(
    title="GreenWay Vision API",
    description="Backend da plataforma GreenWay Vision",
    version="0.1.0"
)


@app.get("/health")
def health_check():
    return {"status": "ok"}