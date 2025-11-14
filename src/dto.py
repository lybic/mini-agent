import os
from typing import Optional

from lybic import LybicAuth
from lybic.dto import CreateSandboxDto
from pydantic import BaseModel

class LybicAuthentication(BaseModel):
    api_key: str
    org_id: str
    api_endpoint: Optional[str] = None

def req_auth_from_dto(auth: Optional[LybicAuthentication]) -> LybicAuth:
    if auth:
        if auth.api_endpoint is None:
            endpoint = os.getenv("LYBIC_API_ENDPOINT", "https://api.lybic.cn")
        else:
            endpoint = auth.api_endpoint
        return LybicAuth(auth.org_id, auth.api_key, endpoint)
    return LybicAuth()
# class CreateSandboxDto(BaseModel):
#     """
#     Create sandbox request.
#     """
#     name: str = Field("sandbox", description="The name of the sandbox.")
#     maxLifeSeconds: int = Field(3600,
#                                 description="The maximum life time of the sandbox in seconds. Default is 1 hour, max is 1 day.",
#                                 ge=1, le=86400)
#     projectId: Optional[str] = Field(None, description="The project id to use for the sandbox. Use default if not provided.")
#     shape: str = Field(..., description="Specs and datacenter of the sandbox.") # 'beijing-2c-4g-cpu'
class CreateSandboxRequest(CreateSandboxDto):
    authentication: Optional[LybicAuthentication] = None

class CancelRequest(BaseModel):
    task_id: Optional[str] = None
    authentication: Optional[LybicAuthentication] = None


class SubmitTaskRequest(BaseModel):
    instruction: str
    user_system_prompt: Optional[str] = None
    sandbox_id: Optional[str] = None
    max_steps: int = 50
    continue_context: bool = False
    task_id: Optional[str] = None
    authentication: Optional[LybicAuthentication] = None
    ark_apikey: Optional[str] = None


class RunAgentRequest(BaseModel):
    instruction: str
    user_system_prompt: Optional[str] = None
    sandbox_id: Optional[str] = None
    continue_context: bool = False
    task_id: Optional[str] = None
    authentication: Optional[LybicAuthentication] = None
    ark_apikey: Optional[str] = None
