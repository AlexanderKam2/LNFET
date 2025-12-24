from functools import wraps
from typing import Literal, Callable, Tuple, Any
import json, zlib
import binascii
import threading
import socket

class client:
    class NewQNA(object):
        def __init__(self, host: str, port: int):
            self.host, self.port = host, port
            self.ctype, self.content = None, None
        
        def set_content(self, content: str | bytes):
            self.ctype = "str" if isinstance(content, str) else "bin"
            self.content = content
        
        def send(self, waitbytes: int = 4096) -> dict:
            if self.ctype and self.content:
                request = {
                    "ctype": self.ctype,
                    "content": self.content if self.ctype == "str" else binascii.hexlify(self.content).decode()
                }
                jreq = json.dumps(request)
                breq = zlib.compress(jreq.encode(encoding="UTF-8"))

                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.connect((self.host, self.port))

                client_socket.send(breq)

                response = client_socket.recv(waitbytes)
                bres = zlib.decompress(response)
                jres = json.loads(bres.decode(encoding="UTF-8"))
                client_socket.close()
                return {
                    "ctype": jres["ctype"],
                    "content": jres["content"] if jres["ctype"] == "str" else binascii.unhexlify(jres["content"])
                }

class server:
    class QNAServer(object):
        def __init__(self, host: str, port: int):
            self._handlers = {
                "str": None,
                "bin": None,
                "all": None
            }
            self.quit = False
            self.host = host
            self.port = port

        def set_handler(self, ctype: Literal["str", "bin"] | None = None):
            def decorator_wrapper(func: Callable) -> Callable:
                @wraps(func)
                def wrapper(*args, **kwargs):
                    return func(*args, **kwargs)
                
                if ctype is None:
                    self._handlers["all"] = wrapper
                else:
                    self._handlers[ctype] = wrapper
                
                return wrapper
            return decorator_wrapper
        
        def stop(self):
            self.quit = True
        
        def _handle_connection(self, conn: socket.socket, addr: tuple, waitbytes: int):
            try:
                data = conn.recv(waitbytes)
                if not data:
                    return
                    
                jdata = json.loads(zlib.decompress(data).decode(encoding="UTF-8"))

                ctype = jdata["ctype"]
                content = jdata["content"] if ctype == "str" else binascii.unhexlify(jdata["content"])

                handler = self._handlers.get(ctype)
                if handler is None:
                    handler = self._handlers.get("all")
                
                if handler:
                    result = handler(content)
                    
                    if result is not None:
                        if isinstance(result, tuple) and len(result) == 2:
                            resp_ctype, resp_content = result
                        else:
                            resp_ctype = "str" if isinstance(result, str) else "bin"
                            resp_content = result
                        
                        response = {
                            "ctype": resp_ctype,
                            "content": resp_content if resp_ctype == "str" else binascii.hexlify(resp_content).decode()
                        }
                        
                        jresp = json.dumps(response)
                        bresp = zlib.compress(jresp.encode(encoding="UTF-8"))
                        conn.send(bresp)
                else:
                    error_response = {
                        "ctype": "str",
                        "content": "No handler registered for this content type"
                    }
                    jresp = json.dumps(error_response)
                    bresp = zlib.compress(jresp.encode(encoding="UTF-8"))
                    conn.send(bresp)
                    
            except Exception as e:
                error_response = {
                    "ctype": "str", 
                    "content": f"Error processing request: {str(e)}"
                }
                jresp = json.dumps(error_response)
                bresp = zlib.compress(jresp.encode(encoding="UTF-8"))
                conn.send(bresp)
            finally:
                conn.close()
        
        def mainloop(self, waitbytes: int = 4096):
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            server_socket.bind((self.host, self.port))
            server_socket.listen(5)

            host = server_socket.getsockname()[0]
            port = server_socket.getsockname()[1]

            print(f"Main loop started.\n * HOST: {host}\n * PORT: {port}")
            
            try:
                while not self.quit:
                    conn, addr = server_socket.accept()
                    print(f"Connect from {addr}")

                    thread = threading.Thread(target=self._handle_connection, args=(conn, addr, waitbytes))
                    thread.daemon = True
                    thread.start()
            finally:
                server_socket.close()