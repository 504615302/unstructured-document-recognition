import argparse
from fastapi import FastAPI
import uvicorn
from app.routers import document_api

app = FastAPI()

app.include_router(document_api.router)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', type=bool, default=False)

    args = parser.parse_args()
    if args.debug:
        uvicorn.run('main:app', host="0.0.0.0", port=23622, reload=args.debug)
    else:
        uvicorn.run('main:app', host="0.0.0.0", port=8089, reload=args.debug)
