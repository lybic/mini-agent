import uuid
from typing import List, Dict, Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionAssistantMessageParam as AssistantMessage
from openai.types.chat import ChatCompletionContentPartImageParam as ContentPartImage
from openai.types.chat import ChatCompletionMessageParam as Message
from openai.types.chat import ChatCompletionSystemMessageParam as SystemMessage
from openai.types.chat import ChatCompletionUserMessageParam as UserMessage
from openai.types.chat.chat_completion_content_part_image_param import ImageURL

from src.store import get_opensearch_store


class AsyncChatModelClient(object):
    """
    Manage chat session with AI models which does not support Function Calls

    Handles message history, image content processing and API communication with large language models.
    """

    def __init__(self, ai_client: AsyncOpenAI, model_name: str, thinking_type: str = "", session_id: str = None):
        self.messages: List[Message] = []
        self.output_messages: List[Message] = []
        self.prompt_count: int = 0
        self.memories: List[str] = []
        self.ai_client = ai_client
        self.model_name = model_name
        self.max_images = 5
        self.max_messages = 20
        self.model_kwargs = {}
        self.model_kwargs['thinking'] = {'type': thinking_type}
        self.session_id = session_id or str(uuid.uuid4())

    def setup_prompt(self, system_prompt: str, user_system_prompt: str, user_prompt: str):
        self.messages.append(SystemMessage(role="system", content=system_prompt))
        if user_system_prompt:
            self.messages.append(SystemMessage(role="system", content=user_system_prompt))
        memories = []
        store = get_opensearch_store()
        if store:
            # Use session-specific namespace for memory isolation
            memories = store.search((self.session_id,), query=user_prompt, limit=3)
        if memories:
            print("memories=%s", memories)
            self.memories = [memory.value['text'] for memory in memories]
            memories_msg = "\n".join(self.memories)
            self.messages.append(SystemMessage(role="system", content=f"Memories:\n{memories_msg}"))
            # self.messages.append(UserMessage(role="user", content=f"Memories:\n{memories_msg}"))

        self.messages.append(UserMessage(role="user", content=user_prompt))
        self.prompt_count = len(self.messages)

    async def process_screenshot_and_update_history_messages(self, screenshot_image_url: str) -> str:
        snap_content = ContentPartImage(type="image_url", image_url=ImageURL(url=screenshot_image_url))
        screenshot_message = UserMessage(role="user", content=[snap_content])
        self.messages.append(screenshot_message)
        self._remove_overflow_image_messages()
        completion = await self.ai_client.chat.completions.create(messages=self.messages,
                                                                  model=self.model_name,
                                                                  extra_body=self.model_kwargs
                                                                  )
        print("completion=%s", completion)
        content = completion.choices[0].message.content
        self.messages.append(AssistantMessage(role="assistant", content=content))
        return content.replace("```", "")

    def _remove_overflow_image_messages(self):
        max_images = self.max_images
        max_messages = self.max_messages

        keep_indices = set()
        img_count = 0
        msg_count = 0

        preserved_messages = self.messages[:self.prompt_count]
        other_messages = self.messages[self.prompt_count:]

        for idx in reversed(range(len(other_messages))):
            msg = other_messages[idx]
            cs = msg.get("content")

            image_contents = []
            non_image_contents = []

            if isinstance(cs, list):
                for item in cs:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        image_contents.append(item)
                    else:
                        non_image_contents.append(item)
            if image_contents and img_count < max_images:
                # 注意，如果存在多张，会超出，当前仅有一张, 无需过滤适配
                img_count += len(image_contents)
                keep_indices.add(idx)
            elif not image_contents and msg_count < max_messages:
                if non_image_contents:
                    msg_count += len(non_image_contents)
                else:
                    msg_count += 1
                keep_indices.add(idx)

            if img_count >= max_images and msg_count >= max_messages:
                break

        messages = [msg for i, msg in enumerate(other_messages) if i in keep_indices]
        self.messages = preserved_messages + self.output_messages + messages

    def add_output_messages(self):
        """
        Add the latest assistant message to the output messages list.
        """
        self.output_messages = self.messages[-1:]

    def get_context_for_persistence(self) -> List[Dict[str, Any]]:
        """
        Extract LLM conversation context without image content for persistence.

        Returns:
            List of message dictionaries without image URLs
        """
        context = []
        for msg in self.messages:
            msg_dict = dict(msg)
            content = msg_dict.get("content")

            # Remove image content from messages
            if isinstance(content, list):
                filtered_content = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") != "image_url":
                        filtered_content.append(item)
                    elif not isinstance(item, dict):
                        filtered_content.append(item)

                if filtered_content:
                    msg_dict["content"] = filtered_content[0] if len(filtered_content) == 1 else filtered_content
                else:
                    continue  # Skip messages with only images

            context.append(msg_dict)

        return context

    def restore_context_from_persistence(self, context: List[Dict[str, Any]]):
        """
        Restore LLM conversation context from persisted data.

        Args:
            context: List of message dictionaries to restore
        """
        self.messages = []
        for msg in context:
            role = msg.get("role")
            content = msg.get("content")

            # Reconstruct the appropriate message type based on role
            if role == "system":
                self.messages.append(SystemMessage(role="system", content=content))
            elif role == "user":
                self.messages.append(UserMessage(role="user", content=content))
            elif role == "assistant":
                self.messages.append(AssistantMessage(role="assistant", content=content))
            else:
                # Fallback: treat as dict
                self.messages.append(msg)

        # Recalculate prompt_count
        self.prompt_count = len([m for m in self.messages if m.get("role") == "system" or
                                 (m.get("role") == "user" and self.messages.index(m) < 3)])
