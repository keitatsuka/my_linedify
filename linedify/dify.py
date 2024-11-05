from enum import Enum
import json
from logging import getLogger, NullHandler
from typing import Dict, Tuple
import aiohttp

logger = getLogger(__name__)
logger.addHandler(NullHandler())

class DifyType(Enum):
    Agent = "Agent"
    Chatbot = "Chatbot"
    TextGenerator = "TextGenerator"
    Workflow = "Workflow"

class DifyAgent:
    def __init__(self, *,
                api_key: str,
                base_url: str,
                user: str,
                type: DifyType = DifyType.Agent,
                verbose: bool = False) -> None:
        self.verbose = verbose
        self.api_key = api_key
        self.base_url = base_url
        self.user = user
        self.type = type
        self.response_processors = {
            DifyType.Agent: self.process_agent_response,
            DifyType.Chatbot: self.process_chatbot_response,
            DifyType.TextGenerator: self.process_textgenerator_response,
            DifyType.Workflow: self.process_workflow_response
        }
        self.conversation_ids = {}

    async def make_payloads(self, text: str, image_bytes: bytes = None, inputs: dict = None) -> Dict:
        payloads = {
            "inputs": inputs or {},
            "query": text or "",
            "response_mode": "streaming" if self.type == DifyType.Agent else "blocking",
            "user": self.user,
            "auto_generate_name": False,
        }

        if image_bytes:
            uploaded_image_id = await self.upload_image(image_bytes)
            if uploaded_image_id:
                payloads["files"] = [{
                    "type": "image",
                    "transfer_method": "local_file",
                    "upload_file_id": uploaded_image_id
                }]
                if not payloads["query"]:
                    payloads["query"] = "."  # queryが空の場合、ダミーのテキストを設定

        return payloads

    async def upload_image(self, image_bytes: bytes) -> str:
        form_data = aiohttp.FormData()
        form_data.add_field(
            "file",
            image_bytes,
            filename="image.png",
            content_type="image/png"
        )
        form_data.add_field('user', self.user)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.base_url + "/files/upload",
                headers={"Authorization": f"Bearer {self.api_key}"},
                data=form_data
            ) as response:
                response_json = await response.json()
                if self.verbose:
                    logger.info(f"File upload response: {json.dumps(response_json, ensure_ascii=False)}")
                response.raise_for_status()
                return response_json["id"]

    async def process_agent_response(self, response: aiohttp.ClientResponse) -> Tuple[str, str, Dict]:
        conversation_id = ""
        response_text = ""
        response_data = {}

        async for line in response.content:
            decoded_line = line.decode("utf-8").strip()
            if not decoded_line.startswith("data:"):
                continue
            json_str = decoded_line[5:].strip()
            if json_str == "[DONE]":
                break
            chunk = json.loads(json_str)

            if self.verbose:
                logger.debug(f"Chunk from Dify: {json.dumps(chunk, ensure_ascii=False)}")

            event_type = chunk.get("event")

            if event_type == "message":
                # メッセージのテキストを蓄積
                response_text += chunk.get("answer", "")
                # conversation_idを取得
                conversation_id = chunk.get("conversation_id", conversation_id)

            elif event_type == "message_end":
                # 必要に応じてmessage_endイベントを処理
                if chunk.get("metadata"):
                    response_data["metadata"] = chunk.get("metadata")

            elif event_type == "error":
                # エラーイベントを処理
                error_message = chunk.get("message", "Unknown error")
                raise Exception(f"Dify API Error: {error_message}")

            # 他のイベントタイプも必要に応じて処理
            # 例: "message_replace", "tts_message", "tts_message_end"など

        return conversation_id, response_text, response_data

    async def process_chatbot_response(self, response: aiohttp.ClientResponse) -> Tuple[str, str, Dict]:
        response_json = await response.json()

        if self.verbose:
            logger.info(f"Response from Dify: {json.dumps(response_json, ensure_ascii=False)}")

        conversation_id = response_json.get("conversation_id", "")
        response_text = response_json.get("answer", "")
        response_data = {}
        if response_json.get("metadata"):
            response_data["metadata"] = response_json.get("metadata")
        return conversation_id, response_text, response_data

    async def process_textgenerator_response(self, response: aiohttp.ClientResponse) -> Tuple[str, str, Dict]:
        if self.verbose:
            logger.info(f"Response from Dify: {json.dumps(await response.json(), ensure_ascii=False)}")

        raise Exception("TextGenerator is not supported for now.")

    async def process_workflow_response(self, response: aiohttp.ClientResponse) -> Tuple[str, str, Dict]:
        if self.verbose:
            logger.info(f"Response from Dify: {json.dumps(await response.json(), ensure_ascii=False)}")

        raise Exception("Workflow is not supported for now.")

    async def invoke(self, conversation_id: str, text: str = None, image: bytes = None, inputs: dict = None, start_as_new: bool = False) -> Tuple[str, str, Dict]:
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        payloads = await self.make_payloads(text, image, inputs)

        if conversation_id and not start_as_new:
            payloads["conversation_id"] = conversation_id

        async with aiohttp.ClientSession() as session:
            if self.verbose:
                logger.info(f"Request to Dify: {json.dumps(payloads, ensure_ascii=False)}")

            async with session.post(
                self.base_url + "/chat-messages",
                headers=headers,
                json=payloads
            ) as response:

                if response.status != 200:
                    error_response = await response.json()
                    logger.error(f"Error response from Dify: {json.dumps(error_response, ensure_ascii=False)}")
                    response.raise_for_status()

                response_processor = self.response_processors[self.type]
                conversation_id, response_text, response_data = await response_processor(response)

                return conversation_id, response_text, response_data
