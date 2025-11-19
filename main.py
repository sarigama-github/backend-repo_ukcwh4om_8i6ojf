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
# Seed a default process definition on first access + rich mock data
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
    logs_seeded: bool = False


def _seed_mock_logs():
    """Insert a diverse set of activity logs across stages/items exactly once."""
    if not db:
        return False
    existing_logs = list(db["activitylog"].find({"process_key": DEFAULT_PROCESS["key"]}).limit(1))
    if existing_logs:
        return False

    actors = [
        "olivia.r", "liam.k", "ava.m", "noah.t", "mia.p",
        "ethan.s", "sophia.j", "lucas.b", "amelia.v", "jack.chen",
    ]
    admins = ["admin", "qa.lead", "compliance.admin", "pm.admin"]

    # Define a set of mock events per item
    events = [
        ("initiation", "requirements", [
            ("upload", "requester uploaded BRD_v1.2.pdf", "olivia.r", {"filename": "BRD_v1.2.pdf", "size": 523_441}),
            ("assignment", "admin assigned liam.k to review", "admin", {"assignee": "liam.k"}),
            ("download", "liam.k downloaded the document", "liam.k", None),
            ("review", "liam.k reviewed the document", "liam.k", {"score": 0.92}),
            ("note", "qa.lead left a note: please clarify scope for module X", "qa.lead", {"note": "please clarify scope for module X"}),
            ("decision", "qa.lead made a decision", "qa.lead", {"decision": "approve with comments"}),
        ]),
        ("initiation", "concept", [
            ("upload", "requester uploaded Concept_Figma_Link.txt", "ava.m", {"filename": "Concept_Figma_Link.txt"}),
            ("assignment", "admin assigned sophia.j to review", "pm.admin", {"assignee": "sophia.j"}),
            ("download", "sophia.j downloaded the document", "sophia.j", None),
            ("review", "sophia.j reviewed the document", "sophia.j", {"score": 0.88}),
            ("note", "pm.admin left a note: explore alt color palette", "pm.admin", {"note": "explore alt color palette"}),
        ]),
        ("initiation", "sqp", [
            ("upload", "requester uploaded SQP_v0.9.docx", "noah.t", {"filename": "SQP_v0.9.docx"}),
            ("assignment", "compliance.admin assigned jack.chen to review", "compliance.admin", {"assignee": "jack.chen"}),
            ("download", "jack.chen downloaded the document", "jack.chen", None),
            ("note", "jack.chen left a note: need threat model section", "jack.chen", {"note": "need threat model section"}),
            ("review", "jack.chen reviewed the document", "jack.chen", {"score": 0.75}),
            ("decision", "compliance.admin made a decision", "compliance.admin", {"decision": "changes requested"}),
        ]),
        ("initiation", "poc", [
            ("upload", "requester uploaded POC_outline.md", "mia.p", {"filename": "POC_outline.md"}),
            ("assignment", "admin assigned lucas.b to review", "admin", {"assignee": "lucas.b"}),
            ("download", "lucas.b downloaded the document", "lucas.b", None),
            ("note", "lucas.b left a note: optional, but useful for risk burn‑down", "lucas.b", {"note": "optional, but useful for risk burn‑down"}),
        ]),
        ("review", "doc_review", [
            ("assignment", "qa.lead assigned amelia.v to review", "qa.lead", {"assignee": "amelia.v"}),
            ("download", "amelia.v downloaded the document", "amelia.v", None),
            ("review", "amelia.v reviewed the document", "amelia.v", {"score": 0.97}),
            ("decision", "qa.lead made a decision", "qa.lead", {"decision": "approved"}),
            ("note", "qa.lead left a note: proceeding to delivery", "qa.lead", {"note": "proceeding to delivery"}),
        ]),
        ("delivery", "handover", [
            ("upload", "requester uploaded handover_package.zip", "ethan.s", {"filename": "handover_package.zip", "size": 5_234_102}),
            ("download", "pm.admin downloaded the document", "pm.admin", None),
            ("note", "pm.admin left a note: scheduling training", "pm.admin", {"note": "scheduling training"}),
            ("decision", "pm.admin made a decision", "pm.admin", {"decision": "signed off"}),
        ]),
    ]

    # Insert a bunch of shuffled timestamps
    now = datetime.now(timezone.utc)
    t = now
    for stage_key, item_key, actions in events:
        for etype, msg, actor, meta in actions:
            log = ActivityLog(
                process_key=DEFAULT_PROCESS["key"],
                stage_key=stage_key,
                item_key=item_key,
                type=etype,
                message=msg,
                actor=actor,
                meta=meta,
            )
            # create_document sets created_at/updated_at, but we want spread out times
            inserted_id = create_document("activitylog", log)
            # backdate created_at incrementally for variety
            try:
                db["activitylog"].update_one({"_id": db["activitylog"].find_one({"_id": db["activitylog"].create_index})}, {"$set": {"created_at": t}})
            except Exception:
                pass
            t = t.replace(microsecond=0)

    # Add a few random notes across items for diversity
    extra_notes = [
        ("initiation", "requirements", "risk: data migration complexity"),
        ("initiation", "concept", "consider accessibility WCAG 2.2"),
        ("delivery", "handover", "need runbook appendix"),
    ]
    for s, i, note in extra_notes:
        create_document("activitylog", ActivityLog(
            process_key=DEFAULT_PROCESS["key"],
            stage_key=s,
            item_key=i,
            type="note",
            message=f"note: {note}",
            actor="observer",
            meta={"note": note},
        ))

    return True


@app.get("/api/seed", response_model=SeedResponse)
def seed_process():
    existing = list(db["process"].find({"key": DEFAULT_PROCESS["key"]}).limit(1)) if db else []
    seeded = False
    if not existing and db:
        create_document("process", Process(**DEFAULT_PROCESS))
        seeded = True
    # Always attempt to seed mock logs once
    logs_seeded = _seed_mock_logs() if db else False
    return {"seeded": seeded, "logs_seeded": logs_seeded}

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
    log = ActivityLog(
        process_key=DEFAULT_PROCESS["key"],
        stage_key=stage_key,
        item_key=item_key,
        type="upload",
        message=f"{actor} uploaded {file.filename}",
        actor=actor,
        meta={"filename": file.filename},
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
