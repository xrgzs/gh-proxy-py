# GitHub Proxy Python

## 简介

GitHub Release、Archive 以及项目文件的加速项目，支持 Clone

## 使用

`https://gh.example.com/<your-url>`

也可以 `https://gh.example.com/?q=<your-url>`

访问私有仓库可以通过

`git clone https://<your-user>:<your-token>@gh.example.com/<your-private-repo-url>` [#71](https://github.com/hunshcn/gh-proxy/issues/71)

以下都是合法输入（仅示例，文件不存在）：

- 分支源码：https://github.com/xrgzs/project/archive/master.zip

- Release 源码：https://github.com/xrgzs/project/archive/v0.1.0.tar.gz

- Release 文件：https://github.com/xrgzs/project/releases/download/v0.1.0/example.zip

- 分支文件：https://github.com/xrgzs/project/blob/master/filename

- Commit 文件：https://github.com/xrgzs/project/blob/32323232323232323232323232323232/filename

- Gist：https://gist.githubusercontent.com/xrgzs/32323232323232323232323232323232/raw/cmd.py

## 特点

- 默认不输出前端，作为接口站使用，减小特征

- 使用 Python 开发，方便扩展更多功能
  - 仅提供 Python 版本，负责部署到边缘节点进行路由

- 代码重构，增加注释，一目了然

- 支持将大文件流量负载到其他服务器
  - 去除原版跳转 jsDelivr 的功能
  - 服务器套 Cloudflare 可以解锁更多功能
    - 境外访问重定向回 GitHub
    - 境内访问重定向到大文件服务器
  - 默认访问重定向到大文件服务器

- 支持通过 ENV 灵活设置参数
  - `SIZE_LIMIT`：允许代理的文件大小限制，单位：字节，默认为 `999GB`
  - `BIG_SERVER`：大文件服务器地址，默认为 `https://ghfast.top/`

- 支持外置访问规则
  - `whitelist.txt`：自定义白名单
  - `blacklist.txt`：自定义黑名单
  - `passlist.txt`：自定义直接跳转大文件服务器名单

- 提供 ghcr.io Docker 镜像
  - 使用 Gunicorn 替代原版的 uWSGI + NGINX，你的服务器可以少跑一个 NGINX
  - 升级 Python 版本

### 访问控制规则

白名单生效后再匹配黑名单，passlist匹配到的会直接跳转到大文件服务器

规则格式（每行一个）：

```text
user1        # 封禁/允许user1的所有仓库
user1/repo1  # 封禁/允许user1的repo1
*/repo1      # 封禁/允许所有名为repo1的仓库
```

## Python 版本部署

### Docker 部署

```shell
docker run -d --name="gh-proxy-py" \
  -p 8848:8000 \
  --restart=always \
  ghcr.io/xrgzs/gh-proxy-py:master
```

第一个8048是你要暴露出去的端口

更多参数见 Compose：

```yaml
services:
  gh-proxy-py:
    image: ghcr.io/xrgzs/gh-proxy-py:master
    container_name: gh-proxy-py
    ports:
      - "127.0.0.1:8848:8000" # 暴露端口（最好用本机Web服务器反代）
    restart: always
    environment:
      - "SIZE_LIMIT=104857600"          # 允许代理的文件大小限制
      - "BIG_SERVER=https://ghfast.top/" # 大文件服务器地址
    volumes:
      - "./whitelist.txt:/app/whitelist.txt" # 自定义白名单规则
      - "./blacklist.txt:/app/blacklist.txt" # 自定义黑名单规则
      - "./passlist.txt:/app/passlist.txt" # 自定义直接跳转大文件服务器名单
```



### 直接部署

安装依赖（请使用python3）

```shell
pip install flask request
```

按需求修改 [app/main.py](app/main.py) 的前几项配置

执行 Python 文件即可：

```shell
cd app
python main.py
```

建议使用 Gunicorn，然后 NGINX / WAF 反代 Gunicorn，以获得最佳性能和灵活性：

```shell
pip install gunicorn
gunicorn --bind 127.0.0.1:8848 main:app
```

### NGINX 反代配置

建议缓存 301 302 请求，减轻多线程下载时服务器压力

跳转优先使用 301，避免 Git 客户端无法 Clone

```nginx
# 限制连接数存储区
limit_conn_zone $binary_remote_addr zone=ghp_addr:10m;
# 限制请求速率存储区（每秒钟最多发起5个请求）
limit_req_zone $binary_remote_addr zone=ghp_req_limit_per_ip:10m rate=5r/s;

server {
    listen 80;
    server_name gh.example.com;

    # 默认返回 nginx 错误页面
    location = / {
        return 404;
    }

    # 拦截非法 referer (referer 分流)
    # 允许 referer 为空或 *.example.com
    valid_referers none server_names *.example.com;
    if ($invalid_referer) {
       return 301 https://ghfast.top$request_uri;
    }

    # 拦截非法 ua (ua 分流)
    if ($http_user_agent ~* aria2) {
       return 301 https://ghfast.top$request_uri;
    }

    # 限制大文件下载速率 (防长期占用带宽)
    # limit_rate 500k;
    # limit_rate_after 50m;

    # 限制并发连接数 (防多线程 CC)
    limit_conn ghp_addr 2;

    # 限制请求速率 (防 CC)
    limit_req zone=ghp_req_limit_per_ip burst=10 nodelay;

    # 重定向 git clone 请求到其他站点，避免造成流量消耗
    # location ~ /info/ {
    #    try_files $uri @redirect;
    # }
    # location ~* git-upload-pack$ {
    #    try_files $uri @redirect;
    # }
    
    # 仅让带有路径的返回后端
    location ~ /.*/ {
        try_files $uri @proxy;
    }

    # 配置固定请求
    location /robots.txt {
        return 200 "User-agent: *\r\nDisallow: /";
    }
    location /favicon.ico {
        return 302 https://www.example.com/favicon.ico;
    }
    location /favicon.png {
        return 302 https://www.example.com/favicon.png;
    }

    # 反代到本地 python
    location @proxy {
        proxy_pass http://gh-proxy-py:8848;
        proxy_http_version 1.1;

        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Real-Port $remote_port;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header REMOTE-HOST $remote_addr;
        proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;

        proxy_cache_key $host$uri$is_args$args;
        proxy_cache_valid 301 302 600s;
        add_header X-Upstream-Cache-Status $upstream_cache_status;

    }

    # 重定向到其他站点
    location @redirect {
        return 301 https://ghfast.top$request_uri;
    }

    access_log logs/gh.example.com.log main;
    error_log logs/gh.example.com.error.log;
}
```

OpenResty 动态重定向代码

```nginx
# 重定向到其他站点
location @redirect {
    # OpenResty 动态重定向
    access_by_lua_block {
        -- 设置多个站点供负载均衡
        local ghproxy_routes = {
            "https://ghfast.top",
            "https://ghfast.top",
            "https://ghfast.top",
            "https://ghfast.top",
            "https://ghfast.top",
        }

        -- 计算当前时间戳并确定10秒的时间窗口
        local now = ngx.now()  -- 获取当前时间戳（秒）
        local time_window = math.floor(now / 10) * 10

        -- 使用时间窗口作为种子生成伪随机数
        math.randomseed(time_window)
        local random_index = math.random(#ghproxy_routes)

        -- 设置响应头以供后续处理阶段使用
        ngx.header['GHP-Total-Indexes'] = #ghproxy_routes
        ngx.header['GHP-Ramdom-Index'] = random_index

        -- 执行重定向
        ngx.redirect(ghproxy_routes[random_index] .. ngx.var.request_uri, 301)
    }
}
```

如果需要前端可以通过 NGINX 配置

如果是流量型服务器，还可以安装 [ypq123456789/TrafficCop](https://github.com/ypq123456789/TrafficCop) 监控流量

### Cloudflare 配置

可以将境外请求直接跳转到大文件服务器，减少服务器请求

规则：`(http.host eq "gh.example.com" and ip.src.country ne "CN")`

URL 重定向：动态 `concat("https://ghfast.top", http.request.uri.path)` 301
