import socket
import sys
import ssl
import os

class RedirectLoopError(Exception):
    pass

class URL:
    def __init__(self, url="file:///index.html"):
        
        self.host = None
        self.port = None
        self.path = None
        self.socket = None
        self.view_source = False

        if url.startswith("data:"):
            self.scheme = "data"
            self.data = url.split(":", 1)[1]
            return
        
        if url.startswith("view-source:"):
            url = url.split(":", 1)[1]
            self.view_source = True

        if url.startswith("file:"):
            self.scheme = "file"
            url = url.split(":", 1)[1]
            if os.name == "nt" and url.startswith("/"):
                url = url.lstrip("/")
            self.path = url
            return

        self.scheme, url = url.split('://', 1)
        assert self.scheme in ["http", "https"]

        if self.scheme in ["http", "https"]:
            if self.scheme == "https":
                self.port = 443
            elif self.scheme == "http":
                self.port = 80
            
            if "/" not in url:
                url += "/"
            self.host, url = url.split('/', 1)
            self.path = "/" + url

            if ":" in self.host:
                self.host, port = self.host.split(':', 1)
                self.port = int(port)            

    def request(self, headers={}, redirect_count=0, visited_urls=None):
        MAX_REDIRECTS = 10
        if redirect_count > MAX_REDIRECTS:
            raise RedirectLoopError("Too many redirects")
        
        if visited_urls is None:
            visited_urls = set()
        
        current_url = f"{self.scheme}://{self.host}:{self.port}{self.path}"
        if current_url in visited_urls:
            raise RedirectLoopError("Redirect loop detected")
        visited_urls.add(current_url)

        if self.scheme in ["http", "https"]:
            if self.socket is None:
                s = socket.socket(
                    family=socket.AF_INET,
                    type=socket.SOCK_STREAM,
                    proto=socket.IPPROTO_TCP,
                )
                s.connect((self.host, self.port))

                if self.scheme == "https":
                    ctx = ssl.create_default_context()
                    s = ctx.wrap_socket(s, server_hostname=self.host)
            else:
                s = self.socket

            request = "GET {} HTTP/1.1\r\n".format(self.path)

            unique_headers = {
                "host": self.host,
                #"connection": "close",
                "content-length": "0",
                "user-agent": "LanKabel/1.0"
            }

            for header, value in headers.items():
                unique_headers[header.lower()] = value

            for header, value in unique_headers.items():
                request += "{}: {}\r\n".format(header.title(), value)

            request += "\r\n"
            s.send(request.encode('utf-8'))

            response = s.makefile('r', encoding='utf-8', newline='\r\n')

            statusline = response.readline()
            version, status, explanation = statusline.split(' ', 2)

            response_headers = {}
            while True:
                line = response.readline()
                if line == '\r\n':
                    break
                header, value = line.split(":", 1)
                response_headers[header.casefold()] = value.strip()
            
            assert "transfer-encoding" not in response_headers
            assert "content-encoding" not in response_headers

            if status in ["301", "302", "303", "307", "308"]:
                if "location" in response_headers:
                    location = response_headers["location"]
                    new_url = URL(location if "://" in location else f"{self.scheme}://{self.host}:{self.port}{location}")
                    new_url.socket = s
                    return new_url.request(headers, redirect_count + 1, visited_urls)

            content_length = int(response_headers.get("content-length", 0))
            content = response.read(content_length)
            
            self.socket = s
            #s.close()

            return content
        
        elif self.scheme == "file":
            try:
                with open(self.path, "r") as f:
                    return f.read()
            except FileNotFoundError as e:
                return f'FileNotFoundError: {str(e)}'
            except Exception as e:
                return str(e)
            
        elif self.scheme == "data":
            return self.data
    
    def __repr__(self):
        return "URL(scheme={}, host={}, port={}, path={!r})".format(
            self.scheme, self.host, self.port, self.path)

def show(body):
    res = ""
    in_tag = False

    for c in body:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            #print(c, end="")
            res += c
            
    res = res.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    print(res)

def view_source(body):
    print(body)

def load(url):
    body = url.request()
    if url.view_source:
        view_source(body)
    else:
        show(body)

if __name__ == "__main__":
    load(URL(sys.argv[1]))