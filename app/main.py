import logging
import os

import uvicorn
from dotenv import load_dotenv


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run(
        "HttpHandler.api:create_app", factory=True,
        host="0.0.0.0", port=int(os.getenv("PORT", "8000")),
    )
