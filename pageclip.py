"""粘贴网址，将网页保存为 Markdown。运行本文件打开窗口。"""

from pathlib import Path
from queue import Empty, Queue
import re
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from markdownify import markdownify
import requests


def html_to_markdown(html, url):
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("h1") or soup.title
    title = title_tag.get_text(" ", strip=True) if title_tag else "网页内容"
    base = soup.find("base", href=True)
    base_url = urljoin(url, base["href"]) if base else url
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    # 优先提取正文；没有语义标签时保留整个页面内容。
    content = soup.find("article") or soup.find("main") or soup.body or soup
    for image in content.find_all("img"):
        source = image.get("data-src") or image.get("src")
        if source:
            image["src"] = urljoin(base_url, source)
    for link in content.find_all("a", href=True):
        link["href"] = urljoin(base_url, link["href"])
    markdown = markdownify(
        str(content), heading_style="ATX", bullets="-",
        keep_inline_images_in=["h1", "h2", "h3", "h4", "h5", "h6", "td", "th"],
    ).strip()
    if not content.find("h1"):
        markdown = f"# {title}\n\n{markdown}"
    return title, f"{markdown}\n\n---\n\n来源：<{url}>\n"


def fetch_article(url):
    url = url.strip()
    if not url:
        raise ValueError("请先粘贴网址。")
    if "://" not in url:
        url = "https://" + url
    if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).netloc:
        raise ValueError("请输入有效的 HTTP 或 HTTPS 网址。")
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    response.raise_for_status()
    # 无 HTTP 编码声明时，让解析器读取 HTML 的编码声明。
    encoding = requests.utils.get_encoding_from_headers(response.headers)
    if encoding and "charset=" in response.headers.get("Content-Type", "").lower():
        html = response.content.decode(encoding, errors="replace")
    else:
        html = response.content
    return html_to_markdown(html, response.url)


class App:
    def __init__(self, root):
        self.root = root
        self.results = Queue()
        self.title = "网页内容"
        self.busy = False
        root.title("网页保存为 Markdown")
        root.geometry("800x600")
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="网址").pack(anchor="w")
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(4, 10))
        self.url = ttk.Entry(row)
        self.url.pack(side="left", fill="x", expand=True)
        self.url.bind("<Return>", lambda event: self.fetch())
        self.fetch_button = ttk.Button(row, text="抓取", command=self.fetch)
        self.fetch_button.pack(side="left", padx=(8, 0))
        ttk.Label(frame, text="Markdown 预览（可直接编辑；图片以网络链接保存）").pack(anchor="w")
        self.preview = ScrolledText(frame, wrap="word", font=("Consolas", 11))
        self.preview.pack(fill="both", expand=True, pady=6)
        self.save_button = ttk.Button(frame, text="另存为 Markdown…", command=self.save, state="disabled")
        self.save_button.pack(anchor="e")
        self.status = tk.StringVar(value="粘贴网址，点击“抓取”或按回车。")
        ttk.Label(frame, textvariable=self.status, wraplength=740).pack(anchor="w", pady=(8, 0))
        self.url.focus_set()
        root.after(100, self.poll)

    def fetch(self):
        if self.busy:
            return
        url = self.url.get().strip()
        if not url:
            messagebox.showinfo("请输入网址", "请先粘贴要抓取的网址。")
            return
        self.busy = True
        self.fetch_button.config(state="disabled")
        self.status.set("正在抓取…")
        Thread(target=self.worker, args=(url,), daemon=True).start()

    def worker(self, url):
        # 后台线程只请求网页；所有窗口操作都留在主线程。
        try:
            self.results.put((fetch_article(url), None))
        except Exception as error:
            self.results.put((None, str(error)))

    def poll(self):
        try:
            result, error = self.results.get_nowait()
        except Empty:
            pass
        else:
            self.busy = False
            self.fetch_button.config(state="normal")
            if error:
                self.status.set("抓取失败，请检查网址或网络后重试。")
                messagebox.showerror("抓取失败", error)
            else:
                self.title, markdown = result
                self.preview.delete("1.0", "end")
                self.preview.insert("1.0", markdown)
                self.save_button.config(state="normal")
                self.status.set("抓取完成，可编辑内容后另存为 .md 文件。")
        self.root.after(100, self.poll)

    def save(self):
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", self.title)[:100].strip(" .") or "网页内容"
        path = filedialog.asksaveasfilename(
            title="保存 Markdown", initialfile=f"{name}.md",
            defaultextension=".md", filetypes=[("Markdown 文件", "*.md")],
        )
        if not path:
            return
        try:
            Path(path).write_text(self.preview.get("1.0", "end-1c"), encoding="utf-8")
        except OSError as error:
            messagebox.showerror("保存失败", str(error))
        else:
            self.status.set(f"已保存：{path}")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
