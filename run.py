import os
from fastapi import FastAPI, Request, BackgroundTasks
from linedify.integration import LineDifyIntegrator  # インポートの修正

# LINE Bot - Dify Agent Integrator
line_dify = LineDifyIntegrator()  # 環境変数はintegration.pyで処理

# FastAPIアプリケーション
app = FastAPI()

@app.post("/linebot")
async def handle_request(request: Request, background_tasks: BackgroundTasks):
    background_tasks.add_task(
        line_dify.process_request,
        request_body=(await request.body()).decode("utf-8"),
        signature=request.headers.get("X-Line-Signature", "")
    )
    return "ok"

# サーバーのシャットダウン処理
@app.on_event("shutdown")
async def shutdown():
    await line_dify.shutdown()
