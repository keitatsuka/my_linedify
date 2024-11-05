from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks
from linedify import LineDify
import os

# 環境変数から値を取得
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
DIFY_API_KEY = os.getenv('DIFY_API_KEY')
DIFY_BASE_URL = os.getenv('DIFY_BASE_URL')
DIFY_USER = os.getenv('DIFY_USER')

# LineDifyのインスタンスを作成
line_dify = LineDify(
    line_channel_access_token=LINE_CHANNEL_ACCESS_TOKEN,
    line_channel_secret=LINE_CHANNEL_SECRET,
    dify_api_key=DIFY_API_KEY,
    dify_base_url=DIFY_BASE_URL,
    dify_user=DIFY_USER
)

# FastAPIのアプリケーションを作成
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await line_dify.shutdown()

app = FastAPI(lifespan=lifespan)

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