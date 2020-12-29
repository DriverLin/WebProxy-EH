
from unicodedata import name
from urllib.parse import urlparse
import urllib.request
import requests
import re
import os
import urllib.parse as parse
import vthread
from urllib import error
import json
from bottle import *
from cacheout import Cache
import queue
import threading
import shutil
from cacheout import LRUCache
from bs4 import BeautifulSoup



headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36',
    'Cookie': "******"
}
ROOT_PATH = r".\\"
DOWNLOAD_LIST_FILE_PATH = os.path.join(ROOT_PATH, r"downloadList.json")
DOWNLOAD_PATH = os.path.join(ROOT_PATH, r"download")
SERVER_FILE = os.path.join(ROOT_PATH, r"server")
CACHE_PATH = os.path.join(ROOT_PATH, r"cache")

if not os.path.exists(DOWNLOAD_LIST_FILE_PATH):
    print("List file not exit, creating ... ")
    json.dump({}, open(DOWNLOAD_LIST_FILE_PATH, 'w'))
download_list = json.load(open(DOWNLOAD_LIST_FILE_PATH))


class multhread_cache(object):
    def __init__(self):
        self.cache = LRUCache()

    def memoize(self, func):
        def new_func(*arg):
            if (func, *arg) not in self.cache:
                con = threading.Condition()
                self.cache.set((func, *arg), [False, con])
                result = func(*arg)
                self.cache.set((func, *arg), [True, result])
                con.acquire()
                con.notifyAll()
                con.release()
                return result
            else:
                stause = self.cache.get((func, *arg))
                if stause[0] == True:
                    return stause[1]
                else:
                    stause[1].acquire()
                    # print("waiting for notify")
                    stause[1].wait()
                    stause[1].release()
                    return self.cache.get((func, *arg))[1]
        return new_func


cache = multhread_cache()

class proxyAccessor:
    def __init__(self, root, headers):
        self.root = root
        self.headers = headers
        self.cache = Cache()

    @cache.memoize
    def getHTML_mostly_static(self, url):
        print("get html:\t["+urljoin(
            self.root, url)+"]\n")
        try:
            req = urllib.request.Request(url=urljoin(
                self.root, url), headers=self.headers)
            res = urllib.request.urlopen(req)
            html = res.read().decode('utf-8')
            print("get html:\t["+urljoin(
                self.root, url)+"] over\n")
            return html
        except Exception as e:
            return "Error"  # 获取网页错误

    def getHTML(self, url):  # 会出现同一时间 多次请求一同个网页 虽然设置缓存，但是第一次会失效
        return self.getHTML_mostly_static(url)

    def downloadFile(self, url, filePath, reWrite=False):
        if os.path.exists(filePath) and reWrite == False:
            print("文件存在")
            return
        try:
            urllib.request.urlretrieve(url, filename=filePath)
        except Exception as e:
            print("Error occurred when downloading\n", e, filePath,)

    @cache.memoize
    def getAllPages(self, url):  # 获取所有的页面 返回 [HTML...]
        htmlText = self.getHTML(url)
        soup = BeautifulSoup(htmlText, features="html.parser")
        result = [x.text for x in soup.select(
            'body > div:nth-child(6) > table > tr > td > a')]
        q = queue.Queue()
        allPages = [htmlText]
        @vthread.pool(5)
        def multThreadGetHtml(url, index):
            htmlText = self.getHTML(url)
            @vthread.atom
            def writeBack():
                allPages[index] = htmlText
            writeBack()
            q.put(0)
        if len(result) > 1:
            lastPage = int(result[-2])
            for i in range(1, lastPage):
                allPages.append("waiting")
                multThreadGetHtml(urljoin(url, "?p={}".format(i)), i)
            for i in range(1, lastPage):
                q.get()
        return allPages

    @cache.memoize
    def getPictureLinks(self, htmlText):  # 从当前HTML文本中解析可点击的浏览页面地址
        soup = BeautifulSoup(htmlText, features="html.parser")
        href = [x.get('href') for x in soup.select(
            'div.gdtm > div > a')]
        prevSrc = [x.get('style') for x in soup.select(
            'div.gdtm > div')]

        pattern = r'url([^)]+)'
        return [
            {
                "href": href[i],
                "src": re.findall(pattern, prevSrc[i])[0].replace("(", "")
            } for i in range(len(href))
        ]

    @cache.memoize
    def getAllPictureLinks(self, url):  # 得到画廊所有图片链接
        htmlTextS = self.getAllPages(url)
        result = []
        for html in htmlTextS:
            for data in self.getPictureLinks(html):
                result.append(data)
        return result

    @cache.memoize
    def getPictureRawSrc(self, pic_page_url):  # 页面URL 获取真实链接
        soup = BeautifulSoup(self.getHTML(pic_page_url),
                             features="html.parser")
        return soup.select("#img")[0].get('src')

    def geiMainPageGllarys(self, url):  # 获取主页的展示
        html = BeautifulSoup(self.getHTML(url), features="html.parser")
        infoS = []
        try:
            mainElem = html.select('div.gl1t')
            for elem in mainElem:
                name = elem.select('div.gl4t.glname.glink')[0].text
                href = elem.select('a:nth-child(1)')[0].get("href")
                imgSrc = elem.select('div.gl3t > a > img')[0].get("src")
                category = elem.select(
                    'div.gl5t > div:nth-child(1) > div:nth-child(1)')[0].text
                pages = elem.select(
                    'div.gl5t > div:nth-child(2) > div:nth-child(2)')[0].text
                lang = elem.select('div.gl6t > div')
                if len(lang) > 0:
                    lang = lang[0].text
                else:
                    lang = ""
                uploadTime = elem.select(
                    "div.gl5t > div > div:nth-child(2)")[0].text
                favo = elem.select(
                    'div.gl5t > div > div:nth-child(2)')[0].get("style") != None
                rankText = elem.select(
                    "div.gl5t > div:nth-child(2) > div:nth-child(1)")[0].get("style")
                rankText.replace("background-position:0px -21px;opacity:1", "")
                rankValue = re.findall("-?[0-9]+px -?[0-9]+px", rankText)[0]

                # # rank_a, rank_b = re.findall("-?[0-9]+px", rankText)
                # # rank_a = int(rank_a[:-2])
                # # rank_b = int(rank_b[:-2])
                # # rankValue = (5-int(rank_a / -16))*2
                # # if(rank_b == -21):  # -21半星
                # #     rankValue -= 1

                infoS.append({
                    "name": name,
                    "href": href.replace(self.root, "/"),
                    "imgSrc": imgSrc.replace((self.root+"t"), "https://ehgt.org"),
                    "category": category,
                    "pages": int(pages.replace(" pages", "")),
                    "lang": lang,
                    "downloaded": (href.split("/")[-3]+"_"+href.split("/")[-2] in download_list),
                    "gid_token": href.split("/")[-3]+"_"+href.split("/")[-2],
                    "favo": favo,  # 下载时钟为false
                    "uploadtime": uploadTime,  # 下载的无
                    "rank": rankValue
                })
        except Exception as e:
            print(e)
            return []
        return infoS

    @cache.memoize
    def getGdata(self, url):  # 只获取页面信息
        apiUrl = urljoin(self.root, "/api.php")
        gallaryUrl = urljoin(self.root, url)
        gid = int(gallaryUrl.split("/")[-3])
        token = gallaryUrl.split("/")[-2]
        post_Data = {
            "method": "gdata",
            "gidlist": [
                [gid, token]
            ],
            "namespace": 1
        }
        try:
            r = requests.post(apiUrl, data=json.dumps(
                post_Data), headers=self.headers)
            return r.json()["gmetadata"][0]
        except:
            print("error")
            return {}

    @cache.memoize
    def get_single_picture(self, url, index):  # 单个画廊的图片的 '链接'  应当为多线程执行或者事件驱动
        page_html = self.getHTML_mostly_static(
            "{}?p={}".format(url, index//40))
        pics = pa.getPictureLinks(page_html)
        request_page_url = pics[index % 40]["href"]
        return self.getPictureRawSrc(request_page_url)


pa = proxyAccessor("https://exhentai.org/", headers)


@route("/main/downloaded", methods="get")
def downloaded_gallarys():
    global download_list
    index = int(request.params.page)
    keys = [x for x in download_list.keys()]
    keys.sort(reverse=True)
    show_gallery = []
    start = index * 25
    end = start + 25
    if end > len(keys):
        end = len(keys)
    for key in keys[start:end]:
        g_data = download_list[key]
        title = g_data["title_jpn"]
        if g_data["title_jpn"] == "":
            title = g_data["title"]
        language = ""
        if "language:chinese" in g_data["tags"]:
            language = "chinese"

        show_gallery.append({
            "name": title,
            "href": "/g/{}/{}/".format(g_data["gid"], g_data["token"]),
            "imgSrc": "/img/{}/{}/?index=0".format(g_data["gid"], g_data["token"]),
            "category": g_data["category"],
            "pages": g_data["filecount"],
            "lang":  language,
            "downloaded": False,
            "favo": False,
            "uploadtime": "",
            "rank": 1
        })
    return json.dumps(show_gallery)


@route("/main/<path:path>", methods="get")
def gallaryList(path):
    parse_result = parse.urlparse(request.url)
    url = (parse_result.path+"?"+parse_result.query).replace("/main", ".")
    result = pa.geiMainPageGllarys(url)
    return json.dumps(result)


@route("/main/", methods="get")
def gallaryList():
    parse_result = parse.urlparse(request.url)
    url = ("?"+parse_result.query)
    result = pa.geiMainPageGllarys(url)
    return json.dumps(result)


@route('/g/<gid>/<token>/', methods='GET')
def g(gid, token):
    return static_file("viewing.html", root=SERVER_FILE)


@route('/profile/<gid>/<token>/', methods='GET')  # 加载画廊时 就去预加载所有页面 缓存一遍后不再重复加载
def profile(gid, token):
    download_flag = ("{}_{}".format(gid, token) in download_list)
    gdata = None
    if download_flag:
        gdata = download_list["{}_{}".format(gid, token)]
        print("profile 来自已下载的画廊")
    else:
        gdata = pa.getGdata("/g/{}/{}/".format(gid, token))

    info = {}
    for tagname in ['language', 'parody', 'group', 'artist', 'character', 'female', 'male', 'reclass', 'misc']:
        info[tagname] = []
    for tag_value in gdata["tags"]:
        if ":" in tag_value:
            tag, value = tag_value.split(":")
        else:
            tag, value = "misc", tag_value
        info[tag].append(value)

    info["fileName"] = gdata["title"]
    info["gallaryName"] = gdata["title_jpn"]
    if info["gallaryName"] == "":
        info["gallaryName"] = gdata["title"]
    info["gid"] = gdata["gid"]
    info["token"] = gdata["token"]
    info["filecount"] = int(gdata["filecount"])
    info["rating"] = gdata["rating"]
    info["cover"] = gdata["thumb"].replace((pa.root+"t"), "https://ehgt.org")
    if download_flag:
        info["cover"] = "/img/{}/{}/?index=0".format(
            gdata["gid"], gdata["token"]),
    return {"downloaded": download_flag, "stause": "ok", "info":  info}


@route('/img/<gid>/<token>/', methods="GET")  # ?index=[pagenumber]
def get_img(gid, token):
    if request.params.index == "":
        return None
    else:
        index = int(request.params.index)
        picName = "{}_{}_{}.jpg".format(gid, token, index)
        if os.path.exists(os.path.join(CACHE_PATH, picName)):
            print("缓存命中")
            return static_file("{}_{}_{}.jpg".format(gid, token, index), root=CACHE_PATH)
        download_dir = os.path.join(
            DOWNLOAD_PATH, "{}_{}".format(gid, token))
        if os.path.exists(os.path.join(download_dir, "{0:08d}.jpg".format(index+1))):
            print("已下载")
            return static_file("{0:08d}.jpg".format(index+1), root=download_dir)

        imgURL = pa.get_single_picture("/g/{}/{}/".format(gid, token), index)
        pa.downloadFile(imgURL, os.path.join(CACHE_PATH, picName))
        # redirect(imgURL)#EH跨域严格 不能直接用他的图片URL
        return static_file("{}_{}_{}.jpg".format(gid, token, index), root=CACHE_PATH)


class CheckImage(object):
    def __init__(self, img):
        self.exist_flag = True
        if not os.path.exists(img):
            self.exist_flag = False
            return
        with open(img, "rb") as f:
            f.seek(-2, 2)
            self.img_text = f.read()
            f.close()

    def check_jpg_jpeg(self):
        """检测jpg图片完整性，完整返回True，不完整返回False"""
        buf = self.img_text
        return buf.endswith(b'\xff\xd9')

    def check_png(self):
        """检测png图片完整性，完整返回True，不完整返回False"""
        buf = self.img_text
        return buf.endswith(b'\xaeB`\x82')

    def getCheck(self):
        if self.exist_flag == False:
            return False
        else:
            return self.check_png() or self.check_jpg_jpeg()


@route('/download/<gid>/<token>/')
def download(gid, token):  # 添加到下载记录文件中 如果已经存在，则检查完整性 出错重新下载 尝试次数限制
    print("下载")
    key = "{}_{}".format(gid, token)
    download_list[key] = pa.getGdata(
        "/g/{}/{}/".format(gid, token))  # 无论下载完成与否 都存入(更新)画廊信息
    if len(download_list[key]) == {}:
        print("g_data请求失败")
        download_list.pop(key)
        json.dump(download_list, open(
            DOWNLOAD_LIST_FILE_PATH, 'w'))
        return "network_error"

    json.dump(download_list, open(
        DOWNLOAD_LIST_FILE_PATH, 'w'))

    download_dir = os.path.join(
        DOWNLOAD_PATH, "{}_{}".format(gid, token))
    print("下载目录{}".format(download_dir))
    if not os.path.exists(download_dir):  # 不存在创建
        os.makedirs(download_dir)
    check_pass = True
    if key in download_list:
        for index in range(int(download_list[key]["filecount"])):
            download_file = os.path.join(
                download_dir, "{0:08d}.jpg".format(index+1))  # 正式下载 从1开始
            if CheckImage(download_file).getCheck() == False:
                check_pass = False
                print("{}检查未通过".format(download_file))
                break
    else:
        check_pass = False
    if check_pass == True:
        print("检查通过 无需重新下载")
        return "check_pass"
    else:
        print("正在下载")
        for index in range(int(download_list[key]["filecount"])):  # 先查询缓存
            cache_file = os.path.join(
                CACHE_PATH, "{}_{}_{}.jpg".format(gid, token, index))
            download_file = os.path.join(
                download_dir, "{0:08d}.jpg".format(index+1))  # 正式下载 从1开始
            if os.path.exists(cache_file):
                print("已经缓存{}".format(cache_file))
                shutil.copy(cache_file, download_file)
        all_img = pa.getAllPictureLinks("/g/{}/{}/".format(gid, token))

        stause = {}
        @vthread.pool(8)
        def download_thread(index):
            download_file = os.path.join(
                download_dir, "{0:08d}.jpg".format(index+1))  # 正式下载 从1开始
            imgdata = all_img[index]
            errorCount = 0
            # 检查不通过 则尝试下载三次   已经保存缓存or下载成功
            while CheckImage(download_file).getCheck() == False:
                pa.downloadFile(pa.getPictureRawSrc(
                    imgdata["href"]), download_file)
                stause[index] = True
                print("下载{} => {}".format(imgdata["href"], download_file))
                errorCount += 1
                if errorCount == 3:
                    print("达到最大尝试次数 下载失败")
                    stause[index] = False
                    break

        for index in range(len(all_img)):
            download_thread(index)

    return json.dumps(stause)


@route('/delete_downloaded/<gid>/<token>/')
def delete_downloaded(gid, token):
    key = "{}_{}".format(gid, token)
    print("请求删除{}".format(key))
    if key not in download_list:
        print("未下载")
        return "success"
    else:
        try:
            print("删除{}".format(key))
            download_list.pop(key)
            json.dump(download_list, open(
                DOWNLOAD_LIST_FILE_PATH, 'w'))
            download_dir = os.path.join(
                DOWNLOAD_PATH, "{}_{}".format(gid, token))
            shutil.rmtree(download_dir)
        except Exception as e:
            return str(e)
        return "success"


@route('/')
@route('/watched')
@route('/popular')
@route('/downloaded')
def data_js():
    return static_file("index.html", root=SERVER_FILE)


@route('/<path:path>')
def server_post(path):
    return static_file(path, root=SERVER_FILE)


if __name__ == '__main__':
    run(host='0.0.0.0', port=8080, reloader=False, server='paste')
    # print(pa.getAllPages("/g/1811756/c38a3e6026/"))
    # for htmltext in pa.getAllPages("/g/1811756/c38a3e6026/"):
    #     # print(htmltext)
    #     print(pa.getPictureLinks(htmltext))
    # print(pa.getPictureRawSrc("/s/74f348a42c/1811756-2"))
    # res = pa.geiMainPageGllarys(
    #     "?f_search=%5BPixiv%5D+Lolicept+%7C+Belko+%5B39123643%5D")
    # for r in res:
    #     print(r)
