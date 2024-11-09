# run.py

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks
from linedify import LineDify
from linedify.dify import DifyType
from linebot.v3.messaging import (
    TextMessage,
    ReplyMessageRequest,
    QuickReply,
    QuickReplyItem,
    MessageAction
)
from linebot.v3.webhooks import (
    PostbackEvent,
    MessageEvent,
    TextMessageContent
)
from linebot.v3.webhooks.models.events import Event
from linedify.session import ConversationSession
import os

# 環境変数から値を取得
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

# Dify エージェント情報を辞書にまとめる
DIFY_AGENTS = {
    "default": {
        "api_key": os.getenv('DIFY_API_KEY_DEFAULT'),
        "base_url": os.getenv('DIFY_BASE_URL_DEFAULT'),
        "user": os.getenv('DIFY_USER_DEFAULT'),
    },
    "タイプ1": {
        "api_key": os.getenv('DIFY_API_KEY_TYPE1'),
        "base_url": os.getenv('DIFY_BASE_URL_TYPE1'),
        "user": os.getenv('DIFY_USER_TYPE1'),
    },
    "タイプ2": {
        "api_key": os.getenv('DIFY_API_KEY_TYPE2'),
        "base_url": os.getenv('DIFY_BASE_URL_TYPE2'),
        "user": os.getenv('DIFY_USER_TYPE2'),
    },
    # 他のタイプも同様に設定
}

# 利用可能なタイプのリスト
AVAILABLE_TYPES = list(DIFY_AGENTS.keys())
AVAILABLE_TYPES.remove("default")  # デフォルトを除外

# LineDify のインスタンスを作成
line_dify = LineDify(
    line_channel_access_token=LINE_CHANNEL_ACCESS_TOKEN,
    line_channel_secret=LINE_CHANNEL_SECRET,
    dify_type=DifyType.Chatbot,
    verbose=True
)

# FastAPI のアプリケーションを作成
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await line_dify.shutdown()

app = FastAPI(lifespan=lifespan)

# @line_dify.validate_event を使用して、イベントの処理前にユーザーのエージェント情報を取得
@line_dify.validate_event
async def validate_event(event: Event):
    # 何も返さない場合、次の処理に進みます
    return None

# メッセージイベントのハンドラー
@line_dify.event("message")
async def handle_message_event(event: MessageEvent):
    user_id = event.source.user_id
    message = event.message

    # ユーザーのセッションを取得
    conversation_session = await line_dify.conversation_session_store.get_session(user_id)

    if isinstance(message, TextMessageContent):
        text = message.text.strip()

        # ユーザーが「16タイプAIを変えたい！」と送信した場合
        if text == "16タイプAI変更":
            conversation_session.state = "selecting_type"

            # 利用可能なタイプをQuickReplyで提示
            quick_reply_items = [
                QuickReplyItem(
                    action=MessageAction(label=type_name, text=type_name)
                ) for type_name in AVAILABLE_TYPES[:13]  # QuickReplyは最大13個
            ]
            reply_message = TextMessage(
                text="どのタイプにしますか？",
                quick_reply=QuickReply(items=quick_reply_items)
            )
            await line_dify.line_api.reply_message(
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[reply_message]
                )
            )

            # セッションを更新
            await line_dify.conversation_session_store.set_session(conversation_session)
            return []

        # ユーザーがタイプ選択中の場合
        elif conversation_session.state == "selecting_type":
            selected_type = text
            if selected_type in AVAILABLE_TYPES:
                conversation_session.agent_key = selected_type
                conversation_session.state = None  # 状態をリセット
                reply_text = f"タイプ '{selected_type}' に切り替えました。"
            else:
                reply_text = "指定されたタイプは存在しません。もう一度選択してください。"

            reply_message = TextMessage(text=reply_text)
            await line_dify.line_api.reply_message(
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[reply_message]
                )
            )

            # セッションを更新
            await line_dify.conversation_session_store.set_session(conversation_session)
            return []

    # 通常のメッセージ処理を行う
    return await line_dify.handle_message_event(event)

# make_inputs 関数を追加（必要に応じて）
@line_dify.make_inputs
async def make_inputs(session: ConversationSession):
    # 必要に応じて入力をカスタマイズ
    return {}

# to_reply_message 関数を追加（必要に応じて）
@line_dify.to_reply_message
async def to_reply_message(text: str, data: dict, session: ConversationSession):
    return [TextMessage(text=text)]

# エラーメッセージのカスタマイズ
@line_dify.to_error_message
async def to_error_message(event: Event, ex: Exception, session: ConversationSession = None):
    text = "申し訳ありませんが、エラーが発生しました。しばらくしてからもう一度お試しください。"
    return [TextMessage(text=text)]

# Webhook エンドポイント
@app.post("/linebot")
async def handle_request(request: Request, background_tasks: BackgroundTasks):
    body = (await request.body()).decode("utf-8")
    signature = request.headers.get("X-Line-Signature", "")

    background_tasks.add_task(
        line_dify.process_request,
        request_body=body,
        signature=signature
    )

    return "ok"
