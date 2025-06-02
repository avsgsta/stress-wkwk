from flask import Flask, request, jsonify
import time
import pandas as pd
import torch
import pickle
import re
import gdown
import os
from transformers import AutoTokenizer
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

app = Flask(__name__)

# 🔄 Download Model jika belum ada
FILE_ID = "1--lgnyJervVJXzYNS-Fv5xrgy6EdVBkp"
MODEL_PATH = "saved_re_train.pkl"
MODEL_TOKENIZER = "cahya/bert-base-indonesian-522M"
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
tokenizer = AutoTokenizer.from_pretrained(MODEL_TOKENIZER)

if not os.path.exists(MODEL_PATH):
    gdown.download(f"https://drive.google.com/uc?id={FILE_ID}", MODEL_PATH, quiet=False)

with open(MODEL_PATH, "rb") as f:
    model = pickle.load(f)

model.to(device)
model.eval()

# 🔍 Fungsi pendeteksi pola ulasan palsu
def is_emoji_only(text):
    emoji_pattern = re.compile(r"^[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F]+$")
    return bool(emoji_pattern.match(text))

def pf2_check(review):
    review = review.strip()
    if not review:
        return False
    
    sentences = re.split(r'[.!?]+', review)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) == 0:
        return False
    
    words_per_sentence = [len(s.split()) for s in sentences]
    avg_words_per_sentence = sum(words_per_sentence) / len(words_per_sentence)
    
    words = review.split()
    avg_word_length = sum(len(w) for w in words) / len(words)
    
    MIN_AVG_WORDS_PER_SENTENCE = 5    
    MIN_AVG_WORD_LENGTH = 4.0          
    
    return avg_words_per_sentence >= MIN_AVG_WORDS_PER_SENTENCE and avg_word_length >= MIN_AVG_WORD_LENGTH

def is_exactly_generic_phrase(text):
    generic_phrases = {
        "ok", "oke", "sip", "mantap", "nice", "good", "top", "not", "sesuai"
    }
    return text.strip().lower() in generic_phrases

def looks_natural(review):
    review = review.lower()
    word_count = len(review.split())

    natural_keywords = [
        "bagus", "keren","mantap", "kualitas oke", "pas di badan", "adem",
        "nyaman dipakai", "lembut", "halus", "enak dipakai", "bagus banget", "real pict",
        "gak nyesel beli", "recommended", "puas", "ukuran pas", "sesuai deskripsi",
        "sesuai gambar", "cutting rapi", "tipis tapi nyaman", "ringan di badan",
        "warna sesuai", "motifnya bagus", "jatuhnya bagus di badan",
        "cepat sampai", "pengiriman cepat", "dikirim hari itu juga", "packaging rapi",
        "packing aman", "barang sampai dengan selamat", "sesuai estimasi", "fast respon",
        "seller ramah", "penjual ramah", "respon cepat", "CS responsif", "penjualnya baik",
        "bahannya adem dan nyaman banget", "suka banget sama bajunya",
        "bakal order lagi deh", "baru nyoba dan langsung suka",
        "beli buat seragaman, cocok semua", "cocok buat dipakai harian",
        "pas di badan, nggak kegedean/kekecilan",
        "beli karena lihat review, ternyata beneran bagus",
        "next order lagi", "baru sampai langsung coba, puas banget"
    ]

    has_punctuation = any(p in review for p in [".", ",", "...", "!"])

    if word_count >= 5 and has_punctuation:
        if any(word in review for word in natural_keywords):
            return True
    return False

# 🔍 Fungsi utama klasifikasi ulasan + alasan
def predict_review_label(review, image_url=None):
    review = review.strip()

    if is_emoji_only(review):
        return "Fake", "Hanya mengandung emoji"

    if pf2_check(review):
        return "Real", "Kalimat dan kata cukup panjang serta informatif"

    if len(review.split()) > 10:
        return "Real", "Review cukup panjang (>10 kata)"

    if image_url:
        return "Real", "Mengandung foto sebagai bukti"

    if looks_natural(review):
        return "Real", "Mengandung frasa alami dan tanda baca yang sesuai"

    if is_exactly_generic_phrase(review):
        return "Fake", "Hanya mengandung frasa umum/generik"

    # Model digunakan jika tidak memenuhi heuristik
    inputs = tokenizer(review, return_tensors="pt", truncation=True, padding=True, max_length=512)
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    logits = outputs.logits
    prediction = torch.argmax(logits, dim=-1).item()

    return ("Fake", "Model prediksi: Fake") if prediction == 0 else ("Real", "Model prediksi: Real")

# 🔎 Scraping dan klasifikasi ulasan
def scrape_reviews(url):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    service = Service()
    driver = webdriver.Chrome(service=service, options=options)
    
    driver.get(url)
    time.sleep(3)
    
    data = []
    max_reviews = 300
    reviews_scraped = 0
    page_number = 1

    def scroll_down():
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

    while reviews_scraped < max_reviews:
        scroll_down()
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        containers = soup.find_all('div', class_='css-1k41fl7')
        
        if not containers:
            print(f"[INFO] Tidak ada container ditemukan di halaman {page_number}")
            break

        for container in containers:
            if reviews_scraped >= max_reviews:
                break
            try:
                user = container.find('span', class_='name')
                review = container.find('span', attrs={'data-testid': 'lblItemUlasan'})
                rating_stars = container.find_all('svg', attrs={'fill': 'var(--YN300, #FFD45F)'})
                image_tag = container.find('img', attrs={'data-testid': 'imgItemPhotoulasan'})

                if user and review:
                    username = user.text.strip()
                    review_text = review.text.strip()
                    rating = len(rating_stars)
                    image_url = image_tag['src'] if image_tag else None

                    label, reason = predict_review_label(review_text, image_url)
                    data.append({
                        "User": username,
                        "Review": review_text,
                        "Rating": rating,
                        "Category": label,
                        "Reason": reason,
                        "Image URL": image_url
                    })
                    reviews_scraped += 1
            except Exception as e:
                print(f"[WARNING] Gagal memproses 1 ulasan: {e}")
                continue

        try:
            next_button = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "button[aria-label^='Laman berikutnya']"))
            )
            if next_button.is_enabled():
                driver.execute_script("arguments[0].click();", next_button)
                time.sleep(3)
                page_number += 1
            else:
                break
        except Exception:
            break

    driver.quit()
    return data

# 🔗 API endpoint
@app.route('/scrape', methods=['POST'])
def scrape_and_detect():
    url = request.json.get('url')
    if not url:
        return jsonify({"error": "URL tidak diberikan"}), 400

    reviews = scrape_reviews(url)
    return jsonify(reviews)

# ▶️ Jalankan server Flask
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
