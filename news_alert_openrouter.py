import os
import time
import hashlib
import requests
import feedparser
import smtplib
from email.mime.text import MIMEText
from newspaper import Article
import re

# ================== ENV CONFIG ==================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
EMAIL_USER         = os.getenv("EMAIL_USER")            # ví dụ: you@gmail.com
EMAIL_PASS         = os.getenv("EMAIL_PASS")            # Gmail App Password 16 ký tự
EMAIL_TO           = os.getenv("EMAIL_TO", EMAIL_USER)  # có thể là "a@x.com,b@y.com,c@z.com"

def parse_recipients(value: str):
    # Tách theo dấu phẩy, bỏ khoảng trắng và lọc trống
    return [e.strip() for e in (value or "").split(",") if e.strip()]

# Gist để lưu hash bài đã gửi (tránh gửi lặp)
GIST_TOKEN = os.getenv("GIST_TOKEN")                    # GitHub PAT (scope: gist)
GIST_ID    = os.getenv("GIST_ID")                       # ID của Gist
GIST_FILE  = "sent_hashes.txt"                          # tên file trong Gist

PER_FEED_DELAY_SEC = 0.5

# ================== RSS FEEDS ==================
rss_feeds = [
    # VnExpress
    "https://vnexpress.net/rss/tin-moi-nhat.rss",
    "https://vnexpress.net/rss/thoi-su.rss",
    "https://vnexpress.net/rss/kinh-doanh.rss",
    "https://vnexpress.net/rss/phap-luat.rss",
    "https://vnexpress.net/rss/the-gioi.rss",
    "https://vnexpress.net/rss/giai-tri.rss",
    "https://vnexpress.net/rss/suc-khoe.rss",
    "https://vnexpress.net/rss/giao-duc.rss",
    "https://vnexpress.net/rss/du-lich.rss",

    # Dân Trí
    "https://dantri.com.vn/rss/tin-moi-nhat.rss",
    "https://dantri.com.vn/rss/xa-hoi.rss",
    "https://dantri.com.vn/rss/phap-luat.rss",
    "https://dantri.com.vn/rss/kinh-doanh.rss",

    # Vietnamnet
    "https://vietnamnet.vn/rss/tin-moi-nhat.rss",
    "https://vietnamnet.vn/rss/thoi-su.rss",
    "https://vietnamnet.vn/rss/phap-luat.rss",

    # Tuổi Trẻ
    "https://tuoitre.vn/rss/tin-moi-nhat.rss",
    "https://tuoitre.vn/rss/thoi-su.rss",
    "https://tuoitre.vn/rss/phap-luat.rss",

    # Lao Động
    "https://laodong.vn/rss/tin-moi-nhat.rss",
    "https://laodong.vn/rss/thoi-su.rss",
    "https://laodong.vn/rss/phap-luat.rss",

    # Thanh Niên
    "https://thanhnien.vn/rss/thoi-su.rss",
    "https://thanhnien.vn/rss/thoi-su/phap-luat.rss",
    "https://thanhnien.vn/rss/kinh-te.rss",

    # VOV
    "https://vov.vn/rss/tin-moi-nhat.rss",
    "https://vov.vn/rss/thoi-su-1.rss",
    "https://vov.vn/rss/phap-luat-5.rss",

    # Nhân Dân
    "https://nhandan.vn/rss/tin-moi-nhat.rss",
    "https://nhandan.vn/rss/thoi-su.rss",
    "https://nhandan.vn/rss/phap-luat.rss",

    # CafeF
    "https://cafef.vn/xa-hoi.rss",

    # Bổ sung theo yêu cầu
    # Người Lao Động
    "https://nld.com.vn/rss/home.rss",
    "https://nld.com.vn/rss/phap-luat.rss",
    # Tiền Phong
    "https://tienphong.vn/rss/xa-hoi-2.rss",
    "https://tienphong.vn/rss/phap-luat-12.rss",
    # VnEconomy
    "https://vneconomy.vn/feed",
    # Báo Chính Phủ
    "https://baochinhphu.vn/rss/home.rss",
    "https://baochinhphu.vn/xa-hoi/phap-luat.rss"
    ,
]

# ================== KEYWORD GROUPS ==================
group1 = ["công ty", "doanh nghiệp", "vietinbank", "Chủ tịch", "Bí thư"]
group2 = [
    "truy tố", "khởi tố", "tạm giam", "phá sản", "bị bắt", "qua đời", "bỏ trốn", "lừa đảo",
    "khám xét", "đánh bạc"
]
# Yêu cầu mới: bỏ nhóm 3 (không lọc theo địa phương)
# => chỉ lọc theo group1 & group2

# ================== HEADERS ==================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
}

# ============= Persist hashes qua GitHub Gist =============
def _gist_headers():
    if not GIST_TOKEN:
        raise RuntimeError("Thiếu GIST_TOKEN (ENV).")
    return {
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def load_sent_hashes():
    if not GIST_ID or not GIST_TOKEN:
        print("Cảnh báo: không có GIST_ID/GIST_TOKEN -> chỉ nhớ local (nếu có).")
        if os.path.exists("sent_hashes.txt"):
            with open("sent_hashes.txt", "r", encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        return set()
    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        r = requests.get(url, headers=_gist_headers(), timeout=30)
        r.raise_for_status()
        data = r.json()
        files = data.get("files", {})
        content = files.get(GIST_FILE, {}).get("content", "")
        hashes = set(line.strip() for line in content.splitlines() if line.strip())
        print(f"Nạp {len(hashes)} hash từ Gist.")
        return hashes
    except Exception as e:
        print(f"Cảnh báo: không tải được Gist: {e}. Sẽ dùng file local tạm.")
        if os.path.exists("sent_hashes.txt"):
            with open("sent_hashes.txt", "r", encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        return set()

def save_sent_hash(hash_str: str, current_hashes: set):
    current_hashes.add(hash_str)
    try:
        with open("sent_hashes.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(current_hashes)))
    except Exception:
        pass
    if not GIST_ID or not GIST_TOKEN:
        return
    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        new_content = "\n".join(sorted(current_hashes))
        payload = {"files": {GIST_FILE: {"content": new_content}}}
        r = requests.patch(url, headers=_gist_headers(), json=payload, timeout=30)
        r.raise_for_status()
        print("Đã cập nhật Gist với hash mới.")
    except Exception as e:
        print(f"Cảnh báo: không ghi được Gist: {e}")

# ------------------ Lọc điều kiện ------------------
def match_groups(title: str, summary: str, g1, g2) -> bool:
    text = (title + " " + summary).lower()
    return (
        any(kw.lower() in text for kw in g1) and
        any(kw.lower() in text for kw in g2)
    )

# ------------------ Tóm tắt AI ------------------
def ai_summarize(text: str, max_sentences: int = 10) -> str:
    if not OPENROUTER_API_KEY:
        return "Không có OPENROUTER_API_KEY (ENV). Bỏ qua tóm tắt AI."

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    prompt = (
        f"Bạn là biên tập viên báo Việt. Tóm tắt nội dung dưới đây bằng tiếng Việt, ngắn gọn khoảng {max_sentences} câu, "
        f"giữ số liệu và tên riêng:\n\n{text}\n\nTóm tắt:"
    )
    data = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800,
        "temperature": 0.2,
    }
    try:
        r = requests.post(url, headers=headers, json=data, timeout=45)
        if r.status_code == 200:
            js = r.json()
            return js["choices"][0]["message"]["content"].strip()
        else:
            return f"Không tóm tắt được bằng AI (HTTP {r.status_code})."
    except Exception as e:
        return f"Không tóm tắt được bằng AI ({e})."

def summarize_article_ai(url: str, max_sentences: int = 10) -> str:
    try:
        article = Article(url)
        article.download()
        article.parse()
        text = (article.text or "").strip()
        if not text:
            return "Không lấy được nội dung chi tiết."
        return ai_summarize(text, max_sentences=max_sentences)
    except Exception:
        return "Không lấy được nội dung chi tiết."

# ------------------ RSS ------------------
def parse_rss_with_headers(feed_url: str):
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception as e:
        print(f"  Lỗi tải RSS {feed_url}: {e}")
        return None

# ------------------ Email (sanitize + template + gửi) ------------------
def sanitize_summary(raw: str) -> str:
    """
    Làm sạch văn bản tóm tắt AI để tránh bị gạch ngang và lỗi hiển thị:
    - Bỏ [BOT] [/BOT], đường gạch phân cách (---, ___, ===), thẻ <s>/<strike>
    - Nếu đa số dòng dạng bullet/numbered -> render <ol><li>…</li></ol>
    - Escape các ký tự HTML đặc biệt khi cần
    """
    if not raw:
        return ""
    text = raw.strip()

    # Bỏ marker [BOT]
    text = re.sub(r'\[/?BOT\]', '', text, flags=re.IGNORECASE).strip()

    # Bỏ các đường gạch phân cách dài
    text = re.sub(r'^\s*[-=_]{3,}\s*$', '', text, flags=re.MULTILINE)

    # Bỏ thẻ s/strike
    text = re.sub(r'</?\s*(s|strike)\s*>', '', text, flags=re.IGNORECASE)

    # Phân tích dòng
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    bullet_like = sum(1 for l in lines if re.match(r'^(\d+\.\s+|[-•]\s+)', l))

    def html_escape(s: str) -> str:
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    if lines and bullet_like >= max(2, len(lines)//2):
        normalized = []
        for l in lines:
            l = re.sub(r'^(\d+\.\s+|[-•]\s+)', '', l).strip()
            normalized.append(html_escape(l))
        items = ''.join(
            f'<li style="margin:4px 0; text-decoration:none;">{l}</li>' for l in normalized
        )
        return f'<ol style="margin:6px 0 0 20px; padding:0; text-decoration:none;">{items}</ol>'

    # Không phải bullet: escape và đổi \n -> <br/>
    safe = html_escape(text)
    return safe.replace('\n', '<br/>')

def template_subject(title: str) -> str:
    # Bạn có thể đổi tiêu đề tại đây
    return f'THỜI BÁO KTKSNB - "{title}"'

def template_body(title: str, link: str, article_summary: str) -> str:
    # Làm sạch tóm tắt và ép style chống gạch ngang
    safe_summary = sanitize_summary(article_summary)
    return f"""
<div style="font-family: Arial, Helvetica, sans-serif; font-size: 15px; line-height: 1.6; color: #111; text-decoration: none;">
  <style>
    /* Một số client bỏ qua <style>, nhưng vẫn thêm để phòng */
    * {{ text-decoration: none !important; }}
    a {{ color: #1155cc; }}
  </style>

  <p style="text-decoration:none;"><em><strong>Kính gửi:</strong> Anh/Chị,</em></p>

  <p style="text-decoration:none;">Tổ hiện đại hóa phòng KTKSNB kính gửi anh/chị thông tin bài báo:
     <strong>"{title}"</strong>
  </p>

  <p style="text-decoration:none;"><em><strong>Link bài báo:</strong></em><br/>
     <a href="{link}" target="_blank" rel="noopener noreferrer" style="text-decoration:none;">{link}</a>
  </p>

  <p style="text-decoration:none;"><em><strong>Tóm tắt:</strong></em></p>
  <div style="text-decoration:none;">{safe_summary}</div>

  <p style="text-decoration:none;">Chúc Anh/Chị ngày làm việc hiệu quả 😊</p>
</div>
"""

def send_email_smtp_html(subject: str, html_body: str, to_addrs, bcc_addrs=None):
    """
    Gửi email HTML với BCC để ẩn danh sách người nhận.
    - to_addrs: list người nhận hiển thị (có thể để [])
    - bcc_addrs: list người nhận ẩn (thực tế sẽ được gửi tới)
    """
    if not EMAIL_USER or not EMAIL_PASS:
        raise RuntimeError("Thiếu EMAIL_USER/EMAIL_PASS trong ENV.")

    to_addrs = to_addrs or []
    bcc_addrs = bcc_addrs or []

    msg = MIMEText(html_body, "html", _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = ", ".join(to_addrs)
    if bcc_addrs:
        msg["Bcc"] = ", ".join(bcc_addrs)

    rcpt_list = list(set(to_addrs + bcc_addrs))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, rcpt_list, msg.as_string())

# ------------------ Main ------------------
def main():
    print("Bắt đầu quét tin tức...")
    if not EMAIL_USER or not EMAIL_PASS:
        print("Thiếu EMAIL_USER/EMAIL_PASS trong ENV. Dừng.")
        return

    sent_hashes = load_sent_hashes()
    print(f"Đã tải {len(sent_hashes)} hash bài đã gửi trước đó.")

    recipients = parse_recipients(EMAIL_TO)
    print(f"Sẽ gửi BCC tới {len(recipients)} người nhận.")

    for i, feed_url in enumerate(rss_feeds, 1):
        print(f"Đang quét RSS {i}/{len(rss_feeds)}: {feed_url}")
        feed = parse_rss_with_headers(feed_url)
        if not feed or not getattr(feed, "entries", None):
            print("  Không có bài viết nào từ RSS này.")
            continue

        for entry in feed.entries:
            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "")
            link = getattr(entry, "link", "")

            if not title or not link:
                continue

            # Dùng link làm khóa duy nhất
            hash_str = hashlib.md5(link.encode("utf-8")).hexdigest()
            if hash_str in sent_hashes:
                continue

            if match_groups(title, summary, group1, group2):
                print(f"  Tìm thấy bài phù hợp: {title}")
                print("  Đang tóm tắt nội dung bằng AI...")
                article_summary = summarize_article_ai(link, max_sentences=10)

                subject = template_subject(title)
                html_body = template_body(title, link, article_summary)

                try:
                    # To để trống (hoặc đặt 1 địa chỉ chung nếu muốn), gửi thật qua BCC
                    send_email_smtp_html(subject, html_body, to_addrs=[], bcc_addrs=recipients)
                    print("  ✓ Đã gửi cảnh báo thành công!")
                    save_sent_hash(hash_str, sent_hashes)
                except Exception as e:
                    print(f"  ✗ Lỗi gửi email: {e}")

        time.sleep(PER_FEED_DELAY_SEC)

    print("Hoàn thành quét tin tức!")

if __name__ == "__main__":
    main()
