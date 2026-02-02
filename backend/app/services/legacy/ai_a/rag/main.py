
import argparse
import sys
import os
import subprocess
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def run_server(host, port, reload):
    """Start the FastAPI server."""
    print(f"Starting API Server at http://{host}:{port} (Reload: {reload})")
    uvicorn.run("app.api.server:app", host=host, port=port, reload=reload)

def run_module(module_path, args=[]):
    """Run a python module as a subprocess."""
    cmd = [sys.executable, "-m", module_path] + args
    print(f"Executing Module: {module_path} with args: {args}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing module: {e}")
    except KeyboardInterrupt:
        print("\nExecution interrupted.")

def main():
    parser = argparse.ArgumentParser(description="Omnihub RAG Pipeline CLI Dashboard")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- Command: server ---
    server_parser = subparsers.add_parser("server", help="Start the API server")
    server_parser.add_argument("--host", default=os.getenv("API_HOST", "0.0.0.0"), help="Host to bind")
    server_parser.add_argument("--port", type=int, default=int(os.getenv("API_PORT", 8000)), help="Port to bind")
    server_parser.add_argument("--no-reload", action="store_false", dest="reload", help="Disable auto-reload")

    # --- Command: pipeline ---
    pipeline_parser = subparsers.add_parser("pipeline", help="Pipeline operations")
    pipeline_subs = pipeline_parser.add_subparsers(dest="pipeline_cmd", help="Pipeline sub-commands")
    
    # (Removed: sync, docai)
    
    # pipeline run <doc_id>
    run_p = pipeline_subs.add_parser("run", help="Run processing pipeline for a single document")
    run_p.add_argument("--doc-id", required=True, help="Document ID to process")
    
    # pipeline bulk
    pipeline_subs.add_parser("bulk", help="Run bulk pipeline for all pending docs")

    # Parse args
    args = parser.parse_args()

    if args.command == "server":
        run_server(args.host, args.port, args.reload)
        
    elif args.command == "pipeline":
        if args.pipeline_cmd == "run":
            # Assuming pipeline_runner accepts --doc-id or --doc_id. 
            # Passing it as a positional or named arg depends on implementation.
            # Passing both styles for safety is risky. Let's assume standard named arg --doc_id is mostly used or doc_id as positional.
            # Based on typical usage: 
            run_module("app.pipeline.runners.pipeline_runner", ["--doc_id", args.doc_id])
        elif args.pipeline_cmd == "bulk":
            run_module("app.pipeline.runners.bulk_pipeline_runner")
        else:
            pipeline_parser.print_help()
            
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
