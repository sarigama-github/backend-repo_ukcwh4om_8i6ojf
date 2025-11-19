"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# ------------------------------------------------------------------
# Core schemas for the simulation environment
# ------------------------------------------------------------------

class ProcessItem(BaseModel):
    key: str = Field(..., description="Unique key e.g. 'requirements' ")
    title: str
    optional: bool = False

class ProcessStage(BaseModel):
    key: str
    title: str
    description: Optional[str] = None
    items: List[ProcessItem]

class Process(BaseModel):
    key: str = Field(..., description="Unique process key, e.g. 'default'")
    name: str
    stages: List[ProcessStage]

class ActivityLog(BaseModel):
    process_key: str = Field(..., description="Which process this log belongs to")
    stage_key: str
    item_key: str
    type: str = Field(..., description="event type: upload|assignment|download|review|decision|note")
    message: str
    actor: str = Field(..., description="user/admin name or role")
    meta: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

# Example schemas (kept for reference)
class User(BaseModel):
    name: str
    email: str
    address: str
    age: Optional[int] = Field(None, ge=0, le=120)
    is_active: bool = True

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float = Field(..., ge=0)
    category: str
    in_stock: bool = True
