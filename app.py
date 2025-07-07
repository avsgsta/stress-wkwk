import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from urllib.parse import urlparse, urlunparse

# ===============================
# 🔧 Fungsi Format URL
# ===============================
def clean_url(url):
    parsed_url = urlparse(url)
    return urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, "", "", ""))

def format_review_url(url):
    url = clean_url(url)
    return url.rstrip("/") + "/review" if "/review" not in url else url

# ===============================
# 🎨 Konfigurasi Streamlit
# ===============================
st.set_page_config(page_title="Deteksi Review Palsu Tokopedia", page_icon="🛒", layout="wide")

# ===============================
# 🧭 Sidebar Navigasi
# ===============================
menu = st.sidebar.selectbox("📌 Navigasi", ["🔍 Deteksi Review", "📖 Panduan Pengguna"])

# ===============================
# 📖 Panduan Pengguna
# ===============================
if menu == "📖 Panduan Pengguna":
    st.title("📖 Panduan Pengguna")
    st.markdown("""
    Selamat datang di aplikasi **Deteksi Review Palsu Tokopedia**!  
    Berikut adalah langkah-langkah untuk menggunakan aplikasi ini:

    1. **Salin URL** produk dari situs Tokopedia.
    2. Tempelkan ke dalam kolom input di menu **Deteksi Review**.
    3. Klik tombol **"Mulai Deteksi"**.
    4. Tunggu beberapa saat hingga hasil scraping dan prediksi selesai.
    5. Lihat ringkasan visual dan detail ulasan yang terdeteksi.
    6. Kamu bisa mengunduh data hasil deteksi dalam format CSV.

    """)
    st.info("Hubungi Pihak Website jika mengalami kendala.")

# ===============================
# 🔍 Menu Deteksi Review
# ===============================
elif menu == "🔍 Deteksi Review":
    st.title("🛍️ Deteksi Review Palsu Tokopedia 🤖")

    url_input = st.text_input("🔗 Masukkan URL produk Tokopedia:")
    start_button = st.button("🚀 Mulai Deteksi")

    if start_button and url_input:
        formatted_url = format_review_url(url_input)
        st.write(f"🔗 **URL yang diformat:** [{formatted_url}]({formatted_url})")
        st.write("⏳ Mencari Data dan Memprediksi")

        try:
            response = requests.post("https://af52-180-249-153-10.ngrok-free.app/scrape", json={"url": formatted_url})
            if response.status_code != 200:
                st.error(f"❌ Gagal mengambil data. Kode: {response.status_code}")
            else:
                results = response.json()

                if not results:
                    st.warning("⚠️ Tidak ada ulasan ditemukan.")
                else:
                    df = pd.DataFrame(results)
                    st.session_state["scraped_data"] = df
                    st.session_state["scraping_done"] = True

        except requests.exceptions.RequestException as e:
            st.error(f"⚠️ Gagal terhubung ke server lokal: {e}")

    # ===============================
    # 📊 Tampilkan Hasil Jika Ada
    # ===============================
    if st.session_state.get("scraping_done"):
        df = st.session_state["scraped_data"]
        real_count = df[df["Category"] == "Real"].shape[0]
        fake_count = df[df["Category"] == "Fake"].shape[0]
        total_reviews = real_count + fake_count
        real_percentage = (real_count / total_reviews) * 100 if total_reviews > 0 else 0

        fig = px.pie(
            names=["Real", "Fake"],
            values=[real_count, fake_count],
            title="Distribusi Ulasan Real vs Fake",
            color_discrete_sequence=["blue", "red"]
        )

        st.subheader("📊 Ringkasan Analisis")
        st.plotly_chart(fig)
        st.dataframe(df)

        # if real_percentage >= 70:
        #     st.success(f"✅ Produk ini **layak dibeli** (Real Reviews: {real_percentage:.2f}%)")
        # elif 50 <= real_percentage < 70:
        #     st.warning(f"⚠️ Produk ini **perlu dipertimbangkan** (Real Reviews: {real_percentage:.2f}%)")
        # else:
        #     st.error(f"❌ Produk ini **tidak layak dibeli** (Real Reviews: {real_percentage:.2f}%)")

        csv_file = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Unduh CSV", data=csv_file, file_name="tokopedia_reviews.csv", mime="text/csv")
