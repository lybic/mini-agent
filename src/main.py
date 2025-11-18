#!/usr/bin/env python3
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    parent_env_path = Path(__file__).parent.parent / '.env'
    if parent_env_path.exists():
        load_dotenv(dotenv_path=parent_env_path)

import asyncio
import json
import uuid
import logging
import re

# Setup logging
logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from lybic import Sandbox, LybicClient
from lybic.dto import GetSandboxResponseDto
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionUserMessageParam as UserMessage
from httpx import HTTPStatusError

from src.dto import *
from src.chat import AsyncChatModelClient
from src.planner import Planner
from src.storage import create_storage, TaskData
from src.prompts import DOUBAO_UI_TARS_SYSTEM_PROMPT_ZH

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "DEBUG"))
app = FastAPI(
    title='Lybic Single Model Agent Server',
)

# Global dictionary to track active tasks with thread-safe lock
active_tasks = {}
active_tasks_lock = asyncio.Lock()

# Initialize storage for task persistence
task_storage = create_storage()

@app.get('/api/health')
async def health():
    """Health check endpoint"""
    return JSONResponse({'status': 'ok'})

async def _create_sandbox(req:CreateSandboxRequest,shape:str='beijing-2c-4g-cpu')->GetSandboxResponseDto:
    async with LybicClient(req_auth_from_dto(req.authentication)) as lybic_client:
        # Create sandbox
        sandbox_service = Sandbox(lybic_client)
        result = await sandbox_service.create(
            CreateSandboxDto(
                name=req.name,
                shape=req.shape or shape,
                maxLifeSeconds=req.maxLifeSeconds,
                projectId=req.projectId
            )
        )
        sandbox_details = await sandbox_service.get(result.id)
    return sandbox_details

@app.post('/api/sandbox/create')
async def create_sandbox(req: CreateSandboxRequest):
    """Create a new sandbox via Lybic SDK"""
    try:
        # Create Lybic client
        sandbox_details = await _create_sandbox(req)
        # Extract sandbox information
        sandbox_id = sandbox_details.sandbox.id
        return JSONResponse({
            'success': True,
            'sandbox_id': sandbox_id,
            'shape': sandbox_details.sandbox.shapeName,
            'os': "WINDOWS",
            'hardware_accelerated_encoding': sandbox_details.sandbox.shape.hardwareAcceleratedEncoding,
            'virtualization': sandbox_details.sandbox.shape.virtualization,
            'architecture': sandbox_details.sandbox.shape.architecture,
            'message': f'Sandbox {sandbox_id} created successfully'
        })
    except HTTPStatusError as he:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=he.response.status_code, detail=str(he))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/api/agent/run')
async def run_agent(req: RunAgentRequest):
    """Stream agent execution with SSE"""
    try:
        if not req.instruction:
            raise HTTPException(status_code=400, detail='instruction is required')

        async def generate():
            sandbox_id = req.sandbox_id
            if sandbox_id is None:
               sandbox_info = await _create_sandbox(CreateSandboxRequest(authentication=req.authentication,shape='beijing-2c-4g-cpu'),shape='beijing-2c-4g-cpu')
               sandbox_id = sandbox_info.sandbox.id
            try:
                # Determine task ID and check for context restoration
                existing_context = None
                if req.continue_context and req.task_id:
                    task_id = req.task_id
                    # Try to restore context
                    task_data = await task_storage.get_task(task_id)
                    if task_data:
                        # Restore sandbox_id from previous task if not provided
                        if not sandbox_id and task_data.sandbox_info:
                            sandbox_id = task_data.sandbox_info.get('sandbox_id')
                        existing_context = task_data.llm_context
                    # Update task with new instruction
                    await task_storage.update_task(task_id, {
                        'status': 'running',
                        'query': req.instruction
                    })
                else:
                    # Generate new task ID for new session
                    task_id = str(uuid.uuid4())
                    # Create task entry
                    new_task = TaskData(
                        task_id=task_id,
                        status='running',
                        query=req.instruction,
                        max_steps=50,
                        sandbox_info={'sandbox_id': sandbox_id},
                        request_data=req.model_dump()
                    )
                    await task_storage.create_task(new_task)
                
                # Setup model and planner using shared function
                model_client, planner=  _setup_model_and_planner(
                    task_id, sandbox_id, req.instruction, 
                    req.continue_context, existing_context,req.user_system_prompt,
                    LybicClient(req_auth_from_dto(req.authentication)),req.ark_apikey
                )
                
                # Show context restored message if applicable
                if existing_context:
                    yield f"data: {json.dumps({'stage': 'System', 'message': '🔄 Context restored, continuing conversation...', 'taskId': task_id, 'timestamp': __import__('datetime').datetime.now().isoformat()}, ensure_ascii=False)}\n\n"
                
                # Register NOTIFY listener if using PostgreSQL
                if hasattr(task_storage, 'register_cancel_listener'):
                    def cancel_callback(cancelled_task_id):
                        if cancelled_task_id == task_id:
                            planner.cancelled = True
                            logger.info(f"Task {task_id} cancelled via NOTIFY")
                    
                    task_storage.register_cancel_listener(task_id, cancel_callback)
                
                # Store planner in active tasks with thread-safe lock
                async with active_tasks_lock:
                    active_tasks[task_id] = planner

                task_cancelled = False
                final_msg:str|None = None
                needs_human_intervention = False
                try:
                    messages =  _execute_planner_with_context_saving(
                        planner, model_client, task_id, sandbox_id
                    )

                    # Yield all collected messages
                    async for msg in messages:
                        yield msg
                        
                        # Check for human intervention needed and extract message
                        try:
                            msg_data = json.loads(msg.replace('data: ', '').strip())
                            if msg_data.get('needs_human'):
                                needs_human_intervention = True
                                final_msg = msg_data.get('message', '')
                                break
                            # Also extract finished message if present
                            if msg_data.get('stage') == 'Planner':
                                final_msg = msg_data.get('message', '')
                        except:
                            pass
                except asyncio.CancelledError:
                    task_cancelled = True
                    logger.info(f"Task {task_id} was cancelled")
                finally:
                    # Unregister NOTIFY listener if using PostgreSQL
                    if hasattr(task_storage, 'unregister_cancel_listener'):
                        task_storage.unregister_cancel_listener(task_id)
                    
                    await _finalize_task(task_id, model_client, task_cancelled, planner,final_msg, needs_human_intervention=needs_human_intervention)
            except Exception as e:
                logger.error(f"Error in generate(): {e}")
                raise
        
        return StreamingResponse(
            generate(),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/api/agent/task/submit')
async def submit_async_task(req: SubmitTaskRequest):
    """Submit an async task and return task_id immediately"""
    try:
        if not req.instruction:
            raise HTTPException(status_code=400, detail='Instruction is required')
        
        # Determine task ID and check for context restoration
        if req.continue_context and req.task_id:
            task_id = req.task_id
            # Check if task exists and get context
            task_data = await task_storage.get_task(task_id)
            if task_data:
                # Restore sandbox_id from previous task if not provided
                sandbox_id = req.sandbox_id
                if not sandbox_id and task_data.sandbox_info:
                    sandbox_id = task_data.sandbox_info.get('sandbox_id')
                # Update task status to running
                await task_storage.update_task(task_id, {
                    'status': 'running',
                    'query': req.instruction
                })
            else:
                # Task not found, create new one
                task_id = str(uuid.uuid4())
                task_data = TaskData(
                    task_id=task_id,
                    status='pending',
                    query=req.instruction,
                    max_steps=req.max_steps,
                    sandbox_info={'sandbox_id': req.sandbox_id} if req.sandbox_id else None,
                    request_data=req.model_dump()
                )
                await task_storage.create_task(task_data)
        else:
            # Generate new task ID
            task_id = str(uuid.uuid4())
            task_data = TaskData(
                task_id=task_id,
                status='pending',
                query=req.instruction,
                max_steps=req.max_steps,
                sandbox_info={'sandbox_id': req.sandbox_id} if req.sandbox_id else None,
                request_data=req.model_dump()
            )
            await task_storage.create_task(task_data)
        
        # Start task execution in background
        asyncio.create_task(
            execute_task_background(task_id, req)
        )
        
        return JSONResponse({
            'success': True,
            'task_id': task_id,
            'message': f'Task {task_id} submitted successfully'
        })
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def execute_task_background(task_id: str, req: SubmitTaskRequest):
    """Execute task in background"""
    sandbox_id = req.sandbox_id
    try:
        # Update status to running
        await task_storage.update_task(task_id, {'status': 'running'})
        
        # Check if we should restore context
        existing_context = None
        if req.continue_context and req.task_id:
            existing_context = await task_storage.get_llm_context(task_id)
        
        # Setup model and planner using shared function
        model_client, planner =  _setup_model_and_planner(
            task_id, sandbox_id, req.instruction,
            req.continue_context, existing_context,req.user_system_prompt,
            LybicClient(req_auth_from_dto(req.authentication)),
            req.ark_apikey
        )
        
        # Register NOTIFY listener if using PostgreSQL
        if hasattr(task_storage, 'register_cancel_listener'):
            def cancel_callback(cancelled_task_id):
                if cancelled_task_id == task_id:
                    planner.cancelled = True
                    logger.info(f"Task {task_id} cancelled via NOTIFY")
            
            task_storage.register_cancel_listener(task_id, cancel_callback)
        
        # Store planner in active tasks
        async with active_tasks_lock:
            active_tasks[task_id] = planner
        
        task_cancelled = False
        final_output = None
        error = None
        needs_human_intervention = False
        
        try:
            async for msg in _execute_planner_with_context_saving(
                 planner, model_client, task_id, sandbox_id
             ):
                msg_or_none=_get_finished_message(msg)
                if isinstance(msg_or_none,str):
                    final_output=msg_or_none
                
                # Check for human intervention needed and extract message
                try:
                    msg_data = json.loads(msg.replace('data: ', '').strip())
                    if msg_data.get('needs_human'):
                        needs_human_intervention = True
                        final_output = msg_data.get('message', '')
                        break
                    # Also extract planner message for finished state
                    if msg_data.get('stage') == 'Planner':
                        final_output = msg_data.get('message', '')
                except:
                    pass
            # task_cancelled, final_output, _ = await _execute_planner_with_context_saving(
            #     planner, model_client, task_id, sandbox_id
            # )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            error = e
            if not planner.cancelled:
                logger.error(f"Error executing task {task_id}: {e}")
        finally:
            # Unregister NOTIFY listener if using PostgreSQL
            if hasattr(task_storage, 'unregister_cancel_listener'):
                task_storage.unregister_cancel_listener(task_id)
            
            await _finalize_task(task_id, model_client, task_cancelled, planner, final_output, error, needs_human_intervention)
    
    except Exception as e:
        logger.error(f"Error in execute_task_background(): {e}")

@app.get('/api/agent/task/status/{task_id}')
async def get_task_status_by_path(task_id: str):
    """Query task status and result"""
    try:
        # Get task from storage
        task_data = await task_storage.get_task(task_id)
        
        if not task_data:
            raise HTTPException(status_code=404, detail='Task not found')
        
        response = {
            'success': True,
            'task_id': task_data.task_id,
            'status': task_data.status,
            'query': task_data.query,
            'max_steps': task_data.max_steps,
            'created_at': task_data.created_at.isoformat() if task_data.created_at else None,
            'updated_at': task_data.updated_at.isoformat() if task_data.updated_at else None
        }
        
        # Add finished_output when task is completed or needs human intervention
        if task_data.status in ('finished', 'human_intervention') and task_data.finished_output:
            response['finished_output'] = task_data.finished_output
        
        # Add error info if task failed
        if task_data.status == 'error' and task_data.final_state:
            response['error_message'] = task_data.final_state
        
        # Add sandbox info if available
        if task_data.sandbox_info:
            response['sandbox_info'] = task_data.sandbox_info
        
        return JSONResponse(response)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/api/agent/task/list')
async def list_tasks(status: Optional[str] = None, limit: Optional[int] = None, offset: int = 0):
    """List all tasks with optional filtering"""
    try:
        # Get tasks from storage
        tasks = await task_storage.list_tasks(status, limit, offset)
        
        task_list = []
        for task in tasks:
            task_info = {
                'task_id': task.task_id,
                'status': task.status,
                'query': task.query,
                'created_at': task.created_at.isoformat() if task.created_at else None,
                'updated_at': task.updated_at.isoformat() if task.updated_at else None
            }
            
            # Add finished_output for completed tasks
            if task.status == 'finished' and task.finished_output:
                task_info['finished_output'] = task.finished_output
            
            task_list.append(task_info)
        
        return JSONResponse({
            'success': True,
            'tasks': task_list,
            'count': len(task_list)
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/agent/info')
async def get_agent_info():
    """Get agent server info"""
    return JSONResponse({
        'version': 'mini-lybic-guiagent-0.1',
        'maxConcurrentTasks': 'unlimited',
        'log_level': os.environ.get("LOG_LEVEL","DEBUG")
    })

@app.get('/api/agent/tasks')
async def list_active_tasks():
    """List all active tasks"""
    try:
        async with active_tasks_lock:
            tasks = [
                {
                    'task_id': task_id,
                    'sandbox_id': planner.sandbox_id,
                    'cancelled': planner.cancelled
                }
                for task_id, planner in active_tasks.items()
            ]
        return JSONResponse({'success': True, 'tasks': tasks, 'count': len(tasks)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/api/agent/cancel')
async def cancel_agent(req: CancelRequest):
    """Cancel agent task execution (stateless)"""
    try:
        if req.task_id:
            # Request cancellation via storage (works across all instances)
            success = await task_storage.request_cancel_task(req.task_id)
            if success:
                # Also try to cancel in-memory if running on this instance
                async with active_tasks_lock:
                    planner = active_tasks.get(req.task_id)
                    if planner:
                        planner.cancelled = True
                        logger.info(f"Task {req.task_id} cancelled in local instance")
                
                # Check if task was already cancelled
                task_data = await task_storage.get_task(req.task_id)
                if task_data and task_data.status == 'cancelled':
                    return JSONResponse({
                        'success': True, 
                        'message': f'Task {req.task_id} successfully cancelled',
                        'already_cancelled': True
                    })
                else:
                    return JSONResponse({
                        'success': True, 
                        'message': f'Cancellation requested for task {req.task_id}',
                        'already_cancelled': False
                    })
            else:
                # Get task details to provide better error message
                task_data = await task_storage.get_task(req.task_id)
                if task_data:
                    raise HTTPException(
                        status_code=400, 
                        detail=f'Task is in "{task_data.status}" state and cannot be cancelled'
                    )
                else:
                    raise HTTPException(status_code=404, detail='Task not found')
        else:
            # Cancel all active tasks
            cancelled_count = await task_storage.request_cancel_all_tasks()
            
            # Also cancel in-memory tasks on this instance
            async with active_tasks_lock:
                for planner in active_tasks.values():
                    planner.cancelled = True
            
            return JSONResponse({'success': True, 'message': f'Cancellation requested for {cancelled_count} task(s)'})
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _setup_model_and_planner(task_id: str, sandbox_id: str, instruction: str,
                             continue_context: bool, existing_context: Optional[dict] = None,
                             user_system_prompt: Optional[str] = None, lybic_client: LybicClient|None = None,
                             llm_api_key: Optional[str] = None
                             ):
    """Setup AI client, model client and planner - shared logic"""
    if not lybic_client:
        lybic_client = LybicClient()

    ai_client = AsyncOpenAI(
        api_key=llm_api_key,#os.environ.get('ARK_API_KEY'),
        base_url='https://ark.cn-beijing.volces.com/api/v3'
    )
    
    model_client = AsyncChatModelClient(
        ai_client=ai_client,
        model_name='doubao-1-5-ui-tars-250428',
        thinking_type='disabled',
        session_id=task_id
    )
    
    # Restore context or setup fresh prompt
    if continue_context and existing_context:
        model_client.restore_context_from_persistence(existing_context)
        model_client.messages.append(UserMessage(role="user", content=instruction))
    else:
        model_client.setup_prompt(DOUBAO_UI_TARS_SYSTEM_PROMPT_ZH, user_system_prompt, instruction)
    
    planner = Planner(
        sandbox_id=sandbox_id,
        model_client=model_client,
        lybic=lybic_client,
        task_storage=task_storage
    )
    planner.task_id = task_id
    
    return model_client, planner


def _get_finished_message(msg):
    # Extract finished output from message
    if 'finished(' in msg:
        match = re.search(r"finished\(content='([^']*)'\)", msg)
        if match:
            return match.group(1)
    return None


async def _execute_planner_with_context_saving(planner: Planner, model_client: AsyncChatModelClient,
                                                task_id: str, sandbox_id: str):
    """Execute planner and save context periodically - shared logic
    
    Returns: yielded_messages
    """
    step_count = 0
    try:
        async for msg in planner.run_task(lang="zh"):
            yield msg
            if planner.cancelled:
                break
            
            # messages.append(msg)
            step_count += 1
            
            # Save context periodically (every 5 steps)
            if step_count % 5 == 0 and not planner.cancelled:
                try:
                    context = model_client.get_context_for_persistence()
                    await task_storage.save_llm_context(task_id, context)
                    await task_storage.update_task(task_id, {
                        'sandbox_info': {'sandbox_id': sandbox_id}
                    })
                except Exception as e:
                    logger.error(f"Failed to save context during execution: {e}")

    except asyncio.CancelledError:
        logger.info(f"Task {task_id} was cancelled")
        raise
    except Exception as e:
        logger.error(f"Error during planner execution for task {task_id}: {e}")
        raise

async def _finalize_task(task_id: str, model_client: AsyncChatModelClient, 
                        task_cancelled: bool, planner: Planner, 
                        final_output: Optional[str] = None, error: Optional[Exception] = None,
                        needs_human_intervention: bool = False):
    """Finalize task - save context and update status - shared logic"""
    try:
        context = model_client.get_context_for_persistence()
        await task_storage.save_llm_context(task_id, context)
        
        if task_cancelled or planner.cancelled:
            await task_storage.update_task(task_id, {'status': 'cancelled'})
        elif needs_human_intervention:
            updates = {'status': 'human_intervention'}
            if final_output:
                updates['finished_output'] = final_output
            await task_storage.update_task(task_id, updates)
        elif error:
            await task_storage.update_task(task_id, {
                'status': 'error',
                'final_state': str(error)
            })
        else:
            updates = {'status': 'finished'}
            if final_output:
                updates['finished_output'] = final_output
            await task_storage.update_task(task_id, updates)
    except Exception as e:
        logger.error(f"Failed to finalize task: {e}")
    finally:
        async with active_tasks_lock:
            active_tasks.pop(task_id, None)

def main():
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5000,log_level=os.environ.get("LOG_LEVEL", "DEBUG").lower())

if __name__ == '__main__':
    main()
