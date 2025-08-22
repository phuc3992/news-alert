import feedparser
import yagmail
import hashlib
import os
import time
import requests
from newspaper import Article

# ĐỌC TỪ ENV (Secrets GitHub)
openrouter_api_key = os.getenv("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")  # KHÔNG hardcode
your_email = os.getenv("phungmanhphuc@gmail.com")
your_app_password = os.getenv("oktv iykw igma vmti")
to_email = os.getenv("phungmanhphuc@gmail.com", your_email)

# Danh sách RSS (giữ nguyên của bạn)
rss_feeds = [
    "https://vnexpress.net/rss/tin-moi-nhat.rss",
    "https://vnexpress.net/rss/thoi-su.rss",
    "https://vnexpress.net/rss/kinh-doanh.rss",
    "https://vnexpress.net/rss/phap-luat.rss",
    "https://vnexpress.net/rss/the-gioi.rss",
    "https://vnexpress.net/rss/giai-tri.rss",
    "https://vnexpress.net/rss/suc-khoe.rss",
    "https://vnexpress.net/rss/giao-duc.rss",
    "https://vnexpress.net/rss/du-lich.rss",
    "https://cafef.vn/rss/tin-moi-nhat.rss",
    "https://cafef.vn/rss/thoi-su.rss",
    "https://cafef.vn/rss/kinh-te.rss",
    "https://cafef.vn/rss/phap-luat.rss",
    "https://dantri.com.vn/rss/tin-moi-nhat.rss",
    "https://dantri.com.vn/rss/su-kien.rss",
    "https://dantri.com.vn/rss/xa-hoi.rss",
    "https://dantri.com.vn/rss/phap-luat.rss",
    "https://vietnamnet.vn/rss/tin-moi-nhat.rss",
    "https://vietnamnet.vn/rss/thoi-su.rss",
    "https://vietnamnet.vn/rss/phap-luat.rss",
    "https://tuoitre.vn/rss/tin-moi-nhat.rss",
    "https://tuoitre.vn/rss/thoi-su.rss",
    "https://tuoitre.vn/rss/phap-luat.rss",
    "https://laodong.vn/rss/tin-moi-nhat.rss",
    "https://laodong.vn/rss/thoi-su.rss",
    "https://laodong.vn/rss/phap-luat.rss",
    "https://baodansinh.vn/rss/tin-moi-nhat.rss",
    "https://baodansinh.vn/rss/thoi-su.rss",
    "https://baodansinh.vn/rss/phap-luat.rss",
    "https://thanhnien.vn/rss/viet-nam.rss",
    "https://thanhnien.vn/rss/thoi-su.rss",
    "https://thanhnien.vn/rss/phap-luat.rss",
    "https://vov.vn/rss/tin-moi-nhat.rss",
    "https://vov.vn/rss/thoi-su-1.rss",
    "https://vov.vn/rss/phap-luat-5.rss",
    "https://nhandan.vn/rss/tin-moi-nhat.rss",
    "https://nhandan.vn/rss/thoi-su.rss",
    "https://nhandan.vn/rss/phap-luat.rss",
]

group1 = ["công ty", "doanh nghiệp", "vietinbank"]
group2 = ["truy tố", "khởi tố", "tạm giam", "phá sản", "bị bắt", "qua đời", "bỏ trốn"]
group3 = [
    "Yên Bái", "Bắc Kạn", "Tuyên Quang", "Lào Cai", "Lai Châu", "Điện Biên", "Cao Bằng", "Sơn La", "Hà Giang", "Lạng Sơn",
    "Thái Nguyên", "Phú Thọ", "Vĩnh Phúc", "Hòa Bình", "Bắc Giang", "Bắc Ninh", "Thái Bình", "Nam Định", "Hà Nam", "Ninh Bình",
    "Thanh Hóa", "Nghệ An", "Hà Tĩnh", "Quảng Bình", "Quảng Trị"
]

sent_hashes_file = "sent_hashes.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
}

def match_3_groups(title, summary, g1, g2, g3):
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

def save_sent_hash(hash_str):
    with open(sent_hashes_file, "a", encoding="utf-8") as f:
        f.write(hash_str + "\n")

def ai_summarize(text, max_sentences=10):
    api_key = openrouter_api_key
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    prompt = (
        f"Tóm tắt nội dung sau thành khoảng {max_sentences} câu, giữ lại các ý chính, ngắn gọn, dễ hiểu, bằng tiếng Việt:\n\n{text}\n\nTóm tắt:"
    )
    data = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800
    }
    try:
        r = requests.post(url, headers=headers, json=data, timeout=45)
        if r.status_code == 200:
            result = r.json()
            return result["choices"][0]["message"]["content"].strip()
        else:
            print("Lỗi OpenRouter:", r.status_code, r.text[:200])
            return "Không tóm tắt được bằng AI."
    except Exception as e:
        print("Lỗi khi gọi OpenRouter:", e)
        return "Không tóm tắt được bằng AI."

def summarize_article_ai(url, max_sentences=10):
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

def parse_rss_with_headers(feed_url):
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception as e:
        print(f"  Lỗi tải RSS {feed_url}: {e}")
        return None

def main():
    print("Bắt đầu quét tin tức...")

    # Kết nối Gmail qua STARTTLS
    try:
        yag = yagmail.SMTP(
            user=your_email,
            password=your_app_password,
            host="smtp.gmail.com",
            port=587,
            smtp_starttls=True,
            smtp_ssl=False
        )
        print("Kết nối Gmail thành công!")
    except Exception as e:
        print(f"Lỗi kết nối Gmail: {e}")
        return

    sent_hashes = load_sent_hashes()
    print(f"Đã tải {len(sent_hashes)} bài đã gửi trước đó.")

    for i, feed_url in enumerate(rss_feeds, 1):
        print(f"Đang quét RSS {i}/{len(rss_feeds)}: {feed_url}")
        feed = parse_rss_with_headers(feed_url)
        if not feed or not getattr(feed, "entries", None):
            print("  Không có bài viết nào từ RSS này.")
            continue

        for entry in feed.entries:
            title = entry.title
            summary = entry.summary if hasattr(entry, "summary") else ""
            link = entry.link

            hash_str = hashlib.md5((title + summary).encode("utf-8")).hexdigest()
            if hash_str in sent_hashes:
                continue

            if match_3_groups(title, summary, group1, group2, group3):
                print(f"  Tìm thấy bài phù hợp: {title}")
                print("  Đang tóm tắt nội dung bằng AI...")
                article_summary = summarize_article_ai(link, max_sentences=10)

                subject = f'KTKSNB CẬP NHẬT - "{title}"'
                body = f"""Kính gửi: Anh/Chị,
Tổ hiện đại hóa phòng KTKSNB kính gửi anh chị thông tin của bài báo: "{title}"
Link bài báo: {link}
Tóm tắt:
{article_summary}
"""
                try:
                    yag.send(to_email, subject, body)
                    print("  ✓ Đã gửi cảnh báo thành công!")
                    save_sent_hash(hash_str)
                    sent_hashes.add(hash_str)
                except Exception as e:
                    print(f"  ✗ Lỗi gửi email: {e}")

        time.sleep(0.5)

    print("Hoàn thành quét tin tức!")

if __name__ == "__main__":
    main()