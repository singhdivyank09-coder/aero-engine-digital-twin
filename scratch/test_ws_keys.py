import asyncio
import websockets
import json

async def main():
    uri = "ws://localhost:8000/ws/telemetry"
    print(f"Connecting to {uri}...")
    async with websockets.connect(uri) as ws:
        for i in range(3):
            msg = await ws.recv()
            data = json.loads(msg)
            print(f"Message {i+1}: keys={list(data.keys())[:10]}")
            print(f"  sequence_number={data.get('sequence_number')}, sequence_no={data.get('sequence_no')}")
            if "telemetry" in data:
                print(f"  telemetry sequence_no={data['telemetry'].get('sequence_no')}")

if __name__ == "__main__":
    asyncio.run(main())
