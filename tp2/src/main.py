from fastapi import FastAPI

app = FastAPI()


# Tareas

@app.get("/tareas")
async def get_tareas():
    return

@app.get("/tareas/{id}")
async def get_tarea(id):
    return

@app.post("/tareas")
async def post_tarea():
    return

@app.delete("/tareas/{id}")
async def delete_tarea(id):
    return

# Estadisticas

@app.get("/estadisticas")
async def get_estadisticas():
    return