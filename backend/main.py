import os
import json
import time
import io
import base64
import asyncio
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from openai import OpenAI

# Import the async agent
from .langgraph_agent import run_agent

load_dotenv()

# --- Setup & Validation ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not set in .env file.")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI()

# --- Static Files & Templates ---
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "frontend", "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "frontend", "static")), name="static")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --- WebSocket Handler ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("--- WebSocket Connected ---")
    
    try:
        while True:
            # Wait for message
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            typ = msg.get("type")
            session_id = msg.get("session_id") or "default_thread"

            # Handle Reset
            if typ == "reset":
                await websocket.send_text(json.dumps({"type":"response", "text":"Session reset."}))
                continue

            # Handle Audio
            if typ == "audio":
                print("\n--- ⚡ STARTING FAST REQUEST ---")
                start_time = time.time()
                
                # 1. DECODE AUDIO (In Memory)
                b64 = msg.get("data")
                if not b64: continue
                
                try:
                    if "," in b64: 
                        b64 = b64.split(",")[1]
                    audio_data = base64.b64decode(b64)
                    
                    # Create in-memory file object (RAM only, no disk I/O)
                    audio_file = io.BytesIO(audio_data)
                    audio_file.name = "audio.webm" 
                    
                    print(f"[{(time.time()-start_time):.2f}s] Audio decoded in RAM.")
                except Exception as e:
                    print(f"Audio Decoding Error: {e}")
                    continue

                # 2. WHISPER STT (Threaded to prevent blocking)
                try:
                    # Define the synchronous blocking call
                    def transcribe_sync():
                        return openai_client.audio.transcriptions.create(
                            model="whisper-1", 
                            file=audio_file,
                            language="en" # SPEEDUP: Skip language detection
                        )
                    
                    # Run it in a separate thread so the server stays responsive
                    transcript_obj = await asyncio.to_thread(transcribe_sync)
                    text = transcript_obj.text.strip()
                    
                    print(f"[{(time.time()-start_time):.2f}s] Whisper: '{text}'")
                except Exception as e:
                    print(f"Whisper Error: {e}")
                    await websocket.send_text(json.dumps({"type":"error", "message":str(e)}))
                    continue
                
                # Send transcript back to UI immediately
                await websocket.send_text(json.dumps({"type":"transcript", "text": text}))

                # 3. LANGGRAPH AGENT (Async)
                print(f"[{(time.time()-start_time):.2f}s] Calling Agent...")
                try:
                    # Await the async agent
                    answer = await run_agent(text, session_id)
                    print(f"[{(time.time()-start_time):.2f}s] Agent Replied.")
                except Exception as e:
                    answer = f"Agent Error: {e}"
                    print(f"Agent Error: {e}")

                # 4. SEND RESPONSE
                await websocket.send_text(json.dumps({"type":"response", "text": answer}))
                total_time = time.time() - start_time
                print(f"--- ✅ FINISHED in {total_time:.2f}s ---")

            # Handle Text
            elif typ == "text":
                text = msg.get("data", "")
                try:
                    answer = await run_agent(text, session_id)
                except Exception as e:
                    answer = f"Error: {e}"
                await websocket.send_text(json.dumps({"type":"response", "text": answer}))

    except Exception as e:
        print(f"WebSocket Disconnected: {e}")
        try:
            await websocket.close()
        except:
            pass