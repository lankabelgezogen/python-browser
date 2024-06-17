import socket
import sys
import ssl
import os

class URL:
    def __init__(self, url="file:///index.html"):
        if url.startswith("data:"):
            self.scheme = "data"
            self.data = url.split(":", 1)[1]
            return

        self.scheme, url = url.split('://', 1)
        assert self.scheme in ["http", "https", "file"]

        self.host = None
        self.port = None
        self.path = None

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

        elif self.scheme == "file":
            if os.name == "nt" and url.startswith("/"):
                path = url[1:]
            self.path = path

    def request(self, headers={}):
        if self.scheme in ["http", "https"]:
            s = socket.socket(
                family=socket.AF_INET,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
            s.connect((self.host, self.port))

            if self.scheme == "https":
                ctx = ssl.create_default_context()
                s = ctx.wrap_socket(s, server_hostname=self.host)

            request = "GET {} HTTP/1.0\r\n".format(self.path)
            request += "Host: {}\r\n".format(self.host)
            request += "Connection: close\r\n"
            request += "User-Agent: LanKabel/1.0\r\n"
            for header, value in headers.items():
                request += "{}: {}\r\n".format(header, value)
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

            content = response.read()
            s.close()

            return content
        
        elif self.scheme == "file":
            try:
                with open(self.path, "r") as f:
                    return f.read()
            except FileNotFoundError:
                return "404 Not Found"
            except Exception as e:
                return str(e)
            
        elif self.scheme == "data":
            return self.data

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

def load(url):
    body = url.request()
    show(body)

if __name__ == "__main__":
    load(URL(sys.argv[1]))