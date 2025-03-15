# -*- coding: utf-8 -*-
import re
import os
import requests
from flask import Flask, Response, redirect, request
from requests.exceptions import (
    ChunkedEncodingError,
    ContentDecodingError, ConnectionError, StreamConsumedError)
from requests.utils import (
    stream_decode_response_unicode, iter_slices, CaseInsensitiveDict)
from urllib3.exceptions import (
    DecodeError, ReadTimeoutError, ProtocolError)
from urllib.parse import quote


# ----------------------
# 配置文件规则读取
# ----------------------
def read_and_process_rules(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = [line.strip()
                     for line in file if line.strip()]  # 去除空行及两端空白
        return [tuple(item.replace(' ', '') for item in line.split('/')) for line in lines]
    except:
        return []


# ----------------------
# 配置部分
# ----------------------
# 允许代理的文件大小限制 https://github.com/hunshcn/gh-proxy/issues/8
size_limit = int(os.environ.get('SIZE_LIMIT', 1024 * 1024 * 1024 * 999))

# 大文件服务器地址
BIG_SERVER = os.environ.get('BIG_SERVER', 'https://ghfast.top/')

# 读取并处理访问控制规则
white_list = read_and_process_rules('whitelist.txt')
black_list = read_and_process_rules('blacklist.txt')
pass_list = read_and_process_rules('passlist.txt')

# 要删除的头部列表
HEADERS_TO_REMOVE = ['Transfer-Encoding', 'Strict-Transport-Security', 'Access-Control-Allow-Origin',
                     'Clear-Site-Data',  'Content-Security-Policy', 'Content-Security-Policy-Report-Only',
                     'Cross-Origin-Resource-Policy', 'X-GitHub-Request-Id', 'X-Fastly-Request-ID', 'Via',
                     'X-Served-By', 'X-Cache', 'X-Cache-Hits', 'X-Timer', 'Expires', 'Source-Age']

# 监听参数（实际以 gunicorn、uwsgi 的为主）
HOST = '127.0.0.1'  # 监听地址，建议监听本地然后由web服务器反代
PORT = 8000         # 监听端口

# 初始化Flask应用
app = Flask(__name__)
CHUNK_SIZE = 1024 * 10  # 流式传输分块大小


# ----------------------
# GitHub URL正则匹配模式
# ----------------------
# 匹配 releases/archive
exp1 = re.compile(
    r'^(?:https?://)?github\.com/(?P<author>.+?)/(?P<repo>.+?)/(?:releases|archive)/.*$')
# 匹配 blob/raw
exp2 = re.compile(
    r'^(?:https?://)?github\.com/(?P<author>.+?)/(?P<repo>.+?)/(?:blob|raw)/.*$')
# 匹配 git信息
exp3 = re.compile(
    r'^(?:https?://)?github\.com/(?P<author>.+?)/(?P<repo>.+?)/(?:info|git-).*$')
# 匹配 raw文件
exp4 = re.compile(
    r'^(?:https?://)?raw\.(?:githubusercontent|github)\.com/(?P<author>.+?)/(?P<repo>.+?)/.+?/.+$')
# 匹配 gist
exp5 = re.compile(
    r'^(?:https?://)?gist\.(?:githubusercontent|github)\.com/(?P<author>.+?)/.+?/.+$')

# 清除requests默认headers
requests.sessions.default_headers = lambda: CaseInsensitiveDict()


# ----------------------
# 路由处理
# ----------------------


@app.route('/')
# 首页处理，支持q参数重定向
def index():
    if 'q' in request.args:  # 如果带q参数则重定向
        return redirect('/' + request.args.get('q'), 301)
    # 默认返回404页面
    return Response('The requested resource was not found on this server.', status=404)

# 禁止爬虫
@app.route('/robots.txt')
def robots():
    return Response("User-agent: *\r\nDisallow: /", status=200)


# ----------------------
# 自定义流式内容处理
# ----------------------


def iter_content(self, chunk_size=1, decode_unicode=False):
    """rewrite requests function, set decode_content with False"""

    def generate():
        # Special case for urllib3.
        if hasattr(self.raw, 'stream'):
            try:
                yield from self.raw.stream(chunk_size, decode_content=False)
            except ProtocolError as e:
                raise ChunkedEncodingError(e)
            except DecodeError as e:
                raise ContentDecodingError(e)
            except ReadTimeoutError as e:
                raise ConnectionError(e)
        else:
            # Standard file-like object.
            while True:
                chunk = self.raw.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        self._content_consumed = True

    if self._content_consumed and isinstance(self._content, bool):
        raise StreamConsumedError()
    elif chunk_size is not None and not isinstance(chunk_size, int):
        raise TypeError(
            f"chunk_size must be an int, it is instead a {type(chunk_size)}.")
    # simulate reading small chunks of the content
    reused_chunks = iter_slices(self._content, chunk_size)

    stream_chunks = generate()

    chunks = reused_chunks if self._content_consumed else stream_chunks

    if decode_unicode:
        chunks = stream_decode_response_unicode(chunks, self)

    return chunks


# ----------------------
# URL校验函数
# ----------------------


def check_url(u):
    for exp in (exp1, exp2, exp3, exp4, exp5):
        if m := exp.match(u):
            return m
    return False


# ----------------------
# 主请求处理
# ----------------------


@app.route('/<path:u>', methods=['GET', 'POST'])
def handler(u):
    # 构造完整URL
    u = u if u.startswith('http') else 'https://' + u
    u = u.replace('s:/', 's://', 1) if u.rfind('://', 3, 9) == - \
        1 else u  # 修复双斜杠问题 uwsgi会将//传递为/

    # 检查URL合法性
    if not (m := check_url(u)):
        return Response('Invalid input.', status=403)

    # 白名单检查
    m_tuple = tuple(m.groups())
    if white_list:
        if not any((m_tuple[:len(i)] == i) or (i[0] == '*' and m_tuple[1] == i[1]) for i in white_list):
            return Response('Forbidden by white list.', status=403)

    # 黑名单检查
    if any((m_tuple[:len(i)] == i) or (i[0] == '*' and m_tuple[1] == i[1]) for i in black_list):
        return Response('Forbidden by black list.', status=403)

    # 直接跳转检查
    if any((m_tuple[:len(i)] == i) or (i[0] == '*' and m_tuple[1] == i[1]) for i in pass_list):
        return redirect(BIG_SERVER + u, 301)

    # 转换blob为raw地址
    if exp2.match(u):
        u = u.replace('/blob/', '/raw/', 1)

    # URL编码处理
    u = quote(u, safe='/:')
    return proxy(u)  # 执行代理请求


# ----------------------
# 代理转发函数
# ----------------------


def proxy(u, allow_redirects=False, last=""):
    try:
        # 构造目标URL
        url = u + request.url.replace(request.base_url, '', 1)
        if url.startswith('https:/') and not url.startswith('https://'):
            url = 'https://' + url[7:]

        # 转发请求
        r = requests.request(
            method=request.method,
            url=url,
            data=request.data,
            headers={k: v for k, v in request.headers if k.lower() != 'host'},
            stream=True,
            allow_redirects=allow_redirects
        )

        # 检查文件大小限制
        if 'Content-length' in r.headers and int(r.headers['Content-length']) > size_limit:
            if not 'CF-IPCountry' in request.headers or request.headers['CF-IPCountry'] == 'CN':
                url = last if last else url
                return redirect(BIG_SERVER + url, 301)
            return redirect(url, 301)

        # 处理重定向
        if 'Location' in r.headers:
            loc = r.headers['Location']
            return proxy(loc, True, url) if not check_url(loc) else redirect('/' + loc, 301)

        # 删除指定的头部信息
        for header in HEADERS_TO_REMOVE:
            if header in r.headers:
                r.headers.pop(header)

        # 流式响应生成器
        def generate():
            for chunk in iter_content(r, chunk_size=CHUNK_SIZE):
                yield chunk

        return Response(generate(), headers=dict(r.headers), status=r.status_code)

    except Exception as e:
        return Response(f'server error {str(e)}', status=500, headers={'content-type': 'text/html; charset=UTF-8'})


# ----------------------
# 启动应用
# ----------------------
# app.debug = True
if __name__ == '__main__':
    app.run(host=HOST, port=PORT)
