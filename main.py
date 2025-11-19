import os
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone

from database import db, create_document, get_documents
from schemas import Process, ProcessStage, ProcessItem, ActivityLog

app = FastAPI(title="Process Simulation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# Seed a default process definition on first access
# ------------------------------------------------------------------
DEFAULT_PROCESS = {
    "key": "default",
    "name": "Product Delivery Lifecycle",
    "stages": [
        {
            "key": "initiation",
            "title": "Initiation",
            "description": "Kick-off and context setup",
            "items": [
                {"key": "requirements", "title": "Requirement Document", "optional": False},
                {"key": "concept", "title": "Concept Design Document", "optional": False},
                {"key": "sqp", "title": "Software Quality Plan", "optional": False},
                {"key": "poc", "title": "Optional POC Scope", "optional": True},
            ],
        },
        {
            "key": "review",
            "title": "Review & Approval",
            "description": "Assignments, downloads, reviews and decisions",
            "items": [
                {"key": "doc_review", "title": "Document Review", "optional": False},
            ],
        },
        {
            "key": "delivery",
            "title": "Delivery",
            "description": "Handover and sign-off",
            "items": [
                {"key": "handover", "title": "Final Handover", "optional": False},
            ],
        },
    ],
}

class SeedResponse(BaseModel):
    seeded: bool

@app.get("/api/seed", response_model=SeedResponse)
def seed_process():
    existing = list(db["process"].find({"key": DEFAULT_PROCESS["key"]}).limit(1)) if db else []
    if not existing and db:
        create_document("process", Process(**DEFAULT_PROCESS))
        return {"seeded": True}
    return {"seeded": False}

# ------------------------------------------------------------------
# Public endpoints
# ------------------------------------------------------------------

@app.get("/api/process", response_model=Process)
def get_process():
    if not db:
        return JSONResponse(status_code=500, content={"error": "Database not configured"})
    doc = db["process"].find_one({"key": DEFAULT_PROCESS["key"]})
    if not doc:
        # auto seed
        create_document("process", Process(**DEFAULT_PROCESS))
        doc = db["process"].find_one({"key": DEFAULT_PROCESS["key"]})
    # Convert Mongo document to Pydantic-like dict
    doc.pop("_id", None)
    return doc

class UploadResponse(BaseModel):
    ok: bool
    filename: str
    item_key: str

@app.post("/api/upload", response_model=UploadResponse)
async def upload_file(item_key: str = Form(...), stage_key: str = Form(...), file: UploadFile = File(...), actor: str = Form("user")):
    # In prototype, we won't store file bytes. We'll log the action.
    if not db:
        return JSONResponse(status_code=500, content={"error": "Database not configured"})
    timestamp = datetime.now(timezone.utc).isoformat()
    log = ActivityLog(
        process_key=DEFAULT_PROCESS["key"],
        stage_key=stage_key,
        item_key=item_key,
        type="upload",
        message=f"{actor} uploaded {file.filename}",
        actor=actor,
        meta={"filename": file.filename, "size": file.size if hasattr(file, 'size') else None},
    )
    create_document("activitylog", log)
    return {"ok": True, "filename": file.filename, "item_key": item_key}

class AssignmentBody(BaseModel):
    stage_key: str
    item_key: str
    assignee: str
    actor: str = "admin"

@app.post("/api/assign")
def assign_reviewer(body: AssignmentBody):
    if not db:
        return JSONResponse(status_code=500, content={"error": "Database not configured"})
    log = ActivityLog(
        process_key=DEFAULT_PROCESS["key"],
        stage_key=body.stage_key,
        item_key=body.item_key,
        type="assignment",
        message=f"{body.actor} assigned {body.assignee} to review",
        actor=body.actor,
        meta={"assignee": body.assignee},
    )
    create_document("activitylog", log)
    return {"ok": True}

class ActionBody(BaseModel):
    stage_key: str
    item_key: str
    action: str # download|review|decision|note
    note: Optional[str] = None
    actor: str = "assignee"

@app.post("/api/action")
def action(body: ActionBody):
    if not db:
        return JSONResponse(status_code=500, content={"error": "Database not configured"})
    assert body.action in ["download", "review", "decision", "note"]
    message = {
        "download": f"{body.actor} downloaded the document",
        "review": f"{body.actor} reviewed the document",
        "decision": f"{body.actor} made a decision",
        "note": f"{body.actor} left a note: {body.note or ''}",
    }[body.action]
    log = ActivityLog(
        process_key=DEFAULT_PROCESS["key"],
        stage_key=body.stage_key,
        item_key=body.item_key,
        type=body.action,
        message=message,
        actor=body.actor,
        meta={"note": body.note} if body.note else None,
    )
    create_document("activitylog", log)
    return {"ok": True}

class LogsResponse(BaseModel):
    logs: List[dict]

@app.get("/api/logs", response_model=LogsResponse)
def get_logs(stage_key: Optional[str] = None, item_key: Optional[str] = None):
    if not db:
        return JSONResponse(status_code=500, content={"error": "Database not configured"})
    query = {"process_key": DEFAULT_PROCESS["key"]}
    if stage_key:
        query["stage_key"] = stage_key
    if item_key:
        query["item_key"] = item_key
    logs = db["activitylog"].find(query).sort("created_at", -1)
    out = []
    for l in logs:
        l["id"] = str(l.pop("_id", ""))
        out.append(l)
    return {"logs": out}

@app.get("/")
def read_root():
    return {"message": "Process Simulation Backend Running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        from database import db as _db
        if _db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = _db.name if hasattr(_db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = _db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
