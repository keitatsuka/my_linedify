import os  # 追加
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks
from linedify import LineDify

# 環境変数からトークンやシークレットを取得
line_channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
line_channel_secret = os.getenv("LINE_CHANNEL_SECRET")
dify_api_key = os.getenv("DIFY_API_KEY")
dify_base_url = os.getenv("DIFY_BASE_URL")
dify_user = os.getenv("DIFY_USER")

# LINE Bot - Dify Agent Integrator
line_dify = LineDify(
    line_channel_access_token=line_channel_access_token,
    line_channel_secret=line_channel_secret,
    dify_api_key=dify_api_key,
    dify_base_url=dify_base_url,    # e.g. http://localhost/v1
    dify_user=dify_user
)

# FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await line_dify.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/linebot")
async def handle_request(request: Request, background_tasks: BackgroundTasks):
    background_tasks.add_task(
        line_dify.process_request,
        request_body=(await request.body()).decode("utf-8"),
        signature=request.headers.get("X-Line-Signature", "")
    )
    return "ok"
