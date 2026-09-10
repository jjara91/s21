from fastapi import FastAPI

app = FastAPI(title="Registros de predicación")


@app.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok"}
