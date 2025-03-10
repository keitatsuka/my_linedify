from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks
from linedify import LineDify
from linedify.dify import DifyAgent, DifyType  # DifyAgentをインポート
from linebot.v3.messaging import (
    TextMessage,
    ReplyMessageRequest,
    QuickReply,
    QuickReplyItem,
    MessageAction
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    Event
)
from linedify.session import ConversationSession
import os


# 環境変数から値を取得
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

# Dify エージェント情報を辞書にまとめる（sender画像も含む）
DIFY_AGENTS = {
    "Emily": {
        "api_key": os.getenv('DIFY_API_KEY_EMILY'),
        "base_url": os.getenv('DIFY_BASE_URL_EMILY'),
        "user": os.getenv('DIFY_USER_EMILY'),
        "iconUrl": os.getenv('DIFY_ICON_URL_EMILY'),
    },
    "フィナ": {
        "api_key": os.getenv('DIFY_API_KEY_FINA'),
        "base_url": os.getenv('DIFY_BASE_URL_FINA'),
        "user": os.getenv('DIFY_USER_FINA'),
        "iconUrl": os.getenv('DIFY_ICON_URL_FINA'),
    },
    # 他のタイプも同様に設定
}

# 利用可能なタイプのリスト
AVAILABLE_TYPES = list(DIFY_AGENTS.keys())

# LineDify のインスタンスを作成
line_dify = LineDify(
    line_channel_access_token=LINE_CHANNEL_ACCESS_TOKEN,
    line_channel_secret=LINE_CHANNEL_SECRET,
    dify_agents=DIFY_AGENTS,  # ここを追加
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

    # セッション内の agent_key が None, 空文字, または "default" の場合は "Emily" に設定
    if conversation_session.agent_key in (None, "", "default"):
        conversation_session.agent_key = "Emily"
        await line_dify.conversation_session_store.set_session(conversation_session)

    if isinstance(message, TextMessageContent):
        text = message.text.strip()

        # デバッグログ
        print("DEBUG: 受信メッセージ:", text)
        print("DEBUG: 現在のエージェント:", conversation_session.agent_key)

        # 条件1: 「フィナ」が含まれており、「バイバイ」が含まれていない場合、かつ現在のエージェントが "Emily" の場合
        if "フィナ" in text and "バイバイ" not in text:
            if conversation_session.agent_key == "Emily":
                conversation_session.agent_key = "フィナ"
                conversation_session.conversation_id = None  # 新規会話開始
                reply_msg = TextMessage(
                    text="エージェントをフィナに切り替えました。",
                    sender={"name": "フィナ", "iconUrl": DIFY_AGENTS["フィナ"]["iconUrl"]}
                )
                await line_dify.line_api.reply_message(
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[reply_msg]
                    )
                )
                await line_dify.conversation_session_store.set_session(conversation_session)
                print("DEBUG: エージェント切替実行：Emily -> フィナ")
                return []

        # 条件2: 「フィナ」と「バイバイ」の両方が含まれている場合、かつ現在のエージェントが "フィナ" の場合
        elif "フィナ" in text and "バイバイ" in text:
            if conversation_session.agent_key == "フィナ":
                conversation_session.agent_key = "Emily"
                conversation_session.conversation_id = None  # 新規会話開始
                reply_msg = TextMessage(
                    text="エージェントをEmilyに切り替えました。",
                    sender={"name": "Emily", "iconUrl": DIFY_AGENTS["Emily"]["iconUrl"]}
                )
                await line_dify.line_api.reply_message(
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[reply_msg]
                    )
                )
                await line_dify.conversation_session_store.set_session(conversation_session)
                print("DEBUG: エージェント切替実行：フィナ -> Emily")
                return []

    # 通常のメッセージ処理を行う
    # ユーザーのエージェントキーに基づいてDifyエージェントを取得
    agent_key = conversation_session.agent_key or "Emily"
    agent_info = DIFY_AGENTS.get(agent_key, DIFY_AGENTS["Emily"])

    # DifyAgentを生成
    dify_agent = DifyAgent(
        api_key=agent_info["api_key"],
        base_url=agent_info["base_url"],
        user=agent_info["user"],
        type=DifyType.Chatbot,
        verbose=True
    )

    # DifyAgentを使用して会話を進行
    conversation_id, response_text, data = await dify_agent.invoke(
        conversation_session.conversation_id,
        text=message.text,
        inputs={}
    )

    # セッション情報を更新
    conversation_session.conversation_id = conversation_id
    await line_dify.conversation_session_store.set_session(conversation_session)

    # 応答メッセージを生成（sender情報を含める）
    reply_message = TextMessage(
        text=response_text,
        sender={"name": agent_key, "iconUrl": agent_info.get("iconUrl")}
    )
    await line_dify.line_api.reply_message(
        ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[reply_message]
        )
    )

    return []

# make_inputs 関数を追加（必要に応じて）
@line_dify.make_inputs
async def make_inputs(session: ConversationSession):
    return {}

# to_reply_message 関数を追加（必要に応じて）
@line_dify.to_reply_message
async def to_reply_message(text: str, data: dict, session: ConversationSession):
    agent_key = session.agent_key or "Emily"
    agent_info = DIFY_AGENTS.get(agent_key, DIFY_AGENTS["Emily"])
    return [TextMessage(
        text=text,
        sender={"name": agent_key, "iconUrl": agent_info.get("iconUrl")}
    )]

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
