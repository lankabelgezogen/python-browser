import socket
import sys
import ssl
import os
import time
import gzip
import io
import tkinter
import tkinter.font

WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
VSTEP_NEWLINE = 24
SCROLL_STEP = 100
weight = "normal"
style = "roman"

class RedirectLoopError(Exception):
    pass

class CacheEntry:
    def __init__(self, content, max_age):
        self.content = content
        self.expiry_time = time.time() + max_age if max_age is not None else None
    def is_expired(self):
        return self.expiry_time is not None and time.time() >= self.expiry_time
    
class Text:
    def __init__(self, text):
        self.text = text

class Tag:
    def __init__(self, tag):
        self.tag = tag

class Layout:
    def __init__(self, tokens):
        self.display_list = []
        self.cursor_x, self.cursor_y = HSTEP, VSTEP
        self.weight = "normal"
        self.style = "roman"

        for token in tokens:
            self.process_token(token)
    
    def process_token(self, token):
        if isinstance(token, Text):
            for word in token.text.split():
                self.process_word(word)
        elif token.tag == "i":
            self.style = "italic"
        elif token.tag == "/i":
            self.style = "roman"
        elif token.tag == "b":
            self.weight = "bold"
        elif token.tag == "/b":
            self.weight = "normal"
    
    def process_word(self, word):
        font = tkinter.font.Font(size=16, weight=self.weight, slant=self.style)
        word_width = font.measure(word)

        if word == "\n":
            self.cursor_x = HSTEP
            self.cursor_y += VSTEP_NEWLINE
            return

        if self.cursor_x + word_width > WIDTH - HSTEP:
            self.cursor_x = HSTEP
            self.cursor_y += font.metrics("linespace") * 1.25
        self.display_list.append((self.cursor_x, self.cursor_y, word, font))
        self.cursor_x += word_width + font.measure(" ")

class Browser:    
    def __init__(self):
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT)
        self.canvas.pack(fill=tkinter.BOTH, expand=True)
        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<Up>", self.scrollup)
        self.window.bind("<MouseWheel>", self.mousewheel)
        self.window.bind("<Configure>", self.resize)
        bi_times = tkinter.font.Font(
            size=16,
            family="Courier New",
            weight="bold",
            slant="italic",
        )
    
    def load(self, url):
        body = url.request()
        tokens = lex(body)
        self.display_list = Layout(tokens).display_list
        self.draw()
        """ self.text = lex(body)
        self.display_list = layout(self.text)
        self.draw() """

    def draw(self):
        self.canvas.delete("all")
        self.can_scroll_down = False
        for x, y, c, font in self.display_list:
            if y > self.scroll + HEIGHT:
                self.can_scroll_down = True
                continue
            if y + VSTEP < self.scroll: continue
            adjusted_y = y - self.scroll
            if adjusted_y >= 0:
                self.canvas.create_text(x, adjusted_y, text=c, font=font, anchor="nw")

        scrollbar_height = HEIGHT / 8
        scrollbar_y = self.scroll * HEIGHT / len(self.display_list)
        self.canvas.create_rectangle(WIDTH - 20, scrollbar_y, WIDTH, scrollbar_y + scrollbar_height, fill="gray")
    
    def scrolldown(self, event):
        if self.can_scroll_down:
            self.scroll += SCROLL_STEP
            self.draw()

    def scrollup(self, event):
        if self.scroll > 0:
            self.scroll -= SCROLL_STEP
            self.draw()
    
    def mousewheel(self, event):
        if event.delta < 0:
            self.scrolldown(event)
        else:
            self.scrollup(event)

    def resize(self, event):
        WIDTH, HEIGHT = event.width, event.height
        #self.display_list = layout(self.text, WIDTH)
        self.draw()

class URL:
    cache = {}

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

        cache_entry = URL.cache.get(current_url)
        if cache_entry and not cache_entry.is_expired():
            return cache_entry.content

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
                "user-agent": "LanKabel/1.0",
                "accept-encoding": "gzip"
            }

            for header, value in headers.items():
                unique_headers[header.lower()] = value

            for header, value in unique_headers.items():
                request += "{}: {}\r\n".format(header.title(), value)

            request += "\r\n"
            s.send(request.encode('utf-8'))

            response = s.makefile('rb', newline='\r\n')

            statusline = response.readline().decode('utf-8')
            version, status, explanation = statusline.split(' ', 2)

            response_headers = {}
            while True:
                line = response.readline().decode('utf-8')
                if line == '\r\n':
                    break
                header, value = line.split(":", 1)
                response_headers[header.casefold()] = value.strip()

            if "transfer-encoding" in response_headers and response_headers["transfer-encoding"] == "chunked":
                content = self._read_chunked(response)
            else:
                content_length = int(response_headers.get("content-length", 0))
                content = response.read(content_length)

            if "content-encoding" in response_headers and response_headers["content-encoding"] == "gzip":
                content = gzip.decompress(content).decode('utf-8')
            else:
                content = content.decode('utf-8')

            if status in ["301", "302", "303", "307", "308"]:
                if "location" in response_headers:
                    location = response_headers["location"]
                    new_url = URL(location if "://" in location else f"{self.scheme}://{self.host}:{self.port}{location}")
                    new_url.socket = s
                    return new_url.request(headers, redirect_count + 1, visited_urls)

            cache_control = response_headers.get("cache-control", "")
            if "no-store" not in cache_control:
                max_age = None
                if "max-age" in cache_control:
                    parts = cache_control.split(",")
                    for part in parts:
                        if "max-age" in part:
                            _, value = part.split("=")
                            max_age = int(value.strip())
                URL.cache[current_url] = CacheEntry(content, max_age)
            
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
        
    def _read_chunked(self, response):
        content = b""
        while True:
            chunk_size_line = response.readline()
            if chunk_size_line == '':
                continue
            chunk_size = int(chunk_size_line, 16)
            if chunk_size == 0:
                break
            chunk_data = response.read(chunk_size)
            content += chunk_data
            response.read(2) # trailing CRLF (carriage return, line feed)
        return content
    
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
            
    res = res.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&nbsp;", " ")
    print(res)

def lex(body):
    out = []
    buffer = ""
    in_tag = False

    for c in body:
        if c == "<":
            in_tag = True
            if buffer:
                out.append(Text(buffer))
                buffer = ""
        elif c == ">":
            in_tag = False
            out.append(Tag(buffer))
            buffer = ""
        else:
            buffer += c
            
    if not in_tag and buffer:
        out.append(Text(buffer))
    return out

def view_source(body):
    print(body)

def load(url):
    body = url.request()
    if url.view_source:
        view_source(body)
    else:
        show(body)

if __name__ == "__main__":
    #load(URL(sys.argv[1]))
    Browser().load(URL(sys.argv[1]))
    tkinter.mainloop()
