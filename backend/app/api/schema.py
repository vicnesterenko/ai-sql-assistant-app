from fastapi import APIRouter
from app.models.types import SchemaResponse
from app.services.schema_service import get_schema_response

router = APIRouter(prefix='/api/schema', tags=['schema'])


@router.get('', response_model=SchemaResponse)
async def schema_endpoint() -> SchemaResponse:
    return get_schema_response()
