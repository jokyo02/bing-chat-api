import aiohttp
import asyncio
import httpx
import json
import urllib

from networks import (
    ChathubRequestPayloadConstructor,
    ConversationRequestHeadersConstructor,
)
from networks import MessageParser
from utils.logger import logger

http_proxy = "http://localhost:11111"  # Replace with yours


class ConversationConnector:
    def __init__(
        self,
        conversation_style: str = "precise",
        sec_access_token: str = "",
        client_id: str = "",
        conversation_id: str = "",
        invocation_id: int = 0,
        cookies={},
    ):
        self.conversation_style = conversation_style
        self.sec_access_token = sec_access_token
        self.client_id = client_id
        self.conversation_id = conversation_id
        self.invocation_id = invocation_id
        self.cookies = cookies

    async def wss_send(self, message):
        serialized_websocket_message = json.dumps(message, ensure_ascii=False) + "\x1e"
        await self.wss.send_str(serialized_websocket_message)

    async def init_handshake(self):
        await self.wss_send({"protocol": "json", "version": 1})
        await self.wss.receive_str()
        await self.wss_send({"type": 6})

    async def connect(self):
        self.quotelized_sec_access_token = urllib.parse.quote(self.sec_access_token)
        self.ws_url = (
            f"wss://sydney.bing.com/sydney/ChatHub"
            f"?sec_access_token={self.quotelized_sec_access_token}"
        )
        self.aiohttp_session = aiohttp.ClientSession(cookies=self.cookies)
        headers_constructor = ConversationRequestHeadersConstructor()
        self.wss = await self.aiohttp_session.ws_connect(
            self.ws_url,
            headers=headers_constructor.request_headers,
            proxy=http_proxy,
        )
        await self.init_handshake()

    async def send_chathub_request(self, prompt):
        payload_constructor = ChathubRequestPayloadConstructor(
            prompt=prompt,
            conversation_style=self.conversation_style,
            client_id=self.client_id,
            conversation_id=self.conversation_id,
            invocation_id=self.invocation_id,
        )
        self.connect_request_payload = payload_constructor.request_payload
        await self.wss_send(self.connect_request_payload)

    async def stream_chat(self, prompt=""):
        await self.connect()
        await self.send_chathub_request(prompt)
        message_parser = MessageParser()
        while not self.wss.closed:
            response_lines_str = await self.wss.receive_str()
            if isinstance(response_lines_str, str):
                response_lines = response_lines_str.split("\x1e")
            else:
                continue
            for line in response_lines:
                if not line:
                    continue
                data = json.loads(line)
                # Stream: Meaningful Messages
                if data.get("type") == 1:
                    message_parser.parse(data)
                # Stream: List of all messages in the whole conversation
                elif data.get("type") == 2:
                    if data.get("item"):
                        # item = data.get("item")
                        # logger.note("\n[Saving chat messages ...]")
                        pass
                # Stream: End of Conversation
                elif data.get("type") == 3:
                    logger.success("\n[Finished]")
                    self.invocation_id += 1
                    await self.wss.close()
                    await self.aiohttp_session.close()
                    break
                # Stream: Heartbeat Signal
                elif data.get("type") == 6:
                    continue
                # Stream: Not Monitored
                else:
                    continue
