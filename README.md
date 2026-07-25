# 🎧 Spoty

Kişisel kullanım için basit, Spotify benzeri bir masaüstü müzik uygulaması.
İnternetten şarkı **arayıp indirir** ve indirdiklerini **çalar**. İndirilen mp3'lere
albüm kapağı ve şarkı/sanatçı bilgisi gömülür.

> Yalnızca kişisel/yerel kullanım içindir.

## Özellikler

- 🔎 Uygulama içinden şarkı arama ve indirme (mp3)
- 🔗 Link yapıştırarak indirme (TikTok, YouTube ve yt-dlp'nin desteklediği siteler)
- 🎵 Çalma: oynat/duraklat, ileri-geri sar, ses, sıradaki/önceki
- 🖼️ Albüm kapağı + etiketler mp3'e gömülü ve arayüzde görünür
- 📂 Çalma listeleri: oluştur, şarkı ekle/çıkar, listeden çal
- 🗑️ Şarkı silme; ses seviyesi ve son çalınan şarkıyı hatırlama

## Gereksinimler

- **Python 3.11+** (geliştirildiği sürüm: 3.13)
- **ffmpeg** (sistemde kurulu ve PATH'te). Windows'ta winget ile:
  ```powershell
  winget install --exact --id Gyan.FFmpeg
  ```
  (Kurulumdan sonra terminali yeniden aç.)
- **WebView2 Runtime** (webview arayüzü için; Windows 11'de genelde hazır gelir). Yoksa
  Microsoft'tan "Evergreen WebView2 Runtime" kurulabilir. (Yalnızca `spoty.webmain` için gerekir.)

## Kurulum

```powershell
# Proje klasöründe sanal ortam oluştur
python -m venv .venv

# Bağımlılıkları kur
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Çalıştırma

```powershell
.\.venv\Scripts\python.exe -m spoty.webmain
```

## Kullanım

1. **Ara / İndir** — üstteki kutuya bir şarkı adı yaz ve **Ara / İndir**'e bas;
   sonuçlardan **⬇** ile indir. Şarkı otomatik olarak kütüphaneye eklenir.
2. **Link ile indir** — aynı kutuya bir TikTok/YouTube linki yapıştırıp bas.
3. **Çal** — Kütüphane veya bir çalma listesinde şarkının yanındaki **▶** ile çal.
   Alt bardan oynat/duraklat, ilerleme çubuğu (sürükle = sar) ve ses kontrolü.
4. **Çalma listeleri** — sol panelden **+ Yeni liste**; bir şarkıdaki **+** ile listeye
   ekle. Liste içinde **✕** çıkarır, başlıktaki **🗑** listeyi siler.

## Klasör yapısı

```
Spoty/
├─ music/            # indirilen mp3'ler (otomatik oluşur)
├─ data/spoty.db     # kütüphane + çalma listeleri (otomatik oluşur)
├─ requirements.txt
└─ spoty/
   ├─ webmain.py     # giriş noktası (webview)
   ├─ web_app.py     # Python<->JS köprüsü (Api)
   ├─ web/           # HTML/CSS/JS arayüz (index.html, style.css, app.js, icons.js)
   ├─ config.py
   └─ core/          # downloader, player, library, metadata, settings
```

Geliştirme ve mimari ayrıntıları için `CLAUDE.md` dosyasına bakın.
