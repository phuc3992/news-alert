import os
import time
import hashlib
import requests
import feedparser
import smtplib
from email.mime.text import MIMEText
from newspaper import Article

# ================== ENV CONFIG (KHÔNG hardcode) ==================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")           # sk-or-...
EMAIL_USER         = os.getenv("EMAIL_USER")                    # ví dụ: you@gmail.com
EMAIL_PASS         = os.getenv("EMAIL_PASS")                    # Gmail App Password 16 ký tự
EMAIL_TO           = os.getenv("EMAIL_TO", EMAIL_USER)          # có thể trùng EMAIL_USER

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
    # CafeF
    "https://cafef.vn/rss/tin-moi-nhat.rss",
    "https://cafef.vn/rss/thoi-su.rss",
    "https://cafef.vn/rss/kinh-te.rss",
    "https://cafef.vn/rss/phap-luat.rss",
    # Dân Trí
    "https://dantri.com.vn/rss/tin-moi-nhat.rss",
    "https://dantri.com.vn/rss/su-kien.rss",
    "https://dantri.com.vn/rss/xa-hoi.rss",
    "https://dantri.com.vn/rss/phap-luat.rss",
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
    # Đời sống & Pháp luật
    "https://baodansinh.vn/rss/tin-moi-nhat.rss",
    "https://baodansinh.vn/rss/thoi-su.rss",
    "https://baodansinh.vn/rss/phap-luat.rss",
    # Thanh Niên
    "https://thanhnien.vn/rss/viet-nam.rss",
    "https://thanhnien.vn/rss/thoi-su.rss",
    "https://thanhnien.vn/rss/phap-luat.rss",
    # VOV
    "https://vov.vn/rss/tin-moi-nhat.rss",
    "https://vov.vn/rss/thoi-su-1.rss",
    "https://vov.vn/rss/phap-luat-5.rss",
    # Nhân Dân
    "https://nhandan.vn/rss/tin-moi-nhat.rss",
    "https://nhandan.vn/rss/thoi-su.rss",
    "https://nhandan.vn/rss/phap-luat.rss",
]

# ================== KEYWORD GROUPS ==================
group1 = ["công ty", "doanh nghiệp", "vietinbank"]
group2 = ["truy tố", "khởi tố", "tạm giam", "phá sản", "bị bắt", "qua đời", "bỏ trốn"]
group3 = [
    "Yên Bái", "Bắc Kạn", "Tuyên Quang", "Lào Cai", "Lai Châu", "Điện Biên", "Cao Bằng", "Sơn La", "Hà Giang", "Lạng Sơn",
    "Thái Nguyên", "Phú Thọ", "Vĩnh Phúc", "Hòa Bình", "Bắc Giang", "Bắc Ninh", "Thái Bình", "Nam Định", "Hà Nam", "Ninh Bình",
    "Thanh Hóa", "Nghệ An", "Hà Tĩnh", "Quảng Bình", "Quảng Trị"
]

# ================== STATE ==================
sent_hashes_file = "sent_hashes.txt"

# ================== HEADERS ==================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
}

# ------------------ Utils ------------------
def match_3_groups(title: str, summary: str, g1, g2, g3) -> bool:
    text = (title + " " + summary).lower()
    return (
        any(kw.lower() in text for kw in g1) and
        any(kw.lower() in text for kw in g2) and
        any(kw.lower() in text for kw in g3)
    )

def load_sent_hashes():
    if not os.path.exists(sent_hashes_file):
        return set()
    with open(sent_hashes_file, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_sent_hash(hash_str: str):
    with open(sent_hashes_file, "a", encoding="utf-8") as f:
        f.write(hash_str + "\n")

def ai_summarize(text: str, max_sentences: int = 10) -> str:
    """
    Tóm tắt bằng OpenRouter. Nếu lỗi, trả thông báo ngắn để email vẫn gửi được.
    """
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
        "temperature": 0.2
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

def parse_rss_with_headers(feed_url: str):
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception as e:
        print(f"  Lỗi tải RSS {feed_url}: {e}")
        return None

# ------------------ Email (SMTP) ------------------
def send_email_smtp(subject: str, body: str, to_addr: str):
    """
    Gửi email bằng SMTP chuẩn của Gmail.
    Yêu cầu:
      - EMAIL_USER: địa chỉ Gmail
      - EMAIL_PASS: App Password 16 ký tự (không phải mật khẩu đăng nhập)
    """
    if not EMAIL_USER or not EMAIL_PASS:
        raise RuntimeError("Thiếu EMAIL_USER/EMAIL_PASS trong ENV.")

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = to_addr

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)

# ------------------ Main ------------------
def main():
    print("Bắt đầu quét tin tức...")

    if not EMAIL_USER or not EMAIL_PASS:
        print("Thiếu EMAIL_USER/EMAIL_PASS trong ENV. Dừng.")
        return

    sent_hashes = load_sent_hashes()
    print(f"Đã tải {len(sent_hashes)} bài đã gửi trước đó (chỉ hiệu lực trong lần chạy này).")

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

            hash_str = hashlib.md5((title + summary).encode("utf-8")).hexdigest()
            if hash_str in sent_hashes:
                continue

            if match_3_groups(title, summary, group1, group2, group3):
                print(f"  Tìm thấy bài phù hợp: {title}")
                print("  Đang tóm tắt nội dung bằng AI...")
                article_summary = summarize_article_ai(link, max_sentences=10)

                subject = f'KTKSNB CẬP NHẬT - "{title}"'
                body = f"""Kính gửi: Anh/Chị,

Tổ hiện đại hóa phòng KTKSNB kính gửi anh/chị thông tin bài báo:
"{title}"

Link bài báo: {link}

Tóm tắt:
{article_summary}
"""
                try:
                    send_email_smtp(subject, body, EMAIL_TO)
                    print("  ✓ Đã gửi cảnh báo thành công!")
                    save_sent_hash(hash_str)
                    sent_hashes.add(hash_str)
                except Exception as e:
                    print(f"  ✗ Lỗi gửi email: {e}")

        time.sleep(PER_FEED_DELAY_SEC)

    print("Hoàn thành quét tin tức!")

if __name__ == "__main__":
    main()