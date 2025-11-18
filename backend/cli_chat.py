# backend/cli_chat.py
import os
import sys
import asyncio
from dotenv import load_dotenv

# Import the async agent from your existing agent file
from .langgraph_agent import run_agent

load_dotenv()

async def main_loop():
    session_id = "cli_session_user"
    print("--- Insurance Assistant (CLI Mode) ---")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            # Standard input is synchronous, which is fine for a simple CLI tool
            text = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not text:
            continue

        if text.lower() in ("exit", "quit"):
            print("Bye.")
            break

        if text.lower() == "reset":
            # In a real app, you might delete the thread from the DB here.
            # For now, we just change the session ID to start fresh.
            import uuid
            session_id = f"cli_{uuid.uuid4().hex[:8]}"
            print(f"Session reset (New ID: {session_id}).")
            continue

        try:
            # The agent now manages history automatically via session_id
            # We just pass the text and the ID.
            answer = await run_agent(text, session_id)
        except Exception as e:
            answer = f"Error: {e}"

        print(f"Assistant: {answer}\n")
        sys.stdout.flush()

def main():
    # Run the async loop
    asyncio.run(main_loop())

if __name__ == "__main__":
    # Ensure we can import modules from the current directory
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    main()