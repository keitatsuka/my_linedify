import json
import os
from logging import getLogger, NullHandler
from traceback import format_exc
from typing import Dict, List, Tuple, Union

from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    Configuration,
    AsyncApiClient,
    AsyncMessagingApi,
    AsyncMessagingApiBlob,
    Message,
    TextMessage,
    ReplyMessageRequest
)
from linebot.v3.webhooks import (
    Event,
    MessageEvent,
    TextMessageContent,
    StickerMessageContent,
    LocationMessageContent,
    ImageMessageContent
)

from .dify import DifyAgent, DifyType
from .session import ConversationSession, ConversationSessionStore

# ログ設定
logger = getLogger(__name__)
logger.addHandler(NullHandler())

class LineDifyIntegrator:
    def __init__(self, *,
                line_channel_access_token: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN"),
                line_channel_secret: str = os.getenv("LINE_CHANNEL_SECRET"),
                dify_api_key: str = os.getenv("DIFY_API_KEY"),
                dify_base_url: str = os.getenv("DIFY_BASE_URL"),
                dify_user: str = os.getenv("DIFY_USER"),
                dify_type: DifyType = DifyType.Agent,
                session_db_url: str = "sqlite:///sessions.db",
                session_timeout: float = 3600.0,
                verbose: bool = False) -> None:

        self.verbose = verbose

        # LINE設定
        line_api_configuration = Configuration(
            access_token=line_channel_access_token
        )
        self.line_api_client = AsyncApiClient(line_api_configuration)
        self.line_api = AsyncMessagingApi(self.line_api_client)
        self.line_api_blob = AsyncMessagingApiBlob(self.line_api_client)
        self.webhook_parser = WebhookParser(line_channel_secret)

        # イベントやメッセージの処理設定
        self._validate_event = self.validate_event_default
        self._event_handlers = {
            "message": self.handle_message_event
        }
        self._default_event_handler = self.event_handler_default
        self._message_parsers = {
            "text": self.parse_text_message,
            "image": self.parse_image_message,
            "sticker": self.parse_sticker_message,
            "location": self.parse_location_message
        }

        # セッション管理
        self.conversation_session_store = ConversationSessionStore(
            db_url=session_db_url,
            timeout=session_timeout
        )

        # Dify設定
        self.dify_agent = DifyAgent(
            api_key=dify_api_key,
            base_url=dify_base_url,
            user=dify_user,
            type=dify_type,
            verbose=self.verbose
        )

        self._make_inputs = self.make_inputs_default
        self._to_reply_message = self.to_reply_message_default
        self._to_error_message = self.to_error_message_default

    # エラーメッセージを返す処理の改善
    async def to_error_message_default(self, event: Event, ex: Exception, session: ConversationSession = None) -> List[Message]:
        error_message = f"エラーが発生しました: {ex}"
        logger.error(error_message)
        return [TextMessage(text=error_message)]

    # その他のコードは修正なし

    async def handle_message_event(self, event: MessageEvent):
        conversation_session = None
        try:
            if self.verbose:
                logger.info(f"Request from LINE: {json.dumps(event.as_json_dict(), ensure_ascii=False)}")

            parse_message = self._message_parsers.get(event.message.type)
            if not parse_message:
                raise Exception(f"Unhandled message type: {event.message.type}")

            request_text, image_bytes = await parse_message(event.message)
            conversation_session = await self.conversation_session_store.get_session(event.source.user_id)
            inputs = await self._make_inputs(conversation_session)

            conversation_id, text, data = await self.dify_agent.invoke(
                conversation_session.conversation_id,
                text=request_text,
                image=image_bytes,
                inputs=inputs
            )

            conversation_session.conversation_id = conversation_id
            await self.conversation_session_store.set_session(conversation_session)

            response_messages = await self._to_reply_message(text, data, conversation_session)

            if self.verbose:
                logger.info(f"Response to LINE: {', '.join([json.dumps(m.as_json_dict(), ensure_ascii=False) for m in response_messages])}")

            return response_messages

        except Exception as ex:
            logger.error(f"Error at handle_message_event: {ex}\n{format_exc()}")
            try:
                return await self._to_error_message(event, ex, conversation_session)
            except Exception as eex:
                logger.error(f"Error at replying error message for message event: {eex}\n{format_exc()}")
