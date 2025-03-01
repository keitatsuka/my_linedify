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

# Dify エージェント情報を辞書にまとめる
DIFY_AGENTS = {
    "Emily": {
        "api_key": os.getenv('DIFY_API_KEY_EMILY'),
        "base_url": os.getenv('DIFY_BASE_URL_EMILY'),
        "user": os.getenv('DIFY_USER_EMILY'),
    },
    "フィナ": {
        "api_key": os.getenv('DIFY_API_KEY_FINA'),
        "base_url": os.getenv('DIFY_BASE_URL_FINA'),
        "user": os.getenv('DIFY_USER_FINA'),
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

    if isinstance(message, TextMessageContent):
        text = message.text.strip()

        # 自動エージェント切替の条件チェック
        # 初回のセッションの場合、デフォルトを "Emily" に設定
        if not conversation_session.agent_key:
            conversation_session.agent_key = "Emily"

        # 条件1: メッセージに「フィナ」が含まれており、「バイバイ」が含まれていない場合、かつ現在のエージェントが "Emily" の場合
        if "フィナ" in text and "バイバイ" not in text:
            if conversation_session.agent_key == "Emily":
                conversation_session.agent_key = "フィナ"
                reply_msg = TextMessage(text="エージェントをフィナに切り替えました。")
                await line_dify.line_api.reply_message(
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[reply_msg]
                    )
                )
                await line_dify.conversation_session_store.set_session(conversation_session)
                return []

        # 条件2: メッセージに「フィナ」と「バイバイ」の両方が含まれている場合、かつ現在のエージェントが "フィナ" の場合
        elif "フィナ" in text and "バイバイ" in text:
            if conversation_session.agent_key == "フィナ":
                conversation_session.agent_key = "Emily"
                reply_msg = TextMessage(text="エージェントをEmilyに切り替えました。")
                await line_dify.line_api.reply_message(
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[reply_msg]
                    )
                )
                await line_dify.conversation_session_store.set_session(conversation_session)
                return []

        # ユーザーが「AIタイプ変更リクエスト」を送信した場合
        if text == "AIタイプ変更リクエスト":
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
                conversation_session.conversation_id = None  # 会話IDをリセット
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

    # 応答メッセージを生成
    reply_message = TextMessage(text=response_text)
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
