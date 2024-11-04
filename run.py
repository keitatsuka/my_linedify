from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks
from linedify import LineDify

# LINE Bot - Dify Agent Integrator
line_dify = LineDify(
    line_channel_access_token="YOUR_CHANNEL_ACCESS_TOKEN",
    line_channel_secret="YOUR_CHANNEL_SECRET",
    dify_api_key="DIFY_API_KEY",
    dify_base_url="DIFY_BASE_URL",    # e.g. http://localhost/v1
    dify_user="DIFY_USER"
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
