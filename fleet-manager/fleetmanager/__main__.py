import argparse

import uvicorn

p = argparse.ArgumentParser(description="ERP Fleet Manager")
p.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to reach it from other machines (put HTTPS in front!)")
p.add_argument("--port", type=int, default=8800)
a = p.parse_args()
print(f"\n  ERP Fleet Manager -> http://{'localhost' if a.host == '127.0.0.1' else a.host}:{a.port}\n")
uvicorn.run("fleetmanager.main:app", host=a.host, port=a.port)
