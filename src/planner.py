import asyncio
import json
import uuid
from typing import Tuple, AsyncGenerator, Any, Optional

from lybic import ComputerUse, Sandbox, LybicClient
from lybic.dto import ModelType, ExecuteSandboxActionDto

from src.chat import AsyncChatModelClient
from src.store import get_opensearch_store


def parse_summary_and_action_from_model_response_v2(text: str) -> Tuple[Optional[str], Optional[str]]:
    lines = text.strip().split('\n')

    thought_lines = []
    action = ''
    current_section = None

    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            continue
        if stripped_line.startswith('Thought:'):
            current_section = 'thought'
            content = stripped_line[len('Thought:'):].strip()
            if content:
                thought_lines.append(content)
        elif stripped_line.startswith('Action:'):
            current_section = 'action'
            action = stripped_line[len('Action:'):].strip()
        else:
            if current_section == 'thought' and stripped_line:
                thought_lines.append(stripped_line)

    thought = '\n'.join(thought_lines)
    return thought, action

class Planner(object):
    def __init__(self, sandbox_id: str, model_client: AsyncChatModelClient, lybic: LybicClient, task_storage=None):
        self.lybic_computer_use = ComputerUse(lybic)
        self.max_actions = 50
        self.task_id: str = ''
        self.sandbox_id: str = sandbox_id
        self.lybic_sandbox = Sandbox(lybic)
        self.model_client: AsyncChatModelClient = model_client
        self.cancelled = False
        self.task_storage = task_storage
        self._cancel_check_interval = 3  # Check cancellation every N actions

    async def _take_screenshot(self) -> Tuple[int, int, str]:
        """
        Capture screen screenshot

        Returns:
            Tuple[int, int, str]: screen width, height and screenshot url
        """
        for i in range(3):
            try:
                result = await self.lybic_sandbox.preview(self.sandbox_id)
                # image_base64 = await self.lybic_sandbox.get_screenshot_base64(self.sandbox_id)
                print("Screenshot captured - size=", result.cursorPosition)
                return result.cursorPosition.screenWidth, result.cursorPosition.screenHeight, result.screenShot
            except Exception as e:
                print(f"Attempt {i + 1} to take screenshot failed: {e}")
                if i < 2:
                    await asyncio.sleep(1)  # wait for 1 second before retrying
                else:
                    raise
        return -1, -1, ""

    def _format_sse(self, data: dict | None = None, **kwargs) -> str:
        """
        Format data to SSE compliant string

        Args:
            data: Initial data dictionary
            **kwargs: Additional fields to merge

        Returns:
            str: Formatted SSE string
        """
        if not data:
            data = {}
        data.update(kwargs)
        data['taskId'] = self.task_id
        data['timestamp'] = data.get('timestamp') or __import__('datetime').datetime.now().isoformat()
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def _check_cancellation(self) -> bool:
        """
        Check if task cancellation has been requested.
        
        This checks both the in-memory flag and queries storage (for stateless cancellation).
        
        Returns:
            bool: True if cancellation was requested
        """
        if self.cancelled:
            return True
        
        # Check storage if available (polling fallback)
        if self.task_storage and self.task_id:
            try:
                cancel_requested = await self.task_storage.check_cancel_requested(self.task_id)
                if cancel_requested:
                    self.cancelled = True
                    return True
            except Exception as e:
                print(f"Error checking cancellation status: {e}")
        
        return False

    async def run_task(self, lang: str = "zh") -> AsyncGenerator[str, Any]:
        start_action = "开始" if lang == "zh" else "Start"
        yield self._format_sse({"stage": "System", "message": start_action})
        if self.model_client.memories:
            memories_text = "\n".join([f"- {m}" for m in self.model_client.memories])
            yield self._format_sse({"stage": "System", "message": f"📝 Loaded memories:\n{memories_text}"})

        try:
            for action_idx in range(self.max_actions):
                # Check if task is cancelled (checks both memory and storage)
                if await self._check_cancellation():
                    cancel_msg = "任务已取消" if lang == "zh" else "Task cancelled"
                    yield self._format_sse({"stage": "System", "message": f"🚫 {cancel_msg}", "cancelled": True})
                    break

                # capture screenshot (no need to send to frontend as they don't display it)
                screen_width, screen_height, screenshot_image = await self._take_screenshot()
                # image_base64 = f"data:image/webp;base64,{screenshot_image}"

                # Check if task is cancelled periodically
                if action_idx % self._cancel_check_interval == 0:
                    if await self._check_cancellation():
                        cancel_msg = "任务已取消" if lang == "zh" else "Task cancelled"
                        yield self._format_sse({"stage": "System", "message": f"🚫 {cancel_msg}", "cancelled": True})
                        break

                # get next action
                response = await self.model_client.process_screenshot_and_update_history_messages(screenshot_image)
                summary, action = parse_summary_and_action_from_model_response_v2(
                    response)  # self.model_action_adaptor.parse_summary_and_action_from_model_response(response)

                if not action:
                    print("No action returned, skipping")
                    continue
                if "finished(" in action:
                    yield self._format_sse({"stage": "Grounding", "message": f"✅ {summary}\n\nAction: {action}"})
                    yield self._format_sse({"stage": "System", "message": "Task completed successfully!", "done": True})
                    break
                if "call_user(" in action:
                    yield self._format_sse({"stage": "System", "message": f"👤 Calling user for help\n\n{summary}", "needs_human": True})
                    break
                if "output(" in action:
                    self.model_client.add_output_messages()
                    yield self._format_sse({"stage": "System", "message": f"💾 Output saved: {summary}"})
                    continue
                if "save_memory(" in action:
                    store = get_opensearch_store()
                    if store:
                        # Use session-specific namespace for memory isolation
                        store.put((self.model_client.session_id,), key=str(uuid.uuid4()), value={"text": summary},
                                  index=["text"])
                    yield self._format_sse({"stage": "System", "message": f"🧠 Memory saved: {summary}"})
                    continue
                if "failed(" in action:
                    yield self._format_sse(
                        {"stage": "Error", "message": f"❌ Task failed: {summary}\n\nAction: {action}"})
                    break

                # Check if task is cancelled
                if await self._check_cancellation():
                    cancel_msg = "任务已取消" if lang == "zh" else "Task cancelled"
                    yield self._format_sse({"stage": "System", "message": f"🚫 {cancel_msg}", "cancelled": True})
                    break

                # Parse and execute action
                parse_result = await self.lybic_computer_use.parse_llm_output(
                    model_type=ModelType.UITARS,
                    llm_output=response
                )

                # Check if task is cancelled
                if self.cancelled:
                    cancel_msg = "任务已取消" if lang == "zh" else "Task cancelled"
                    yield self._format_sse({"stage": "System", "message": f"🚫 {cancel_msg}", "cancelled": True})
                    break

                # Send thinking/summary as a separate message
                if summary:
                    yield self._format_sse({"stage": "manager_planner", "message": f"💭 Thought: {summary}"})

                # Execute action(s)
                if len(parse_result.actions) == 1:
                    yield self._format_sse({"stage": "Grounding", "message": f"🎯 Executing action: {action}"})
                    await self.lybic_sandbox.execute_sandbox_action(
                        self.sandbox_id,
                        ExecuteSandboxActionDto(
                            action=parse_result.actions[0],
                            includeScreenShot=False,
                            includeCursorPosition=False
                        )
                    )
                else:
                    for idx, parsed_action in enumerate(parse_result.actions, 1):
                        yield self._format_sse({"stage": "Grounding",
                                                "message": f"🎯 Executing action {idx}/{len(parse_result.actions)}: {parsed_action}"})
                        await self.lybic_sandbox.execute_sandbox_action(
                            self.sandbox_id,
                            ExecuteSandboxActionDto(
                                action=parsed_action,
                                includeScreenShot=False,
                                includeCursorPosition=False
                            )
                        )
                # sleep several seconds
                await asyncio.sleep(1.5)
        except Exception as e:
            print("Task execution failed, error=%s", e)
            error_msg = "任务执行遇到问题，请稍后重试" if lang == "zh" else "Task execution encountered a problem, please try again later."
            yield self._format_sse({"stage": "Error", "message": f"❌ {error_msg}", "error": str(e)})
        except asyncio.CancelledError as e:
            print("Task execution failed, error=%s", e)
            error_msg = "请求MCP服务超时，请稍后重试" if lang == "zh" else "Request to MCP server timed out, please try again later."
            yield self._format_sse({"stage": "Error", "message": f"❌ {error_msg}", "error": str(e)})
        finally:
            print("Task completed, task_id=%s", self.task_id)
